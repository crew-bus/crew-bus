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

    public static func agentRename(_ id: Int) -> String {
        "/api/agent/\(id)/rename"
    }

    public static func agentTerminate(_ id: Int) -> String {
        "/api/agent/\(id)/terminate"
    }

    public static let createAgent = "/api/agents/create"
    public static let trust = "/api/trust"
    public static let energy = "/api/energy"
    public static let configSet = "/api/config/set"

    // Setup
    public static let setupStatus = "/api/setup/status"
    public static let setupComplete = "/api/setup/complete"

    // Messages & Audit
    public static let messageFeed = "/api/messages/feed"
    public static let audit = "/api/audit"

    // Social
    public static let socialDrafts = "/api/social/drafts"

    // Agent actions
    public static func agentDeactivate(_ id: Int) -> String {
        "/api/agent/\(id)/deactivate"
    }

    public static func agentActivate(_ id: Int) -> String {
        "/api/agent/\(id)/activate"
    }

    public static func agentMessage(_ id: Int) -> String {
        "/api/agent/\(id)/message"
    }

    // Teams
    public static func team(_ id: Int) -> String {
        "/api/teams/\(id)"
    }

    public static func teamDelete(_ id: Int) -> String {
        "/api/teams/\(id)/delete"
    }

    public static func teamAgents(_ id: Int) -> String {
        "/api/teams/\(id)/agents"
    }

    public static func teamMailbox(_ id: Int) -> String {
        "/api/teams/\(id)/mailbox"
    }

    // Agent Settings
    public static func agentAvatar(_ id: Int) -> String {
        "/api/agent/\(id)/avatar"
    }

    public static func agentSoul(_ id: Int) -> String {
        "/api/agent/\(id)/soul"
    }

    public static func agentThinking(_ id: Int) -> String {
        "/api/agent/\(id)/thinking"
    }

    public static func agentHeartbeat(_ id: Int) -> String {
        "/api/agent/\(id)/heartbeat"
    }

    public static func agentLearnings(_ id: Int) -> String {
        "/api/agent/\(id)/learnings"
    }

    public static func agentFace(_ id: Int) -> String {
        "/api/agent/\(id)/face"
    }

    public static func agentFaceMode(_ id: Int) -> String {
        "/api/agent/\(id)/face/mode"
    }

    // Heartbeat actions
    public static func heartbeatToggle(_ id: Int) -> String {
        "/api/heartbeat/\(id)/toggle"
    }

    public static func heartbeatDelete(_ id: Int) -> String {
        "/api/heartbeat/\(id)/delete"
    }

    // Skills
    public static func agentSkills(_ id: Int) -> String {
        "/api/skills/\(id)"
    }

    public static let skillRegistry = "/api/skill-registry"

    public static let skillsAdd = "/api/skills/add"

    // Telemetry
    public static let telemetry = "/api/telemetry"
    public static let telemetryStats = "/api/telemetry/stats"

    // Crew Channels
    public static let crewChannels = "/api/crew/channels"

    public static func channelMessages(_ id: Int) -> String {
        "/api/crew/channels/\(id)/messages"
    }

    public static func channelPost(_ id: Int) -> String {
        "/api/crew/channels/\(id)/post"
    }

    public static func channelMembers(_ id: Int) -> String {
        "/api/crew/channels/\(id)/members"
    }

    // Gateway Auth
    public static let authMode = "/api/auth/mode"
    public static let authPin = "/api/auth/pin"
    public static let authConfig = "/api/auth/config"
    public static let authPairingCode = "/api/auth/pairing-code"
    public static let authPair = "/api/auth/pair"
    public static let devices = "/api/devices"

    public static func deviceRevoke(_ id: Int) -> String {
        "/api/devices/\(id)/revoke"
    }
}
