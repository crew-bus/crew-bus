import Foundation
import CrewBusKit

// MARK: - Navigation

enum NavDestination: Equatable {
    case dashboard
    case agentChat(Agent)
    case teamDetail(Team)
    case messageFeed
    case auditLog
    case socialDrafts
    case observability
    case channelList
    case channelDetail(CrewChannel)
    case deviceManagement

    var transitionId: String {
        switch self {
        case .dashboard:           return "dashboard"
        case .agentChat(let a):    return "chat-\(a.id)"
        case .teamDetail(let t):   return "team-\(t.id)"
        case .messageFeed:         return "message-feed"
        case .auditLog:            return "audit-log"
        case .socialDrafts:        return "social-drafts"
        case .observability:       return "observability"
        case .channelList:         return "channel-list"
        case .channelDetail(let c): return "channel-\(c.id)"
        case .deviceManagement:    return "device-mgmt"
        }
    }
}

enum ColorSchemePreference {
    case light, dark
}

// MARK: - App State

@Observable
final class AppState {
    var agents: [Agent] = []
    var stats: CrewStats?
    var teams: [Team] = []
    var navDestination: NavDestination = .dashboard
    var colorScheme: ColorSchemePreference = .dark
    var isServerReady = false
    var isLoading = false
    var serverError: String?
    var needsSetup = false
    var isDashboardLocked = false
    var requiresPinAuth = false

    let client: APIClient
    let chatService: ChatService

    /// Agents that are part of the core crew (not human, not manager/worker)
    var crewAgents: [Agent] {
        agents.filter { agent in
            !agent.isHuman && !["manager", "worker"].contains(agent.agentType)
        }
    }

    /// Team agents (managers and workers)
    var teamAgents: [Agent] {
        agents.filter { ["manager", "worker"].contains($0.agentType) }
    }

    private let serverManager: ServerManager

    init(serverManager: ServerManager) {
        self.serverManager = serverManager
        self.client = APIClient()
        self.chatService = ChatService(client: client)
    }

    func startMonitoring() {
        Task {
            while !serverManager.isReady && serverManager.error == nil {
                try? await Task.sleep(for: .milliseconds(200))
            }

            await MainActor.run {
                if let error = serverManager.error {
                    self.serverError = error
                } else {
                    self.isServerReady = true
                }
            }

            if serverManager.isReady {
                await restoreAuthToken()
                await checkAuthMode()
                await checkSetupStatus()
                await loadInitialData()
                startPeriodicRefresh()
            }
        }
    }

    func loadInitialData() async {
        await MainActor.run { isLoading = true }
        do {
            let fetchedStats: CrewStats = try await client.get(APIEndpoints.stats)
            let fetchedAgents: [Agent] = try await client.get(APIEndpoints.agents)
            let fetchedTeams: [Team] = try await client.get(APIEndpoints.teams)
            await MainActor.run {
                self.stats = fetchedStats
                self.agents = fetchedAgents
                self.teams = fetchedTeams
                self.isLoading = false
            }
        } catch {
            print("Failed to load data: \(error)")
            await MainActor.run { self.isLoading = false }
        }
    }

    func updateTrustScore(_ score: Int) async {
        do {
            try await client.post(APIEndpoints.trust, body: ["score": score])
            await loadInitialData()
        } catch {
            print("Failed to update trust score: \(error)")
        }
    }

    func updateBurnoutScore(_ score: Int) async {
        do {
            try await client.post(APIEndpoints.burnout, body: ["score": score])
            await loadInitialData()
        } catch {
            print("Failed to update burnout score: \(error)")
        }
    }

    func checkSetupStatus() async {
        struct SetupStatus: Decodable {
            let needsSetup: Bool
        }
        do {
            let status: SetupStatus = try await client.get(APIEndpoints.setupStatus)
            await MainActor.run { self.needsSetup = status.needsSetup }
        } catch {
            // If setup endpoint fails, assume setup not needed
            await MainActor.run { self.needsSetup = false }
        }
    }

    func completeSetup(model: String, apiKey: String, pin: String) async throws {
        var body: [String: Any] = ["model": model]
        if !apiKey.isEmpty { body["api_key"] = apiKey }
        if !pin.isEmpty { body["dashboard_pin"] = pin }
        try await client.post(APIEndpoints.setupComplete, body: body)
        await MainActor.run { self.needsSetup = false }
    }

    func lockDashboard() async {
        do {
            try await client.post(APIEndpoints.configSet, body: ["key": "dashboard_locked", "value": "true"])
            await MainActor.run { self.isDashboardLocked = true }
        } catch {
            print("Failed to lock dashboard: \(error)")
        }
    }

    func retryConnection() {
        serverError = nil
        isServerReady = false
        serverManager.stop()
        serverManager.start()
        startMonitoring()
    }

    // MARK: - Auth

    private func restoreAuthToken() async {
        if let token = UserDefaults.standard.string(forKey: "crew_bus_device_token") {
            await client.setAuthToken(token)
        }
    }

    private func checkAuthMode() async {
        struct AuthModeResponse: Decodable { let mode: String }
        do {
            let response: AuthModeResponse = try await client.get(APIEndpoints.authMode)
            let hasToken = UserDefaults.standard.string(forKey: "crew_bus_device_token") != nil
            if response.mode != "none" && !hasToken {
                await MainActor.run { self.requiresPinAuth = true }
            }
        } catch {
            // Auth endpoint may not exist, skip
        }
    }

    private func startPeriodicRefresh() {
        Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(10))
                await refreshData()
            }
        }
    }

    private func refreshData() async {
        do {
            let fetchedStats: CrewStats = try await client.get(APIEndpoints.stats)
            let fetchedAgents: [Agent] = try await client.get(APIEndpoints.agents)
            let fetchedTeams: [Team] = try await client.get(APIEndpoints.teams)
            await MainActor.run {
                self.stats = fetchedStats
                self.agents = fetchedAgents
                self.teams = fetchedTeams
            }
        } catch {
            // Silent refresh failure
        }
    }
}
