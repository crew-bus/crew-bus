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
                ZStack(alignment: .topTrailing) {
                    // Outer glow ring (breathing)
                    Circle()
                        .stroke(glowColor.opacity(breathe ? 0.6 : 0.25), lineWidth: 2.5)
                        .frame(width: size + 16, height: size + 16)
                        .shadow(color: glowColor.opacity(breathe ? 0.5 : 0.2), radius: breathe ? 16 : 8)

                    // Main circle
                    Circle()
                        .fill(CrewTheme.surface)
                        .frame(width: size, height: size)
                        .overlay(
                            Circle().stroke(glowColor.opacity(0.6), lineWidth: 2)
                        )
                        .overlay(
                            Image(systemName: typeInfo.symbolName)
                                .font(.system(size: size * 0.32))
                                .foregroundStyle(glowColor)
                        )

                    // Green status dot
                    Circle()
                        .fill(agent.status == "active" ? CrewTheme.green : CrewTheme.muted)
                        .frame(width: 12, height: 12)
                        .overlay(Circle().stroke(CrewTheme.bg, lineWidth: 2))
                        .offset(x: 2, y: -2)
                }
                .frame(width: size + 16, height: size + 16)

                // Name
                Text(agent.resolvedDisplayName)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)

                // Optional timestamp
                if let ts = agent.lastMessageTime, !ts.isEmpty {
                    Text(ts)
                        .font(.system(size: 10))
                        .foregroundStyle(CrewTheme.muted)
                        .lineLimit(1)
                }
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
