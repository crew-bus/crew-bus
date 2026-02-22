import SwiftUI
import CrewBusKit

struct HeartbeatSection: View {
    let agent: Agent
    @Environment(AppState.self) private var appState
    @State private var isExpanded = false
    @State private var tasks: [HeartbeatTask] = []
    @State private var newSchedule = "hourly"
    @State private var newTask = ""

    private let scheduleOptions = ["minutely", "hourly", "daily", "weekly"]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    Label("Heartbeat Tasks (\(tasks.count))", systemImage: "heart.circle")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(CrewTheme.text)
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11))
                        .foregroundStyle(CrewTheme.muted)
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                if tasks.isEmpty {
                    Text("No heartbeat tasks scheduled")
                        .font(.system(size: 12))
                        .foregroundStyle(CrewTheme.muted)
                        .padding(.vertical, 4)
                } else {
                    ForEach(tasks) { task in
                        HStack(spacing: 8) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(task.task)
                                    .font(.system(size: 12))
                                    .foregroundStyle(CrewTheme.text)
                                    .lineLimit(2)
                                Text(task.schedule)
                                    .font(.system(size: 10))
                                    .foregroundStyle(CrewTheme.muted)
                            }
                            Spacer()
                            Toggle("", isOn: Binding(
                                get: { task.enabled == 1 },
                                set: { _ in toggleTask(task) }
                            ))
                            .toggleStyle(.switch)
                            .controlSize(.small)
                            Button {
                                deleteTask(task)
                            } label: {
                                Image(systemName: "trash")
                                    .font(.system(size: 11))
                                    .foregroundStyle(CrewTheme.highlight)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(8)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }

                // Add new task
                HStack(spacing: 6) {
                    Picker("", selection: $newSchedule) {
                        ForEach(scheduleOptions, id: \.self) { opt in
                            Text(opt.capitalized).tag(opt)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 100)

                    TextField("Task description...", text: $newTask)
                        .font(.system(size: 12))
                        .textFieldStyle(.plain)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(CrewTheme.bg)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(CrewTheme.border, lineWidth: 1))

                    Button {
                        addTask()
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 18))
                            .foregroundStyle(CrewTheme.accent)
                    }
                    .buttonStyle(.plain)
                    .disabled(newTask.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .padding(12)
        .background(CrewTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(CrewTheme.border, lineWidth: 1))
        .task {
            await fetchTasks()
        }
    }

    private func fetchTasks() async {
        do {
            let fetched: [HeartbeatTask] = try await appState.client.get(
                APIEndpoints.agentHeartbeat(agent.id)
            )
            await MainActor.run { tasks = fetched }
        } catch {
            // Silent fail
        }
    }

    private func addTask() {
        let taskText = newTask.trimmingCharacters(in: .whitespaces)
        guard !taskText.isEmpty else { return }
        Task {
            try? await appState.client.post(
                APIEndpoints.agentHeartbeat(agent.id),
                body: ["schedule": newSchedule, "task": taskText]
            )
            await MainActor.run { newTask = "" }
            await fetchTasks()
        }
    }

    private func toggleTask(_ task: HeartbeatTask) {
        Task {
            try? await appState.client.post(
                APIEndpoints.heartbeatToggle(task.id),
                body: [:]
            )
            await fetchTasks()
        }
    }

    private func deleteTask(_ task: HeartbeatTask) {
        Task {
            try? await appState.client.post(
                APIEndpoints.heartbeatDelete(task.id),
                body: [:]
            )
            await fetchTasks()
        }
    }
}
