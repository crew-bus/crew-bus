import SwiftUI
import CrewBusKit

struct DashboardView: View {
    @Environment(AppState.self) private var appState
    @State private var showSettings = false
    @State private var showEnergy = false

    var body: some View {
        Group {
            if let stats = appState.stats {
                HStack(spacing: 0) {
                    // LEFT — Constellation (~55%)
                    ConstellationView(
                        agents: appState.crewAgents,
                        stats: stats,
                        showSettings: $showSettings,
                        showEnergy: $showEnergy
                    )
                    .frame(maxWidth: .infinity)

                    // Vertical divider
                    Rectangle()
                        .fill(CrewTheme.border)
                        .frame(width: 1)

                    // RIGHT — Teams Panel (~45%)
                    TeamsPanelView(teams: appState.teams)
                        .frame(maxWidth: .infinity)
                }
                .sheet(isPresented: $showSettings) {
                    if let stats = appState.stats {
                        AdjustSettingsSheet(
                            trustScore: stats.trustScore
                        )
                    }
                }
                .sheet(isPresented: $showEnergy) {
                    if let stats = appState.stats {
                        EnergyScoreSheet(
                            energyScore: stats.energyScore ?? 5
                        )
                    }
                }
            } else {
                VStack {
                    ProgressView()
                    Text("Loading crew...")
                        .font(.caption)
                        .foregroundStyle(CrewTheme.muted)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color.clear)
    }
}
