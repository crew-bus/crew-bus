import SwiftUI
import CrewBusKit

struct DecisionLogView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "list.clipboard.fill")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Decision Log")
                .font(.title2)
            Text("Decision history coming soon")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
