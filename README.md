# Crew Bus

**Your agents. Your hardware. Your rules.**

Crew Bus is open-source software that runs on your own machine and lets your AI agents work together as a coordinated team — no cloud dependency, no API subscriptions, no data leaving your network.

> Most agent frameworks send your data to someone else's servers and charge you monthly for the privilege. Crew Bus runs locally, costs $29 once, and puts a security Guardian between your agents and the outside world.

[![GitHub release](https://img.shields.io/github/v/release/crew-bus/crew-bus)](https://github.com/crew-bus/crew-bus/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-265%20passing-brightgreen)](#)
[![macOS](https://img.shields.io/badge/macOS-14.0%2B-blue)](#download)

---

## Download

**[Download Crew Bus for Mac](https://github.com/crew-bus/crew-bus/releases/latest)** (macOS 14.0+)

Native SwiftUI app — no browser, no Electron. Just a real Mac app.

1. Download `CrewBus-1.0.0.dmg`
2. Drag **Crew Bus** to Applications
3. Launch and your crew is ready

The app is code-signed and notarized by Apple for safe installation.

---

## Why Crew Bus?

Setting up a team of AI agents today is painful. You download a framework, wrestle with config files, wire up message routing, figure out which agent talks to which, pray nothing breaks — and your data flows through someone else's cloud the whole time.

Crew Bus takes a different approach:

- **Native Mac app.** A real SwiftUI desktop app — not a web page in a wrapper.
- **Runs on your Mac.** Your machine, your data. Nothing leaves your network unless you tell it to.
- **Works out of the box.** Three agents in a triangle — Crew Boss, Guardian, Vault — ready to go in minutes, not hours.
- **Built-in security from day one.** The Guardian agent controls all external access, vets every skill before install, and monitors everything in real time. No other agent framework ships with an immune system.
- **Auto-updates via Sparkle.** The app checks for updates automatically — every 2 hours during your first 14 days for rapid bug fixes, then every 6 hours after that.
- **One price, forever.** $29 lifetime Guardian Activation key. No subscriptions. No per-token charges. No surprise bills.

---

## How It Works

```
         +------------+
         | Crew Boss  |  <- your AI right-hand
         +--+------+--+
            |      |
   +--------+      +--------+
   |                         |
+--+-------+          +-----+---+
| Guardian |          |  Vault  |
| protects |          |remembers|
+----------+          +---------+
```

**Boss talks, Guard protects, Vault remembers.**

**Crew Boss** sits at the top and coordinates everything. Your AI right-hand — handles 80% of what you need so you can focus on living. Every message flows through the bus — agents don't talk directly to each other, they talk through the system.

**Guardian** is the gatekeeper. It controls web access, vets skills for safety, monitors runtime health, and auto-quarantines anything that degrades. Your crew's immune system.

**Vault** is your private journal and life-data agent. It remembers everything — moods, goals, money notes, relationship changes, dreams, wins, fears. Never nags, never checks in. Only speaks when spoken to. Like a journal that writes back.

---

## The App

Crew Bus is a native macOS app built with SwiftUI. No browser windows, no Electron, no web views.

**Dashboard** — See your entire crew at a glance. Crew Boss at the top, Guardian and Vault alongside, teams on the right. Dark mode with particle effects.

**Chat** — Talk to any agent directly. Crew Boss handles most things, but you can go straight to Guardian or Vault when needed.

**Teams** — Team templates coming soon — specialized agent groups for business, creative, and more.

**Update Settings** — Auto-update preferences, channel picker (Stable / Latest), early access mode indicator.

**Security & Devices** — PIN lock, device management, auth modes.

---

## Quick Start (Developer)

If you want to run from source instead of the DMG:

```bash
# Clone the repo
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus

# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
python3 dashboard.py

# Build the Mac app
cd macos
xcodegen generate
xcodebuild build -scheme CrewBus -destination "platform=macOS"
```

The Mac app connects to this backend automatically on launch.

---

## Features

### Core (Free & Open Source)
- **Native Mac app** — SwiftUI, code-signed, notarized, auto-updates via Sparkle
- **3 coordinated agents** — Crew Boss (right-hand), Guardian (security), Vault (private journal)
- **Hierarchical message routing** — every message flows through the bus
- **Private sessions** — isolated conversations per agent
- **Team mailboxes** — agents can send structured messages to each other
- **Local-first** — runs entirely on your machine
- **Dashboard** — native UI to monitor and interact with your crew
- **Teams (coming soon)** — specialized agent groups for business, creative, and more
- **Audit log** — full trail of every action across your crew
- **Observability** — real-time health metrics and monitoring
- **Claude Desktop integration** — link your crew to Claude via MCP

### Guardian Activation ($29 lifetime)

**Web Search** — Every agent can search the internet and read URLs. Powered by DuckDuckGo — no API key needed, zero external dependencies. Internal IPs are blocked. Guardian controls all access.

**Skill Store** — 20 curated skills across 10 categories — creative writing, homework help, budget tracking, meal planning, music production, lead finding, fitness planning, data analysis, and more. Guardian analyzes what an agent needs, recommends the best skill, vets it for safety, and installs it. Community skills from trusted HTTPS sources also supported.

**Skill Sandbox** — Guardian monitors every installed skill in real time: health scoring (0-100), error rate tracking, charter violation detection, automatic quarantine for degraded skills, restore with re-vetting, and full audit trail.

---

## Crew Bus vs. The Alternatives

| | **Crew Bus** | **CrewAI** | **AutoGen** | **LangGraph** |
|---|---|---|---|---|
| **Native desktop app** | Yes | No | No | No |
| **Runs locally** | Your hardware, your data | Cloud-first | Possible but not default | Requires setup |
| **Built-in security agent** | Guardian monitors everything | No equivalent | No equivalent | No equivalent |
| **Skill marketplace** | 20 curated + community skills | Manual tool setup | Manual tool setup | Manual tool setup |
| **Runtime skill monitoring** | Health scores, auto-quarantine | None | None | None |
| **Auto-updates** | Sparkle (signed + notarized) | N/A | N/A | N/A |
| **Setup time** | Download DMG, drag to Applications | Hours | Hours | Hours |
| **Pricing** | $29 once (core is free) | Free OSS / Enterprise | Free OSS | Free OSS |
| **Target user** | Everyone | Enterprise dev teams | Researchers | Advanced developers |

### The real difference

CrewAI, AutoGen, and LangGraph are powerful frameworks built for developers who want to code agent systems from scratch. They assume you'll wire everything together yourself.

**Crew Bus is built for people who want agents working together *today*.** You get a pre-configured crew, a security layer, a skill marketplace, and a native Mac app — all running on your own machine. No PhD in prompt engineering required.

---

## What People Use It For

- **Personal productivity** — Crew Boss organizes your life, Vault remembers everything, Guardian keeps it safe
- **Private journaling** — Talk to Vault about your day, goals, fears, wins — it connects dots across weeks and months
- **Content creation** — Install creative writing skills, coordinate research + drafting + editing across agents
- **Budget & finance tracking** — Share money notes with Vault, get pattern insights when you ask
- **Learning & homework help** — Install education skills, get tutoring from a coordinated agent team
- **Small business operations** — Meal planning, fitness coaching, data analysis — all local, all private

---

## Architecture

```
+-------------------------------------------+
|          Crew Bus (SwiftUI Mac App)        |
+-------------------------------------------+
|              API Layer (stdlib)            |
+-------------------------------------------+
|           Agent Worker Engine              |
|  +-------------------------------------+  |
|  |  Crew Boss  |  Guardian  |   Vault  |  |
|  +-------------------------------------+  |
+-------------------------------------------+
|  Guardian Layer                           |
|  +----------+-----------+-----------+     |
|  |Web Bridge| Skill Store|  Sandbox |     |
|  +----------+-----------+-----------+     |
+-------------------------------------------+
|           SQLite (Local DB)               |
+-------------------------------------------+
```

Everything runs on your machine. No Docker required. No cloud services. No external databases.

---

## System Requirements

- macOS 14.0 (Sonoma) or later
- Python 3.9+ (bundled server)
- Any LLM provider (local or API-based)

---

## Roadmap

- [ ] Voice interface — talk to your crew
- [ ] iOS companion app
- [ ] Plugin SDK — build and share your own skills
- [ ] Multi-machine crew networking (LAN)
- [ ] Messaging integrations for on-the-go access

---

## Contributing

Crew Bus is open source and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Run tests before submitting
pytest
```

---

## License

MIT — use it however you want.

---

## Links

- **Website:** [crew-bus.dev](https://crew-bus.dev)
- **Download:** [Latest Release](https://github.com/crew-bus/crew-bus/releases/latest)
- **GitHub:** [github.com/crew-bus/crew-bus](https://github.com/crew-bus/crew-bus)
- **Activation Keys:** [crew-bus.dev](https://crew-bus.dev) ($29 lifetime)

---

*Built for everyone — kids, teens, moms, dads, families, artists, hobbyists, small businesses, startups, ex-coders. Every human gets their own local Crew Bus — private, sovereign.*
