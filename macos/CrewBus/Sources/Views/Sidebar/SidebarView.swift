import SwiftUI
import CrewBusKit

struct SidebarView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        List(selection: $state.selectedAgent) {
            Section("Home") {
                Label("Dashboard", systemImage: "square.grid.2x2")
                    .tag(nil as Agent?)
                    .onTapGesture {
                        appState.selectedAgent = nil
                    }
            }

            Section("Your Crew") {
                ForEach(appState.crewAgents) { agent in
                    AgentRow(agent: agent)
                        .tag(agent as Agent?)
                }
            }

            if !appState.teamAgents.isEmpty {
                Section("Teams") {
                    ForEach(appState.teamAgents) { agent in
                        AgentRow(agent: agent)
                            .tag(agent as Agent?)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Crew Bus")
    }
}
