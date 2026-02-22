import SwiftUI
import CrewBusKit

struct HamburgerMenuView: View {
    @Binding var isPresented: Bool
    @Environment(AppState.self) private var appState
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            menuItem("Crew Message Trail", icon: "bubble.left.and.bubble.right") {
                navigate(to: .messageFeed)
            }
            menuItem("Crew Audit Trail", icon: "doc.text.magnifyingglass") {
                navigate(to: .auditLog)
            }
            menuItem("Social Media Drafts", icon: "pencil.and.outline") {
                navigate(to: .socialDrafts)
            }

            Divider()
                .background(CrewTheme.border)
                .padding(.vertical, 4)

            menuItem("Crew Channels", icon: "number") {
                navigate(to: .channelList)
            }
            menuItem("Observability", icon: "chart.bar.xaxis") {
                navigate(to: .observability)
            }
            menuItem("Security & Devices", icon: "lock.shield") {
                navigate(to: .deviceManagement)
            }
            menuItem("Link to Claude Desktop", icon: "link.badge.plus") {
                navigate(to: .claudeExtension)
            }

            Divider()
                .background(CrewTheme.border)
                .padding(.vertical, 4)

            menuItem("Software Update", icon: "arrow.down.circle") {
                isPresented = false
                UpdateManager.shared.checkNow()
            }
            menuItem("Update Settings", icon: "gearshape") {
                navigate(to: .updateSettings)
            }
            menuItem("Lock Dashboard", icon: "lock.fill") {
                isPresented = false
                Task { await appState.lockDashboard() }
            }
            menuItem("Send Feedback", icon: "envelope") {
                isPresented = false
                if let url = URL(string: "https://github.com/anthropics/claude-code/issues") {
                    NSWorkspace.shared.open(url)
                }
            }
        }
        .padding(.vertical, 8)
        .frame(width: 220)
        .background(CrewTheme.surface)
    }

    private func navigate(to destination: NavDestination) {
        isPresented = false
        withAnimation(.easeInOut(duration: 0.25)) {
            appState.navDestination = destination
        }
    }

    @ViewBuilder
    private func menuItem(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button {
            action()
        } label: {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .frame(width: 20)
                    .foregroundStyle(CrewTheme.muted)
                Text(title)
                    .font(.system(size: 13))
                    .foregroundStyle(CrewTheme.text)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
