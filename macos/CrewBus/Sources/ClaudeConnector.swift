import Foundation
import AppKit

@Observable
final class ClaudeConnector {

    enum ConnectionState: Equatable {
        case checking
        case notInstalled
        case disconnected
        case connecting
        case connected(needsRestart: Bool)
        case error(String)
    }

    var state: ConnectionState = .checking
    var crewbusRunning = false
    var claudeInstalled = false
    var mcpAvailable = false
    var errorMessage: String?

    // MARK: - Public

    func checkStatus() async {
        await MainActor.run { state = .checking }

        let result = await runScript(["status"])
        guard let result else {
            await MainActor.run { state = .disconnected }
            return
        }
        await MainActor.run {
            crewbusRunning = result["crewbus_running"] as? Bool ?? false
            claudeInstalled = result["claude_installed"] as? Bool ?? false
            mcpAvailable = result["mcp_available"] as? Bool ?? false
            let connected = result["already_connected"] as? Bool ?? false

            if !claudeInstalled {
                state = .notInstalled
            } else if connected {
                state = .connected(needsRestart: false)
            } else {
                state = .disconnected
            }
            errorMessage = nil
        }
    }

    func connect() async {
        await MainActor.run {
            state = .connecting
            errorMessage = nil
        }

        let mcpPath = resolveMCPPath()
        var args = ["connect"]
        if !mcpPath.isEmpty {
            args += ["--mcp-path", mcpPath]
        }

        let result = await runScript(args)
        guard let result else {
            await MainActor.run {
                state = .error("Something went wrong. Please try again.")
                errorMessage = "Something went wrong. Please try again."
            }
            return
        }
        let success = result["success"] as? Bool ?? false
        let message = result["message"] as? String ?? ""
        let needsRestart = result["needs_restart"] as? Bool ?? false

        await MainActor.run {
            if success {
                state = .connected(needsRestart: needsRestart)
                errorMessage = nil
            } else {
                state = .error(message)
                errorMessage = message
            }
        }
    }

    func disconnect() async {
        await MainActor.run {
            state = .connecting
            errorMessage = nil
        }

        let result = await runScript(["disconnect"])
        guard let result else {
            await MainActor.run {
                state = .error("Something went wrong. Please try again.")
                errorMessage = "Something went wrong. Please try again."
            }
            return
        }
        let success = result["success"] as? Bool ?? false
        let message = result["message"] as? String ?? ""

        await MainActor.run {
            if success {
                state = .disconnected
                errorMessage = nil
            } else {
                state = .error(message)
                errorMessage = message
            }
        }
    }

    func openClaude() {
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.anthropic.claudefordesktop") {
            NSWorkspace.shared.openApplication(at: url, configuration: .init())
        }
    }

    // MARK: - Private

    private func resolveScriptPath() -> String {
        if let bundled = Bundle.main.url(forResource: "connect_claude", withExtension: "py") {
            return bundled.path
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/crew-bus/scripts/connect_claude.py"
    }

    private func resolveMCPPath() -> String {
        if let bundled = Bundle.main.url(forResource: "crew_bus_mcp", withExtension: "py") {
            return bundled.path
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let devPath = "\(home)/crew-bus/crew_bus_mcp.py"
        if FileManager.default.fileExists(atPath: devPath) {
            return devPath
        }
        return ""
    }

    private func runScript(_ args: [String]) async -> [String: Any]? {
        let scriptPath = resolveScriptPath()
        return await withCheckedContinuation { continuation in
            DispatchQueue.global().async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
                process.arguments = [scriptPath] + args

                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = FileHandle.nullDevice

                do {
                    try process.run()
                    process.waitUntilExit()

                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    if process.terminationStatus == 0,
                       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        continuation.resume(returning: json)
                    } else {
                        continuation.resume(returning: nil)
                    }
                } catch {
                    continuation.resume(returning: nil)
                }
            }
        }
    }
}
