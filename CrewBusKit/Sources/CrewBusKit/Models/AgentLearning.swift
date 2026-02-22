import Foundation

public struct AgentLearningsResponse: Codable {
    public let errors: [AgentMemory]
    public let learnings: [AgentMemory]
}

public struct AgentMemory: Codable, Identifiable {
    public let id: Int
    public let content: String
    public let createdAt: String?
}
