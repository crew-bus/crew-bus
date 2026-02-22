import Foundation
import CrewBusKit

// MARK: - Navigation

enum NavDestination: Equatable {
    case dashboard
    case agentChat(Agent)
    case teamDetail(Team)

    var transitionId: String {
        switch self {
        case .dashboard:        return "dashboard"
        case .agentChat(let a): return "chat-\(a.id)"
        case .teamDetail(let t): return "team-\(t.id)"
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

    func retryConnection() {
        serverError = nil
        isServerReady = false
        serverManager.stop()
        serverManager.start()
        startMonitoring()
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
