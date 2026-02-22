import SwiftUI
import CrewBusKit

struct SocialDraftsView: View {
    @Environment(AppState.self) private var appState
    @State private var drafts: [Draft] = []
    @State private var isLoading = true

    struct Draft: Decodable, Identifiable {
        let id: Int
        let platform: String
        let content: String
        let status: String
        let createdAt: String
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

                Image(systemName: "pencil.and.outline")
                    .foregroundStyle(CrewTheme.accent)
                Text("Social Media Drafts")
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
            } else if drafts.isEmpty {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "pencil.and.outline")
                        .font(.system(size: 40))
                        .foregroundStyle(CrewTheme.muted)
                    Text("No drafts yet")
                        .font(.system(size: 15))
                        .foregroundStyle(CrewTheme.muted)
                    Text("Ask your crew to draft social posts and they'll appear here.")
                        .font(.system(size: 13))
                        .foregroundStyle(CrewTheme.muted.opacity(0.7))
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, 40)
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(drafts) { draft in
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(platformIcon(draft.platform))
                                    Text(draft.platform.capitalized)
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(CrewTheme.text)
                                    Spacer()
                                    Text(draft.status)
                                        .font(.system(size: 11, weight: .medium))
                                        .foregroundStyle(draft.status == "draft" ? CrewTheme.orange : CrewTheme.green)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 2)
                                        .background(
                                            (draft.status == "draft" ? CrewTheme.orange : CrewTheme.green).opacity(0.15)
                                        )
                                        .clipShape(Capsule())
                                }

                                Text(draft.content)
                                    .font(.system(size: 13))
                                    .foregroundStyle(CrewTheme.text.opacity(0.9))
                                    .lineLimit(5)

                                Text(draft.createdAt)
                                    .font(.system(size: 11))
                                    .foregroundStyle(CrewTheme.muted)
                            }
                            .padding(16)
                            .background(CrewTheme.surface)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(CrewTheme.border, lineWidth: 1))
                        }
                    }
                    .padding(20)
                }
            }
        }
        .background(CrewTheme.bg)
        .task { await loadDrafts() }
    }

    private func loadDrafts() async {
        do {
            let fetched: [Draft] = try await appState.client.get(APIEndpoints.socialDrafts)
            await MainActor.run {
                drafts = fetched
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    private func platformIcon(_ platform: String) -> String {
        switch platform.lowercased() {
        case "twitter", "x": return "𝕏"
        case "instagram": return "📸"
        case "linkedin": return "💼"
        case "facebook": return "📘"
        default: return "📝"
        }
    }
}
