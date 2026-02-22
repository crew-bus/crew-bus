import SwiftUI
import CrewBusKit

struct AgentDetailView: View {
    let agent: Agent

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: typeInfo.symbolName)
                .font(.system(size: 64))
                .foregroundStyle(typeInfo.color)

            Text(agent.resolvedDisplayName)
                .font(.title)
                .fontWeight(.bold)

            VStack(spacing: 8) {
                DetailRow(label: "Type", value: typeInfo.displayName)
                DetailRow(label: "Status", value: agent.status.capitalized)
                if let trust = agent.trustScore {
                    DetailRow(label: "Trust", value: "\(trust)")
                }
                if let parent = agent.parentName {
                    DetailRow(label: "Reports to", value: parent)
                }
                if let desc = agent.description {
                    DetailRow(label: "Description", value: desc)
                }
            }
            .padding()

            Spacer()
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct DetailRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
                .frame(width: 100, alignment: .trailing)
            Text(value)
            Spacer()
        }
    }
}
