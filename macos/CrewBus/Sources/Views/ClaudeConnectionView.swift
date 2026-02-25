import SwiftUI
import CrewBusKit

struct ClaudeConnectionView: View {
    @Environment(AppState.self) private var appState
    @State private var connector = ClaudeConnector()

    private let suggestions = [
        "Who's on my crew?",
        "Send a message to Crew Boss about my schedule",
        "What has Guardian flagged recently?",
        "Show me what the team has been up to",
        "Check the team mailbox",
        "What has Vault learned about me?",
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
                    case .checking:
                        ProgressView()
                            .frame(maxWidth: .infinity, minHeight: 100)
                    case .notInstalled:
                        notInstalledContent
                    case .disconnected:
                        disconnectedContent
                    case .connecting:
                        connectingContent
                    case .connected(let needsRestart):
                        connectedContent(needsRestart: needsRestart)
                    case .error(let message):
                        errorContent(message: message)
                    }
                }
                .padding(20)
                .animation(.easeInOut(duration: 0.25), value: stateId)
            }
        }
        .background(CrewTheme.bg)
        .task { await connector.checkStatus() }
    }

    /// Stable ID for animating state transitions.
    private var stateId: String {
        switch connector.state {
        case .checking: return "checking"
        case .notInstalled: return "not-installed"
        case .disconnected: return "disconnected"
        case .connecting: return "connecting"
        case .connected: return "connected"
        case .error: return "error"
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
                Text("Connect to Claude Desktop")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                Text("Chat with your crew directly from Claude")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
            }

            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    // MARK: - Not Installed

    private var notInstalledContent: some View {
        VStack(spacing: 16) {
            VStack(spacing: 12) {
                Image(systemName: "info.circle")
                    .font(.system(size: 36))
                    .foregroundStyle(CrewTheme.accent)

                Text("Claude Desktop Required")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                Text("Install Claude Desktop to chat with your crew using natural language.")
                    .font(.system(size: 13))
                    .foregroundStyle(CrewTheme.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(24)
            .frame(maxWidth: .infinity)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

            Button {
                if let url = URL(string: "https://claude.ai/download") {
                    NSWorkspace.shared.open(url)
                }
            } label: {
                Text("Download Claude Desktop")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(CrewTheme.accent)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)

            Text("Already installed? Try restarting CrewBus.")
                .font(.system(size: 11))
                .foregroundStyle(CrewTheme.muted)

            refreshButton
        }
    }

    // MARK: - Disconnected

    private var disconnectedContent: some View {
        VStack(spacing: 16) {
            statusCards

            if !connector.mcpAvailable {
                mcpMissingCard
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

            suggestionsSection
        }
    }

    // MARK: - Connecting

    private var connectingContent: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)
            Text("Connecting to Claude Desktop...")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(CrewTheme.text)
            Text("Setting up the connection")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)
        }
        .frame(maxWidth: .infinity, minHeight: 120)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    // MARK: - Connected

    private func connectedContent(needsRestart: Bool) -> some View {
        VStack(spacing: 16) {
            // Success card
            HStack(spacing: 12) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(CrewTheme.green)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Connected to Claude Desktop")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                    Text("Your crew is available in Claude. Just ask Claude to talk to your agents.")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }

                Spacer()
            }
            .padding(14)
            .background(CrewTheme.green.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.green.opacity(0.3), lineWidth: 1))

            // Restart hint
            if needsRestart {
                HStack(spacing: 8) {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.accent)
                    Text("Restart Claude Desktop to activate the connection")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(CrewTheme.accent.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            // Action buttons
            HStack(spacing: 10) {
                Button {
                    connector.openClaude()
                } label: {
                    Text("Open Claude")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)

                Button {
                    Task { await connector.disconnect() }
                } label: {
                    Text("Disconnect")
                        .font(.system(size: 13))
                        .foregroundStyle(CrewTheme.muted)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                }
                .buttonStyle(.plain)

                refreshButton
            }

            suggestionsSection
        }
    }

    // MARK: - Error

    private func errorContent(message: String) -> some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(CrewTheme.highlight)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Connection failed")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                    Text(message)
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }

                Spacer()
            }
            .padding(14)
            .background(CrewTheme.highlight.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.highlight.opacity(0.3), lineWidth: 1))

            HStack(spacing: 10) {
                Button {
                    Task { await connector.connect() }
                } label: {
                    Text("Try Again")
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
        }
    }

    // MARK: - Shared Components

    private var statusCards: some View {
        VStack(spacing: 10) {
            statusCard(
                title: "Crew Bus Server",
                subtitle: connector.crewbusRunning ? "Running on port 8420" : "Not reachable",
                icon: "server.rack",
                ok: connector.crewbusRunning
            )
            statusCard(
                title: "Claude Desktop",
                subtitle: connector.claudeInstalled ? "Installed" : "Not detected",
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

    private var suggestionsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Things you can ask Claude")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Once connected, try saying things like:")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)

            VStack(spacing: 6) {
                ForEach(suggestions, id: \.self) { suggestion in
                    HStack(spacing: 10) {
                        Image(systemName: "quote.opening")
                            .font(.system(size: 10))
                            .foregroundStyle(CrewTheme.accent.opacity(0.6))
                            .frame(width: 16)

                        Text(suggestion)
                            .font(.system(size: 13))
                            .foregroundStyle(CrewTheme.text)
                            .italic()

                        Spacer()
                    }
                    .padding(.vertical, 6)
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
