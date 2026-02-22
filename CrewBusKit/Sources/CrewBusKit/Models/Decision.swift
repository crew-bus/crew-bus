import Foundation

public struct Decision: Codable, Identifiable {
    public let id: Int
    public let action: String?
    public let riskLevel: String?
    public let status: String?
    public let createdAt: String?
    public let rhName: String?
    public let humanName: String?
}
