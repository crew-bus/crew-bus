import SwiftUI
import CrewBusKit

struct ChatBubbleView: View {
    let message: ChatMessage
    let agentName: String

    var body: some View {
        HStack {
            if message.isFromHuman { Spacer(minLength: 60) }

            VStack(alignment: message.isFromHuman ? .trailing : .leading, spacing: 4) {
                Text(message.isFromHuman ? "You" : agentName)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Text(message.text)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(message.isFromHuman ? Color.blue : Color(.controlBackgroundColor))
                    .foregroundStyle(message.isFromHuman ? .white : .primary)
                    .clipShape(RoundedRectangle(cornerRadius: 16))

                if message.isPrivate {
                    Label("Private", systemImage: "lock.fill")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if !message.isFromHuman { Spacer(minLength: 60) }
        }
    }
}
