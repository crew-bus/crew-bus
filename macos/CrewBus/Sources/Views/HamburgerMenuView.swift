import SwiftUI

struct HamburgerMenuView: View {
    @Binding var isPresented: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            menuItem("Crew Message Trail", icon: "bubble.left.and.bubble.right")
            menuItem("Crew Audit Trail",   icon: "doc.text.magnifyingglass")
            menuItem("Social Media Drafts", icon: "pencil.and.outline")

            Divider()
                .background(CrewTheme.border)
                .padding(.vertical, 4)

            menuItem("Software Update", icon: "arrow.down.circle")
            menuItem("Lock Dashboard",  icon: "lock.fill")
            menuItem("Send Feedback",   icon: "envelope")
        }
        .padding(.vertical, 8)
        .frame(width: 220)
        .background(CrewTheme.surface)
    }

    @ViewBuilder
    private func menuItem(_ title: String, icon: String) -> some View {
        Button {
            isPresented = false
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
