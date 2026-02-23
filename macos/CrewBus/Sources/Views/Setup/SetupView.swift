import SwiftUI
import CrewBusKit

struct SetupView: View {
    @Environment(AppState.self) private var appState
    @State private var step: SetupStep = .welcome
    @State private var selectedModel = "ollama"
    @State private var apiKey = ""
    @State private var pin = ""
    @State private var isSubmitting = false
    @State private var errorMessage = ""

    private enum SetupStep {
        case welcome, modelPicker, apiKeyEntry, pinEntry
    }

    /// Detect Grok/xAI key: starts with gsk_, or contains xai/grok (case-insensitive)
    private var isGrokKey: Bool {
        let lower = apiKey.lowercased()
        return apiKey.hasPrefix("gsk_")
            || lower.contains("xai")
            || lower.contains("grok")
            || selectedModel == "xai"
    }

    private let models: [(id: String, name: String, needsKey: Bool)] = [
        ("ollama", "Ollama (Local / Free)", false),
        ("kimi", "Kimi", true),
        ("claude", "Claude (Anthropic)", true),
        ("openai", "OpenAI", true),
        ("groq", "Groq", true),
        ("gemini", "Gemini (Google)", true),
        ("xai", "xAI Grok", true),
    ]

    private var selectedModelNeedsKey: Bool {
        models.first { $0.id == selectedModel }?.needsKey ?? false
    }

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 32) {
                switch step {
                case .welcome:
                    welcomeStep
                case .modelPicker:
                    modelStep
                case .apiKeyEntry:
                    apiKeyStep
                case .pinEntry:
                    pinStep
                }
            }
            .frame(maxWidth: 480)

            Spacer()

            // Progress dots
            HStack(spacing: 8) {
                ForEach(0..<4) { i in
                    Circle()
                        .fill(stepIndex >= i ? CrewTheme.accent : CrewTheme.border)
                        .frame(width: 8, height: 8)
                }
            }
            .padding(.bottom, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(CrewTheme.bg)
    }

    private var stepIndex: Int {
        switch step {
        case .welcome: return 0
        case .modelPicker: return 1
        case .apiKeyEntry: return 2
        case .pinEntry: return selectedModelNeedsKey ? 3 : 2
        }
    }

    // MARK: - Welcome

    private var welcomeStep: some View {
        VStack(spacing: 20) {
            Text("👽")
                .font(.system(size: 64))

            Text("Welcome to Crew Bus")
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Your personal AI crew — private, local, yours.\nLet's get you set up in under a minute.")
                .font(.system(size: 15))
                .foregroundStyle(CrewTheme.muted)
                .multilineTextAlignment(.center)
                .lineSpacing(4)

            Button {
                withAnimation { step = .modelPicker }
            } label: {
                Text("Get Started")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 12)
                    .background(CrewTheme.accent)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
        }
    }

    // MARK: - Model Picker

    private var modelStep: some View {
        VStack(spacing: 20) {
            Text("Choose Your AI Model")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Pick the brain behind your crew. You can change this later.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)

            VStack(spacing: 8) {
                ForEach(models, id: \.id) { model in
                    Button {
                        selectedModel = model.id
                    } label: {
                        HStack {
                            Image(systemName: selectedModel == model.id ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(selectedModel == model.id ? CrewTheme.accent : CrewTheme.muted)
                                .font(.system(size: 18))
                            Text(model.name)
                                .font(.system(size: 14))
                                .foregroundStyle(CrewTheme.text)
                            Spacer()
                            if !model.needsKey {
                                Text("FREE")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(CrewTheme.green)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(CrewTheme.green.opacity(0.15))
                                    .clipShape(Capsule())
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(selectedModel == model.id ? CrewTheme.accent.opacity(0.1) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(selectedModel == model.id ? CrewTheme.accent : CrewTheme.border, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }

            HStack(spacing: 12) {
                Button {
                    withAnimation { step = .welcome }
                } label: {
                    Text("Back")
                        .font(.system(size: 14))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)

                Button {
                    withAnimation {
                        step = selectedModelNeedsKey ? .apiKeyEntry : .pinEntry
                    }
                } label: {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 10)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - API Key

    private var apiKeyStep: some View {
        VStack(spacing: 20) {
            Text("Enter Your API Key")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Your key stays 100% local — never sent anywhere except the provider.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)
                .multilineTextAlignment(.center)

            SecureField("API Key", text: $apiKey)
                .textFieldStyle(.plain)
                .font(.system(size: 14, design: .monospaced))
                .padding(12)
                .background(CrewTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))

            // Grok mode detection indicator
            if isGrokKey {
                HStack(spacing: 6) {
                    Image(systemName: "bolt.fill")
                        .foregroundStyle(CrewTheme.orange)
                        .font(.system(size: 12))
                    Text("Grok Mode Unlocked")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(CrewTheme.orange)
                    Text("— direct, truth-seeking, zero coddling")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(CrewTheme.orange.opacity(0.1))
                .clipShape(Capsule())
            }

            HStack(spacing: 12) {
                Button {
                    withAnimation { step = .modelPicker }
                } label: {
                    Text("Back")
                        .font(.system(size: 14))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)

                Button {
                    withAnimation { step = .pinEntry }
                } label: {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 10)
                        .background(apiKey.isEmpty ? CrewTheme.muted : CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                .disabled(apiKey.isEmpty)
            }
        }
    }

    // MARK: - PIN

    private var pinStep: some View {
        VStack(spacing: 20) {
            Text("Set a Dashboard PIN")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            Text("Optional — lock your dashboard from prying eyes.")
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)

            SecureField("4-digit PIN (optional)", text: $pin)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .padding(12)
                .background(CrewTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
                .frame(maxWidth: 200)

            if !errorMessage.isEmpty {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(CrewTheme.highlight)
            }

            HStack(spacing: 12) {
                Button {
                    withAnimation {
                        step = selectedModelNeedsKey ? .apiKeyEntry : .modelPicker
                    }
                } label: {
                    Text("Back")
                        .font(.system(size: 14))
                        .foregroundStyle(CrewTheme.muted)
                }
                .buttonStyle(.plain)

                Button {
                    finishSetup()
                } label: {
                    if isSubmitting {
                        ProgressView()
                            .controlSize(.small)
                            .frame(width: 100)
                    } else {
                        Text("Launch My Crew")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 32)
                            .padding(.vertical, 10)
                            .background(CrewTheme.green)
                            .clipShape(Capsule())
                    }
                }
                .buttonStyle(.plain)
                .disabled(isSubmitting)
            }
        }
    }

    // MARK: - Submit

    private func finishSetup() {
        isSubmitting = true
        errorMessage = ""
        Task {
            do {
                try await appState.completeSetup(
                    model: selectedModel, apiKey: apiKey,
                    pin: pin, grokMode: isGrokKey
                )
                await appState.loadInitialData()
            } catch {
                await MainActor.run {
                    errorMessage = "Setup failed — check your connection."
                    isSubmitting = false
                }
            }
        }
    }
}
