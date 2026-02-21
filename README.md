# 🚌 crew-bus

**Your agents. Your hardware. Your rules.**

crew-bus is open-source software that runs on your own machine and lets your AI agents work together as a coordinated team — no cloud dependency, no API subscriptions, no data leaving your network.

> Most agent frameworks send your data to someone else's servers and charge you monthly for the privilege. crew-bus runs locally, costs $29 once, and puts a security Guardian between your agents and the outside world.

[![GitHub release](https://img.shields.io/github/v/release/crew-bus/crew-bus)](https://github.com/crew-bus/crew-bus/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-222%20passing-brightgreen)](#)

---

## Why crew-bus?

Setting up a team of AI agents today is painful. You download a framework, wrestle with config files, wire up message routing, figure out which agent talks to which, pray nothing breaks — and your data flows through someone else's cloud the whole time.

crew-bus takes a different approach:

- **Runs on your hardware.** Your laptop, your desktop, your home server. Your data never leaves your network unless you tell it to.
- **Works out of the box.** Three agents in a triangle — Crew Boss, Guardian, Vault — ready to go in minutes, not hours.
- **Built-in security from day one.** The Guardian agent controls all external access, vets every skill before install, and monitors everything in real time. No other agent framework ships with an immune system.
- **One price, forever.** $29 lifetime Guardian Activation key. No subscriptions. No per-token charges. No surprise bills.

---

## How It Works

```
         ┌──────────┐
         │Crew Boss │  ← your AI right-hand
         └──┬───┬───┘
            │   │
   ┌────────┘   └────────┐
   │                      │
┌──┴───────┐       ┌──────┴──┐
│ Guardian │       │  Vault  │
│ protects │       │remembers│
└──────────┘       └─────────┘
```

**Boss talks, Guard protects, Vault remembers.**

**Crew Boss** sits at the top and coordinates everything. Your AI right-hand — handles 80% of what you need so you can focus on living. Every message flows through the bus — agents don't talk directly to each other, they talk through the system.

**Guardian** is the gatekeeper. It controls web access, vets skills for safety, monitors runtime health, and auto-quarantines anything that degrades. Your crew's immune system.

**Vault** is your private journal and life-data agent. It remembers everything — moods, goals, money notes, relationship changes, dreams, wins, fears. Never nags, never checks in. Only speaks when spoken to. Like a journal that writes back.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus

# Install dependencies
pip install -r requirements.txt

# Start crew-bus
python3 dashboard.py
```

Open `http://localhost:8420` and you're running. Three agents in a triangle, ready to coordinate.

To unlock Guardian features (web search, Skill Store, Skill Sandbox), grab a [$29 lifetime activation key at crew-bus.dev](https://crew-bus.dev).

---

## Features

### Core (Free & Open Source)
- **3 coordinated agents** — Crew Boss (right-hand), Guardian (security), Vault (private journal)
- **Hierarchical message routing** — every message flows through the bus
- **Private sessions** — isolated conversations per agent
- **Team mailboxes** — agents can send structured messages to each other
- **Local-first** — runs entirely on your machine
- **Dashboard** — web UI to monitor and interact with your crew
- **Expandable** — spawn additional teams and agents when you need them

### Guardian Activation ($29 lifetime)

#### 🔍 Web Search
Every agent can search the internet and read URLs. Powered by DuckDuckGo — no API key needed, zero external dependencies. Internal IPs are blocked. Guardian controls all access.

#### 🏪 Skill Store
20 curated skills across 10 categories — creative writing, homework help, budget tracking, meal planning, music production, lead finding, fitness planning, data analysis, and more. Guardian analyzes what an agent needs, recommends the best skill, vets it for safety, and installs it. Community skills from trusted HTTPS sources also supported.

#### 🛡️ Skill Sandbox
Guardian monitors every installed skill in real time:
- **Health scoring** (0–100) per skill
- **Error rate tracking** and charter violation detection
- **Automatic quarantine** for degraded skills
- **Restore with re-vetting** before reinstall
- **Full audit trail** of every action

---

## crew-bus vs. The Alternatives

| | **crew-bus** | **CrewAI** | **AutoGen** | **LangGraph** |
|---|---|---|---|---|
| **Runs locally** | ✅ Your hardware, your data | ❌ Cloud-first, AMP platform | ⚠️ Possible but not default | ⚠️ Requires setup |
| **Built-in security agent** | ✅ Guardian monitors everything | ❌ No equivalent | ❌ No equivalent | ❌ No equivalent |
| **Skill marketplace** | ✅ 20 curated + community skills | ❌ Manual tool setup | ❌ Manual tool setup | ❌ Manual tool setup |
| **Runtime skill monitoring** | ✅ Health scores, auto-quarantine | ❌ None | ❌ None | ❌ None |
| **Setup time** | Minutes | Hours | Hours | Hours |
| **Pricing** | $29 once (core is free) | Free OSS / Enterprise $$$  | Free OSS | Free OSS |
| **Target user** | Individuals, small teams | Enterprise dev teams | Researchers, developers | Advanced developers |
| **Dependencies** | Python + your LLM | Python + UV + cloud APIs | Python + cloud APIs | Python + LangChain ecosystem |

### The real difference

CrewAI, AutoGen, and LangGraph are powerful frameworks built for developers who want to code agent systems from scratch. They assume you'll wire everything together yourself.

**crew-bus is built for people who want agents working together *today*.** You get a pre-configured crew, a security layer, a skill marketplace, and a dashboard — all running on your own machine. No PhD in prompt engineering required.

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
┌─────────────────────────────────────────┐
│              Dashboard (Web UI)          │
├─────────────────────────────────────────┤
│              API Layer (stdlib)          │
├─────────────────────────────────────────┤
│           Agent Worker Engine            │
│  ┌─────────────────────────────────┐    │
│  │  Crew Boss  │ Guardian │  Vault │    │
│  └─────────────────────────────────┘    │
├─────────────────────────────────────────┤
│  Guardian Layer                         │
│  ┌──────────┬───────────┬───────────┐   │
│  │Web Bridge│Skill Store│  Sandbox  │   │
│  └──────────┴───────────┴───────────┘   │
├─────────────────────────────────────────┤
│           SQLite (Local DB)             │
└─────────────────────────────────────────┘
```

Everything runs in a single process on your machine. No Docker required. No cloud services. No external databases.

---

## Roadmap

- [ ] Voice interface — talk to your crew
- [ ] Mobile companion app
- [ ] Plugin SDK — build and share your own skills
- [ ] Multi-machine crew networking (LAN)
- [ ] WhatsApp & Telegram bridge for on-the-go access

---

## Contributing

crew-bus is open source and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT — use it however you want.

---

## Links

- **Website:** [crew-bus.dev](https://crew-bus.dev)
- **GitHub:** [github.com/crew-bus/crew-bus](https://github.com/crew-bus/crew-bus)
- **Releases:** [Latest Release](https://github.com/crew-bus/crew-bus/releases/latest)
- **Activation Keys:** [crew-bus.dev](https://crew-bus.dev) ($29 lifetime)

---

*Built by one person who got tired of agent frameworks that make simple things complicated.*
*crew-bus — your agents, your hardware, your rules.*
