import Foundation

public struct TelemetryStatsResponse: Codable {
    public let stats: [TelemetryStat]
    public let totalSpans: Int?
    public let avgResponseMs: Double?
    public let errorRate: Double?
}

public struct TelemetryStat: Codable, Identifiable {
    public var id: String { spanName }
    public let spanName: String
    public let callCount: Int
    public let avgMs: Double
    public let p95Ms: Double?
    public let errorCount: Int?
    public let errorRate: Double?
}
