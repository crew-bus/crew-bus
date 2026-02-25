import SwiftUI
import CrewBusKit

struct ClaudeConnectionView: View {
    @Environment(AppState.self) private var appState
    @State private var connector = ClaudeConnector()

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
                    switch connector.state {
                    case .unknown:
                        ProgressView()
                            .frame(maxWidth: .infinity, minHeight: 100)
                    case .disconnected:
                        disconnectedContent
                    case .connecting:
                        connectingContent
                    case .connected:
                        connectedContent
                    }
                }
                .padding(20)
            }
        }
        .background(CrewTheme.bg)
        .task { await connector.checkStatus() }
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
                Text("Connect to Claude Desktop")
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

    // MARK: - Disconnected

    private var disconnectedContent: some View {
        VStack(spacing: 16) {
            statusCards

            if !connector.mcpAvailable {
                mcpMissingCard
            }

            if let error = connector.errorMessage {
                Text(error)
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.highlight)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(spacing: 10) {
                Button {
                    Task { await connector.connect() }
                } label: {
                    Text("Connect to Claude")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)

                refreshButton
            }

            toolsSection
        }
    }

    // MARK: - Connecting

    private var connectingContent: some View {
        VStack(spacing: 16) {
            VStack(spacing: 12) {
                ProgressView()
                    .controlSize(.large)
                Text("Connecting to Claude Desktop...")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(CrewTheme.text)
                Text("Writing MCP config")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
            }
            .frame(maxWidth: .infinity, minHeight: 120)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        }
    }

    // MARK: - Connected

    private var connectedContent: some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(CrewTheme.green)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Connected to Claude Desktop")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                    Text("Restart Claude Desktop if you haven't already")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }

                Spacer()
            }
            .padding(14)
            .background(CrewTheme.green.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.green.opacity(0.3), lineWidth: 1))

            HStack(spacing: 10) {
                Button {
                    Task { await connector.disconnect() }
                } label: {
                    Label("Disconnect", systemImage: "xmark.circle")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(CrewTheme.highlight)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)

                refreshButton
            }

            toolsSection
        }
    }

    // MARK: - Shared Components

    private var statusCards: some View {
        VStack(spacing: 10) {
            statusCard(
                title: "Crew Bus Server",
                subtitle: connector.serverOk ? "Running on port 8420" : "Not reachable",
                icon: "server.rack",
                ok: connector.serverOk
            )
            statusCard(
                title: "Claude Desktop",
                subtitle: connector.claudeInstalled ? "Config file found" : "Not detected",
                icon: "app.badge",
                ok: connector.claudeInstalled
            )
            statusCard(
                title: "MCP Package",
                subtitle: connector.mcpAvailable ? "Installed" : "Not found",
                icon: "shippingbox",
                ok: connector.mcpAvailable
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

    private var mcpMissingCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "info.circle")
                    .foregroundStyle(CrewTheme.accent)
                Text("MCP package not found")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(CrewTheme.text)
            }
            Text("Install it so Claude Desktop can talk to your crew:")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)

            let installCmd = "pip install mcp"
            HStack {
                Text(installCmd)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(CrewTheme.accent)
                    .textSelection(.enabled)
                Spacer()
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(installCmd, forType: .string)
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)
            }
            .padding(10)
            .background(CrewTheme.bg)
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    private var refreshButton: some View {
        Button {
            Task { await connector.checkStatus() }
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

    private var toolsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Available MCP Tools")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Once connected, Claude Desktop can use these tools to interact with your crew:")
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
}
