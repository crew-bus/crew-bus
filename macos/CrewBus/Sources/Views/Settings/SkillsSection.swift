import SwiftUI
import CrewBusKit

struct SkillsSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var isExpanded = false
    @State private var skills: [AgentSkill] = []
    @State private var registry: [SkillRegistryEntry] = []
    @State private var newName = ""
    @State private var newConfig = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    Label("Skills (\(skills.count))", systemImage: "puzzlepiece")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                if skills.isEmpty {
                    Text("No skills installed")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                        .padding(.vertical, 4)
                } else {
                    ForEach(skills) { skill in
                        HStack(spacing: 8) {
                            Text(skill.skillName)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(CrewTheme.text)

                            Spacer()

                            Text(vetBadge(for: skill))
                                .font(.system(size: 14))
                        }
                        .padding(8)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }

                // Add form
                HStack(spacing: 6) {
                    TextField("Skill name", text: $newName)
                        .font(.system(size: 12))
                        .textFieldStyle(.plain)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(CrewTheme.border, lineWidth: 1))

                    TextField("Config", text: $newConfig)
                        .font(.system(size: 12))
                        .textFieldStyle(.plain)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(CrewTheme.border, lineWidth: 1))
                        .frame(width: 100)

                    Button {
                        addSkill()
                    } label: {
                        Text("Add")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(CrewTheme.accent)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .task {
            await fetchSkills()
        }
    }

    private func vetBadge(for skill: AgentSkill) -> String {
        let regEntry = registry.first { $0.name == skill.skillName }
        switch regEntry?.vetStatus ?? skill.vetStatus {
        case "approved": return "✅"
        case "warning": return "⚠️"
        case "blocked": return "🚫"
        default: return "⚠️"
        }
    }

    private func fetchSkills() async {
        do {
            let fetched: [AgentSkill] = try await appState.client.get(
                APIEndpoints.agentSkills(agent.id)
            )
            await MainActor.run { skills = fetched }
        } catch {}

        do {
            let reg: [SkillRegistryEntry] = try await appState.client.get(
                APIEndpoints.skillRegistry
            )
            await MainActor.run { registry = reg }
        } catch {}
    }

    private func addSkill() {
        let name = newName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        Task {
            try? await appState.client.post(
                APIEndpoints.skillsAdd,
                body: ["agent_id": agent.id, "skill_name": name, "skill_config": newConfig]
            )
            await MainActor.run {
                newName = ""
                newConfig = ""
            }
            await fetchSkills()
        }
    }
}
