import Foundation

public struct Agent: Codable, Identifiable, Hashable {
    public let id: Int
    public let name: String
    public let agentType: String
    public let status: String
    public let trustScore: Int?
    public let burnoutScore: Int?
    public let displayName: String?
    public let unreadCount: Int?
    public let lastMessageTime: String?
    public let periodCount: Int?
    public let parentName: String?
    public let description: String?
    public let parentAgentId: Int?
    public let model: String?
    public let createdAt: String?

    public var resolvedDisplayName: String {
        displayName ?? name
    }

    public var isHuman: Bool {
        agentType == "human"
    }
}
