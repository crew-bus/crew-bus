import SwiftUI

public struct AgentTypeInfo {
    public let displayName: String
    public let symbolName: String
    public let color: Color

    public static func info(for agentType: String) -> AgentTypeInfo {
        switch agentType {
        case "right_hand":
            return AgentTypeInfo(displayName: "Crew Boss", symbolName: "star.fill", color: .white)
        case "guardian":
            return AgentTypeInfo(displayName: "Guardian", symbolName: "shield.fill", color: .orange)
        case "wellness":
            return AgentTypeInfo(displayName: "Health Buddy", symbolName: "heart.fill", color: Color(red: 1.0, green: 0.67, blue: 0.34))
        case "strategy":
            return AgentTypeInfo(displayName: "Growth Coach", symbolName: "chart.line.uptrend.xyaxis", color: .green)
        case "communications":
            return AgentTypeInfo(displayName: "Friend & Family", symbolName: "bubble.left.and.bubble.right.fill", color: .teal)
        case "financial":
            return AgentTypeInfo(displayName: "Life Assistant", symbolName: "dollarsign.circle.fill", color: .blue)
        case "human":
            return AgentTypeInfo(displayName: "You", symbolName: "person.fill", color: .purple)
        case "manager":
            return AgentTypeInfo(displayName: "Team Manager", symbolName: "person.3.fill", color: .indigo)
        case "worker":
            return AgentTypeInfo(displayName: "Worker", symbolName: "wrench.fill", color: .gray)
        case "vault":
            return AgentTypeInfo(displayName: "Vault", symbolName: "lock.shield.fill", color: Color(red: 0.74, green: 0.55, blue: 1.0))
        default:
            return AgentTypeInfo(displayName: agentType.capitalized, symbolName: "cpu", color: .secondary)
        }
    }
}
