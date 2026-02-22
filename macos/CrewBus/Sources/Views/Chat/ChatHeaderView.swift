import SwiftUI
import CrewBusKit

struct ChatHeaderView: View {
    let agent: Agent
    var onRefresh: () -> Void = {}
    @Environment(AppState.self) private var appState
    @State private var statusPulse = false
    @State private var isRenaming = false
    @State private var editedName = ""
    @State private var showTerminateAlert = false
    @State private var refreshTapped = false

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    /// If this agent belongs to a team, go back to that team; otherwise dashboard.
    private var backDestination: NavDestination {
        if agent.agentType == "manager" || agent.agentType == "worker" {
            // Find the team this agent belongs to
            if agent.agentType == "manager" {
                if let team = appState.teams.first(where: {
                    agent.name.lowercased().contains($0.name.lowercased())
                }) {
                    return .teamDetail(team)
                }
            } else if let parentId = agent.parentAgentId,
                      let manager = appState.teamAgents.first(where: { $0.id == parentId }),
                      let team = appState.teams.first(where: {
                          manager.name.lowercased().contains($0.name.lowercased())
                      }) {
                return .teamDetail(team)
            }
        }
        return .dashboard
    }

    var body: some View {
        HStack(spacing: 12) {
            // Back button
            Button {
                withAnimation(.easeInOut(duration: 0.25)) {
                    appState.navDestination = backDestination
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
                    .frame(width: 160)
                } else {
                    Text(agent.resolvedDisplayName)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                        .onTapGesture(count: 2) {
                            editedName = agent.resolvedDisplayName
                            isRenaming = true
                        }
                        .help("Double-click to rename")
                }

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
            HStack(spacing: 12) {
                Button {
                    refreshTapped = true
                    refreshChat()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                        refreshTapped = false
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 11))
                        Text(refreshTapped ? "Refreshing..." : "Refresh Chat")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .foregroundStyle(refreshTapped ? CrewTheme.green : CrewTheme.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background((refreshTapped ? CrewTheme.green : CrewTheme.accent).opacity(0.1))
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke((refreshTapped ? CrewTheme.green : CrewTheme.accent).opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)

                Menu {
                    Button {
                        editedName = agent.resolvedDisplayName
                        isRenaming = true
                    } label: {
                        Label("Rename", systemImage: "pencil")
                    }

                    Divider()

                    Button(role: .destructive) {
                        showTerminateAlert = true
                    } label: {
                        Label("Terminate Agent", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "gearshape")
                        .font(.system(size: 15))
                        .foregroundStyle(CrewTheme.muted)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 60)
        .background(CrewTheme.surface)
        .overlay(alignment: .bottom) {
            Rectangle().fill(CrewTheme.border).frame(height: 1)
        }
        .alert("Terminate Agent", isPresented: $showTerminateAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Terminate", role: .destructive) {
                terminateAgent()
            }
        } message: {
            Text("Terminate \"\(agent.resolvedDisplayName)\"? This retires the agent permanently and archives all messages.")
        }
    }

    private func refreshChat() {
        onRefresh()
    }

    private func terminateAgent() {
        Task {
            try? await appState.client.post(
                APIEndpoints.agentTerminate(agent.id),
                body: [:]
            )
            await appState.loadInitialData()
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.25)) {
                    appState.navDestination = backDestination
                }
            }
        }
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

}
