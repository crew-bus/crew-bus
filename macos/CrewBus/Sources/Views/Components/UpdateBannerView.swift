import SwiftUI

struct UpdateBannerView: View {
    private var manager = UpdateManager.shared

    private var shouldShow: Bool {
        manager.updateAvailable && !manager.isDismissedForSession
    }

    var body: some View {
        if shouldShow {
            HStack(spacing: 12) {
                // Left accent bar is done via overlay

                Image(systemName: "arrow.down.circle")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(CrewTheme.accent)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("Update Available")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(CrewTheme.text)

                        if let version = manager.latestVersion {
                            Text("v\(version)")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(CrewTheme.muted)
                        }

                        if manager.isEarlyLaunchMode {
                            Text("Early Access")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(CrewTheme.accent)
                                .clipShape(Capsule())
                        }
                    }
                }

                Spacer()

                Button {
                    manager.checkNow()
                } label: {
                    Text("Update Now")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)

                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        manager.dismissForSession()
                    }
                } label: {
                    Text("Later")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(CrewTheme.surface)
            .overlay(alignment: .leading) {
                Rectangle()
                    .fill(CrewTheme.accent)
                    .frame(width: 3)
            }
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }
            .transition(.move(edge: .top).combined(with: .opacity))
        }
    }
}
