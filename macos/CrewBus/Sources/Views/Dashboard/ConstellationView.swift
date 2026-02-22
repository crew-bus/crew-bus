import SwiftUI
import CrewBusKit

struct ConstellationView: View {
    @Environment(AppState.self) private var appState
    let agents: [Agent]
    let stats: CrewStats
    @Binding var showSettings: Bool

    // Resolve core agents by type
    private var boss: Agent? { agents.first { $0.agentType == "right_hand" } }
    private var guardian: Agent? { agents.first { $0.agentType == "guardian" } }
    private var vault: Agent? {
        agents.first { $0.agentType == "vault" }
        ?? agents.first { $0.agentType == "manager" && $0.name.lowercased().contains("vault") }
    }

    // Remaining agents not in the main triangle
    private var otherAgents: [Agent] {
        let mainIds = Set([boss?.id, guardian?.id, vault?.id].compactMap { $0 })
        return agents.filter { !mainIds.contains($0.id) }
    }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height

            // Triangle positions
            let topCenter   = CGPoint(x: w * 0.42, y: h * 0.22)
            let bottomLeft  = CGPoint(x: w * 0.22, y: h * 0.65)
            let bottomRight = CGPoint(x: w * 0.62, y: h * 0.65)

            ZStack {
                // Dashed connection lines
                ConnectionLinesView(points: [topCenter, bottomLeft, bottomRight])

                // Boss — top center, largest
                if let boss = boss {
                    AgentCircleView(agent: boss, size: 130, glowColor: .white) {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            appState.navDestination = .agentChat(boss)
                        }
                    }
                    .position(topCenter)
                }

                // Guardian — bottom left
                if let guardian = guardian {
                    AgentCircleView(agent: guardian, size: 90, glowColor: CrewTheme.orange) {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            appState.navDestination = .agentChat(guardian)
                        }
                    }
                    .position(bottomLeft)
                }

                // Vault — bottom right
                if let vault = vault {
                    AgentCircleView(agent: vault, size: 90, glowColor: CrewTheme.purple) {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            appState.navDestination = .agentChat(vault)
                        }
                    }
                    .position(bottomRight)
                }

                // Sun/Moon toggle — top left
                SunMoonToggleView()
                    .position(x: 60, y: 24)

                // Trust + Energy pills — bottom
                TrustEnergyPillsView(stats: stats, showSettings: $showSettings)
                    .position(x: w * 0.42, y: h - 30)
            }
        }
    }
}
