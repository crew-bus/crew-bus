import SwiftUI
import CrewBusKit

struct DashboardView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let stats = appState.stats {
                    Text(stats.crewName)
                        .font(.largeTitle)
                        .fontWeight(.bold)
                        .padding(.top)

                    HStack(spacing: 16) {
                        StatsCardView(
                            title: "Trust Score",
                            value: "\(stats.trustScore)",
                            icon: "checkmark.shield.fill",
                            color: .green
                        )
                        StatsCardView(
                            title: "Agents",
                            value: "\(stats.agentCount)",
                            icon: "person.3.fill",
                            color: .blue
                        )
                        StatsCardView(
                            title: "Messages",
                            value: "\(stats.messageCount)",
                            icon: "message.fill",
                            color: .purple
                        )
                        StatsCardView(
                            title: "Decisions",
                            value: "\(stats.decisionCount)",
                            icon: "list.clipboard.fill",
                            color: .orange
                        )
                    }
                }

                Text("Your Crew")
                    .font(.title2)
                    .fontWeight(.semibold)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 16)], spacing: 16) {
                    ForEach(appState.crewAgents) { agent in
                        AgentCardView(agent: agent)
                            .onTapGesture {
                                appState.selectedAgent = agent
                            }
                    }
                }
            }
            .padding()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct AgentCardView: View {
    let agent: Agent

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: typeInfo.symbolName)
                .font(.system(size: 32))
                .foregroundStyle(typeInfo.color)

            Text(agent.resolvedDisplayName)
                .font(.headline)

            HStack(spacing: 4) {
                Circle()
                    .fill(agent.status == "active" ? .green : .gray)
                    .frame(width: 8, height: 8)
                Text(agent.status.capitalized)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let unread = agent.unreadCount, unread > 0 {
                Text("\(unread) unread")
                    .font(.caption2)
                    .foregroundStyle(.blue)
            }
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(.quaternary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
