import SwiftUI
import CrewBusKit

struct TeamsPanelView: View {
    @Environment(AppState.self) private var appState
    let teams: [Team]
    @State private var showAddTeam = false
    @State private var selectedTeamId: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Teams")
                    .font(.title3)
                    .fontWeight(.bold)
                    .foregroundStyle(CrewTheme.text)
                Spacer()
                Button { showAddTeam = true } label: {
                    Text("+ Add Team")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(CrewTheme.accent)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .overlay(Capsule().stroke(CrewTheme.accent, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)

            if teams.isEmpty {
                VStack(spacing: 16) {
                    Spacer()
                    Text("No teams yet.")
                        .foregroundStyle(CrewTheme.muted)
                    Button("Create Your First Team") { showAddTeam = true }
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 10)
                        .background(CrewTheme.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .buttonStyle(.plain)
                    Spacer()
                }
                .frame(maxWidth: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(teams) { team in
                            TeamRowCard(team: team, isSelected: selectedTeamId == team.id)
                                .onTapGesture {
                                    selectedTeamId = team.id
                                    withAnimation(.easeInOut(duration: 0.25)) {
                                        appState.navDestination = .teamDetail(team)
                                    }
                                }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
                }
            }
        }
        .frame(maxHeight: .infinity)
        .background(CrewTheme.bg)
        .sheet(isPresented: $showAddTeam) {
            AddTeamSheet()
        }
    }
}

// MARK: - Team Row Card

private struct TeamRowCard: View {
    let team: Team
    let isSelected: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "building.2.fill")
                .font(.system(size: 16))
                .foregroundStyle(CrewTheme.muted)
                .frame(width: 32, height: 32)
                .background(CrewTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 6))

            VStack(alignment: .leading, spacing: 2) {
                Text(team.name)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)
                Text("\(team.agentCount) agents")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
            }

            Spacer()

            Image(systemName: "doc.on.doc")
                .font(.system(size: 13))
                .foregroundStyle(CrewTheme.muted)
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? CrewTheme.accent : CrewTheme.border, lineWidth: 1)
        )
    }
}
