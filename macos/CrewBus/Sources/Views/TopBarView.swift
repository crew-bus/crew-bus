import SwiftUI
import CrewBusKit

struct TopBarView: View {
    @Environment(AppState.self) private var appState
    @Binding var isMenuOpen: Bool

    var body: some View {
        HStack(spacing: 0) {
            // Left: brand title
            Text("crew-bus")
                .font(.system(size: 16, weight: .bold, design: .monospaced))
                .foregroundStyle(CrewTheme.accent)
                .padding(.leading, 20)

            Spacer()

            // Right: Crew button + hamburger
            HStack(spacing: 12) {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .dashboard
                    }
                } label: {
                    Text("Crew")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)

                Button {
                    isMenuOpen.toggle()
                } label: {
                    Image(systemName: "line.3.horizontal")
                        .font(.system(size: 18))
                        .foregroundStyle(CrewTheme.text)
                        .frame(width: 36, height: 36)
                        .background(CrewTheme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(CrewTheme.border, lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
                .popover(isPresented: $isMenuOpen, arrowEdge: .top) {
                    HamburgerMenuView(isPresented: $isMenuOpen)
                }
            }
            .padding(.trailing, 16)
        }
        .frame(height: 50)
        .background(CrewTheme.surface)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(CrewTheme.border)
                .frame(height: 1)
        }
    }
}
