import SwiftUI
import CrewBusKit

// MARK: - Bubble Shape (with tail)

struct BubbleShape: Shape {
    enum Side { case left, right }
    let side: Side
    let cornerRadius: CGFloat

    init(side: Side, cornerRadius: CGFloat = 16) {
        self.side = side
        self.cornerRadius = cornerRadius
    }

    func path(in rect: CGRect) -> Path {
        let r = cornerRadius
        let (minX, minY, maxX, maxY) = (rect.minX, rect.minY, rect.maxX, rect.maxY)
        var path = Path()

        if side == .right {
            // All corners rounded except bottom-right (sharp)
            path.move(to: CGPoint(x: minX + r, y: minY))
            path.addLine(to: CGPoint(x: maxX - r, y: minY))
            path.addArc(center: CGPoint(x: maxX - r, y: minY + r), radius: r,
                        startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
            path.addLine(to: CGPoint(x: maxX, y: maxY)) // sharp corner
            path.addLine(to: CGPoint(x: minX + r, y: maxY))
            path.addArc(center: CGPoint(x: minX + r, y: maxY - r), radius: r,
                        startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
            path.addLine(to: CGPoint(x: minX, y: minY + r))
            path.addArc(center: CGPoint(x: minX + r, y: minY + r), radius: r,
                        startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        } else {
            // All corners rounded except bottom-left (sharp)
            path.move(to: CGPoint(x: minX + r, y: minY))
            path.addLine(to: CGPoint(x: maxX - r, y: minY))
            path.addArc(center: CGPoint(x: maxX - r, y: minY + r), radius: r,
                        startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
            path.addLine(to: CGPoint(x: maxX, y: maxY - r))
            path.addArc(center: CGPoint(x: maxX - r, y: maxY - r), radius: r,
                        startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
            path.addLine(to: CGPoint(x: minX, y: maxY)) // sharp corner
            path.addLine(to: CGPoint(x: minX, y: minY + r))
            path.addArc(center: CGPoint(x: minX + r, y: minY + r), radius: r,
                        startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        }

        path.closeSubpath()
        return path
    }
}

// MARK: - Typing Indicator

struct TypingIndicatorView: View {
    @State private var phase = false

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(CrewTheme.muted)
                    .frame(width: 8, height: 8)
                    .scaleEffect(phase ? 1.3 : 0.7)
                    .animation(
                        .easeInOut(duration: 0.5)
                            .repeatForever(autoreverses: true)
                            .delay(Double(i) * 0.15),
                        value: phase
                    )
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(CrewTheme.surface.opacity(0.9), in: BubbleShape(side: .left))
        .onAppear { phase = true }
    }
}

// MARK: - Chat Bubble

struct ChatBubbleView: View {
    let message: ChatMessage
    let agentName: String

    var body: some View {
        HStack(alignment: .bottom) {
            if message.isFromHuman { Spacer(minLength: 60) }

            VStack(alignment: message.isFromHuman ? .trailing : .leading, spacing: 4) {
                Text(message.text)
                    .font(.system(size: 14))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        message.isFromHuman
                            ? CrewTheme.highlight
                            : CrewTheme.surface.opacity(0.9),
                        in: BubbleShape(side: message.isFromHuman ? .right : .left)
                    )

                Text(relativeTime(message.time))
                    .font(.system(size: 10))
                    .foregroundStyle(CrewTheme.muted)

                if message.isPrivate {
                    Label("Private", systemImage: "lock.fill")
                        .font(.caption2)
                        .foregroundStyle(CrewTheme.muted)
                }
            }

            if !message.isFromHuman { Spacer(minLength: 60) }
        }
        .padding(.horizontal, 16)
    }

    private func relativeTime(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: iso) ?? ISO8601DateFormatter().date(from: iso) else {
            return iso.isEmpty ? "" : "just now"
        }
        let seconds = Int(-date.timeIntervalSinceNow)
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(seconds / 60)m ago" }
        if seconds < 86400 { return "\(seconds / 3600)h ago" }
        return "\(seconds / 86400)d ago"
    }
}
