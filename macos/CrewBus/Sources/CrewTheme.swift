import SwiftUI

enum CrewTheme {
    // Backgrounds
    static let bg      = Color(hex: "#0d1117")
    static let surface = Color(hex: "#161b22")
    static let border  = Color(hex: "#30363d")

    // Text
    static let text    = Color(hex: "#e6edf3")
    static let muted   = Color(hex: "#8b949e")

    // Accents
    static let accent    = Color(hex: "#58a6ff")
    static let highlight = Color(hex: "#e94560")
    static let green     = Color(hex: "#3fb950")
    static let orange    = Color(hex: "#d18616")
    static let purple    = Color(hex: "#bc8cff")
}

extension Color {
    init(hex: String) {
        let h = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var int: UInt64 = 0
        Scanner(string: h).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255.0
        let g = Double((int >> 8)  & 0xFF) / 255.0
        let b = Double( int        & 0xFF) / 255.0
        self.init(red: r, green: g, blue: b)
    }
}
