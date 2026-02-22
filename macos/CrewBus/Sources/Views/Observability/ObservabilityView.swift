import SwiftUI
import CrewBusKit

struct ObservabilityView: View {
    @Environment(AppState.self) private var appState
    @State private var statsResponse: TelemetryStatsResponse?
    @State private var spans: [TelemetrySpan] = []
    @State private var refreshTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .dashboard
                    }
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                        .frame(width: 34, height: 34)
                        .background(CrewTheme.surface)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(CrewTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)

                Text("Observability")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(height: 54)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            ScrollView {
                VStack(spacing: 16) {
                    // Stats cards
                    statsCardsRow

                    // Spans table
                    spansTable
                }
                .padding(16)
            }
        }
        .background(CrewTheme.bg)
        .onAppear { startRefresh() }
        .onDisappear { stopRefresh() }
    }

    private var statsCardsRow: some View {
        HStack(spacing: 12) {
            statCard(
                title: "Total Spans",
                value: "\(statsResponse?.totalSpans ?? 0)",
                icon: "chart.bar",
                color: CrewTheme.accent
            )
            statCard(
                title: "Avg Response",
                value: String(format: "%.0fms", statsResponse?.avgResponseMs ?? 0),
                icon: "clock",
                color: CrewTheme.green
            )
            statCard(
                title: "Error Rate",
                value: String(format: "%.1f%%", (statsResponse?.errorRate ?? 0) * 100),
                icon: "exclamationmark.triangle",
                color: CrewTheme.highlight
            )
        }
    }

    private func statCard(title: String, value: String, icon: String, color: Color) -> some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundStyle(color)
            Text(value)
                .font(.system(size: 20, weight: .bold, design: .monospaced))
                .foregroundStyle(CrewTheme.text)
            Text(title)
                .font(.system(size: 11))
                .foregroundStyle(CrewTheme.muted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    private var spansTable: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Spans")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(CrewTheme.text)

            // Table header
            HStack(spacing: 0) {
                Text("Time").frame(width: 80, alignment: .leading)
                Text("Span Name").frame(maxWidth: .infinity, alignment: .leading)
                Text("Duration").frame(width: 80, alignment: .trailing)
                Text("Status").frame(width: 70, alignment: .center)
                Text("Agent").frame(width: 60, alignment: .trailing)
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(CrewTheme.muted)
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(CrewTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 4))

            if spans.isEmpty {
                Text("No telemetry data yet")
                    .font(.system(size: 12))
                    .foregroundStyle(CrewTheme.muted)
                    .padding(.vertical, 8)
            } else {
                ForEach(spans) { span in
                    HStack(spacing: 0) {
                        Text(formatTime(span.createdAt))
                            .frame(width: 80, alignment: .leading)
                        Text(span.spanName)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .lineLimit(1)
                        Text(span.durationMs.map { String(format: "%.0fms", $0) } ?? "-")
                            .frame(width: 80, alignment: .trailing)
                        Text(span.status ?? "-")
                            .foregroundStyle(span.status == "error" ? CrewTheme.highlight : CrewTheme.green)
                            .frame(width: 70, alignment: .center)
                        Text(span.agentId.map { "#\($0)" } ?? "-")
                            .frame(width: 60, alignment: .trailing)
                    }
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(CrewTheme.text)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
    }

    private func formatTime(_ timestamp: String?) -> String {
        guard let ts = timestamp else { return "-" }
        // Show just HH:MM:SS portion
        if let tIdx = ts.firstIndex(of: "T") {
            let timeStr = ts[ts.index(after: tIdx)...]
            return String(timeStr.prefix(8))
        }
        return String(ts.suffix(8))
    }

    private func startRefresh() {
        refreshTask = Task {
            while !Task.isCancelled {
                await fetchData()
                try? await Task.sleep(for: .seconds(10))
            }
        }
    }

    private func stopRefresh() {
        refreshTask?.cancel()
        refreshTask = nil
    }

    private func fetchData() async {
        do {
            let stats: TelemetryStatsResponse = try await appState.client.get(
                APIEndpoints.telemetryStats, query: ["since": "24h"]
            )
            await MainActor.run { statsResponse = stats }
        } catch {}

        do {
            let fetched: [TelemetrySpan] = try await appState.client.get(
                APIEndpoints.telemetry, query: ["limit": "50"]
            )
            await MainActor.run { spans = fetched }
        } catch {}
    }
}
