import SwiftUI
import CrewBusKit

struct SoulEditorSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var isExpanded = false
    @State private var soulText = ""
    @State private var saved = false
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    Label("Identity & Soul", systemImage: "sparkles")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                TextEditor(text: $soulText)
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.text)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 80, maxHeight: 120)
                    .padding(8)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))

                HStack {
                    Spacer()
                    if saved {
                        Text("Saved!")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(CrewTheme.green)
                            .transition(.opacity)
                    }
                    Button {
                        saveSoul()
                    } label: {
                        HStack(spacing: 4) {
                            if isSaving {
                                ProgressView()
                                    .controlSize(.mini)
                            }
                            Text("Save")
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 5)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(isSaving)
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .onAppear {
            soulText = agent.soul ?? ""
        }
    }

    private func saveSoul() {
        isSaving = true
        Task {
            try? await appState.client.post(
                APIEndpoints.agentSoul(agent.id),
                body: ["soul": soulText]
            )
            await appState.loadInitialData()
            await MainActor.run {
                isSaving = false
                saved = true
            }
            try? await Task.sleep(for: .seconds(2))
            await MainActor.run { saved = false }
        }
    }
}
