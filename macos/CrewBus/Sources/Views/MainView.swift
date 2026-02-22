import SwiftUI
import CrewBusKit

struct MainView: View {
    @Environment(AppState.self) private var appState
    @State private var isMenuOpen = false

    var body: some View {
        Group {
            if appState.isServerReady {
                appContentView
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
