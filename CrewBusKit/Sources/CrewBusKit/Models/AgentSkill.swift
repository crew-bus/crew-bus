import Foundation

public struct AgentSkill: Codable, Identifiable {
    public var id: String { skillName }
    public let skillName: String
    public let skillConfig: String?
    public let vetStatus: String?
}

public struct SkillRegistryEntry: Codable, Identifiable {
    public var id: String { name }
    public let name: String
    public let description: String?
    public let vetStatus: String?
}
