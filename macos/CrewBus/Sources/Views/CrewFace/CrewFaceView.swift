import SwiftUI
import CrewBusKit

struct CrewFaceView: View {
    let agentId: Int
    let size: CGFloat
    var fallbackSymbol: String = "cpu"
    var fallbackColor: Color = .secondary

    @Environment(AppState.self) private var appState
    @State private var faceState: FaceState?
    @State private var bounceScale: CGFloat = 1.0
    @State private var glowOpacity: Double = 0.0
    @State private var pulseOpacity: Double = 1.0
    @State private var pollingTask: Task<Void, Never>?

    private static let emotionMap: [String: String] = [
        "neutral": "\u{1F610}",    // 😐
        "thinking": "\u{1F914}",   // 🤔
        "happy": "\u{1F60A}",      // 😊
        "excited": "\u{1F929}",    // 🤩
        "proud": "\u{1F60E}",      // 😎
        "confused": "\u{1F615}",   // 😕
        "tired": "\u{1F634}",      // 😴
        "sad": "\u{1F622}",        // 😢
        "angry": "\u{1F620}",      // 😠
    ]

    var body: some View {
        Group {
            if let face = faceState, let emotion = face.emotion, let emoji = Self.emotionMap[emotion] {
                Text(emoji)
                    .font(.system(size: size))
                    .scaleEffect(bounceScale)
                    .shadow(color: CrewTheme.accent.opacity(glowOpacity), radius: 8)
                    .opacity(pulseOpacity)
            } else {
                Image(systemName: fallbackSymbol)
                    .font(.system(size: size * 0.8))
                    .foregroundStyle(fallbackColor)
            }
        }
        .onAppear { startPolling() }
        .onDisappear { stopPolling() }
        .onChange(of: faceState?.effect) { _, newEffect in
            applyEffect(newEffect)
        }
    }

    private func startPolling() {
        pollingTask = Task {
            while !Task.isCancelled {
                do {
                    let state: FaceState = try await appState.client.get(
                        APIEndpoints.agentFace(agentId)
                    )
                    await MainActor.run { faceState = state }
                } catch {
                    // Silent
                }
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    private func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    private func applyEffect(_ effect: String?) {
        guard let effect else { return }
        switch effect {
        case "bounce":
            withAnimation(.spring(response: 0.3, dampingFraction: 0.4)) {
                bounceScale = 1.3
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                    bounceScale = 1.0
                }
            }
        case "glow":
            withAnimation(.easeInOut(duration: 0.5)) {
                glowOpacity = 0.8
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                withAnimation(.easeInOut(duration: 0.5)) {
                    glowOpacity = 0.0
                }
            }
        case "pulse":
            withAnimation(.easeInOut(duration: 0.4).repeatCount(3, autoreverses: true)) {
                pulseOpacity = 0.5
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) {
                pulseOpacity = 1.0
            }
        default:
            break
        }
    }
}
