import SwiftUI
import CrewBusKit

struct MessageFeedView: View {
    @Environment(AppState.self) private var appState
    @State private var messages: [FeedMessage] = []
    @State private var isLoading = true

    struct FeedMessage: Decodable, Identifiable {
        let id: Int
        let sender: String
        let content: String
        let timestamp: String
        let agentType: String?
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 12) {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .dashboard
                    }
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                        .frame(width: 34, height: 34)
                        .background(CrewTheme.surface)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(CrewTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)

                Image(systemName: "bubble.left.and.bubble.right")
                    .foregroundStyle(CrewTheme.accent)
                Text("Crew Message Trail")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            // Content
            if isLoading {
                Spacer()
                ProgressView()
                Spacer()
            } else if messages.isEmpty {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 40))
                        .foregroundStyle(CrewTheme.muted)
                    Text("No messages yet")
                        .font(.system(size: 15))
                        .foregroundStyle(CrewTheme.muted)
                    Text("Your crew's conversations will appear here.")
                        .font(.system(size: 13))
                        .foregroundStyle(CrewTheme.muted.opacity(0.7))
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(messages) { msg in
                            HStack(alignment: .top, spacing: 12) {
                                let typeInfo = AgentTypeInfo.info(for: msg.agentType ?? "")
                                Image(systemName: typeInfo.symbolName)
                                    .font(.system(size: 14))
                                    .foregroundStyle(typeInfo.color)
                                    .frame(width: 32, height: 32)
                                    .background(CrewTheme.bg)
                                    .clipShape(Circle())

                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(msg.sender)
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundStyle(CrewTheme.text)
                                        Text(msg.timestamp)
                                            .font(.system(size: 11))
                                            .foregroundStyle(CrewTheme.muted)
                                    }
                                    Text(msg.content)
                                        .font(.system(size: 13))
                                        .foregroundStyle(CrewTheme.text.opacity(0.9))
                                        .lineLimit(4)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 20)
                            .padding(.vertical, 12)
                            .background(CrewTheme.surface)
                        }
                    }
                    .padding(.top, 8)
                }
            }
        }
        .background(CrewTheme.bg)
        .task { await loadMessages() }
    }

    private func loadMessages() async {
        do {
            let fetched: [FeedMessage] = try await appState.client.get(APIEndpoints.messageFeed)
            await MainActor.run {
                messages = fetched
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
