import SwiftUI
import WebKit

struct DashboardView: View {
    @State private var host = ""
    @State private var isConnected = false
    @AppStorage("lastHost") private var lastHost = ""

    var body: some View {
        if isConnected {
            let urlString = "http://\(host):8420"
            if let url = URL(string: urlString) {
                WebView(url: url)
                    .ignoresSafeArea()
            }
        } else {
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

                    Button(action: {
                        host = host.trimmingCharacters(in: .whitespaces)
                        lastHost = host
                        isConnected = true
                        print("Connecting to http://\(host):8420")
                    }) {
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
    }
}
