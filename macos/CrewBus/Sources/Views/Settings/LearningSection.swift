import SwiftUI
import CrewBusKit

struct LearningSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var isExpanded = false
    @State private var errors: [AgentMemory] = []
    @State private var learnings: [AgentMemory] = []

    private var totalCount: Int { errors.count + learnings.count }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    Label("Learning Log (\(totalCount))", systemImage: "book.closed")
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
                if totalCount == 0 {
                    Text("No learning entries yet")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                        .padding(.vertical, 4)
                }

                if !errors.isEmpty {
                    Text("Mistakes to Avoid")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(CrewTheme.highlight)
                        .padding(.top, 4)

                    ForEach(errors) { memory in
                        memoryRow(memory, tint: CrewTheme.highlight)
                    }
                }

                if !learnings.isEmpty {
                    Text("What Works Well")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(CrewTheme.green)
                        .padding(.top, 4)

                    ForEach(learnings) { memory in
                        memoryRow(memory, tint: CrewTheme.green)
                    }
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .task {
            await fetchLearnings()
        }
    }

    @ViewBuilder
    private func memoryRow(_ memory: AgentMemory, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(memory.content)
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.text)
            if let date = memory.createdAt {
                Text(date)
                    .font(.system(size: 10))
                    .foregroundStyle(CrewTheme.muted)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(tint.opacity(0.2), lineWidth: 1))
    }

    private func fetchLearnings() async {
        do {
            let response: AgentLearningsResponse = try await appState.client.get(
                APIEndpoints.agentLearnings(agent.id)
            )
            await MainActor.run {
                errors = response.errors
                learnings = response.learnings
            }
        } catch {
            // Silent fail
        }
    }
}
