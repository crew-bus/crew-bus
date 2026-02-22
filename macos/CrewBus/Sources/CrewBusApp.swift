import SwiftUI

@main
struct CrewBusApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var appState: AppState?

    var body: some Scene {
        WindowGroup {
            Group {
                if let appState {
                    MainView()
                        .environment(appState)
                } else {
                    ProgressView("Initializing...")
                }
            }
            .frame(minWidth: 900, minHeight: 600)
            .onAppear {
                if appState == nil {
                    let state = AppState(serverManager: appDelegate.serverManager)
                    appState = state
                    state.startMonitoring()
                }
            }
        }
        .defaultSize(width: 1200, height: 800)
    }
}
