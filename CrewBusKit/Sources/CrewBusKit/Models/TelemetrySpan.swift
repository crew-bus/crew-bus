import Foundation

public struct TelemetrySpan: Codable, Identifiable {
    public let id: Int
    public let traceId: String?
    public let spanName: String
    public let agentId: Int?
    public let durationMs: Double?
    public let status: String?
    public let metadata: String?
    public let createdAt: String?
}
