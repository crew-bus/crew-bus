import SwiftUI
import CrewBusKit

struct TeamDetailView: View {
    let team: Team
    @Environment(AppState.self) private var appState
    @State private var showHireSheet = false
    @State private var agentToTerminate: Agent?
    @State private var showPauseConfirm = false
    @State private var showDeleteConfirm = false
    @State private var deletePin = ""
    @State private var isPausing = false
    @State private var isDeleting = false
    @State private var mailboxMessages: [MailboxMessage] = []
    @State private var isLoadingMailbox = true

    struct MailboxMessage: Decodable, Identifiable {
        let id: Int
        let sender: String
        let content: String
        let timestamp: String
    }

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

            GeometryReader { geo in
                ScrollView {
                    VStack(spacing: 24) {
                        // Hierarchy (includes mailbox + linked teams at bottom)
                        hierarchySection
                    }
                    .padding(24)
                    .frame(minHeight: geo.size.height)
                }
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
        .alert("Pause Team", isPresented: $showPauseConfirm) {
            Button("Cancel", role: .cancel) { }
            Button("Pause All", role: .destructive) { pauseTeam() }
        } message: {
            Text("Deactivate all agents in \"\(team.name)\"? You can reactivate them later.")
        }
        .alert("Delete Team", isPresented: $showDeleteConfirm) {
            SecureField("Enter PIN to confirm", text: $deletePin)
            Button("Cancel", role: .cancel) { deletePin = "" }
            Button("Delete", role: .destructive) { deleteTeam() }
        } message: {
            Text("Permanently delete \"\(team.name)\" and all its agents? This cannot be undone.")
        }
        .task { await loadMailbox() }
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

            // Hire Agent
            Button { showHireSheet = true } label: {
                HStack(spacing: 5) {
                    Image(systemName: "plus")
                        .font(.system(size: 11, weight: .bold))
                    Text("Hire Agent")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(CrewTheme.green)
                .clipShape(Capsule())
            }
            .buttonStyle(.plain)

            // Pause Team
            Button { showPauseConfirm = true } label: {
                if isPausing {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 80)
                } else {
                    Text("Pause Team")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(CrewTheme.orange)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .overlay(Capsule().stroke(CrewTheme.orange, lineWidth: 1))
                }
            }
            .buttonStyle(.plain)
            .disabled(isPausing)

            // Delete Team
            Button { showDeleteConfirm = true } label: {
                if isDeleting {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 80)
                } else {
                    Text("Delete Team")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color(hex: "#d63031"))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .overlay(Capsule().stroke(Color(hex: "#d63031"), lineWidth: 1))
                }
            }
            .buttonStyle(.plain)
            .disabled(isDeleting)
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
            Spacer().frame(height: 20)

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

            }

            Spacer(minLength: 16)

            // Bottom bar: mailbox icon left, link icon right
            HStack {
                // Mailbox icon
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        mailboxExpanded.toggle()
                        if mailboxExpanded { linkedTeamsExpanded = false }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text("📬")
                            .font(.system(size: 16))
                        Text("\(mailboxMessages.count)")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(mailboxMessages.isEmpty ? CrewTheme.muted : .white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(mailboxMessages.isEmpty ? CrewTheme.muted.opacity(0.3) : CrewTheme.accent)
                            .clipShape(Capsule())
                    }
                    .padding(8)
                    .background(mailboxExpanded ? CrewTheme.accent.opacity(0.15) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
                .buttonStyle(.plain)
                .help("Mailbox")

                Spacer()

                // Linked Teams icon
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        linkedTeamsExpanded.toggle()
                        if linkedTeamsExpanded { mailboxExpanded = false }
                    }
                } label: {
                    Text("🔗")
                        .font(.system(size: 16))
                        .padding(8)
                        .background(linkedTeamsExpanded ? CrewTheme.accent.opacity(0.15) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                }
                .buttonStyle(.plain)
                .help("Linked Teams")
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)

            // Expanded content area
            if mailboxExpanded {
                Divider().background(CrewTheme.border)
                mailboxContent
            }

            if linkedTeamsExpanded {
                Divider().background(CrewTheme.border)
                linkedTeamsContent
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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

    @State private var mailboxExpanded = false

    private var mailboxContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            if isLoadingMailbox {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
            } else if mailboxMessages.isEmpty {
                Text("No messages yet. Agents will post updates here.")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
            } else {
                ForEach(mailboxMessages) { msg in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "envelope.fill")
                            .font(.system(size: 12))
                            .foregroundStyle(CrewTheme.accent)
                            .frame(width: 24, height: 24)
                            .background(CrewTheme.accent.opacity(0.1))
                            .clipShape(Circle())

                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(msg.sender)
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(CrewTheme.text)
                                Spacer()
                                Text(msg.timestamp)
                                    .font(.system(size: 10))
                                    .foregroundStyle(CrewTheme.muted)
                            }
                            Text(msg.content)
                                .font(.system(size: 12))
                                .foregroundStyle(CrewTheme.text.opacity(0.85))
                                .lineLimit(3)
                        }
                    }
                    .padding(.vertical, 2)

                    if msg.id != mailboxMessages.last?.id {
                        Divider().background(CrewTheme.border)
                    }
                }
            }
        }
        .padding(12)
    }

    // MARK: - Linked Teams

    @State private var linkedTeamsExpanded = false

    private var linkedTeamsContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("No linked teams yet.")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)

            if !appState.teams.isEmpty {
                HStack(spacing: 8) {
                    Menu {
                        ForEach(appState.teams.filter { $0.id != team.id }) { t in
                            Button(t.name) {}
                        }
                    } label: {
                        HStack {
                            Text("Select team...")
                                .font(.system(size: 12))
                                .foregroundStyle(CrewTheme.text)
                            Spacer()
                            Image(systemName: "chevron.down")
                                .font(.system(size: 10))
                                .foregroundStyle(CrewTheme.muted)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))
                    }

                    Button {} label: {
                        Label("Link", systemImage: "link")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(CrewTheme.accent)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(12)
    }
}

// MARK: - Team Actions

extension TeamDetailView {
    func startTeamMeeting() {
        guard let mgr = managerAgent else { return }
        let prompt = "Start a team meeting. Check in with each worker, summarize what everyone is working on, and identify any blockers."
        Task {
            try? await appState.client.post(
                APIEndpoints.agentMessage(mgr.id),
                body: ["message": prompt]
            )
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.25)) {
                    appState.navDestination = .agentChat(mgr)
                }
            }
        }
    }

    func pauseTeam() {
        isPausing = true
        let allAgents = [managerAgent].compactMap { $0 } + workerAgents
        Task {
            for agent in allAgents {
                try? await appState.client.post(
                    APIEndpoints.agentDeactivate(agent.id),
                    body: [:]
                )
            }
            await appState.loadInitialData()
            await MainActor.run { isPausing = false }
        }
    }

    func deleteTeam() {
        isDeleting = true
        Task {
            do {
                try await appState.client.post(
                    APIEndpoints.teamDelete(team.id),
                    body: ["pin": deletePin]
                )
                await appState.loadInitialData()
                await MainActor.run {
                    deletePin = ""
                    isDeleting = false
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .dashboard
                    }
                }
            } catch {
                await MainActor.run {
                    deletePin = ""
                    isDeleting = false
                }
            }
        }
    }

    func loadMailbox() async {
        do {
            let fetched: [MailboxMessage] = try await appState.client.get(
                APIEndpoints.teamMailbox(team.id)
            )
            await MainActor.run {
                mailboxMessages = fetched
                isLoadingMailbox = false
            }
        } catch {
            await MainActor.run { isLoadingMailbox = false }
        }
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
