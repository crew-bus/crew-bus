import SwiftUI
import CrewBusKit

struct MainView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if appState.isServerReady {
                NavigationSplitView {
                    SidebarView()
                } detail: {
                    if let agent = appState.selectedAgent {
                        ChatView(agent: agent)
                    } else {
                        DashboardView()
                    }
                }
            } else {
                StartupView()
            }
        }
    }
}

struct StartupView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 20) {
            if let error = appState.serverError {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)
                Text("Couldn't connect to Crew Bus")
                    .font(.title2)
                Text(error)
                    .foregroundStyle(.secondary)
                Button("Retry") {
                    appState.retryConnection()
                }
                .buttonStyle(.borderedProminent)
            } else {
                ProgressView()
                    .scaleEffect(1.5)
                Text("Starting your crew...")
                    .font(.title2)
                    .foregroundStyle(.secondary)
                Text("This may take a moment on first launch")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
