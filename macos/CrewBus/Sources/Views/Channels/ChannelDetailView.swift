import SwiftUI
import CrewBusKit

struct ChannelDetailView: View {
    let channel: CrewChannel
    @Environment(AppState.self) private var appState
    @State private var messages: [ChannelMessage] = []
    @State private var inputText = ""
    @State private var pollingTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 12) {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        appState.navDestination = .channelList
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

                Image(systemName: "number")
                    .font(.system(size: 14))
                    .foregroundStyle(CrewTheme.accent)

                Text(channel.name)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                if let purpose = channel.purpose, !purpose.isEmpty {
                    Text(purpose)
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                        .lineLimit(1)
                }

                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(height: 54)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 6) {
                        if messages.isEmpty {
                            VStack(spacing: 8) {
                                Spacer().frame(height: 60)
                                Text("No messages yet")
                                    .font(.system(size: 14))
                                    .foregroundStyle(CrewTheme.muted)
                                Text("Be the first to post in #\(channel.name)")
                                    .font(.system(size: 12))
                                    .foregroundStyle(CrewTheme.muted)
                            }
                            .frame(maxWidth: .infinity)
                        } else {
                            ForEach(messages) { msg in
                                HStack(alignment: .top, spacing: 8) {
                                    Text(msg.fromName?.prefix(2).uppercased() ?? "?")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(.white)
                                        .frame(width: 28, height: 28)
                                        .background(CrewTheme.accent)
                                        .clipShape(Circle())

                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack(spacing: 6) {
                                            Text(msg.fromName ?? "Unknown")
                                                .font(.system(size: 12, weight: .semibold))
                                                .foregroundStyle(CrewTheme.text)
                                            if let ts = msg.createdAt {
                                                Text(ts)
                                                    .font(.system(size: 10))
                                                    .foregroundStyle(CrewTheme.muted)
                                            }
                                        }
                                        Text(msg.body)
                                            .font(.system(size: 13))
                                            .foregroundStyle(CrewTheme.text)
                                    }

                                    Spacer()
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 4)
                                .id(msg.id)
                            }
                        }
                    }
                    .padding(.vertical, 12)
                }
                .background(CrewTheme.bg)
                .onChange(of: messages.count) {
                    if let last = messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            // Input
            HStack(spacing: 8) {
                TextField("Message #\(channel.name)", text: $inputText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .padding(10)
                    .background(CrewTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
                    .onSubmit { sendMessage() }

                Button {
                    sendMessage()
                } label: {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(inputText.trimmingCharacters(in: .whitespaces).isEmpty ? CrewTheme.muted : CrewTheme.accent)
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(inputText.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(12)
            .background(CrewTheme.surface)
            .overlay(alignment: .top) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }
        }
        .background(CrewTheme.bg)
        .onAppear { startPolling() }
        .onDisappear { stopPolling() }
    }

    private func startPolling() {
        pollingTask = Task {
            while !Task.isCancelled {
                await fetchMessages()
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    private func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    private func fetchMessages() async {
        do {
            let fetched: [ChannelMessage] = try await appState.client.get(
                APIEndpoints.channelMessages(channel.id)
            )
            await MainActor.run { messages = fetched }
        } catch {}
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        inputText = ""
        Task {
            try? await appState.client.post(
                APIEndpoints.channelPost(channel.id),
                body: ["body": text]
            )
            await fetchMessages()
        }
    }
}
