import SwiftUI
import CrewBusKit

struct ChannelListView: View {
    @Environment(AppState.self) private var appState
    @State private var channels: [CrewChannel] = []
    @State private var showNewChannel = false
    @State private var newName = ""
    @State private var newPurpose = ""

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

                Text("Crew Channels")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(CrewTheme.text)

                Spacer()

                Button {
                    showNewChannel = true
                } label: {
                    Label("New Channel", systemImage: "plus")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .frame(height: 54)
            .background(CrewTheme.surface)
            .overlay(alignment: .bottom) {
                Rectangle().fill(CrewTheme.border).frame(height: 1)
            }

            ScrollView {
                LazyVStack(spacing: 8) {
                    if channels.isEmpty {
                        VStack(spacing: 8) {
                            Image(systemName: "bubble.left.and.bubble.right")
                                .font(.system(size: 32))
                                .foregroundStyle(CrewTheme.muted)
                            Text("No channels yet")
                                .font(.system(size: 14))
                                .foregroundStyle(CrewTheme.muted)
                            Text("Create a channel for your crew to communicate")
                                .font(.system(size: 12))
                                .foregroundStyle(CrewTheme.muted)
                        }
                        .padding(.top, 60)
                    } else {
                        ForEach(channels) { channel in
                            Button {
                                withAnimation(.easeInOut(duration: 0.25)) {
                                    appState.navDestination = .channelDetail(channel)
                                }
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "number")
                                        .font(.system(size: 16, weight: .medium))
                                        .foregroundStyle(CrewTheme.accent)
                                        .frame(width: 36, height: 36)
                                        .background(CrewTheme.accent.opacity(0.1))
                                        .clipShape(Circle())

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(channel.name)
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundStyle(CrewTheme.text)
                                        if let purpose = channel.purpose, !purpose.isEmpty {
                                            Text(purpose)
                                                .font(.system(size: 12))
                                                .foregroundStyle(CrewTheme.muted)
                                                .lineLimit(1)
                                        }
                                    }

                                    Spacer()

                                    VStack(alignment: .trailing, spacing: 2) {
                                        if let members = channel.memberCount {
                                            Text("\(members) members")
                                                .font(.system(size: 10))
                                                .foregroundStyle(CrewTheme.muted)
                                        }
                                        if let msgs = channel.msgCount, msgs > 0 {
                                            Text("\(msgs) msgs")
                                                .font(.system(size: 10))
                                                .foregroundStyle(CrewTheme.accent)
                                        }
                                    }

                                    Image(systemName: "chevron.right")
                                        .font(.system(size: 11))
                                        .foregroundStyle(CrewTheme.muted)
                                }
                                .padding(12)
                                .background(CrewTheme.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                                .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(16)
            }
        }
        .background(CrewTheme.bg)
        .task {
            await fetchChannels()
        }
        .sheet(isPresented: $showNewChannel) {
            newChannelSheet
        }
    }

    private var newChannelSheet: some View {
        VStack(spacing: 16) {
            Text("New Channel")
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(CrewTheme.text)

            VStack(alignment: .leading, spacing: 6) {
                Text("Name")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(CrewTheme.muted)
                TextField("general", text: $newName)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .padding(8)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Purpose")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(CrewTheme.muted)
                TextField("What's this channel for?", text: $newPurpose)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .padding(8)
                    .background(CrewTheme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(CrewTheme.border, lineWidth: 1))
            }

            HStack {
                Button("Cancel") {
                    showNewChannel = false
                }
                .buttonStyle(.plain)
                .foregroundStyle(CrewTheme.muted)

                Spacer()

                Button {
                    createChannel()
                } label: {
                    Text("Create")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                        .background(newName.trimmingCharacters(in: .whitespaces).isEmpty ? CrewTheme.muted : CrewTheme.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(24)
        .frame(width: 360)
        .background(CrewTheme.surface)
    }

    private func fetchChannels() async {
        do {
            let fetched: [CrewChannel] = try await appState.client.get(APIEndpoints.crewChannels)
            await MainActor.run { channels = fetched }
        } catch {}
    }

    private func createChannel() {
        let name = newName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        Task {
            try? await appState.client.post(
                APIEndpoints.crewChannels,
                body: ["name": name, "purpose": newPurpose]
            )
            showNewChannel = false
            newName = ""
            newPurpose = ""
            await fetchChannels()
        }
    }
}
