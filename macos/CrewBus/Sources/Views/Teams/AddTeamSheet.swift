import SwiftUI

struct AddTeamSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .center, spacing: 0) {
            // Drag handle
            RoundedRectangle(cornerRadius: 2)
                .fill(CrewTheme.muted)
                .frame(width: 40, height: 4)
                .padding(.top, 12)

            // Title
            VStack(spacing: 6) {
                Text("Add a Team")
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundStyle(CrewTheme.text)

                HStack(spacing: 8) {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark")
                            .font(.caption2)
                        Text("Free")
                    }
                    .font(.caption)
                    .foregroundStyle(CrewTheme.green)

                    Text("|")
                        .foregroundStyle(CrewTheme.muted)

                    HStack(spacing: 4) {
                        Image(systemName: "creditcard")
                            .font(.caption2)
                        Text("Paid (trial available)")
                    }
                    .font(.caption)
                    .foregroundStyle(CrewTheme.muted)
                }
            }
            .padding(.vertical, 16)

            Divider().background(CrewTheme.border)

            // Team options
            ScrollView {
                VStack(spacing: 0) {
                    teamOption(emoji: "🎓", name: "School", desc: "Tutor, Research Assistant, Study Planner", free: true)
                    teamOption(emoji: "🎨", name: "Passion Project", desc: "Project Planner, Skill Coach, Progress Tracker", free: true)
                    teamOption(emoji: "🏠", name: "Household", desc: "Meal Planner, Budget Tracker, Schedule", free: true)
                    teamOption(emoji: "💼", name: "Freelance", desc: "Lead Finder, Invoice Bot, Follow-up", price: "$5 trial · $30/yr")
                    teamOption(emoji: "⚡", name: "Side Hustle", desc: "Market Scout, Content, Sales", price: "$5 trial · $30/yr")
                    teamOption(emoji: "🧩", name: "Custom", desc: "You name it, pick the agents", price: "$10 trial · $50/yr")
                }
            }

            Divider().background(CrewTheme.border)

            Button("Cancel") { dismiss() }
                .font(.system(size: 14))
                .foregroundStyle(CrewTheme.muted)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .buttonStyle(.plain)
        }
        .frame(width: 420, height: 520)
        .background(CrewTheme.surface)
    }

    @ViewBuilder
    private func teamOption(emoji: String, name: String, desc: String, free: Bool = false, price: String? = nil) -> some View {
        Button {
            dismiss()
        } label: {
            HStack(spacing: 14) {
                Text(emoji)
                    .font(.title2)
                    .frame(width: 36)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(name)
                            .fontWeight(.semibold)
                            .foregroundStyle(CrewTheme.text)
                        if free {
                            Image(systemName: "checkmark")
                                .font(.caption2)
                                .foregroundStyle(CrewTheme.green)
                        }
                    }
                    HStack(spacing: 4) {
                        Text(desc)
                            .font(.caption)
                            .foregroundStyle(CrewTheme.muted)
                        if let price = price {
                            Text(price)
                                .font(.caption)
                                .foregroundStyle(CrewTheme.orange)
                        }
                    }
                }

                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)

        Divider().background(CrewTheme.border).padding(.leading, 70)
    }
}
