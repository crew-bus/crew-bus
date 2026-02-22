import Foundation

public struct HeartbeatTask: Codable, Identifiable {
    public let id: Int
    public let agentId: Int
    public let schedule: String
    public let task: String
    public let enabled: Int
    public let lastRun: String?
}
