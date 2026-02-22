import Foundation

public struct CrewChannel: Codable, Identifiable, Equatable, Hashable {
    public let id: Int
    public let name: String
    public let purpose: String?
    public let memberCount: Int?
    public let msgCount: Int?
}
