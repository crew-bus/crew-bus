import SwiftUI

struct UpdateSettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var manager = UpdateManager.shared

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
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

                Text("Update Settings")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(height: 54)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            ScrollView {
                VStack(spacing: 16) {
                    // Mode card
                    modeCard

                    // Auto-updates toggle
                    toggleCard

                    // Channel picker
                    channelCard

                    // Check now
                    checkNowCard

                    // Version info
                    versionCard
                }
                .padding(16)
            }
        }
        .background(CrewTheme.bg)
    }

    // MARK: - Mode Card

    @ViewBuilder
    private var modeCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Update Mode")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(CrewTheme.text)

            HStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(CrewTheme.green)
                    .font(.system(size: 18))

                if manager.isEarlyLaunchMode {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text("Early Access")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(CrewTheme.text)
                            Text("\(manager.daysLeftInEarlyMode) days left")
                                .font(.system(size: 12))
                                .foregroundStyle(CrewTheme.muted)
                        }
                        Text("Checking every 2 hours for rapid bug fixes")
                            .font(.system(size: 12))
                            .foregroundStyle(CrewTheme.muted)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Standard")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(CrewTheme.text)
                        Text("Checking every 6 hours")
                            .font(.system(size: 12))
                            .foregroundStyle(CrewTheme.muted)
                    }
                }

                Spacer()
            }
            .padding(12)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(CrewTheme.border, lineWidth: 1))
        }
    }

    // MARK: - Toggle Card

    @ViewBuilder
    private var toggleCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Automatic Updates")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(CrewTheme.text)

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Check for updates automatically")
                        .font(.system(size: 13))
                        .foregroundStyle(CrewTheme.text)
                    Text("Crew Bus will check in the background and notify you")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }

                Spacer()

                Toggle("", isOn: Binding(
                    get: { manager.autoUpdatesEnabled },
                    set: { manager.autoUpdatesEnabled = $0 }
                ))
                .toggleStyle(.switch)
                .tint(CrewTheme.accent)
            }
            .padding(12)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(CrewTheme.border, lineWidth: 1))
        }
    }

    // MARK: - Channel Card

    @ViewBuilder
    private var channelCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Update Channel")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(CrewTheme.text)

            VStack(alignment: .leading, spacing: 10) {
                Picker("Channel", selection: Binding(
                    get: { manager.updateChannel },
                    set: { manager.updateChannel = $0 }
                )) {
                    Text("Stable").tag("stable")
                    Text("Latest").tag("latest")
                }
                .pickerStyle(.segmented)

                Text(manager.updateChannel == "stable"
                     ? "Recommended. Receive tested, stable releases."
                     : "Get the newest features sooner. May contain bugs.")
                    .font(.system(size: 11))
                    .foregroundStyle(CrewTheme.muted)
            }
            .padding(12)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(CrewTheme.border, lineWidth: 1))
        }
    }

    // MARK: - Check Now Card

    @ViewBuilder
    private var checkNowCard: some View {
        Button {
            manager.checkNow()
        } label: {
            HStack {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 14, weight: .medium))
                Text("Check for Updates Now")
                    .font(.system(size: 13, weight: .semibold))
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(CrewTheme.accent)
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Version Card

    @ViewBuilder
    private var versionCard: some View {
        HStack {
            Text("Current Version")
                .font(.system(size: 12))
                .foregroundStyle(CrewTheme.muted)
            Spacer()
            Text("v\(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?")"
                 + " (\(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"))")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(CrewTheme.text)
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(CrewTheme.border, lineWidth: 1))
    }
}
