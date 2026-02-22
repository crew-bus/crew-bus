import SwiftUI
import CrewBusKit

struct ChatView: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var scrollProxy: ScrollViewProxy?

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 12) {
                Image(systemName: typeInfo.symbolName)
                    .font(.title2)
                    .foregroundStyle(typeInfo.color)
                VStack(alignment: .leading) {
                    Text(agent.resolvedDisplayName)
                        .font(.headline)
                    Text(typeInfo.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding()
            .background(.bar)

            Divider()

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(appState.chatService.messages) { message in
                            ChatBubbleView(message: message, agentName: agent.resolvedDisplayName)
                                .id(message.id)
                        }
                    }
                    .padding()
                }
                .onAppear { scrollProxy = proxy }
                .onChange(of: appState.chatService.messages.count) {
                    if let last = appState.chatService.messages.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            ChatInputView(agentId: agent.id)
        }
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
}
