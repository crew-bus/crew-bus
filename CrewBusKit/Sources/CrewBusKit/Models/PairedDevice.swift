import Foundation

public struct PairedDevice: Codable, Identifiable {
    public let id: Int
    public let deviceName: String?
    public let role: String?
    public let pairedAt: String?
    public let active: Bool?
}
