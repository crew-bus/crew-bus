import SwiftUI
import CrewBusKit

struct ChatView: View {
    let agent: Agent
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 0) {
            // Header with back button + agent info
            ChatHeaderView(agent: agent)

            // Messages area
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        if appState.chatService.messages.isEmpty && !appState.chatService.isLoading {
                            emptyChatState
                        } else {
                            ForEach(appState.chatService.messages) { msg in
                                ChatBubbleView(message: msg, agentName: agent.resolvedDisplayName)
                                    .id(msg.id)
                            }

                            if appState.chatService.isLoading && appState.chatService.messages.isEmpty {
                                HStack {
                                    TypingIndicatorView()
                                        .padding(.leading, 16)
                                    Spacer()
                                }
                            }
                        }
                    }
                    .padding(.vertical, 16)
                }
                .background(CrewTheme.bg)
                .onChange(of: appState.chatService.messages.count) {
                    if let last = appState.chatService.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            // Input
            ChatInputView(agentId: agent.id, agentName: agent.resolvedDisplayName)
        }
        .background(CrewTheme.bg)
        .onAppear {
            appState.chatService.startPolling(agentId: agent.id)
        }
        .onDisappear {
            appState.chatService.stopPolling()
        }
        .onChange(of: agent.id) { _, newId in
            appState.chatService.startPolling(agentId: newId)
        }
    }

    private var emptyChatState: some View {
        VStack(spacing: 12) {
            Spacer().frame(height: 80)
            Text("Say hi to \(agent.resolvedDisplayName)!")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(CrewTheme.text)
            Text("Just type a message below.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)
        }
        .frame(maxWidth: .infinity)
        .padding(40)
    }
}
