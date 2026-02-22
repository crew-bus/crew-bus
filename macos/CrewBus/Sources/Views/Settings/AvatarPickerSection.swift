import SwiftUI
import CrewBusKit

struct AvatarPickerSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var isExpanded = false
    @State private var currentAvatar: String = ""
    @State private var saved = false

    private static let avatarEmojis = [
        "🤖", "🧠", "🦊", "🐺", "🦁", "🐯", "🐻", "🐼",
        "🦄", "🐲", "🦅", "🦉", "🐬", "🦈", "🐙", "🦋",
        "🌟", "⚡", "🔥", "💎", "🎯", "🚀", "🛡️", "⚔️",
        "🎨", "🎵", "📚", "🔬", "💡", "🌈", "🌙", "☀️",
        "🏆", "👑", "💫", "🍀", "🌺", "🌻", "🎪", "🎭",
        "🧩", "🎲", "🔮", "💰", "📡", "🛸", "🏔️", "🌊",
        "🍕", "☕", "🧁", "🎂"
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    Label("Avatar", systemImage: "face.smiling")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)

                    Spacer()

                    if !currentAvatar.isEmpty {
                        Text(currentAvatar)
                            .font(.system(size: 20))
                    }

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 8), spacing: 4) {
                    ForEach(Self.avatarEmojis, id: \.self) { emoji in
                        Button {
                            selectAvatar(emoji)
                        } label: {
                            Text(emoji)
                                .font(.system(size: 22))
                                .frame(width: 44, height: 44)
                                .background(currentAvatar == emoji ? CrewTheme.accent.opacity(0.2) : CrewTheme.bg)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 6)
                                        .stroke(currentAvatar == emoji ? CrewTheme.accent : Color.clear, lineWidth: 2)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 4)

                if saved {
                    Text("Saved!")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(CrewTheme.green)
                        .transition(.opacity)
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .onAppear {
            currentAvatar = agent.avatar ?? ""
        }
    }

    private func selectAvatar(_ emoji: String) {
        currentAvatar = emoji
        Task {
            try? await appState.client.post(
                APIEndpoints.agentAvatar(agent.id),
                body: ["avatar": emoji]
            )
            await appState.loadInitialData()
            await MainActor.run {
                saved = true
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded = false
                }
            }
            try? await Task.sleep(for: .seconds(2))
            await MainActor.run { saved = false }
        }
    }
}
