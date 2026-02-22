import SwiftUI
import CrewBusKit

struct AuditLogView: View {
    @Environment(AppState.self) private var appState
    @State private var entries: [AuditEntry] = []
    @State private var isLoading = true

    struct AuditEntry: Decodable, Identifiable {
        let id: Int
        let action: String
        let actor: String
        let detail: String?
        let timestamp: String
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 12) {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .dashboard
                    }
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                        .frame(width: 34, height: 34)
                        .background(CrewTheme.surface)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(CrewTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)

                Image(systemName: "doc.text.magnifyingglass")
                    .foregroundStyle(CrewTheme.accent)
                Text("Crew Audit Trail")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(CrewTheme.text)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            // Content
            if isLoading {
                Spacer()
                ProgressView()
                Spacer()
            } else if entries.isEmpty {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 40))
                        .foregroundStyle(CrewTheme.muted)
                    Text("No audit entries yet")
                        .font(.system(size: 15))
                        .foregroundStyle(CrewTheme.muted)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(entries) { entry in
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: iconForAction(entry.action))
                                    .font(.system(size: 13))
                                    .foregroundStyle(colorForAction(entry.action))
                                    .frame(width: 28, height: 28)
                                    .background(colorForAction(entry.action).opacity(0.1))
                                    .clipShape(Circle())

                                VStack(alignment: .leading, spacing: 3) {
                                    HStack {
                                        Text(entry.action)
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundStyle(CrewTheme.text)
                                        Text("by \(entry.actor)")
                                            .font(.system(size: 12))
                                            .foregroundStyle(CrewTheme.muted)
                                        Spacer()
                                        Text(entry.timestamp)
                                            .font(.system(size: 11))
                                            .foregroundStyle(CrewTheme.muted)
                                    }
                                    if let detail = entry.detail, !detail.isEmpty {
                                        Text(detail)
                                            .font(.system(size: 12))
                                            .foregroundStyle(CrewTheme.text.opacity(0.8))
                                            .lineLimit(2)
                                    }
                                }
                            }
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .background(CrewTheme.surface)
                        }
                    }
                    .padding(.top, 8)
                }
            }
        }
        .background(CrewTheme.bg)
        .task { await loadEntries() }
    }

    private func loadEntries() async {
        do {
            let fetched: [AuditEntry] = try await appState.client.get(APIEndpoints.audit)
            await MainActor.run {
                entries = fetched
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    private func iconForAction(_ action: String) -> String {
        let lower = action.lowercased()
        if lower.contains("creat") || lower.contains("hire") { return "plus.circle" }
        if lower.contains("delet") || lower.contains("terminat") { return "trash" }
        if lower.contains("message") || lower.contains("chat") { return "bubble.left" }
        if lower.contains("lock") { return "lock" }
        if lower.contains("trust") { return "shield" }
        return "doc.text"
    }

    private func colorForAction(_ action: String) -> Color {
        let lower = action.lowercased()
        if lower.contains("delet") || lower.contains("terminat") { return CrewTheme.highlight }
        if lower.contains("creat") || lower.contains("hire") { return CrewTheme.green }
        return CrewTheme.accent
    }
}
