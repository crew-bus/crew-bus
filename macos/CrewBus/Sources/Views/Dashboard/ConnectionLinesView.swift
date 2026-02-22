import SwiftUI

struct ConnectionLinesView: View {
    let points: [CGPoint]

    @State private var breathe = false

    var body: some View {
        Canvas { ctx, _ in
            guard points.count >= 2 else { return }
            // Draw lines between all point pairs
            for i in 0..<points.count {
                for j in (i + 1)..<points.count {
                    var path = Path()
                    path.move(to: points[i])
                    path.addLine(to: points[j])
                    ctx.stroke(
                        path,
                        with: .color(Color.white.opacity(breathe ? 0.18 : 0.06)),
                        style: StrokeStyle(lineWidth: 1, dash: [6, 8])
                    )
                }
            }
        }
        .allowsHitTesting(false)
        .onAppear { breathe = true }
        .animation(
            .easeInOut(duration: 3.0).repeatForever(autoreverses: true),
            value: breathe
        )
    }
}
