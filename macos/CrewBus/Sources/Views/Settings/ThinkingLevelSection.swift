import SwiftUI
import CrewBusKit

struct ThinkingLevelSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var selectedLevel: String = "auto"

    private let levels = ["auto", "off", "minimal", "standard", "deep", "ultra"]

    var body: some View {
        HStack {
            Label("Thinking Depth", systemImage: "brain")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(CrewTheme.text)

            Spacer()

            Picker("", selection: $selectedLevel) {
                ForEach(levels, id: \.self) { level in
                    Text(level.capitalized).tag(level)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 120)
            .onChange(of: selectedLevel) { _, newValue in
                updateThinking(newValue)
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .onAppear {
            selectedLevel = agent.thinkingLevel ?? "auto"
        }
    }

    private func updateThinking(_ level: String) {
        Task {
            try? await appState.client.post(
                APIEndpoints.agentThinking(agent.id),
                body: ["level": level]
            )
            await appState.loadInitialData()
        }
    }
}
