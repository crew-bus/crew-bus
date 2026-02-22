import Foundation
import Sparkle

@Observable
final class UpdateManager: NSObject {
    static let shared = UpdateManager()

    // MARK: - State

    var updateAvailable = false
    var latestVersion: String?
    var isDismissedForSession = false

    var autoUpdatesEnabled: Bool {
        get { UserDefaults.standard.object(forKey: Keys.autoUpdates) as? Bool ?? true }
        set {
            UserDefaults.standard.set(newValue, forKey: Keys.autoUpdates)
            controller?.updater.automaticallyChecksForUpdates = newValue
        }
    }

    var updateChannel: String {
        get { UserDefaults.standard.string(forKey: Keys.channel) ?? "stable" }
        set { UserDefaults.standard.set(newValue, forKey: Keys.channel) }
    }

    // MARK: - Early Launch

    var isEarlyLaunchMode: Bool { daysSinceInstall < 14 }

    var daysSinceInstall: Int {
        guard let firstLaunch = UserDefaults.standard.object(forKey: Keys.firstLaunch) as? Date else {
            return 0
        }
        return Calendar.current.dateComponents([.day], from: firstLaunch, to: Date()).day ?? 0
    }

    var daysLeftInEarlyMode: Int { max(0, 14 - daysSinceInstall) }

    var checkInterval: TimeInterval {
        daysSinceInstall < 14 ? 2 * 3600 : 6 * 3600
    }

    // MARK: - Private

    private var controller: SPUStandardUpdaterController?

    private enum Keys {
        static let firstLaunch = "crewbus_first_launch_date"
        static let autoUpdates = "crewbus_auto_updates_enabled"
        static let channel = "crewbus_update_channel"
    }

    // MARK: - Init

    private override init() {
        super.init()

        if UserDefaults.standard.object(forKey: Keys.firstLaunch) == nil {
            UserDefaults.standard.set(Date(), forKey: Keys.firstLaunch)
        }

        controller = SPUStandardUpdaterController(
            startingUpdater: false,
            updaterDelegate: self,
            userDriverDelegate: self
        )

        if let updater = controller?.updater {
            updater.automaticallyChecksForUpdates = autoUpdatesEnabled
            updater.updateCheckInterval = checkInterval
        }

        if isEarlyLaunchMode {
            print("[UpdateManager] Mode: early-launch (day \(daysSinceInstall + 1)/14, every 2h)")
        } else {
            print("[UpdateManager] Mode: steady (every 6h)")
        }
    }

    // MARK: - Public Methods

    func startWithDelay() {
        Task {
            try? await Task.sleep(for: .seconds(10))
            await MainActor.run {
                do {
                    try controller?.startUpdater()
                    controller?.updater.checkForUpdatesInBackground()
                } catch {
                    print("[UpdateManager] Failed to start updater: \(error)")
                }
            }
        }
    }

    func checkNow() {
        controller?.checkForUpdates(nil)
    }

    func dismissForSession() {
        isDismissedForSession = true
    }
}

// MARK: - SPUUpdaterDelegate

extension UpdateManager: SPUUpdaterDelegate {
    func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
        Task { @MainActor in
            updateAvailable = true
            latestVersion = item.displayVersionString
        }
    }

    func updaterDidNotFindUpdate(_ updater: SPUUpdater, error: any Error) {
        Task { @MainActor in
            updateAvailable = false
        }
    }

    func feedURLString(for updater: SPUUpdater) -> String? {
        let base = "https://crew-bus.dev/appcast.xml"
        if updateChannel == "latest" {
            return base + "?channel=latest"
        }
        return base
    }
}

// MARK: - SPUStandardUserDriverDelegate

extension UpdateManager: SPUStandardUserDriverDelegate {}
