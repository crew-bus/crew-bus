import Foundation

@Observable
public final class ChatService {
    public var messages: [ChatMessage] = []
    public var isLoading = false

    private let client: APIClient
    private var pollingTask: Task<Void, Never>?
    private var currentAgentId: Int?

    public init(client: APIClient) {
        self.client = client
    }

    public func startPolling(agentId: Int) {
        stopPolling()
        currentAgentId = agentId
        isLoading = true

        pollingTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.fetchMessages(agentId: agentId)
                try? await Task.sleep(for: .milliseconds(1500))
            }
        }
    }

    public func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
        currentAgentId = nil
    }

    public func sendMessage(agentId: Int, text: String) async {
        do {
            try await client.post(
                APIEndpoints.agentChat(agentId),
                body: ["text": text]
            )
            await fetchMessages(agentId: agentId)
        } catch {
            print("Send failed: \(error)")
        }
    }

    public func forceRefresh(agentId: Int) async {
        // Clear chat history on the server
        await clearChat(agentId: agentId)
        // Restart polling for fresh state
        startPolling(agentId: agentId)
    }

    public func clearChat(agentId: Int) async {
        do {
            try await client.post(
                APIEndpoints.agentChatClear(agentId),
                body: [:]
            )
            messages = []
        } catch {
            print("Clear failed: \(error)")
        }
    }

    private func fetchMessages(agentId: Int) async {
        do {
            let fetched: [ChatMessage] = try await client.get(APIEndpoints.agentChat(agentId))
            if !Task.isCancelled {
                await MainActor.run {
                    self.messages = fetched
                    self.isLoading = false
                }
            }
        } catch {
            if !Task.isCancelled {
                await MainActor.run {
                    self.isLoading = false
                }
            }
        }
    }
}
