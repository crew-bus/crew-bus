import SwiftUI

struct SunMoonToggleView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        HStack(spacing: 0) {
            togglePill(icon: "sun.max.fill", isSelected: appState.colorScheme == .light) {
                appState.colorScheme = .light
            }
            togglePill(icon: "moon.fill", isSelected: appState.colorScheme == .dark) {
                appState.colorScheme = .dark
            }
        }
        .background(CrewTheme.surface)
        .clipShape(Capsule())
        .overlay(Capsule().stroke(CrewTheme.border, lineWidth: 1))
    }

    @ViewBuilder
    private func togglePill(icon: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12))
                .foregroundStyle(isSelected ? CrewTheme.bg : CrewTheme.muted)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(isSelected ? CrewTheme.accent : Color.clear)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}
