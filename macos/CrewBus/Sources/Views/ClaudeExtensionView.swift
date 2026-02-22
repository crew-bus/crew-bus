import SwiftUI
import CrewBusKit

struct ClaudeExtensionView: View {
    @Environment(AppState.self) private var appState

    @State private var isServerReachable = false
    @State private var isClaudeInstalled = false
    @State private var isLinked = false
    @State private var isChecking = true
    @State private var isLinking = false
    @State private var statusMessage = ""
    @State private var showError = false
    @State private var errorMessage = ""

    private var configURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json")
    }

    private let tools: [(name: String, desc: String)] = [
        ("list_agents", "List all crew members with status"),
        ("send_message", "Chat with any agent, get reply"),
        ("get_agent_chat", "Recent chat history with an agent"),
        ("get_crew_stats", "Dashboard overview and stats"),
        ("list_teams", "All teams with managers/counts"),
        ("get_team_detail", "Team info + agent list"),
        ("get_message_feed", "Recent crew message feed"),
        ("search_agent_memory", "Search an agent's memory"),
        ("get_agent_learnings", "Mistakes + what works well"),
        ("get_audit_log", "Recent crew audit events"),
        ("post_to_team_mailbox", "Post to team mailbox"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            header

            Rectangle()
                .fill(CrewTheme.border)
                .frame(height: 1)

            ScrollView {
                VStack(spacing: 20) {
                    statusSection
                    actionSection
                    toolsSection
                }
                .padding(20)
            }
        }
        .background(CrewTheme.bg)
        .task { await checkStatus() }
        .alert("Error", isPresented: $showError) {
            Button("OK", role: .cancel) { }
        } message: {
            Text(errorMessage)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.25)) {
                    appState.navDestination = .dashboard
                }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(CrewTheme.muted)
            }
            .buttonStyle(.plain)

            Image(systemName: "link.badge.plus")
                .font(.system(size: 20))
                .foregroundStyle(CrewTheme.accent)

            VStack(alignment: .leading, spacing: 2) {
                Text("Claude Desktop Extension")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                Text("Let Claude Desktop talk to your local crew via MCP")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
            }

            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    // MARK: - Status

    private var statusSection: some View {
        VStack(spacing: 10) {
            statusCard(
                title: "Crew Bus Server",
                subtitle: isServerReachable ? "Running on port 8420" : "Not reachable",
                icon: "server.rack",
                ok: isServerReachable
            )
            statusCard(
                title: "Claude Desktop",
                subtitle: isClaudeInstalled ? "Config file found" : "Not detected",
                icon: "app.badge",
                ok: isClaudeInstalled
            )
            statusCard(
                title: "MCP Link",
                subtitle: isLinked ? "crew-bus linked in config" : "Not linked",
                icon: "link",
                ok: isLinked
            )
        }
    }

    private func statusCard(title: String, subtitle: String, icon: String, ok: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(ok ? CrewTheme.green : CrewTheme.muted)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundStyle(CrewTheme.muted)
            }

            Spacer()

            Circle()
                .fill(ok ? CrewTheme.green : CrewTheme.muted.opacity(0.4))
                .frame(width: 8, height: 8)
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    // MARK: - Actions

    private var actionSection: some View {
        VStack(spacing: 10) {
            if !statusMessage.isEmpty {
                Text(statusMessage)
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(spacing: 10) {
                if isLinked {
                    Button {
                        Task { await unlinkFromClaude() }
                    } label: {
                        Label("Unlink", systemImage: "xmark.circle")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .background(CrewTheme.highlight)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                } else {
                    Button {
                        Task { await linkToClaude() }
                    } label: {
                        HStack(spacing: 6) {
                            if isLinking {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            Text(isLinking ? "Linking..." : "Link to Claude Desktop")
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(isLinking ? CrewTheme.muted : CrewTheme.accent)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(isLinking)
                }

                Button {
                    Task { await checkStatus() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .font(.system(size: 13))
                        .foregroundStyle(CrewTheme.text)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(CrewTheme.surface)
                        .clipShape(Capsule())
                        .overlay(Capsule().stroke(CrewTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Tools List

    private var toolsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Available MCP Tools")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Once linked, Claude Desktop can use these tools to interact with your crew:")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)

            VStack(spacing: 6) {
                ForEach(tools, id: \.name) { tool in
                    HStack(spacing: 10) {
                        Text(tool.name)
                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                            .foregroundStyle(CrewTheme.accent)
                            .frame(width: 180, alignment: .leading)

                        Text(tool.desc)
                            .font(.system(size: 12))
                            .foregroundStyle(CrewTheme.muted)

                        Spacer()
                    }
                    .padding(.vertical, 4)
                    .padding(.horizontal, 10)
                }
            }
            .padding(10)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        }
    }

    // MARK: - Logic

    private func checkStatus() async {
        isChecking = true

        // Check server
        do {
            struct HealthResponse: Decodable { let status: String }
            let _: HealthResponse = try await appState.client.get(APIEndpoints.health)
            await MainActor.run { isServerReachable = true }
        } catch {
            await MainActor.run { isServerReachable = false }
        }

        // Check Claude Desktop config
        let configExists = FileManager.default.fileExists(atPath: configURL.path)

        // Check link status
        var linked = false
        if configExists,
           let data = try? Data(contentsOf: configURL),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let servers = json["mcpServers"] as? [String: Any] {
            linked = servers["crew-bus"] != nil
        }

        await MainActor.run {
            isClaudeInstalled = configExists
            isLinked = linked
            isChecking = false
        }
    }

    private func linkToClaude() async {
        await MainActor.run {
            isLinking = true
            statusMessage = "Checking MCP package..."
        }

        // Resolve paths
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let crewBusDir = "\(home)/crew-bus"
        let venvPython = "\(crewBusDir)/.venv/bin/python"
        let mcpScript = "\(crewBusDir)/crew_bus_mcp.py"

        let pythonPath: String
        if FileManager.default.fileExists(atPath: venvPython) {
            pythonPath = venvPython
        } else {
            pythonPath = "/usr/bin/python3"
        }

        // Check if mcp package is available
        let mcpAvailable = await runProcess(pythonPath, args: ["-c", "import mcp"])

        if !mcpAvailable {
            await MainActor.run { statusMessage = "Installing mcp package..." }
            let installed = await runProcess(pythonPath, args: ["-m", "pip", "install", "mcp>=1.0.0"])
            if !installed {
                await MainActor.run {
                    isLinking = false
                    errorMessage = "Failed to install the 'mcp' Python package.\nPlease run: pip install mcp"
                    showError = true
                    statusMessage = ""
                }
                return
            }
        }

        await MainActor.run { statusMessage = "Writing Claude Desktop config..." }

        // Read existing config or start fresh
        var config: [String: Any] = [:]
        if FileManager.default.fileExists(atPath: configURL.path),
           let data = try? Data(contentsOf: configURL),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            config = json
        }

        // Merge crew-bus server entry
        var servers = config["mcpServers"] as? [String: Any] ?? [:]
        servers["crew-bus"] = [
            "command": pythonPath,
            "args": [mcpScript],
            "env": ["CREW_BUS_URL": "http://127.0.0.1:8420"],
        ] as [String: Any]
        config["mcpServers"] = servers

        // Write config
        do {
            let configDir = configURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: configURL)
        } catch {
            await MainActor.run {
                isLinking = false
                errorMessage = "Failed to write config: \(error.localizedDescription)"
                showError = true
                statusMessage = ""
            }
            return
        }

        await MainActor.run {
            isLinking = false
            isLinked = true
            statusMessage = "Linked! Restart Claude Desktop to activate."
        }
    }

    private func unlinkFromClaude() async {
        guard FileManager.default.fileExists(atPath: configURL.path),
              let data = try? Data(contentsOf: configURL),
              var json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              var servers = json["mcpServers"] as? [String: Any] else {
            return
        }

        servers.removeValue(forKey: "crew-bus")
        json["mcpServers"] = servers

        do {
            let updated = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
            try updated.write(to: configURL)
        } catch {
            await MainActor.run {
                errorMessage = "Failed to update config: \(error.localizedDescription)"
                showError = true
            }
            return
        }

        await MainActor.run {
            isLinked = false
            statusMessage = "Unlinked. Restart Claude Desktop to apply."
        }
    }

    private func runProcess(_ executable: String, args: [String]) async -> Bool {
        await withCheckedContinuation { continuation in
            DispatchQueue.global().async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: executable)
                process.arguments = args
                process.standardOutput = FileHandle.nullDevice
                process.standardError = FileHandle.nullDevice
                do {
                    try process.run()
                    process.waitUntilExit()
                    continuation.resume(returning: process.terminationStatus == 0)
                } catch {
                    continuation.resume(returning: false)
                }
            }
        }
    }
}
