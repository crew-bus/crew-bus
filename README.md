# crew-bus

Your AI crew. Your hardware. Your rules.

**crew-bus** is a free, open-source coordination system for managing multiple AI agents from a single dashboard. No cloud. No subscriptions. No data leaving your machine.

One human. One crew. Full control.

---

## What is this?

You have AI agents — maybe a personal assistant, a security monitor, a wellness tracker, a financial advisor, a brainstorming partner. Right now they're scattered across different apps with no coordination.

crew-bus is the message bus that connects them. It sits between you and your agents, routing messages, enforcing hierarchy, and making sure nothing important gets lost.

Your **Crew Boss** is your AI chief of staff — the only agent that talks to you directly (unless you want private conversations with others). Every other agent reports through the chain of command.

## Features

- **5 core agents** — Crew Boss, Guard, Wellness, Ideas, Wallet. Pre-configured and ready.
- **Trust score (1-10)** — Controls how much Crew Boss handles autonomously. Set it to 1 and you see everything. Set it to 10 and you get a morning brief.
- **Burnout awareness** — When you're running hot, non-urgent messages get held for better timing.
- **Private sessions** — Talk directly with any agent. 🔒 means private — not even Crew Boss sees the content.
- **Teams** — Add departments with managers and workers. Scale from 5 agents to 50.
- **Team mailbox** — Any agent can escalate directly to you if something critical is being ignored. No message gets silenced.
- **Visual dashboard** — Clean circle layout. Status dots tell you everything. Mobile-first.
- **Full audit trail** — Every message, every decision, every routing event. Logged locally.
- **Runs on anything** — Python + SQLite. Works on a Raspberry Pi, a laptop, or a server.

## Quick Start

```bash
# Replace with your GitHub username in the URL
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus
pip install pyyaml
python dashboard.py
```

Open `http://localhost:8080` in your browser. That's it.

## Try These Example Crews

Get started in seconds. Pick a crew, load it, done.

### Family Crew
For busy families — chores, meals, homework, health, and daily life.
```bash
crew-bus load examples/family-crew.yaml
```
Includes: Crew Boss (warm big-sister energy), Friend & Family Helper, Health Buddy, Life Assistant. Family Mode with quiet hours 9pm-7am.

### Artist / Passion Crew
For artists, musicians, writers, and makers of all kinds.
```bash
crew-bus load examples/artist-passion-crew.yaml
```
Includes: Crew Boss (encouraging friend), Muse (creative prompts + streak tracker), Health Buddy, Growth Coach. Passion Mode with daily creative sparks.

### Teen Crew
For teens — homework, gaming, music, big ideas, zero lectures.
```bash
crew-bus load examples/teen-crew.yaml
```
Includes: Crew Boss (chill big-bro energy), Friend & Family Helper, Muse (gaming, music, drawing), Growth Coach (study timer + skill tree). Fun Mode with gamification.

### Launch Crew (for growing Crew Bus)
For spreading the word about Crew Bus — warm, human, zero-corporate outreach.
```bash
crew-bus load examples/launch-crew.yaml
```
Includes: Crew Boss (warm launch captain), Content Creator (tweets, threads, Reddit posts), Outreach Buddy (finds communities, drafts friendly intros), Visual Helper (images, GIFs, thumbnails), Momentum Tracker (reads replies, suggests next moves). Launch Mode with burnout protection and content approval.

> Want to customize? Copy any example to `configs/my-crew.yaml` and make it yours. Rename Crew Boss to anything you want.

## Screenshots

[Add screenshots of the circle layout, agent space, team dashboard, and private session]

## Architecture

```
Human
  ↕
Crew Boss (trust: 1-10)
  ↕           ↕           ↕           ↕
Guard      Wellness     Ideas      Wallet
                          ↕
                    Team Managers
                      ↕       ↕
                   Workers  Workers
```

Messages flow through the bus. Routing rules enforce the hierarchy. Trust score governs autonomy. Burnout score affects timing. Every message is logged in SQLite.

## The Circle

The dashboard shows your 5 core agents in a circle around Crew Boss:

- 🔷 **Crew Boss** (center) — Your AI chief of staff
- 🛡️ **Guard** (left) — Security monitoring
- 💚 **Wellness** (top) — Health and wellbeing
- 💡 **Ideas** (right) — Strategy and brainstorming
- 💰 **Wallet** (bottom) — Financial tracking

Tap any agent to open a private 1-on-1 space with activity feed and chat.

## Privacy

- **Private sessions** are truly private. Crew Boss logs that a session happened but never sees the content.
- **Team mailbox** logs that a message was sent but never the content.
- **Everything runs locally.** No cloud, no telemetry, no phone-home.
- **You own your data.** It's a SQLite file on your machine. Back it up, delete it, move it — your choice.

## Multi-Channel

Agents can communicate through:
- **Web dashboard** — Always available, no setup
- **Telegram** — Assign bot tokens to agents for real-time mobile chat
- **Signal** — Coming soon
- **Smartphone app** — Coming soon

## Requirements

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- That's it. No frameworks. No Docker. No cloud accounts.

## Project Structure

```
crew-bus/
├── bus.py              # Core message bus engine
├── dashboard.py        # Web dashboard (localhost:8080)
├── cli.py              # Command-line interface
├── configs/            # Agent hierarchy configs
│   └── example_stack.yaml # Default configuration (copy and customize)
├── examples/           # Ready-to-use crew configs
│   ├── family-crew.yaml        # Family crew (chores, meals, health)
│   ├── artist-passion-crew.yaml # Creative crew (art, music, writing)
│   ├── teen-crew.yaml          # Teen crew (school, gaming, big ideas)
│   └── launch-crew.yaml        # Launch crew (grow Crew Bus organically)
├── templates/          # HTML templates
├── test_day2.py        # Core bus tests (38)
├── test_day3.py        # Advanced feature tests (61)
├── test_private_sessions.py  # Privacy tests (34)
├── test_team_mailbox.py      # Mailbox tests (34)
├── test_guard_activation.py  # Guard activation + skill gating tests (24)
├── test_techie_marketplace.py # Techie marketplace tests (43)
└── README.md           # You are here
```

## Philosophy

1. **Your hardware, your rules.** No cloud dependency. Ever.
2. **Privacy is real, not performative.** Private means private.
3. **Simple by default, powerful when needed.** Trust score 1 = see everything. Trust score 10 = full autopilot.
4. **No agent can silence another agent.** The team mailbox is the fire alarm anyone can pull.
5. **Free for everyone.** crew-bus is infrastructure for the world.

## License

MIT — do whatever you want with it.

## Status

Active development. Core bus, dashboard, private sessions, team mailbox, Guard activation, and techie marketplace are working. 234 tests passing.

To customize your agent hierarchy, copy `configs/example_stack.yaml` to `configs/my_stack.yaml` and edit it.

Coming soon: Smartphone app, Signal integration.

---

*Built by one person in a few days. That's the point — AI should be simple enough that anyone can run their own crew.*
