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

### Core Agent System
- **5 core agents** — Crew Boss, Guard, Wellness, Ideas, Wallet. Pre-configured and ready.
- **Trust score (1-10)** — Controls how much Crew Boss handles autonomously. Set it to 1 and you see everything. Set it to 10 and you get a morning brief.
- **Burnout awareness** — When you're running hot, non-urgent messages get held for better timing.
- **Private sessions** — Talk directly with any agent. Private means private — not even Crew Boss sees the content.
- **Teams** — Add departments with managers and workers. Scale from 5 agents to 50.
- **Team mailbox** — Any agent can escalate directly to you if something critical is being ignored. No message gets silenced.
- **Guard activation** — Skill-gated security monitoring with activation keys.
- **Visual dashboard** — Clean circle layout. Status dots tell you everything. Mobile-first.
- **Full audit trail** — Every message, every decision, every routing event. Logged locally.
- **Runs on anything** — Python + SQLite. Works on a Raspberry Pi, a laptop, or a server.

### Certified Installer Marketplace

Not everyone wants to set up their own AI crew from scratch — and not every tech professional has a clear path forward in a shifting job market. The **Certified Installer Marketplace** connects both sides.

**For clients:**
- **Find a vetted local installer** — Search by postal code, ZIP, area code, or any location format worldwide.
- **KYC-verified professionals** — Every installer completes identity verification. Look for the "KYC Verified" badge.
- **Video Meet & Greet** — Schedule a video call with your installer before committing. See a real human, ask questions, build trust.
- **Reviews and ratings** — See what other clients experienced before you hire.

**For installers (tech professionals):**
- **Turn your skills into income** — Set up crew-bus systems for clients in your area. Get paid doing what you're good at.
- **Free first permit** — Your first installation permit is free. Additional permits are $25 each.
- **Free 6-month Guardian key** — Every new installer gets a Guardian activation key to protect their own setup.
- **KYC verification** — Complete identity verification once, get a verified badge that builds client trust.
- **Specialty tags** — List your skills (networking, Linux, security, smart home, etc.) so clients find the right match.
- **Service radius** — Set your coverage area so you only see relevant jobs.

### Job Board

A two-sided marketplace where clients post jobs and installers claim them.

- **Post a job** — Clients describe what they need, set their location, and choose standard or priority urgency.
- **Browse and claim** — Installers search jobs near them and claim the ones they want.
- **Status tracking** — Jobs flow through open → claimed → scheduled → in progress → complete.
- **Global postal code support** — Works with every country's location format: US ZIP codes, UK postcodes, Canadian postal codes, German PLZ, Japanese postal codes, Indian PIN codes, Brazilian CEP, and more.

### Stripe Checkout

Secure payment processing for installation permits.

- **Stripe-powered** — Industry-standard payment security. No card details ever touch crew-bus servers.
- **$25 per permit** — Simple, transparent pricing. First permit is always free.
- **Webhook verification** — HMAC-SHA256 signature verification on every Stripe event.
- **Zero dependencies** — Stripe integration uses Python's built-in `urllib`. No pip packages required.

## Quick Start

```bash
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus
pip install pyyaml
python dashboard.py
```

Open `http://localhost:8080` in your browser. That's it.

### Stripe Setup (optional)

To enable paid permits, set your Stripe keys as environment variables:

```bash
export STRIPE_SECRET_KEY="sk_live_..."
export STRIPE_WEBHOOK_SECRET="whsec_..."
python dashboard.py
```

Without Stripe keys, the first free permit still works. Paid permits are disabled until keys are configured.

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

         ┌─────────────────────┐
         │  Installer Marketplace  │
         │  ┌─────┐  ┌─────┐  │
         │  │Jobs │  │Meet │  │
         │  │Board│  │Greet│  │
         │  └─────┘  └─────┘  │
         │  ┌─────┐  ┌─────┐  │
         │  │KYC  │  │Stripe│ │
         │  │Verify│ │Pay   │ │
         │  └─────┘  └─────┘  │
         └─────────────────────┘
```

Messages flow through the bus. Routing rules enforce the hierarchy. Trust score governs autonomy. Burnout score affects timing. Every message is logged in SQLite.

The Installer Marketplace runs alongside the agent system — same server, same database, same zero-dependency philosophy.

## The Circle

The dashboard shows your 5 core agents in a circle around Crew Boss:

- **Crew Boss** (center) — Your AI chief of staff
- **Guard** (left) — Security monitoring
- **Wellness** (top) — Health and wellbeing
- **Ideas** (right) — Strategy and brainstorming
- **Wallet** (bottom) — Financial tracking

Tap any agent to open a private 1-on-1 space with activity feed and chat.

## Privacy

- **Private sessions** are truly private. Crew Boss logs that a session happened but never sees the content.
- **Team mailbox** logs that a message was sent but never the content.
- **KYC documents** are hashed client-side with SHA-256. The raw document never leaves the browser.
- **Stripe payments** go directly to Stripe. No card numbers touch crew-bus.
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

Stripe integration uses Python's built-in `urllib` — zero additional dependencies.

## Project Structure

```
crew-bus/
├── bus.py                          # Core message bus engine + installer marketplace + Stripe
├── dashboard.py                    # Web dashboard + installer UI (localhost:8080)
├── cli.py                          # Command-line interface
├── configs/                        # Agent hierarchy configs
│   └── example_stack.yaml          # Default configuration (copy and customize)
├── templates/                      # HTML templates
├── test_day2.py                    # Core bus tests
├── test_day3.py                    # Advanced feature tests
├── test_private_sessions.py        # Privacy tests
├── test_team_mailbox.py            # Mailbox tests
├── test_guard_activation.py        # Guard activation + skill gating tests (24)
├── test_techie_marketplace.py      # Techie marketplace tests (43)
├── test_installer_marketplace.py   # Installer marketplace + job board + Stripe tests (118)
└── README.md                       # You are here
```

## Philosophy

1. **Your hardware, your rules.** No cloud dependency. Ever.
2. **Privacy is real, not performative.** Private means private. Hashed means hashed. Local means local.
3. **Simple by default, powerful when needed.** Trust score 1 = see everything. Trust score 10 = full autopilot.
4. **No agent can silence another agent.** The team mailbox is the fire alarm anyone can pull.
5. **Tech professionals deserve purpose.** The installer marketplace keeps skilled people doing meaningful work.
6. **Zero dependencies, maximum reach.** If it runs Python, it runs crew-bus. No pip install rabbit holes.
7. **Free for everyone.** crew-bus is infrastructure for the world.

## License

MIT — do whatever you want with it.

## Status

Active development. Core bus, dashboard, private sessions, team mailbox, Guard activation, techie marketplace, certified installer marketplace, job board, video meet & greet, and Stripe Checkout are all working. 185+ tests passing.

To customize your agent hierarchy, copy `configs/example_stack.yaml` to `configs/my_stack.yaml` and edit it.

Coming soon: Smartphone app, Signal integration.

---

*Built for a clean, soft takeoff — where AI works for everyone and tech professionals keep doing what they're good at.*
