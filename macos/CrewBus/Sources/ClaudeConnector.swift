import Foundation

@Observable
final class ClaudeConnector {

    enum ConnectionState: Equatable {
        case unknown, disconnected, connecting, connected
    }

    var state: ConnectionState = .unknown
    var serverOk = false
    var claudeInstalled = false
    var mcpAvailable = false
    var errorMessage: String?

    // MARK: - Public

    func checkStatus() async {
        let result = await runScript(["--status"])
        guard let result else {
            await MainActor.run { state = .disconnected }
            return
        }
        await MainActor.run {
            serverOk = result["server_ok"] as? Bool ?? false
            claudeInstalled = result["claude_installed"] as? Bool ?? false
            mcpAvailable = result["mcp_available"] as? Bool ?? false
            let linked = result["mcp_linked"] as? Bool ?? false
            state = linked ? .connected : .disconnected
            errorMessage = nil
        }
    }

    func connect() async {
        await MainActor.run {
            state = .connecting
            errorMessage = nil
        }

        let mcpPath = resolveMCPPath()
        let result = await runScript(["--connect", "--mcp-path", mcpPath])
        guard let result else {
            await MainActor.run {
                state = .disconnected
                errorMessage = "Failed to run connect script."
            }
            return
        }
        let ok = result["ok"] as? Bool ?? false
        let message = result["message"] as? String
        await MainActor.run {
            if ok {
                state = .connected
                errorMessage = nil
            } else {
                state = .disconnected
                errorMessage = message ?? "Connection failed."
            }
        }
    }

    func disconnect() async {
        await MainActor.run {
            state = .connecting
            errorMessage = nil
        }

        let result = await runScript(["--disconnect"])
        guard let result else {
            await MainActor.run {
                state = .connected
                errorMessage = "Failed to run disconnect script."
            }
            return
        }
        let ok = result["ok"] as? Bool ?? false
        let message = result["message"] as? String
        await MainActor.run {
            if ok {
                state = .disconnected
                errorMessage = nil
            } else {
                state = .connected
                errorMessage = message ?? "Disconnect failed."
            }
        }
    }

    // MARK: - Private

    private func resolveScriptPath() -> String {
        // Bundled inside .app
        if let bundled = Bundle.main.url(forResource: "connect_claude", withExtension: "py") {
            return bundled.path
        }
        // Dev fallback
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/crew-bus/scripts/connect_claude.py"
    }

    private func resolveMCPPath() -> String {
        // Bundled inside .app
        if let bundled = Bundle.main.url(forResource: "crew_bus_mcp", withExtension: "py") {
            return bundled.path
        }
        // Dev fallback
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/crew-bus/crew_bus_mcp.py"
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
