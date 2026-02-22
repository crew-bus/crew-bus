import SwiftUI
import CrewBusKit

struct TeamDetailView: View {
    let team: Team
    @Environment(AppState.self) private var appState
    @State private var showHireSheet = false
    @State private var agentToTerminate: Agent?

    // Derive manager/workers from team agents
    private var managerAgent: Agent? {
        appState.teamAgents.first {
            $0.agentType == "manager" &&
            $0.name.lowercased().contains(team.name.lowercased())
        }
    }

    private var workerAgents: [Agent] {
        guard let mgr = managerAgent else { return [] }
        return appState.teamAgents.filter {
            $0.agentType == "worker" && $0.parentAgentId == mgr.id
        }
    }

    private func terminateAgent(_ agent: Agent) {
        Task {
            try? await appState.client.post(
                APIEndpoints.agentTerminate(agent.id),
                body: [:]
            )
            await appState.loadInitialData()
        }
        agentToTerminate = nil
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header bar
            teamHeader

            ScrollView {
                VStack(spacing: 24) {
                    // Hierarchy
                    hierarchySection

                    // Team Meeting button
                    Button {} label: {
                        Label("Team Meeting", systemImage: "person.2.fill")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 32)
                            .padding(.vertical, 12)
                            .background(CrewTheme.accent)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)

                    // Mailbox
                    mailboxSection

                    // Linked Teams
                    linkedTeamsSection
                }
                .padding(24)
            }
        }
        .background(CrewTheme.bg)
        .sheet(isPresented: $showHireSheet) {
            HireAgentSheet(managerName: managerAgent?.name ?? team.manager)
        }
        .alert(
            "Terminate Agent",
            isPresented: Binding(
                get: { agentToTerminate != nil },
                set: { if !$0 { agentToTerminate = nil } }
            )
        ) {
            Button("Cancel", role: .cancel) { agentToTerminate = nil }
            Button("Terminate", role: .destructive) {
                if let agent = agentToTerminate {
                    terminateAgent(agent)
                }
            }
        } message: {
            if let agent = agentToTerminate {
                Text("Terminate \"\(agent.resolvedDisplayName)\"? This retires the agent permanently and archives all messages.")
            }
        }
    }

    // MARK: - Header

    private var teamHeader: some View {
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

            Text(teamEmoji(for: team.name))
                .font(.title2)

            Text(team.name)
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            // Agent count badge
            Text("\(team.agentCount) AGENTS")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(CrewTheme.green)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(CrewTheme.green.opacity(0.15))
                .clipShape(Capsule())

            Spacer()

            // Pause Team
            Button {} label: {
                Text("Pause Team")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(CrewTheme.orange)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .overlay(Capsule().stroke(CrewTheme.orange, lineWidth: 1))
            }
            .buttonStyle(.plain)

            // Delete Team
            Button {} label: {
                Text("Delete Team")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color(hex: "#d63031"))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .overlay(Capsule().stroke(Color(hex: "#d63031"), lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(CrewTheme.surface)
        .overlay(alignment: .bottom) {
            Rectangle().fill(CrewTheme.border).frame(height: 1)
        }
    }

    // MARK: - Hierarchy

    private var hierarchySection: some View {
        VStack(spacing: 0) {
            // Manager node
            if let mgr = managerAgent {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .agentChat(mgr)
                    }
                } label: {
                    agentNode(agent: mgr, size: 80, ringColor: CrewTheme.accent, subtitle: "Manager")
                }
                .buttonStyle(.plain)
            } else {
                placeholderNode(size: 80, label: team.manager.isEmpty ? "Manager" : team.manager, subtitle: "Manager")
            }

            // Dashed vertical line
            DashedVerticalLine()
                .stroke(CrewTheme.border, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                .frame(width: 1, height: 40)

            // Worker nodes + Hire Agent
            HStack(spacing: 24) {
                ForEach(workerAgents) { worker in
                    Button {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            appState.navDestination = .agentChat(worker)
                        }
                    } label: {
                        agentNode(agent: worker, size: 60, ringColor: CrewTheme.border, subtitle: "Worker")
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        Button {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                appState.navDestination = .agentChat(worker)
                            }
                        } label: {
                            Label("Chat", systemImage: "message")
                        }
                        Divider()
                        Button(role: .destructive) {
                            agentToTerminate = worker
                        } label: {
                            Label("Terminate", systemImage: "trash")
                        }
                    }
                }

                // Hire Agent button
                Button { showHireSheet = true } label: {
                    VStack(spacing: 8) {
                        Circle()
                            .stroke(CrewTheme.border, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                            .frame(width: 60, height: 60)
                            .overlay(
                                Image(systemName: "plus")
                                    .font(.system(size: 20))
                                    .foregroundStyle(CrewTheme.muted)
                            )
                        Text("Hire Agent")
                            .font(.system(size: 11))
                            .foregroundStyle(CrewTheme.muted)
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(CrewTheme.border, lineWidth: 1))
    }

    @ViewBuilder
    private func agentNode(agent: Agent, size: CGFloat, ringColor: Color, subtitle: String) -> some View {
        let typeInfo = AgentTypeInfo.info(for: agent.agentType)
        VStack(spacing: 6) {
            ZStack(alignment: .topTrailing) {
                Circle()
                    .fill(CrewTheme.surface)
                    .frame(width: size, height: size)
                    .overlay(Circle().stroke(ringColor, lineWidth: 2.5))
                    .overlay(
                        Image(systemName: typeInfo.symbolName)
                            .font(.system(size: size * 0.35))
                            .foregroundStyle(ringColor)
                    )

                Circle()
                    .fill(agent.status == "active" ? CrewTheme.green : CrewTheme.muted)
                    .frame(width: 10, height: 10)
                    .overlay(Circle().stroke(CrewTheme.bg, lineWidth: 2))
                    .offset(x: 2, y: -2)
            }

            Text(agent.resolvedDisplayName)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(CrewTheme.text)
                .lineLimit(1)

            Text(subtitle)
                .font(.system(size: 10))
                .foregroundStyle(CrewTheme.muted)
        }
    }

    @ViewBuilder
    private func placeholderNode(size: CGFloat, label: String, subtitle: String) -> some View {
        VStack(spacing: 6) {
            Circle()
                .fill(CrewTheme.surface)
                .frame(width: size, height: size)
                .overlay(Circle().stroke(CrewTheme.accent, lineWidth: 2.5))
                .overlay(
                    Image(systemName: "person.fill")
                        .font(.system(size: size * 0.35))
                        .foregroundStyle(CrewTheme.accent)
                )

            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(CrewTheme.text)

            Text(subtitle)
                .font(.system(size: 10))
                .foregroundStyle(CrewTheme.muted)
        }
    }

    // MARK: - Mailbox

    private var mailboxSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Text("📬")
                Text("Mailbox")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)
            }
            Text("No messages yet. Your agents will post updates here as they work.")
                .font(.system(size: 13))
                .foregroundStyle(CrewTheme.muted)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(CrewTheme.border, lineWidth: 1))
    }

    // MARK: - Linked Teams

    private var linkedTeamsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Text("🔗")
                Text("Linked Teams")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)
            }
            Text("No linked teams yet.")
                .font(.system(size: 13))
                .foregroundStyle(CrewTheme.muted)

            if !appState.teams.isEmpty {
                HStack(spacing: 8) {
                    // Team picker
                    Menu {
                        ForEach(appState.teams.filter { $0.id != team.id }) { t in
                            Button(t.name) {}
                        }
                    } label: {
                        HStack {
                            Text("Select team...")
                                .font(.system(size: 13))
                                .foregroundStyle(CrewTheme.text)
                            Spacer()
                            Image(systemName: "chevron.down")
                                .font(.system(size: 11))
                                .foregroundStyle(CrewTheme.muted)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))
                    }

                    Button {} label: {
                        Label("Link", systemImage: "link")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(CrewTheme.accent)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(CrewTheme.border, lineWidth: 1))
    }
}

// MARK: - Hire Agent Sheet

struct HireAgentSheet: View {
    let managerName: String
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    @State private var agentName = ""
    @State private var agentDescription = ""
    @State private var errorMessage = ""
    @State private var isHiring = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 6) {
                Text("Hire a New Agent")
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundStyle(CrewTheme.text)
                Text("Reports to \(managerName)")
                    .font(.caption)
                    .foregroundStyle(CrewTheme.muted)
            }
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider().background(CrewTheme.border)

            VStack(spacing: 12) {
                TextField("Agent name", text: $agentName)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .padding(10)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

                TextField("What does this agent do? (optional)", text: $agentDescription)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .padding(10)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

                if !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(CrewTheme.highlight)
                }
            }
            .padding(20)

            Divider().background(CrewTheme.border)

            HStack(spacing: 12) {
                Button("Cancel") { dismiss() }
                    .font(.system(size: 14))
                    .foregroundStyle(CrewTheme.muted)
                    .buttonStyle(.plain)

                Button {
                    hire()
                } label: {
                    if isHiring {
                        ProgressView()
                            .controlSize(.small)
                            .frame(width: 60)
                    } else {
                        Text("Hire")
                            .font(.system(size: 14, weight: .semibold))
                    }
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 8)
                .background(agentName.trimmingCharacters(in: .whitespaces).isEmpty ? CrewTheme.muted : CrewTheme.accent)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .buttonStyle(.plain)
                .disabled(agentName.trimmingCharacters(in: .whitespaces).isEmpty || isHiring)
            }
            .padding(.vertical, 14)
        }
        .frame(width: 360)
        .background(CrewTheme.surface)
    }

    private func hire() {
        let name = agentName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else {
            errorMessage = "Name is required."
            return
        }
        isHiring = true
        errorMessage = ""
        Task {
            do {
                var body: [String: Any] = [
                    "name": name,
                    "agent_type": "worker",
                    "parent": managerName
                ]
                let desc = agentDescription.trimmingCharacters(in: .whitespacesAndNewlines)
                if !desc.isEmpty { body["description"] = desc }

                try await appState.client.post(APIEndpoints.createAgent, body: body)
                await appState.loadInitialData()
                await MainActor.run { dismiss() }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to hire agent."
                    isHiring = false
                }
            }
        }
    }
}

// MARK: - Dashed Vertical Line Shape

struct DashedVerticalLine: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        return path
    }
}
