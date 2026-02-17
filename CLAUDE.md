# Crew Bus — Sovereign Multi-Agent OS

**One human always at the top.** Every agent answers to the operator.

## Principles
- 100% local-first. MIT license. No cloud services, ever.
- Human sustainability: burnout score, quiet hours, trust sliders, private sessions.
- Visual style: dark, circle-dashboard aesthetic (Star Trek meets modern OS).

## Dev Workflow
- Always run `pytest` before committing.
- Use conventional commits: `feat:`, `fix:`, `chore:`, `tweak:`, `ci:`, etc.
- Keep Python files in repo root (flat structure).
- Landing page / public site lives in `public/` and `templates/`.

## Skills (see details in each)
- `.claude/skills/crew-bus-core/` — core OS architecture & agent bus
- `.claude/skills/dashboard-ui/` — dashboard & landing page visuals
- `.claude/skills/security/` — encryption, private sessions, trust model

## Key Files
- `bus.py` — the agent message bus (core)
- `dashboard.py` — Textual TUI dashboard
- `security.py` — encryption & trust layer
- `test_*.py` — test suite (run with `pytest`)
