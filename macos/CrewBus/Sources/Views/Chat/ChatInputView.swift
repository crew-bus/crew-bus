import SwiftUI
import CrewBusKit

struct ChatInputView: View {
    let agentId: Int
    let agentName: String
    @Environment(AppState.self) private var appState
    @State private var text = ""
    @State private var isSending = false
    @State private var glowing = false

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespaces).isEmpty && !isSending
    }

    var body: some View {
        HStack(spacing: 10) {
            // Capsule text field
            TextField("Talk to \(agentName)...", text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.text)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(CrewTheme.surface)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(CrewTheme.border, lineWidth: 1))
                .onSubmit { send() }

            // Pink send button with breathing glow
            Button(action: send) {
                Image(systemName: "play.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(canSend ? CrewTheme.highlight : CrewTheme.muted.opacity(0.5))
                    .clipShape(Circle())
                    .shadow(
                        color: CrewTheme.highlight.opacity(glowing && canSend ? 0.6 : 0.15),
                        radius: glowing && canSend ? 10 : 4
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(CrewTheme.bg)
        .overlay(alignment: .top) {
            Rectangle().fill(CrewTheme.border).frame(height: 1)
        }
        .onAppear { glowing = true }
        .animation(
            .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
            value: glowing
        )
    }

    private func send() {
        let msg = text.trimmingCharacters(in: .whitespaces)
        guard !msg.isEmpty, !isSending else { return }
        text = ""
        isSending = true
        Task {
            await appState.chatService.sendMessage(agentId: agentId, text: msg)
            isSending = false
        }
    }
}
