import SwiftUI
import WebKit

struct DashboardView: View {
    @State private var host = ""
    @State private var isConnected = false
    @State private var showSettings = false

    private var dashboardURL: URL? {
        guard !host.isEmpty else { return nil }
        let h = host.contains("://") ? host : "http://\(host)"
        return URL(string: h.hasSuffix(":8420") || h.contains(":") && h.last != ":" ? h : "\(h):8420")
    }

    var body: some View {
        NavigationStack {
            if isConnected, let url = dashboardURL {
                WebView(url: url)
                    .ignoresSafeArea(edges: .bottom)
                    .navigationTitle("Crew Bus")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button(action: { showSettings = true }) {
                                Image(systemName: "gear")
                            }
                        }
                    }
                    .sheet(isPresented: $showSettings) {
                        SettingsSheet(host: $host, isConnected: $isConnected)
                    }
            } else {
                ConnectView(host: $host, isConnected: $isConnected)
            }
        }
    }
}

struct ConnectView: View {
    @Binding var host: String
    @Binding var isConnected: Bool
    @AppStorage("lastHost") private var lastHost = ""

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 12) {
                Text("Crew Bus")
                    .font(.system(size: 42, weight: .bold))
                Text("Your personal AI crew")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 16) {
                TextField("192.168.1.x or Mac's IP", text: $host)
                    .textFieldStyle(.roundedBorder)
                    .keyboardType(.URL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .padding(.horizontal, 40)
                    .onAppear {
                        if host.isEmpty { host = lastHost }
                    }

                Button(action: connect) {
                    Text("Connect")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(host.isEmpty ? Color.gray : Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .disabled(host.isEmpty)
                .padding(.horizontal, 40)
            }

            Text("Make sure Crew Bus is running on your Mac\nand your iPhone is on the same Wi-Fi network.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Spacer()
            Spacer()
        }
    }

    private func connect() {
        lastHost = host
        isConnected = true
    }
}

struct SettingsSheet: View {
    @Binding var host: String
    @Binding var isConnected: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    TextField("Host", text: $host)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }
                Section {
                    Button("Disconnect", role: .destructive) {
                        isConnected = false
                        dismiss()
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
