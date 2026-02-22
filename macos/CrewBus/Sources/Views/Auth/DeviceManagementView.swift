import SwiftUI
import CrewBusKit

struct DeviceManagementView: View {
    @Environment(AppState.self) private var appState
    @State private var authMode = "none"
    @State private var devices: [PairedDevice] = []
    @State private var pairingCode = ""
    @State private var showPairingCode = false

    private let authModes = ["none", "pin", "token"]

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

                Text("Security & Devices")
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
                    // Auth mode
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Authentication Mode")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(CrewTheme.text)

                        Picker("", selection: $authMode) {
                            Text("None").tag("none")
                            Text("PIN").tag("pin")
                            Text("Token").tag("token")
                        }
                        .pickerStyle(.segmented)
                        .onChange(of: authMode) { _, newValue in
                            updateAuthMode(newValue)
                        }

                        Text(authModeDescription)
                            .font(.system(size: 11))
                            .foregroundStyle(CrewTheme.muted)
                    }
                    .padding(12)
                    .background(CrewTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

                    // Pairing code
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Device Pairing")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(CrewTheme.text)
                            Spacer()
                            Button {
                                generatePairingCode()
                            } label: {
                                Label("Generate Code", systemImage: "qrcode")
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 4)
                                    .background(CrewTheme.accent)
                                    .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }

                        if showPairingCode {
                            Text(pairingCode)
                                .font(.system(size: 28, weight: .bold, design: .monospaced))
                                .foregroundStyle(CrewTheme.accent)
                                .frame(maxWidth: .infinity)
                                .padding(12)
                                .background(CrewTheme.accent.opacity(0.1))
                                .clipShape(RoundedRectangle(cornerRadius: 8))

                            Text("Share this code with the device you want to pair")
                                .font(.system(size: 11))
                                .foregroundStyle(CrewTheme.muted)
                        }
                    }
                    .padding(12)
                    .background(CrewTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

                    // Paired devices
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Paired Devices")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(CrewTheme.text)

                        if devices.isEmpty {
                            Text("No paired devices")
                                .font(.system(size: 12))
                                .foregroundStyle(CrewTheme.muted)
                                .padding(.vertical, 4)
                        } else {
                            ForEach(devices) { device in
                                HStack {
                                    Image(systemName: "desktopcomputer")
                                        .font(.system(size: 14))
                                        .foregroundStyle(CrewTheme.accent)

                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(device.deviceName ?? "Unknown Device")
                                            .font(.system(size: 12, weight: .medium))
                                            .foregroundStyle(CrewTheme.text)
                                        HStack(spacing: 4) {
                                            if let role = device.role {
                                                Text(role)
                                                    .font(.system(size: 10))
                                                    .foregroundStyle(CrewTheme.muted)
                                            }
                                            if device.active == true {
                                                Circle()
                                                    .fill(CrewTheme.green)
                                                    .frame(width: 6, height: 6)
                                            }
                                        }
                                    }

                                    Spacer()

                                    Button {
                                        revokeDevice(device)
                                    } label: {
                                        Text("Revoke")
                                            .font(.system(size: 11, weight: .medium))
                                            .foregroundStyle(CrewTheme.highlight)
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 3)
                                            .background(CrewTheme.highlight.opacity(0.1))
                                            .clipShape(Capsule())
                                    }
                                    .buttonStyle(.plain)
                                }
                                .padding(8)
                                .background(CrewTheme.bg)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                    .padding(12)
                    .background(CrewTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
                }
                .padding(16)
            }
        }
        .background(CrewTheme.bg)
        .task {
            await fetchData()
        }
    }

    private var authModeDescription: String {
        switch authMode {
        case "pin": return "Requires a 6-digit PIN to access the dashboard"
        case "token": return "Requires a device token for API access"
        default: return "No authentication required (local access only)"
        }
    }

    private func fetchData() async {
        struct AuthModeResponse: Decodable { let mode: String }
        do {
            let response: AuthModeResponse = try await appState.client.get(APIEndpoints.authMode)
            await MainActor.run { authMode = response.mode }
        } catch {}

        do {
            let fetched: [PairedDevice] = try await appState.client.get(APIEndpoints.devices)
            await MainActor.run { devices = fetched }
        } catch {}
    }

    private func updateAuthMode(_ mode: String) {
        Task {
            try? await appState.client.post(
                APIEndpoints.authConfig,
                body: ["mode": mode]
            )
        }
    }

    private func generatePairingCode() {
        struct PairingResponse: Decodable { let code: String }
        Task {
            do {
                let response: PairingResponse = try await appState.client.get(APIEndpoints.authPairingCode)
                await MainActor.run {
                    pairingCode = response.code
                    showPairingCode = true
                }
            } catch {}
        }
    }

    private func revokeDevice(_ device: PairedDevice) {
        Task {
            try? await appState.client.post(
                APIEndpoints.deviceRevoke(device.id),
                body: [:]
            )
            await fetchData()
        }
    }
}
