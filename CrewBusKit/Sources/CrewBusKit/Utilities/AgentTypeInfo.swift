import SwiftUI

public struct AgentTypeInfo {
    public let displayName: String
    public let symbolName: String
    public let color: Color

    public static func info(for agentType: String) -> AgentTypeInfo {
        switch agentType {
        case "right_hand":
            return AgentTypeInfo(displayName: "Crew Boss", symbolName: "star.fill", color: .white)
        case "guardian", "security":
            return AgentTypeInfo(displayName: "Guardian", symbolName: "shield.fill", color: .orange)
        case "vault":
            return AgentTypeInfo(displayName: "Vault", symbolName: "lock.shield.fill", color: Color(red: 0.74, green: 0.55, blue: 1.0))
        case "human":
            return AgentTypeInfo(displayName: "You", symbolName: "person.fill", color: .purple)
        case "manager":
            return AgentTypeInfo(displayName: "Team Manager", symbolName: "person.3.fill", color: .indigo)
        case "worker":
            return AgentTypeInfo(displayName: "Worker", symbolName: "wrench.fill", color: .gray)
        default:
            return AgentTypeInfo(displayName: agentType.capitalized, symbolName: "cpu", color: .secondary)
        }
    }
}
