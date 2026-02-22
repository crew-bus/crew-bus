import SwiftUI
import CrewBusKit

struct TeamsPanelView: View {
    @Environment(AppState.self) private var appState
    let teams: [Team]
    @State private var showAddTeam = false
    @State private var selectedTeamId: Int?
    @State private var glowingIndex: Int = 0

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
                        ForEach(Array(teams.enumerated()), id: \.element.id) { index, team in
                            TeamRowCard(
                                team: team,
                                isSelected: selectedTeamId == team.id,
                                isGlowing: index == glowingIndex
                            )
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
        .background(Color.clear)
        .sheet(isPresented: $showAddTeam) {
            AddTeamSheet()
        }
        .onAppear { startSequentialGlow() }
        .onChange(of: teams.count) { startSequentialGlow() }
    }

    private func startSequentialGlow() {
        guard !teams.isEmpty else { return }
        glowingIndex = 0
        Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2.0))
                await MainActor.run {
                    withAnimation(.easeInOut(duration: 0.8)) {
                        glowingIndex = (glowingIndex + 1) % teams.count
                    }
                }
            }
        }
    }
}

// MARK: - Team Emoji Lookup

/// Maps team names to the emojis shown in AddTeamSheet.
/// The server returns a generic 🏢 for all teams, so we resolve client-side.
func teamEmoji(for name: String) -> String {
    let key = name.lowercased()
    if key.contains("school")          { return "🎓" }
    if key.contains("passion")         { return "🎨" }
    if key.contains("household")       { return "🏠" }
    if key.contains("freelance")       { return "💼" }
    if key.contains("side hustle")     { return "⚡" }
    if key.contains("custom")          { return "🧩" }
    return "📋"
}

// MARK: - Team Row Card

private struct TeamRowCard: View {
    let team: Team
    let isSelected: Bool
    let isGlowing: Bool

    var body: some View {
        HStack(spacing: 12) {
            Text(teamEmoji(for: team.name))
                .font(.system(size: 20))
                .frame(width: 32, height: 32)

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
        .shadow(
            color: CrewTheme.accent.opacity(isGlowing ? 0.5 : 0),
            radius: isGlowing ? 12 : 0
        )
        .animation(.easeInOut(duration: 0.8), value: isGlowing)
    }
}
