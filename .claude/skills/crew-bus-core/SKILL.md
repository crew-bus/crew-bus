# Crew Bus — Core Skill

You are building **Crew Bus** – the sovereign multi-agent OS.

## Priorities
1. **Human sustainability first.** Every feature must consider:
   - Burnout score tracking and alerts
   - Quiet hours enforcement
   - Trust sliders (per-agent autonomy levels)
   - Private sessions (encrypted, operator-only)
2. **Never suggest cloud services.** Everything runs local. No SaaS, no hosted APIs, no telemetry.
3. **One human at the top.** The operator has final authority over every agent action.

## Architecture
- `bus.py` — Agent message bus. All inter-agent communication flows through here.
- `right_hand.py` — The operator's trusted assistant agent.
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
