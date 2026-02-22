import SwiftUI

struct SetupView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "gear")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Setup")
                .font(.title2)
            Text("First-run setup coming soon")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
