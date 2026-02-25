import SwiftUI
import CrewBusKit

struct EnergyScoreSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    @State private var energyScore: Double

    init(energyScore: Int) {
        _energyScore = State(initialValue: Double(energyScore))
    }

    var body: some View {
        VStack(alignment: .center, spacing: 24) {
            Text("Your Energy Score")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(CrewTheme.text)

            Text("How much energy do you have right now? Your crew adjusts its pace to match.")
                .font(.system(size: 13))
                .foregroundStyle(CrewTheme.muted)
                .multilineTextAlignment(.center)

            VStack(alignment: .leading, spacing: 12) {
                Text("\(Int(energyScore))")
                    .font(.system(size: 48, weight: .bold))
                    .foregroundStyle(CrewTheme.orange)
                    .frame(maxWidth: .infinity)

                Slider(value: $energyScore, in: 1...10, step: 1)
                    .tint(CrewTheme.orange)

                HStack {
                    Text("Low energy")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                    Spacer()
                    Text("Full power")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
            }

            Spacer()

            Button {
                Task {
                    await appState.updateEnergyScore(Int(energyScore))
                    dismiss()
                }
            } label: {
                Text("Done")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(CrewTheme.orange)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .buttonStyle(.plain)
        }
        .padding(28)
        .frame(width: 380, height: 420)
        .background(CrewTheme.surface)
    }
}
