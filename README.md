<h1 align="center">crew-bus</h1>

<p align="center">
  <strong>Your AI crew. Your hardware. Your rules.</strong>
</p>

<div align="center">

**crew-bus is LIVE.** Free, open-source AI crew for everyone.

[**Get Started**](https://crew-bus.dev) | [**Pricing**](https://crew-bus.dev/pricing)

</div>

---

**crew-bus** is a free, open-source system for running your own personal AI crew from a single dashboard. No cloud. No data leaving your machine. Every human gets their own local Crew Bus — private, sovereign.

One human. One crew. Full control.

---

## What is this?

crew-bus is a local message bus that coordinates multiple AI agents on your machine. Your **Crew Boss** is your AI right-hand — the agent you talk to 80% of the time. All other agents stay hidden unless you ask to talk directly.

On first launch, a setup Wizard walks you through configuration — pick your AI model, paste your API key, and build your first team from ready-made templates. No terminal knowledge required.

## Features

- **Crew Boss** — Your AI chief of staff. Powered by Kimi K2.5, Ollama, Claude, OpenAI, Groq, Gemini, or any OpenAI-compatible model.
- **5 core agents** — Crew Boss, Guard, Wellness, Ideas, Wallet. Pre-configured and orbiting the center of your dashboard.
- **Setup Wizard** — Guides new users through model selection, API key setup, and first team creation. Runs automatically on first launch.
- **8 team templates** — 3 free (School, Passion Project, Household) + 5 paid (Business Management, Department, Freelance, Side Hustle, Custom). Pick one, name it, and your team is live.
- **Up to 10 agents per team** — Each team gets a manager + up to 9 workers. Hire and terminate agents anytime.
- **6 LLM providers** — Kimi K2.5 (free tier), Claude, OpenAI, Groq, Gemini, or Ollama (fully local). Per-agent model picker.
- **Trust score (1–10)** — Controls how much Crew Boss handles autonomously. 1 = see everything. 10 = morning brief only.
- **Burnout awareness** — When you're running hot, non-urgent messages get held for better timing.
- **Private sessions** — Talk directly with any agent. 🔒 means private — not even Crew Boss sees the content.
- **Team mailbox** — Any agent can escalate directly to you if something critical is being ignored. No message gets silenced.
- **Dashboard PIN lock** — Optional PIN protects against accidental deletion and unauthorized changes. Auto-locks after idle. Kid-proof.
- **Guardian activation** — Unlock the Skill Store with a $29 one-time key. Adds threat monitoring, anomaly detection, and audit hardening.
- **Auto-update** — One-click update button in the topbar + silent auto-updates every 24 hours.
- **Desktop shortcut** — Auto-created on first launch. Works on macOS, Windows, and Linux.
- **Visual dashboard** — Circle layout with status dots. Mobile-first. Auto-opens in your browser on startup.
- **Activity time filters** — Today, 3-Day, Week, and Month views to see agent activity across different time windows.
- **Full audit trail** — Every message, every decision, every routing event. Logged locally in SQLite.
- **Runs on anything** — Python + SQLite. Works on a Raspberry Pi, a laptop, or a server.

## Pricing

crew-bus itself is **free and open-source** (MIT). Paid add-ons unlock extra team templates and capabilities:

| Tier | Price | What You Get |
|------|-------|-------------|
| **Core** | **Free forever** | Full message bus, Crew Boss, 5 core agents, dashboard, private sessions, team mailbox, Wizard setup, 3 free team templates (School, Passion Project, Household). MIT License. |
| **Guardian** | **$29 one-time** | Unlock the Skill Store — downloadable skills that make your agents smarter. Threat monitoring, anomaly detection, audit hardening. Lifetime activation key. |
| **Business Management** | **$50/yr or $10 trial** | Full business team — Operations Lead, HR Coordinator, Finance Monitor, Strategy Advisor, Comms Manager. |
| **Department** | **$25/yr or $5 trial** | Add-on department with manager + workers (Task Runner, Research Aide). |
| **Freelance** | **$30/yr or $5 trial** | Lead Finder, Invoice Bot, Client Follow-up — everything a freelancer needs. |
| **Side Hustle** | **$30/yr or $5 trial** | Market Scout, Content Creator, Sales Tracker — launch and grow your idea. |
| **Custom Team** | **$50/yr or $10 trial** | Build your own team from scratch with any agents you want. |

Each team license covers one team. Need 3 departments? That's 3 licenses. No subscriptions on core. No cloud fees. No hidden charges. Payments via Stripe.

## Quick Start

```bash
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus
pip install pyyaml
python3 dashboard.py
```

Your browser opens automatically. The Wizard walks you through setup.

Use `--no-browser` if you don't want the browser to auto-open.

## Example Crews

Load a pre-built crew config to get started fast:

### Family Crew
For busy families — chores, meals, homework, health, and daily life.
```bash
python3 dashboard.py --config examples/family-crew.yaml
```

### Artist / Passion Crew
For artists, musicians, writers, and makers of all kinds.
```bash
python3 dashboard.py --config examples/artist-passion-crew.yaml
```

### Teen Crew
For teens — homework, gaming, music, big ideas, zero lectures.
```bash
python3 dashboard.py --config examples/teen-crew.yaml
```

### Launch Crew
For spreading the word — warm, human, zero-corporate outreach.
```bash
python3 dashboard.py --config examples/launch-crew.yaml
```

> Or skip the examples and let the Wizard build your first team interactively.

## Architecture

```
Human
  ↕
Crew Boss (trust: 1–10)
  ↕           ↕           ↕           ↕
Guard      Wellness     Ideas      Wallet
                          ↕
                    Team Managers
                      ↕       ↕
                   Workers  Workers
```

Messages flow through the bus. Routing rules enforce the hierarchy. Trust score governs autonomy. Burnout score affects timing. Every message is logged in SQLite.

## The Circle

The dashboard shows your 5 core agents orbiting Crew Boss:

- 🔷 **Crew Boss** (center) — Your AI right-hand
- 🛡️ **Guard** (left) — Security monitoring
- 💚 **Wellness** (top) — Health and wellbeing
- 💡 **Ideas** (right) — Strategy and brainstorming
- 💰 **Wallet** (bottom) — Financial tracking

Tap any agent to open their private space with activity feed and chat.

## Privacy

- **Private sessions** are truly private. Crew Boss logs that a session happened but never sees the content.
- **Everything runs locally.** No cloud, no telemetry, no phone-home.
- **You own your data.** It's a SQLite file on your machine. Back it up, delete it, move it — your choice.

## Requirements

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- An LLM API key (Kimi K2.5 free at platform.moonshot.ai, or use Ollama for fully local)
- That's it. No frameworks. No Docker. No cloud accounts.

## Project Structure

```
crew-bus/
├── bus.py              # Core message bus engine (~4,300 LOC)
├── dashboard.py        # Web dashboard — localhost:8080 (~5,200 LOC)
├── agent_worker.py     # LLM integration — 6 providers (~630 LOC)
├── right_hand.py       # Crew Boss decision engine (~750 LOC)
├── security.py         # Encryption & trust model (~790 LOC)
├── cli.py              # CLI with 50+ commands (~1,100 LOC)
├── agent_bridge.py     # OpenClaw agent bridge (~420 LOC)
├── delivery.py         # Message delivery backends (~435 LOC)
├── email_formatter.py  # Briefing email templates (~270 LOC)
├── configs/            # Agent hierarchy configs
├── examples/           # Ready-to-use crew configs
├── deploy/             # Server deployment (nginx, etc.)
├── public/             # Website (crew-bus.dev)
├── templates/          # HTML templates
├── conftest.py         # Pytest configuration
├── test_agent_worker.py # Agent worker tests (6 tests)
└── README.md           # You are here
```

## Philosophy

1. **Your hardware, your rules.** No cloud dependency. Ever.
2. **Privacy is real, not performative.** Private means private.
3. **Simple by default, powerful when needed.** Trust score 1 = see everything. Trust score 10 = full autopilot.
4. **No agent can silence another agent.** The team mailbox is the fire alarm anyone can pull.
5. **Free for everyone.** crew-bus is infrastructure for the world.
6. **A 10-year-old should be able to figure it out.** If the UX isn't obvious, it's a bug.

## License

MIT — do whatever you want with it.

## Status

Live and actively developed. Core bus, dashboard, private sessions, teams, Wizard setup, Guardian activation, Stripe payments, auto-updates, per-team licensing, and desktop shortcuts are all working.

---

*Built by one person within a month. That's the point — AI should be simple enough that anyone can run their own crew.*
