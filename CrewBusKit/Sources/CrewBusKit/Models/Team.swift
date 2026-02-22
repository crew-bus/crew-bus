import Foundation

public struct Team: Codable, Identifiable {
    public let id: Int
    public let name: String
    public let icon: String
    public let agentCount: Int
    public let manager: String
    public let status: String
    public let lockedName: Bool?
}
