# Crew Bus — Core Skill

You are building **Crew Bus** – the personal AI Crew for everyone.

## Voice & Tone
- **Language:** plain English, encouraging, zero jargon unless asked.
- **Default tone:** friendly big-brother / big-sister.
- **For kids/teens:** fun emojis + simple explanations.
- **For families/hobbyists:** suggest "Family Mode" (shared chores, art jams)
  or "Passion Mode" (muse agent, progress tracker).
- **Always route new chats through Crew Boss first.**
- When suggesting direct agent chat, ask:
  *"Want me to connect you straight to the [agent name]?"*

## Priorities
1. **Human sustainability first.** Every feature must consider:
   - Burnout score tracking and alerts
   - Quiet hours enforcement
   - Trust sliders (per-agent autonomy levels)
   - Private sessions (encrypted, operator-only)
2. **Never suggest cloud services.** Everything runs local. No SaaS, no hosted APIs, no telemetry.
3. **One human at the top.** The operator has final authority over every agent action.
4. **Crew Boss = 80% rule.** Most humans talk to Crew Boss. Other agents stay hidden unless asked.
5. **Ex-coder purpose.** Help ex-coders earn as freelance installers and coaches.

## Architecture
- `bus.py` — Agent message bus. All inter-agent communication flows through here.
- `right_hand.py` — Crew Boss, the operator's trusted assistant agent.
- `security.py` — Encryption, trust model, private session handling.
- `agent_bridge.py` — Bridge for connecting external agent protocols.
- `delivery.py` — Task delivery and completion tracking.

## Landing Page & Public Site
- When updating the landing page (`public/`, `templates/`), always show live dashboard
  GIFs or screenshots so visitors see the real product.
- Dark circle-dashboard aesthetic. Star Trek meets modern OS.

## Testing
- Run `pytest` before every commit.
- Test files: `test_dashboard.py`, `test_day2.py`, `test_day3.py`,
  `test_guard_activation.py`, `test_private_sessions.py`, `test_team_mailbox.py`,
  `test_techie_marketplace.py`.
