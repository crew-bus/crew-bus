import Foundation
import CrewBusKit

@Observable
final class AppState {
    var agents: [Agent] = []
    var stats: CrewStats?
    var selectedAgent: Agent?
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
            // Wait for server to become ready
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
            await MainActor.run {
                self.stats = fetchedStats
                self.agents = fetchedAgents
                self.isLoading = false
            }
        } catch {
            print("Failed to load data: \(error)")
            await MainActor.run { self.isLoading = false }
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
            await MainActor.run {
                self.stats = fetchedStats
                self.agents = fetchedAgents
            }
        } catch {
            // Silent refresh failure — don't disrupt the UI
        }
    }
}
