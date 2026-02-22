import SwiftUI
import CrewBusKit

struct TrustEnergyPillsView: View {
    let stats: CrewStats
    @Binding var showSettings: Bool

    var body: some View {
        HStack(spacing: 12) {
            // Trust score pill
            Button { showSettings = true } label: {
                HStack(spacing: 6) {
                    Text("CREW-BOSS TRUST SCORE")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(CrewTheme.muted)
                    Text("\(stats.trustScore)")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(CrewTheme.text)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .overlay(Capsule().stroke(CrewTheme.border, lineWidth: 1))
            }
            .buttonStyle(.plain)

            // Energy score pill
            Button { showSettings = true } label: {
                HStack(spacing: 6) {
                    Text("YOUR ENERGY SCORE")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(CrewTheme.muted)
                    Circle()
                        .fill(CrewTheme.orange)
                        .frame(width: 10, height: 10)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .overlay(Capsule().stroke(CrewTheme.border, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
    }
}
