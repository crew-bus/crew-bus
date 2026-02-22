import SwiftUI
import CrewBusKit

struct PinEntryView: View {
    @Environment(AppState.self) private var appState
    @State private var digits: [String] = Array(repeating: "", count: 6)
    @FocusState private var focusedIndex: Int?
    @State private var errorMessage = ""
    @State private var isVerifying = false

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "lock.fill")
                .font(.system(size: 48))
                .foregroundStyle(CrewTheme.accent)

            Text("Enter Your PIN")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Enter your 6-digit PIN to unlock Crew Bus.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)

            // 6-digit PIN input
            HStack(spacing: 8) {
                ForEach(0..<6, id: \.self) { index in
                    SecureField("", text: digitBinding(index))
                        .font(.system(size: 24, weight: .bold, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .frame(width: 44, height: 52)
                        .background(CrewTheme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(focusedIndex == index ? CrewTheme.accent : CrewTheme.border, lineWidth: focusedIndex == index ? 2 : 1)
                        )
                        .focused($focusedIndex, equals: index)
                        .textFieldStyle(.plain)
                        .onChange(of: digits[index]) { _, newValue in
                            if newValue.count > 1 {
                                digits[index] = String(newValue.suffix(1))
                            }
                            if !newValue.isEmpty && index < 5 {
                                focusedIndex = index + 1
                            }
                            if allDigitsFilled {
                                verifyPin()
                            }
                        }
                }
            }

            if !errorMessage.isEmpty {
                Text(errorMessage)
                    .font(.system(size: 13))
                    .foregroundStyle(CrewTheme.highlight)
            }

            if isVerifying {
                ProgressView()
                    .controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(CrewTheme.bg)
        .onAppear { focusedIndex = 0 }
    }

    private var allDigitsFilled: Bool {
        digits.allSatisfy { !$0.isEmpty }
    }

    private var pinString: String {
        digits.joined()
    }

    private func digitBinding(_ index: Int) -> Binding<String> {
        Binding(
            get: { digits[index] },
            set: { newValue in
                let filtered = newValue.filter(\.isNumber)
                digits[index] = String(filtered.prefix(1))
            }
        )
    }

    private func verifyPin() {
        isVerifying = true
        errorMessage = ""
        let pin = pinString

        struct PinResponse: Decodable {
            let deviceToken: String?
        }

        Task {
            do {
                let response: PinResponse = try await appState.client.post(
                    APIEndpoints.authPin,
                    body: ["pin": pin]
                )
                if let token = response.deviceToken {
                    UserDefaults.standard.set(token, forKey: "crew_bus_device_token")
                    await appState.client.setAuthToken(token)
                }
                await MainActor.run {
                    isVerifying = false
                    appState.isDashboardLocked = false
                }
            } catch {
                await MainActor.run {
                    isVerifying = false
                    errorMessage = "Wrong PIN. Try again."
                    digits = Array(repeating: "", count: 6)
                    focusedIndex = 0
                }
            }
        }
    }
}
