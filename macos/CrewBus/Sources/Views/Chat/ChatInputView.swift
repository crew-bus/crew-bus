import SwiftUI
import CrewBusKit

struct ChatInputView: View {
    let agentId: Int
    @Environment(AppState.self) private var appState
    @State private var text = ""
    @State private var isSending = false

    var body: some View {
        HStack(spacing: 12) {
            TextField("Type a message...", text: $text)
                .textFieldStyle(.plain)
                .onSubmit { send() }

            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundStyle(text.trimmingCharacters(in: .whitespaces).isEmpty ? .gray : .blue)
            }
            .buttonStyle(.plain)
            .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty || isSending)
        }
        .padding()
    }

    private func send() {
        let message = text.trimmingCharacters(in: .whitespaces)
        guard !message.isEmpty, !isSending else { return }
        text = ""
        isSending = true
        Task {
            await appState.chatService.sendMessage(agentId: agentId, text: message)
            isSending = false
        }
    }
}
