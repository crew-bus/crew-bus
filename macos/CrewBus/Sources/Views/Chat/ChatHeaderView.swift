import SwiftUI
import CrewBusKit

struct ChatHeaderView: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var statusPulse = false

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        HStack(spacing: 12) {
            // Back button
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

            // Avatar circle (42px)
            ZStack {
                Circle()
                    .fill(CrewTheme.surface)
                    .frame(width: 42, height: 42)
                    .overlay(
                        Circle().stroke(typeInfo.color.opacity(0.7), lineWidth: 2)
                    )
                    .shadow(color: typeInfo.color.opacity(0.4), radius: 6)

                Image(systemName: typeInfo.symbolName)
                    .font(.system(size: 16))
                    .foregroundStyle(typeInfo.color)
            }

            // Name + Online
            VStack(alignment: .leading, spacing: 2) {
                Text(agent.resolvedDisplayName)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                HStack(spacing: 4) {
                    Circle()
                        .fill(CrewTheme.green)
                        .frame(width: 7, height: 7)
                        .scaleEffect(statusPulse ? 1.3 : 1.0)
                    Text("Online")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.green)
                }
            }
            .onAppear { statusPulse = true }
            .animation(
                .easeInOut(duration: 0.8).repeatForever(autoreverses: true),
                value: statusPulse
            )

            Spacer()

            // Action icons
            HStack(spacing: 16) {
                headerIcon("sparkles")
                headerIcon("bell")
                headerIcon("gearshape")
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 60)
        .background(CrewTheme.surface)
        .overlay(alignment: .bottom) {
            Rectangle().fill(CrewTheme.border).frame(height: 1)
        }
    }

    @ViewBuilder
    private func headerIcon(_ name: String) -> some View {
        Button {} label: {
            Image(systemName: name)
                .font(.system(size: 15))
                .foregroundStyle(CrewTheme.muted)
        }
        .buttonStyle(.plain)
    }
}
