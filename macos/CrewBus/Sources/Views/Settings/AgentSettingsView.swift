import SwiftUI
import CrewBusKit

struct AgentSettingsView: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var isRenaming = false
    @State private var editedName = ""
    @State private var showTerminateAlert = false

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header bar
            HStack {
                Text("Agent Settings")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)
            }
            .padding(16)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            ScrollView {
                VStack(spacing: 16) {
                    // Agent identity header
                    agentHeader

                    // Avatar picker
                    AvatarPickerSection(agent: agent)

                    // Soul editor
                    SoulEditorSection(agent: agent)

                    // Thinking level
                    ThinkingLevelSection(agent: agent)

                    // Heartbeat tasks
                    HeartbeatSection(agent: agent)

                    // Learning log
                    LearningSection(agent: agent)

                    // Skills
                    SkillsSection(agent: agent)

                    // Danger zone
                    dangerZone
                }
                .padding(16)
            }
        }
        .frame(width: 520, height: 640)
        .background(CrewTheme.bg)
        .alert("Terminate Agent", isPresented: $showTerminateAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Terminate", role: .destructive) {
                terminateAgent()
            }
        } message: {
            Text("Terminate \"\(agent.resolvedDisplayName)\"? This retires the agent permanently and archives all messages.")
        }
    }

    private var agentHeader: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(CrewTheme.surface)
                    .frame(width: 48, height: 48)
                    .overlay(Circle().stroke(typeInfo.color.opacity(0.7), lineWidth: 2))

                if let avatar = agent.avatar, !avatar.isEmpty {
                    Text(avatar)
                        .font(.system(size: 22))
                } else {
                    Image(systemName: typeInfo.symbolName)
                        .font(.system(size: 18))
                        .foregroundStyle(typeInfo.color)
                }
            }

            VStack(alignment: .leading, spacing: 2) {
                if isRenaming {
                    TextField("Name", text: $editedName, onCommit: {
                        submitRename()
                    })
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(CrewTheme.accent, lineWidth: 1))
                } else {
                    Text(agent.resolvedDisplayName)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                }

                Text(typeInfo.displayName)
                    .font(.system(size: 12))
                    .foregroundStyle(typeInfo.color)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(typeInfo.color.opacity(0.15))
                    .clipShape(Capsule())
            }

            Spacer()
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    private var dangerZone: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Danger Zone")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(CrewTheme.highlight)

            HStack(spacing: 8) {
                Button {
                    editedName = agent.resolvedDisplayName
                    isRenaming = true
                } label: {
                    Label("Rename", systemImage: "pencil")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(CrewTheme.text)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(CrewTheme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)

                Button {
                    showTerminateAlert = true
                } label: {
                    Label("Terminate Agent", systemImage: "trash")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(CrewTheme.highlight)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(CrewTheme.highlight.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.highlight.opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.highlight.opacity(0.3), lineWidth: 1))
    }

    private func submitRename() {
        let newName = editedName.trimmingCharacters(in: .whitespacesAndNewlines)
        isRenaming = false
        guard !newName.isEmpty, newName != agent.resolvedDisplayName else { return }
        Task {
            try? await appState.client.post(
                APIEndpoints.agentRename(agent.id),
                body: ["name": newName]
            )
            await appState.loadInitialData()
        }
    }

    private func terminateAgent() {
        Task {
            try? await appState.client.post(
                APIEndpoints.agentTerminate(agent.id),
                body: [:]
            )
            await appState.loadInitialData()
            await MainActor.run {
                dismiss()
                withAnimation(.easeInOut(duration: 0.25)) {
                    appState.navDestination = .dashboard
                }
            }
        }
    }
}
