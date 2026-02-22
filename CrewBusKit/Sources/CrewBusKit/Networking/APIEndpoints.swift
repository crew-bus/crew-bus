import Foundation

public enum APIEndpoints {
    public static let stats = "/api/stats"
    public static let agents = "/api/agents"
    public static let teams = "/api/teams"
    public static let decisions = "/api/decisions"
    public static let health = "/api/health"

    public static func agent(_ id: Int) -> String {
        "/api/agent/\(id)"
    }

    public static func agentChat(_ id: Int) -> String {
        "/api/agent/\(id)/chat"
    }

    public static func agentActivity(_ id: Int) -> String {
        "/api/agent/\(id)/activity"
    }

    public static func agentChatClear(_ id: Int) -> String {
        "/api/agent/\(id)/chat/clear"
    }
}
