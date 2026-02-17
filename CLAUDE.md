# Crew Bus — Personal AI Crew for Everyone

Crew Bus is the personal AI Crew for everyone — kids, teens, moms, dads,
families, artists, hobbyists, small businesses, startups, ex-coders.
Every human gets their own local Crew Bus — private, sovereign.
Crew Boss is the friendly right-hand assistant you talk to 80% of the time.
All other agents stay hidden unless the human asks to talk directly.
One human always in charge. 100% local, MIT license, no cloud ever.
Make everything simple, warm, fun first — then powerful.
Help ex-coders earn as freelance installers/coaches.
Passion crews welcome: art, music, hobbies, whatever lights you up.

## Dev Workflow
- Always run `pytest` before committing.
- Conventional commits: `feat:`, `fix:`, `chore:`, `tweak:`, `ci:`, etc.
- Python files in repo root (flat). Public site in `public/` & `templates/`.

## Skills → see details in each
- `.claude/skills/crew-bus-core/` — core OS, agent bus, Crew Boss
- `.claude/skills/dashboard-ui/` — dashboard & landing page visuals
- `.claude/skills/security/` — encryption, private sessions, trust model

## Key Files
- `bus.py` — agent message bus | `dashboard.py` — TUI dashboard
- `security.py` — encryption & trust | `test_*.py` — run with `pytest`
