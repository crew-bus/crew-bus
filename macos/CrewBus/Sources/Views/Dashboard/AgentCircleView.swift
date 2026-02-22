import SwiftUI
import CrewBusKit

struct AgentCircleView: View {
    let agent: Agent
    let size: CGFloat
    let glowColor: Color
    var onTap: (() -> Void)? = nil

    @State private var breathe = false

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(spacing: 8) {
                ZStack {
                    // Main circle with breathing glow
                    Circle()
                        .fill(CrewTheme.surface)
                        .frame(width: size, height: size)
                        .overlay(
                            Circle().stroke(glowColor.opacity(0.6), lineWidth: 2)
                        )
                        .overlay(
                            Group {
                                if let avatar = agent.avatar, !avatar.isEmpty {
                                    Text(avatar)
                                        .font(.system(size: size * 0.38))
                                } else {
                                    Image(systemName: typeInfo.symbolName)
                                        .font(.system(size: size * 0.32))
                                        .foregroundStyle(glowColor)
                                }
                            }
                        )
                        .shadow(color: glowColor.opacity(breathe ? 0.6 : 0.15), radius: breathe ? 20 : 8)

                    // Green status dot — top trailing
                    Circle()
                        .fill(agent.status == "active" ? CrewTheme.green : CrewTheme.muted)
                        .frame(width: 12, height: 12)
                        .overlay(Circle().stroke(CrewTheme.bg, lineWidth: 2))
                        .offset(x: (size + 16) / 2 - 6, y: -(size + 16) / 2 + 6)
                }
                .frame(width: size + 16, height: size + 16)

                // Name
                Text(agent.resolvedDisplayName)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)

            }
        }
        .buttonStyle(.plain)
        .onAppear { breathe = true }
        .animation(
            .easeInOut(duration: 2.0).repeatForever(autoreverses: true),
            value: breathe
        )
    }
}
