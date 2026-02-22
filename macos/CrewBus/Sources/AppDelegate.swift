import Cocoa

class AppDelegate: NSObject, NSApplicationDelegate {
    let serverManager = ServerManager()

    func applicationDidFinishLaunching(_ notification: Notification) {
        serverManager.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        serverManager.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}
