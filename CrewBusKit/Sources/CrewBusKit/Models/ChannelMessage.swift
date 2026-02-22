import Foundation

public struct ChannelMessage: Codable, Identifiable {
    public let id: Int
    public let fromAgentId: Int?
    public let fromName: String?
    public let body: String
    public let createdAt: String?
}
