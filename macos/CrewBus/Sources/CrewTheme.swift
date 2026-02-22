import SwiftUI
import AppKit

enum CrewTheme {
    // Backgrounds
    static let bg      = Color.adaptive(light: "#f6f8fa", dark: "#0d1117")
    static let surface = Color.adaptive(light: "#ffffff", dark: "#161b22")
    static let border  = Color.adaptive(light: "#d0d7de", dark: "#30363d")

    // Text
    static let text    = Color.adaptive(light: "#1f2328", dark: "#e6edf3")
    static let muted   = Color.adaptive(light: "#656d76", dark: "#8b949e")

    // Accents (same in both modes)
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

    /// Creates a color that adapts to light/dark appearance.
    static func adaptive(light: String, dark: String) -> Color {
        Color(nsColor: NSColor(name: nil, dynamicProvider: { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return isDark ? NSColor(Color(hex: dark)) : NSColor(Color(hex: light))
        }))
    }
}
