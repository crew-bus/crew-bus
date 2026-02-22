import Foundation

@Observable
final class ServerManager {
    private(set) var isReady = false
    private(set) var error: String?
    private var serverProcess: Process?

    func start() {
        startProcess()
        pollUntilReady()
    }

    func stop() {
        if let process = serverProcess, process.isRunning {
            process.terminate()
            print("Crew Bus server stopped")
        }
        serverProcess = nil
    }

    private func startProcess() {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let crewBusDir = homeDir.appendingPathComponent("crew-bus")
        let dashboardPath = crewBusDir.appendingPathComponent("dashboard.py")
        let venvPython = crewBusDir.appendingPathComponent(".venv/bin/python")

        guard FileManager.default.fileExists(atPath: dashboardPath.path) else {
            error = "Crew Bus not found at \(crewBusDir.path)"
            return
        }

        let pythonPath: String
        if FileManager.default.fileExists(atPath: venvPython.path) {
            pythonPath = venvPython.path
        } else {
            pythonPath = "/usr/bin/env"
        }

        let process = Process()
        process.currentDirectoryURL = crewBusDir

        if pythonPath == "/usr/bin/env" {
            process.executableURL = URL(fileURLWithPath: pythonPath)
            process.arguments = ["python3", "dashboard.py", "--no-browser"]
        } else {
            process.executableURL = URL(fileURLWithPath: pythonPath)
            process.arguments = ["dashboard.py", "--no-browser"]
        }

        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
        process.environment = env

        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            serverProcess = process
            print("Crew Bus server started (PID: \(process.processIdentifier))")
        } catch {
            self.error = "Failed to start server: \(error.localizedDescription)"
        }
    }

    private func pollUntilReady() {
        guard error == nil else { return }

        Task {
            for attempt in 1...20 {
                let ready = await checkHealth()
                if ready {
                    await MainActor.run { self.isReady = true }
                    print("Server ready after \(attempt) attempt(s)")
                    return
                }
                try? await Task.sleep(for: .seconds(1))
            }
            await MainActor.run {
                self.error = "Server did not respond after 20 seconds"
            }
        }
    }

    private func checkHealth() async -> Bool {
        guard let url = URL(string: "http://127.0.0.1:8420/api/health") else { return false }
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
