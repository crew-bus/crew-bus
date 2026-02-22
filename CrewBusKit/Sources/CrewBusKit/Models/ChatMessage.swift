import Foundation

public struct ChatMessage: Codable, Identifiable, Equatable {
    public let id: Int
    public let direction: String
    public let text: String
    public let time: String
    public let isPrivate: Bool

    enum CodingKeys: String, CodingKey {
        case id, direction, text, time
        case isPrivate = "private"
    }

    public var isFromHuman: Bool {
        direction == "from_human"
    }
}
