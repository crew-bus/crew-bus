import SwiftUI
import CrewBusKit

struct MainView: View {
    @Environment(AppState.self) private var appState
    @State private var isMenuOpen = false

    var body: some View {
        Group {
            if appState.isServerReady {
                if appState.needsSetup {
                    SetupView()
                } else if appState.requiresPinAuth {
                    PinEntryView()
                } else if appState.isDashboardLocked {
                    LockScreenView()
                } else {
                    appContentView
                }
            } else {
                StartupView()
            }
        }
        .preferredColorScheme(appState.colorScheme == .dark ? .dark : .light)
    }

    @ViewBuilder
    private var appContentView: some View {
        VStack(spacing: 0) {
            TopBarView(isMenuOpen: $isMenuOpen)

            ZStack {
                CrewTheme.bg.ignoresSafeArea()

                ParticlesView()

                switch appState.navDestination {
                case .dashboard:
                    DashboardView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .leading).combined(with: .opacity),
                            removal: .move(edge: .leading).combined(with: .opacity)
                        ))
                case .agentChat(let agent):
                    ChatView(agent: agent)
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .teamDetail(let team):
                    TeamDetailView(team: team)
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .messageFeed:
                    MessageFeedView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .auditLog:
                    AuditLogView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .socialDrafts:
                    SocialDraftsView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .observability:
                    ObservabilityView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .channelList:
                    ChannelListView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .channelDetail(let channel):
                    ChannelDetailView(channel: channel)
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                case .deviceManagement:
                    DeviceManagementView()
                        .transition(.asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        ))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: appState.navDestination)
        }
        .background(CrewTheme.bg)
    }
}

// MARK: - Startup View

struct StartupView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 20) {
            if let error = appState.serverError {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 48))
                    .foregroundStyle(CrewTheme.muted)
                Text("Couldn't connect to Crew Bus")
                    .font(.title2)
                    .foregroundStyle(CrewTheme.text)
                Text(error)
                    .foregroundStyle(CrewTheme.muted)
                Button("Retry") {
                    appState.retryConnection()
                }
                .buttonStyle(.borderedProminent)
                .tint(CrewTheme.accent)
            } else {
                ProgressView()
                    .scaleEffect(1.5)
                Text("Starting your crew...")
                    .font(.title2)
                    .foregroundStyle(CrewTheme.text)
                Text("This may take a moment on first launch")
                    .font(.caption)
                    .foregroundStyle(CrewTheme.muted)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(CrewTheme.bg)
    }
}

// MARK: - Lock Screen

struct LockScreenView: View {
    @Environment(AppState.self) private var appState
    @State private var pin = ""
    @State private var errorMessage = ""
    @State private var isUnlocking = false

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "lock.fill")
                .font(.system(size: 48))
                .foregroundStyle(CrewTheme.accent)

            Text("Dashboard Locked")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Enter your PIN to unlock.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)

            SecureField("PIN", text: $pin)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .padding(12)
                .background(CrewTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
                .frame(maxWidth: 200)
                .multilineTextAlignment(.center)
                .onSubmit { unlock() }

            if !errorMessage.isEmpty {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(CrewTheme.highlight)
            }

            Button {
                unlock()
            } label: {
                if isUnlocking {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Text("Unlock")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 10)
                        .background(pin.isEmpty ? CrewTheme.muted : CrewTheme.accent)
                        .clipShape(Capsule())
                }
            }
            .buttonStyle(.plain)
            .disabled(pin.isEmpty || isUnlocking)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(CrewTheme.bg)
    }

    private func unlock() {
        isUnlocking = true
        errorMessage = ""
        Task {
            do {
                try await appState.client.post(
                    APIEndpoints.configSet,
                    body: ["key": "dashboard_locked", "value": "false", "pin": pin]
                )
                await MainActor.run {
                    appState.isDashboardLocked = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Wrong PIN."
                    isUnlocking = false
                    pin = ""
                }
            }
        }
    }
}
