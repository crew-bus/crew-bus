import SwiftUI
import CrewBusKit

struct AdjustSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    @State private var trustScore: Double
    @State private var burnoutScore: Double

    init(trustScore: Int, burnoutScore: Int) {
        _trustScore = State(initialValue: Double(trustScore))
        _burnoutScore = State(initialValue: Double(burnoutScore))
    }

    var body: some View {
        VStack(alignment: .center, spacing: 24) {
            Text("Adjust Settings")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(CrewTheme.text)

            // Trust Score
            VStack(alignment: .leading, spacing: 12) {
                Text("TRUST SCORE")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(CrewTheme.muted)

                Text("\(Int(trustScore))")
                    .font(.system(size: 48, weight: .bold))
                    .foregroundStyle(CrewTheme.accent)
                    .frame(maxWidth: .infinity)

                Slider(value: $trustScore, in: 1...10, step: 1)
                    .tint(CrewTheme.accent)
            }

            // Burnout Score
            VStack(alignment: .leading, spacing: 12) {
                Text("BURNOUT SCORE")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(CrewTheme.muted)

                Slider(value: $burnoutScore, in: 1...10, step: 1)
                    .tint(CrewTheme.accent)
            }

            Spacer()

            Button {
                Task {
                    await appState.updateTrustScore(Int(trustScore))
                    await appState.updateBurnoutScore(Int(burnoutScore))
                    dismiss()
                }
            } label: {
                Text("Done")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(CrewTheme.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .buttonStyle(.plain)
        }
        .padding(28)
        .frame(width: 380, height: 380)
        .background(CrewTheme.surface)
    }
}
