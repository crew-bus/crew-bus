import SwiftUI
import CrewBusKit

struct AgentRow: View {
    let agent: Agent

    private var typeInfo: AgentTypeInfo {
        AgentTypeInfo.info(for: agent.agentType)
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: typeInfo.symbolName)
                .foregroundStyle(typeInfo.color)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(agent.resolvedDisplayName)
                    .fontWeight(.medium)
                if agent.status != "active" {
                    Text(agent.status.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            if let unread = agent.unreadCount, unread > 0 {
                Text("\(unread)")
                    .font(.caption2)
                    .fontWeight(.bold)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.blue)
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
            }
        }
        .padding(.vertical, 2)
    }
}
