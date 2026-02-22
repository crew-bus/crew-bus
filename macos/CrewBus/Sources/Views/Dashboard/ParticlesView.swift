import SwiftUI

struct ParticlesView: View {
    private let particles = (0..<40).map { _ in ParticleConfig() }

    var body: some View {
        TimelineView(.animation) { timeline in
            let now = timeline.date.timeIntervalSinceReferenceDate
            GeometryReader { geo in
                Canvas { context, size in
                    for p in particles {
                        let elapsed = now - p.birthTime
                        let phase = fmod(elapsed / p.duration, 1.0)

                        let swayX = sin(phase * .pi * 2) * p.drift
                        let x = p.xFraction * size.width + swayX
                        let y = size.height * (1.0 - CGFloat(phase))

                        let opacity = particleOpacity(phase: phase)
                        guard opacity > 0.01 else { continue }

                        let rect = CGRect(
                            x: x - p.dotSize / 2,
                            y: y - p.dotSize / 2,
                            width: p.dotSize,
                            height: p.dotSize
                        )

                        context.opacity = opacity
                        context.fill(
                            Circle().path(in: rect),
                            with: .color(p.color)
                        )

                        // Soft glow
                        let glowRect = rect.insetBy(dx: -p.dotSize, dy: -p.dotSize)
                        context.opacity = opacity * 0.3
                        context.fill(
                            Circle().path(in: glowRect),
                            with: .color(p.color)
                        )
                    }
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func particleOpacity(phase: Double) -> Double {
        if phase < 0.05 { return (phase / 0.05) * 0.7 }
        if phase > 0.95 { return ((1.0 - phase) / 0.05) * 0.4 }
        // Brightest near bottom, gently dims toward top
        return 0.3 + 0.4 * (1.0 - phase)
    }
}

// MARK: - Particle Config

private struct ParticleConfig {
    let xFraction: CGFloat = .random(in: 0...1)
    let drift: CGFloat = .random(in: 15...40)
    let dotSize: CGFloat = [2, 2, 2, 3, 3, 4].randomElement()!
    let duration: Double = .random(in: 30...50)
    let birthTime: Double = Date.timeIntervalSinceReferenceDate - .random(in: 0...20)
    let colorIndex: Int = .random(in: 0..<8)

    static let colors: [Color] = [
        .white.opacity(0.35),
        .white.opacity(0.25),
        Color(hex: "#4dd0b8").opacity(0.30),
        Color(hex: "#b388ff").opacity(0.30),
        Color(hex: "#64b5f6").opacity(0.30),
        Color(hex: "#e94560").opacity(0.25),
        Color(hex: "#ffab57").opacity(0.25),
        Color(hex: "#66d97a").opacity(0.25),
    ]

    var color: Color { Self.colors[colorIndex] }
}
