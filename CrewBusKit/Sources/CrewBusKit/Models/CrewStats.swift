import Foundation

public struct CrewStats: Codable {
    public let crewName: String
    public let humanName: String
    public let humanId: Int?
    public let bossName: String
    public let trustScore: Int
    public let burnoutScore: Int
    public let agentCount: Int
    public let messageCount: Int
    public let decisionCount: Int
}
