"""
crew-bus Personal Edition Dashboard.

Mobile-first circle UI. 5 core agents orbiting Crew Boss.
Built on Python stdlib http.server — no frameworks.

Port 8080 by default.

Pages (SPA — single HTML page, JS-routed):
  /              -> Main Circle (5 agents, trust, burnout, teams)
  /messages      -> Message Feed (legacy, still works)
  /decisions     -> Decisions (legacy, still works)
  /audit         -> Audit Trail (legacy, still works)
  /team/<name>   -> Team Dashboard (hierarchy view for a team)

API — all existing endpoints preserved, plus new ones:
  GET  /api/stats                    -> summary stats
  GET  /api/agents                   -> all agents
  GET  /api/agents?period=today|3days|week|month -> with time-filtered counts
  GET  /api/agent/<id>               -> single agent detail
  GET  /api/agent/<id>/activity      -> recent activity feed
  GET  /api/agent/<id>/chat          -> chat history
  POST /api/agent/<id>/chat          -> send message in private chat
  GET  /api/teams                    -> teams list
  POST /api/teams                    -> create team from template
  GET  /api/teams/<id>               -> team detail
  GET  /api/teams/<id>/agents        -> agents belonging to a team
  GET  /api/agent/<id>/private/status  -> active private session info or {}
  POST /api/agent/<id>/private/start  -> start private session
  POST /api/agent/<id>/private/message-> send private message
  POST /api/agent/<id>/private/end    -> end private session
  GET  /api/teams/<id>/mailbox        -> team mailbox messages
  GET  /api/teams/<id>/mailbox/summary-> unread counts for team card indicators
  POST /api/teams/<id>/mailbox/<mid>/read -> mark mailbox message read
  POST /api/mailbox                   -> send to team mailbox (agents/testing)
  GET  /api/guard/checkin             -> latest guard check-in
  GET  /api/messages                  -> message feed
  GET  /api/decisions                 -> decision log
  GET  /api/audit                     -> audit trail
  POST /api/trust                     -> update trust score
  POST /api/burnout                   -> update burnout score
  POST /api/quarantine/<id>           -> quarantine agent
  POST /api/restore/<id>              -> restore agent
  POST /api/decision/<id>/approve     -> approve decision
  POST /api/decision/<id>/override    -> override decision

FREE AND OPEN SOURCE — crew-bus is free infrastructure for the world.
Security Guard module available separately (paid activation key).
"""

import hashlib
import json
import os
import random
import re
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Optional
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))
import bus
import agent_worker

# Stripe integration — optional, only required for public deployment
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_GUARD_PRICE_ID = os.environ.get("STRIPE_GUARD_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://crew-bus.dev")

DEFAULT_PORT = 8080
DEFAULT_DB = bus.DB_PATH

# Agent-type to Personal Edition name mapping
PERSONAL_NAMES = {
    "right_hand": "Crew Boss",
    "security": "Friend & Family Helper",
    "wellness": "Health Buddy",
    "strategy": "Growth Coach",
    "financial": "Life Assistant",
    "creative": "Muse",
    "help": "Help",
    "human": "You",
}

PERSONAL_COLORS = {
    "right_hand": "#ffffff",
    "security": "#4dd0b8",
    "wellness": "#ffab57",
    "strategy": "#66d97a",
    "financial": "#64b5f6",
    "creative": "#b388ff",
}

CORE_TYPES = ("right_hand", "security", "wellness", "strategy", "financial", "creative")

AGENT_ACKS = {
    "right_hand": [
        "Hey! I\u2019m right here with you \U0001F60A What\u2019s on your mind today?",
        "On it! I\u2019ll take care of this for you.",
        "Got it \u2014 leave it with me!",
        "No worries, I\u2019ll handle this.",
    ],
    "security": [
        "I\u2019ll make a note for the family!",
        "Got it \u2014 I\u2019ll keep everyone in the loop.",
        "Added to the family board!",
    ],
    "wellness": [
        "Thanks for sharing that with me \U0001F49A",
        "I hear you. Let\u2019s take care of you first.",
        "Noted \u2014 I\u2019ll check in with you later.",
    ],
    "strategy": [
        "Love that idea! Let me help you grow it \U0001F331",
        "Great thinking \u2014 let\u2019s make a plan.",
        "Noted! I\u2019ll help you take the next step.",
    ],
    "financial": [
        "On it! I\u2019ll add that to your list.",
        "Got it \u2014 I\u2019ll sort this out for you.",
        "No problem, handling the details!",
    ],
    "creative": [
        "Ooh, love it! Let\u2019s make something beautiful \U0001f3a8",
        "Inspiration incoming! I\u2019m on it.",
        "Great idea \u2014 let\u2019s get creative!",
    ],
    "help": [
        "Good question! Check the info above for guidance.",
        "Take a look at the overview above \u2014 it covers most topics.",
        "I\u2019m here to help! The info above should point you in the right direction.",
    ],
    "_default": [
        "Got it! Working on this for you.",
        "No worries \u2014 I\u2019m on it!",
        "Received. I\u2019ll follow up soon.",
    ],
}

# ── CSS ─────────────────────────────────────────────────────────────

CSS = r"""
:root{
  --bg:#0d1117;--sf:#161b22;--bd:#30363d;
  --tx:#e6edf3;--mu:#8b949e;--ac:#58a6ff;
  --gn:#3fb950;--yl:#d29922;--rd:#f85149;
  --or:#d18616;--pr:#bc8cff;--tl:#39d0d0;
  --r:12px;--sh:0 2px 12px rgba(0,0,0,.4);
}
*{margin:0;padding:0;box-sizing:border-box}
html{font-size:16px;-webkit-text-size-adjust:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  background:var(--bg);color:var(--tx);line-height:1.5;
  min-height:100vh;min-height:100dvh;overflow-x:hidden;
  -webkit-tap-highlight-color:transparent;
}
a{color:var(--ac);text-decoration:none}

/* ── Top bar ── */
.topbar{
  position:sticky;top:0;z-index:90;
  background:var(--sf);border-bottom:1px solid var(--bd);
  padding:10px 16px;display:flex;align-items:center;gap:12px;
  min-height:48px;
}
.topbar .brand{font-weight:700;font-size:1rem;color:var(--ac);white-space:nowrap}
.topbar .spacer{flex:1}
.topbar .nav-pill{
  padding:5px 12px;border-radius:20px;font-size:.8rem;
  color:var(--mu);border:1px solid var(--bd);background:transparent;
  cursor:pointer;transition:all .2s;white-space:nowrap;
  min-height:34px;min-width:44px;display:inline-flex;align-items:center;
  justify-content:center;
}
.topbar .nav-pill:hover,.topbar .nav-pill.active{
  color:var(--tx);background:var(--bd);border-color:var(--mu);
}

/* ── Views ── */
.view{display:none;min-height:calc(100vh - 49px);min-height:calc(100dvh - 49px)}
.view.active{display:block}
#view-crew.active{display:flex;flex-direction:column}
#view-crew .main-layout{flex:1}
#view-crew .compose-bar{margin-top:auto}

/* ── Time pills ── */
.time-bar{
  display:flex;gap:6px;justify-content:center;
  padding:16px 16px 0;flex-wrap:wrap;
}
.time-pill{
  padding:6px 16px;border-radius:20px;font-size:.8rem;
  border:1px solid var(--bd);background:transparent;color:var(--mu);
  cursor:pointer;transition:all .2s;min-height:36px;
  display:inline-flex;align-items:center;
}
.time-pill:hover,.time-pill.active{
  color:var(--tx);background:var(--bd);
}

/* ── Circle layout — scales with main-left ── */
.circle-wrap{
  position:relative;width:100%;
  max-width:520px;margin:0 auto;
  aspect-ratio:1;padding:16px;
  overflow:visible;
}
.circle-wrap svg.lines{
  position:absolute;top:0;left:0;width:100%;height:100%;
  pointer-events:none;z-index:1;
}
.circle-wrap svg.lines line{
  stroke-width:1;stroke-dasharray:6 4;opacity:0.18;
}

/* Agent bubble — base */
.bubble{
  position:absolute;z-index:5;
  display:flex;flex-direction:column;align-items:center;
  cursor:pointer;-webkit-tap-highlight-color:transparent;
  transition:transform .35s cubic-bezier(.4,0,.2,1);
}
.bubble:active{transform:scale(.92)!important}
.bubble-circle{
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  position:relative;
  transition:box-shadow .4s cubic-bezier(.4,0,.2,1), transform .35s ease, border-color .35s ease;
  background:var(--sf);border:2px solid var(--bd);
}
.bubble:hover{transform:scale(1.08)}
.bubble:hover .bubble-circle{box-shadow:0 0 30px rgba(255,255,255,.12)}
.bubble-circle .icon{font-size:2rem;filter:drop-shadow(0 0 5px rgba(255,255,255,0.4))}
.bubble-circle .status-dot{
  position:absolute;top:4px;right:4px;width:11px;height:11px;
  border-radius:50%;border:2.5px solid rgba(12,14,22,0.95);
}
.dot-green{background:var(--gn)}
.dot-yellow{background:var(--yl)}
.dot-red{background:var(--rd)}
.bubble-label{
  margin-top:8px;font-size:.78rem;font-weight:700;color:rgba(255,255,255,0.92);
  text-align:center;white-space:nowrap;letter-spacing:0.04em;
  text-shadow:0 1px 6px rgba(0,0,0,0.7);
}
.bubble-count{
  font-size:.62rem;color:var(--ac);margin-top:2px;font-weight:600;
}
.bubble-sub{
  font-size:.55rem;color:var(--mu);margin-top:1px;
  max-width:110px;text-align:center;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;
}

/* ── Crew Boss — dominant center star ── */
.bubble.center .bubble-circle{
  width:150px;height:150px;
  border-color:rgba(255,255,255,0.9);border-width:3px;
  background:rgba(12,14,22,0.95);
  box-shadow:
    0 0 35px rgba(255,255,255,0.30),
    0 0 70px rgba(255,255,255,0.12),
    0 0 110px rgba(255,255,255,0.05),
    inset 0 0 25px rgba(255,255,255,0.04);
  animation:bossGlow 3s ease-in-out infinite;
}
.bubble.center .bubble-circle::after{
  content:'';position:absolute;inset:-10px;border-radius:50%;
  border:1px solid rgba(255,255,255,0.15);
  animation:bossPulse 2.5s ease-in-out infinite;
}
.bubble.center .bubble-circle .icon{font-size:3.2rem;filter:drop-shadow(0 0 12px rgba(255,255,255,0.7))}
.bubble.center .bubble-label{
  font-size:.95rem;color:#fff;font-weight:800;letter-spacing:0.06em;
  text-shadow:0 0 14px rgba(255,255,255,0.4);
}
.bubble.center:hover .bubble-circle{
  box-shadow:
    0 0 45px rgba(255,255,255,0.45),
    0 0 90px rgba(255,255,255,0.18),
    0 0 130px rgba(255,255,255,0.07),
    inset 0 0 30px rgba(255,255,255,0.06);
}
@keyframes bossGlow{
  0%,100%{box-shadow:0 0 35px rgba(255,255,255,0.30),0 0 70px rgba(255,255,255,0.12),0 0 110px rgba(255,255,255,0.05),inset 0 0 25px rgba(255,255,255,0.04)}
  50%{box-shadow:0 0 45px rgba(255,255,255,0.45),0 0 90px rgba(255,255,255,0.18),0 0 130px rgba(255,255,255,0.07),inset 0 0 30px rgba(255,255,255,0.06)}
}
@keyframes bossPulse{
  0%,100%{transform:scale(1);opacity:0.35}
  50%{transform:scale(1.18);opacity:0}
}

/* ── Outer agents — sized for pentagon in ~500px ── */
.bubble.outer .bubble-circle{
  width:100px;height:100px;
  background:rgba(12,14,22,0.9);
  padding:1rem;
}
.bubble.outer .bubble-circle .icon{font-size:2.2rem}
.bubble.outer:hover{transform:scale(1.12)}

/* ── Agent-specific premium neon glows (visible! not subtle) ── */

/* Teal — Friend & Family Helper */
#bubble-family .bubble-circle{
  border-color:#4dd0b8;border-width:2.5px;
  box-shadow:0 0 22px rgba(77,208,184,0.40),0 0 50px rgba(77,208,184,0.16),0 0 80px rgba(77,208,184,0.06);
  animation:breatheTeal 2.5s ease-in-out infinite;
}
#bubble-family:hover .bubble-circle{
  border-color:#6eecd4;
  box-shadow:0 0 35px rgba(77,208,184,0.60),0 0 70px rgba(77,208,184,0.25),0 0 100px rgba(77,208,184,0.10);
}

/* Soft orange — Health Buddy */
#bubble-health .bubble-circle{
  border-color:#ffab57;border-width:2.5px;
  box-shadow:0 0 22px rgba(255,171,87,0.40),0 0 50px rgba(255,171,87,0.16),0 0 80px rgba(255,171,87,0.06);
  animation:breatheOrange 2.5s ease-in-out infinite;
}
#bubble-health:hover .bubble-circle{
  border-color:#ffc580;
  box-shadow:0 0 35px rgba(255,171,87,0.60),0 0 70px rgba(255,171,87,0.25),0 0 100px rgba(255,171,87,0.10);
}

/* Fresh green — Growth Coach */
#bubble-growth .bubble-circle{
  border-color:#66d97a;border-width:2.5px;
  box-shadow:0 0 22px rgba(102,217,122,0.40),0 0 50px rgba(102,217,122,0.16),0 0 80px rgba(102,217,122,0.06);
  animation:breatheGreen 2.5s ease-in-out infinite;
}
#bubble-growth:hover .bubble-circle{
  border-color:#8aeea0;
  box-shadow:0 0 35px rgba(102,217,122,0.60),0 0 70px rgba(102,217,122,0.25),0 0 100px rgba(102,217,122,0.10);
}

/* Clean blue — Life Assistant */
#bubble-life .bubble-circle{
  border-color:#64b5f6;border-width:2.5px;
  box-shadow:0 0 22px rgba(100,181,246,0.40),0 0 50px rgba(100,181,246,0.16),0 0 80px rgba(100,181,246,0.06);
  animation:breatheBlue 2.5s ease-in-out infinite;
}
#bubble-life:hover .bubble-circle{
  border-color:#90caf9;
  box-shadow:0 0 35px rgba(100,181,246,0.60),0 0 70px rgba(100,181,246,0.25),0 0 100px rgba(100,181,246,0.10);
}

/* Warm purple — Muse */
#bubble-muse .bubble-circle{
  border-color:#b388ff;border-width:2.5px;
  box-shadow:0 0 22px rgba(179,136,255,0.40),0 0 50px rgba(179,136,255,0.16),0 0 80px rgba(179,136,255,0.06);
  animation:breathePurple 2.5s ease-in-out infinite;
}
#bubble-muse:hover .bubble-circle{
  border-color:#d0b0ff;
  box-shadow:0 0 35px rgba(179,136,255,0.60),0 0 70px rgba(179,136,255,0.25),0 0 100px rgba(179,136,255,0.10);
}

/* Breathing keyframes — warm visible pulsation */
@keyframes breatheTeal{0%,100%{box-shadow:0 0 22px rgba(77,208,184,0.40),0 0 50px rgba(77,208,184,0.16),0 0 80px rgba(77,208,184,0.06)}50%{box-shadow:0 0 35px rgba(77,208,184,0.60),0 0 70px rgba(77,208,184,0.25),0 0 100px rgba(77,208,184,0.10)}}
@keyframes breatheOrange{0%,100%{box-shadow:0 0 22px rgba(255,171,87,0.40),0 0 50px rgba(255,171,87,0.16),0 0 80px rgba(255,171,87,0.06)}50%{box-shadow:0 0 35px rgba(255,171,87,0.60),0 0 70px rgba(255,171,87,0.25),0 0 100px rgba(255,171,87,0.10)}}
@keyframes breatheGreen{0%,100%{box-shadow:0 0 22px rgba(102,217,122,0.40),0 0 50px rgba(102,217,122,0.16),0 0 80px rgba(102,217,122,0.06)}50%{box-shadow:0 0 35px rgba(102,217,122,0.60),0 0 70px rgba(102,217,122,0.25),0 0 100px rgba(102,217,122,0.10)}}
@keyframes breatheBlue{0%,100%{box-shadow:0 0 22px rgba(100,181,246,0.40),0 0 50px rgba(100,181,246,0.16),0 0 80px rgba(100,181,246,0.06)}50%{box-shadow:0 0 35px rgba(100,181,246,0.60),0 0 70px rgba(100,181,246,0.25),0 0 100px rgba(100,181,246,0.10)}}
@keyframes breathePurple{0%,100%{box-shadow:0 0 22px rgba(179,136,255,0.40),0 0 50px rgba(179,136,255,0.16),0 0 80px rgba(179,136,255,0.06)}50%{box-shadow:0 0 35px rgba(179,136,255,0.60),0 0 70px rgba(179,136,255,0.25),0 0 100px rgba(179,136,255,0.10)}}

/* Trust + Burnout beneath circle */
.indicators{
  display:flex;gap:20px;justify-content:center;
  padding:0 16px 16px;
}
.indicator{
  display:flex;align-items:center;gap:8px;
  background:var(--sf);border:1px solid var(--bd);
  border-radius:var(--r);padding:8px 14px;cursor:pointer;
  transition:border-color .2s;
}
.indicator:hover{border-color:var(--mu)}
.indicator label{font-size:.7rem;color:var(--mu);text-transform:uppercase;letter-spacing:.04em;cursor:pointer}
.indicator .val{font-size:1.1rem;font-weight:700}
.burnout-dot{
  width:12px;height:12px;border-radius:50%;
  display:inline-block;vertical-align:middle;
}

/* ── Trust/Burnout popup ── */
.tb-popup{
  display:none;position:fixed;top:50%;left:50%;
  transform:translate(-50%,-50%);
  z-index:310;background:var(--sf);border:1px solid var(--bd);
  border-radius:var(--r);padding:24px;width:90%;max-width:340px;
  box-shadow:0 8px 32px rgba(0,0,0,.5);
}
.tb-popup.open{display:block}
.tb-popup-overlay{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:305;background:rgba(0,0,0,.5);
}
.tb-popup-overlay.open{display:block}
.tb-popup h3{text-align:center;margin-bottom:16px;font-size:1rem}
.tb-popup label{font-size:.75rem;color:var(--mu);text-transform:uppercase;
  display:block;margin-bottom:6px;margin-top:14px}
.tb-popup .tb-val{
  text-align:center;font-size:2rem;font-weight:700;color:var(--ac);
  margin-bottom:4px;
}
.tb-popup input[type=range]{accent-color:var(--ac);cursor:pointer;width:100%}
.tb-popup .tb-close{
  display:block;margin:18px auto 0;padding:8px 24px;border-radius:20px;
  border:1px solid var(--bd);background:transparent;color:var(--tx);
  cursor:pointer;font-size:.85rem;min-height:40px;
}
.tb-popup .tb-close:hover{background:var(--bd)}

/* ── Teams section ── */
.teams-section{padding:0 16px 24px;max-width:500px;margin:0 auto}
.teams-header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:10px;
}
.teams-header h2{font-size:.9rem;color:var(--mu);font-weight:600}
.btn-add{
  padding:6px 14px;border-radius:20px;font-size:.75rem;
  border:1px solid var(--bd);background:var(--sf);color:var(--ac);
  cursor:pointer;min-height:36px;display:inline-flex;align-items:center;
  transition:all .2s;
}
.btn-add:hover{background:var(--bd)}
.team-card{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:12px 14px;margin-bottom:8px;display:flex;align-items:center;
  gap:12px;cursor:pointer;transition:border-color .2s;min-height:52px;
}
.team-card:hover{border-color:var(--ac)}
.team-icon{font-size:1.3rem}
.team-info{flex:1}
.team-name{font-size:.85rem;font-weight:600}
.team-meta{font-size:.7rem;color:var(--mu)}

/* ── Team Dashboard view ── */
.team-dash{padding:16px;max-width:500px;margin:0 auto}
.team-dash-header{
  display:flex;align-items:center;gap:12px;margin-bottom:20px;
}
.team-dash-back{
  width:44px;height:44px;border-radius:50%;border:1px solid var(--bd);
  background:transparent;color:var(--tx);font-size:1.2rem;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
}
.team-dash-title{font-weight:700;font-size:1.2rem;flex:1}
.team-hierarchy{position:relative;padding:16px 0}
.team-mgr-wrap{text-align:center;margin-bottom:16px}
.team-mgr-bubble{
  display:inline-flex;flex-direction:column;align-items:center;
  cursor:pointer;transition:transform .2s;
}
.team-mgr-bubble:active{transform:scale(.94)}
.team-mgr-circle{
  width:80px;height:80px;border-radius:50%;background:var(--sf);
  border:2.5px solid var(--ac);display:flex;align-items:center;
  justify-content:center;font-size:1.6rem;position:relative;
  transition:box-shadow .3s;
}
.team-mgr-bubble:hover .team-mgr-circle{box-shadow:0 0 20px rgba(88,166,255,.2)}
.team-mgr-label{margin-top:6px;font-size:.85rem;font-weight:600;color:var(--tx)}
.team-mgr-sub{font-size:.7rem;color:var(--mu)}
.team-line-svg{display:block;margin:0 auto;width:100%;max-width:400px;height:40px}
.team-line-svg line{stroke:var(--bd);stroke-width:1.5;stroke-dasharray:6 4;opacity:.5}
.team-workers{
  display:flex;flex-wrap:wrap;justify-content:center;gap:16px;padding:0 8px;
}
.team-worker-bubble{
  display:flex;flex-direction:column;align-items:center;
  cursor:pointer;transition:transform .2s;width:90px;
}
.team-worker-bubble:active{transform:scale(.94)}
.team-worker-circle{
  width:60px;height:60px;border-radius:50%;background:var(--sf);
  border:2px solid var(--bd);display:flex;align-items:center;
  justify-content:center;font-size:1.2rem;position:relative;
  transition:box-shadow .3s;
}
.team-worker-bubble:hover .team-worker-circle{box-shadow:0 0 16px rgba(88,166,255,.15)}
.team-worker-label{margin-top:4px;font-size:.7rem;font-weight:600;color:var(--mu);text-align:center}
.team-worker-dot{
  position:absolute;top:2px;right:2px;width:8px;height:8px;
  border-radius:50%;border:2px solid var(--sf);
}

/* ── Agent Space (FULL SCREEN mobile, LEFT HALF desktop) ── */
.agent-space{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:200;background:var(--bg);
  flex-direction:column;overflow:hidden;
}
.agent-space.open{display:flex;animation:slideInLeft .25s ease}
.agent-space.closing{animation:slideOutLeft .2s ease forwards}
@keyframes slideInLeft{from{transform:translateX(-100%)}to{transform:translateX(0)}}
@keyframes slideOutLeft{from{transform:translateX(0)}to{transform:translateX(-100%)}}
.as-topbar{
  display:flex;align-items:center;gap:12px;
  padding:12px 16px;background:var(--sf);border-bottom:1px solid var(--bd);
  min-height:52px;flex-shrink:0;
}
.as-back{
  width:44px;height:44px;border-radius:50%;border:1px solid var(--bd);
  background:transparent;color:var(--tx);font-size:1.2rem;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
}
.as-title{font-weight:700;font-size:1rem;flex:1}
.as-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.as-body{
  flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;
  padding:16px;
}

/* Agent space intro */
.as-intro{
  padding:16px;border-radius:var(--r);margin-bottom:16px;
  border:1px solid var(--bd);
}
.as-intro p{font-size:.9rem;color:var(--mu);line-height:1.6}

/* Activity feed */
.activity-feed{margin-bottom:16px}
.activity-feed h3{font-size:.8rem;color:var(--mu);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:8px}
.activity-item{
  padding:10px 14px;background:var(--sf);border:1px solid var(--bd);
  border-radius:var(--r);margin-bottom:6px;font-size:.85rem;
}
.activity-time{font-size:.7rem;color:var(--mu)}
.activity-body{margin-top:4px}

/* Chat interface */
.chat-wrap{
  display:flex;flex-direction:column;
  background:var(--sf);border:1px solid var(--bd);
  border-radius:var(--r);overflow:hidden;
  min-height:200px;max-height:50vh;
}
.chat-msgs{
  flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;
  padding:12px;display:flex;flex-direction:column;gap:8px;
}
.chat-msg{
  max-width:85%;padding:8px 12px;border-radius:14px;
  font-size:.85rem;line-height:1.4;word-break:break-word;
}
.chat-msg.from-agent{
  background:var(--bd);color:var(--tx);align-self:flex-start;
  border-bottom-left-radius:4px;
}
.chat-msg.from-human{
  background:var(--ac);color:#fff;align-self:flex-end;
  border-bottom-right-radius:4px;
}
.chat-msg .chat-time{font-size:.6rem;opacity:.6;margin-top:2px}
.chat-input-row{
  display:flex;border-top:1px solid var(--bd);
}
.chat-input{
  flex:1;padding:14px 16px;border:none;background:transparent;
  color:var(--tx);font-size:1rem;font-family:inherit;
  outline:none;min-height:52px;
}
.chat-send{
  padding:14px 20px;border:none;background:transparent;
  color:var(--ac);font-weight:700;cursor:pointer;font-size:1rem;
  min-width:60px;min-height:52px;transition:background .2s;
  border-radius:0;
}
.chat-send:hover{background:rgba(88,166,255,.1)}

/* ── Template picker modal ── */
.modal-overlay{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:300;background:rgba(0,0,0,.6);align-items:flex-end;
  justify-content:center;
}
.modal-overlay.open{display:flex}
.modal-sheet{
  background:var(--sf);border-top-left-radius:20px;border-top-right-radius:20px;
  width:100%;max-width:500px;max-height:80vh;overflow-y:auto;
  padding:20px 16px 32px;animation:sheetUp .25s ease;
}
@keyframes sheetUp{from{transform:translateY(100%)}to{transform:translateY(0)}}
.modal-sheet h3{text-align:center;margin-bottom:16px;font-size:1rem}
.modal-sheet .handle{
  width:40px;height:4px;background:var(--bd);border-radius:2px;
  margin:0 auto 14px;
}
.template-card{
  padding:14px;background:var(--bg);border:1px solid var(--bd);
  border-radius:var(--r);margin-bottom:8px;cursor:pointer;
  display:flex;align-items:center;gap:12px;
  min-height:56px;transition:border-color .2s;
}
.template-card:hover{border-color:var(--ac)}
.template-icon{font-size:1.5rem}
.template-name{font-weight:600;font-size:.9rem}
.template-desc{font-size:.75rem;color:var(--mu)}

/* ── Override modal ── */
.override-modal{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:300;background:rgba(0,0,0,.6);align-items:center;
  justify-content:center;padding:16px;
}
.override-modal.open{display:flex}
.override-box{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:20px;width:100%;max-width:420px;
}
.override-box h3{margin-bottom:12px}
.override-box textarea{
  width:100%;min-height:80px;background:var(--bg);border:1px solid var(--bd);
  border-radius:8px;color:var(--tx);padding:10px;font-family:inherit;
  font-size:.9rem;resize:vertical;margin-bottom:12px;
}
.override-actions{display:flex;gap:8px;justify-content:flex-end}

/* ── Legacy pages (messages, decisions, audit) ── */
.legacy-container{padding:16px;max-width:900px;margin:0 auto}
.legacy-container h1{font-size:1.3rem;margin-bottom:12px}

/* Filter bar */
.filter-bar{
  display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;align-items:center;
}
.filter-btn{
  padding:5px 12px;border-radius:20px;font-size:.75rem;
  border:1px solid var(--bd);cursor:pointer;
  background:transparent;color:var(--mu);transition:all .2s;
  min-height:34px;
}
.filter-btn:hover,.filter-btn.active{color:var(--tx);background:var(--bd)}
.filter-bar select,.filter-bar input[type=text]{
  padding:5px 10px;border-radius:8px;font-size:.8rem;
  border:1px solid var(--bd);background:var(--sf);color:var(--tx);
  min-height:34px;
}

/* Tables */
table{
  width:100%;border-collapse:collapse;background:var(--sf);
  border:1px solid var(--bd);border-radius:var(--r);
  overflow:hidden;margin-bottom:16px;font-size:.8rem;
}
th{background:var(--bg);text-align:left;font-weight:600;font-size:.7rem;
  text-transform:uppercase;color:var(--mu);letter-spacing:.04em}
th,td{padding:8px 10px;border-bottom:1px solid var(--bd)}
tr:hover td{background:rgba(88,166,255,.04)}
tr.override td{background:rgba(210,153,34,.08)}

.pri-critical{color:var(--rd);font-weight:700}
.pri-high{color:var(--or);font-weight:600}
.pri-normal{color:var(--tx)}
.pri-low{color:var(--mu)}

.stats-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.stat-card{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:8px 12px;text-align:center;min-width:80px;flex:1;
}
.stat-val{font-size:1.2rem;font-weight:700}
.stat-lbl{font-size:.65rem;color:var(--mu);text-transform:uppercase}

/* Buttons */
.btn{
  display:inline-flex;align-items:center;justify-content:center;
  padding:6px 12px;border-radius:8px;font-size:.75rem;font-weight:600;
  border:1px solid var(--bd);cursor:pointer;background:var(--sf);
  color:var(--tx);transition:all .2s;min-height:36px;min-width:44px;
}
.btn:hover{background:var(--bd)}
.btn-danger{border-color:var(--rd);color:var(--rd)}
.btn-danger:hover{background:rgba(248,81,73,.12)}
.btn-success{border-color:var(--gn);color:var(--gn)}
.btn-success:hover{background:rgba(63,185,80,.12)}
.btn-accent{border-color:var(--ac);color:var(--ac)}
.btn-accent:hover{background:rgba(88,166,255,.12)}

/* Badge */
.badge{
  display:inline-block;padding:2px 8px;border-radius:12px;
  font-size:.7rem;font-weight:600;text-transform:uppercase;
}
.badge-active{background:rgba(63,185,80,.12);color:var(--gn)}
.badge-quarantined{background:rgba(209,134,22,.12);color:var(--or)}
.badge-terminated{background:rgba(139,148,158,.12);color:var(--mu)}

/* ── Desktop overrides ── */
@media(min-width:768px){
  .main-layout{
    display:flex;align-items:flex-start;justify-content:flex-start;
    gap:32px;max-width:1100px;margin:0 0 0 60px;padding:24px;
  }
  .main-left{flex:3;min-width:420px;max-width:540px}
  .main-right{flex:1;min-width:200px;max-width:320px}
  .circle-wrap{max-width:540px;aspect-ratio:unset;height:490px}
  /* Agent space: left half on desktop */
  .agent-space{
    width:50%;max-width:520px;
    border-right:1px solid var(--bd);border-left:none;
  }
  .agent-space.open ~ .main-layout{opacity:.5;pointer-events:none}
  .teams-section{padding:0 0 24px}
}

/* Refresh bar */
.refresh-bar{height:2px;background:var(--ac);position:fixed;top:0;left:0;z-index:999;
  transition:width 1s linear;width:0%}

/* ── Private session indicator ── */
.private-toggle{background:none;border:1px solid var(--bd);border-radius:6px;padding:4px 10px;
  color:var(--mu);font-size:.8rem;cursor:pointer;margin-left:8px;transition:all .2s}
.private-toggle:hover{border-color:var(--ac);color:var(--ac)}
.private-toggle.active{background:var(--ac);color:#000;border-color:var(--ac)}
.private-badge{display:inline-block;margin-left:6px;font-size:.7rem;opacity:.7}
.chat-msg.private .chat-time::before{content:'\1F512 ';font-size:.65rem}
.chat-input-row.private-mode{border-color:var(--ac)}
.chat-input-row.private-mode .chat-input{border-color:var(--ac)}

/* ── Mailbox severity indicators ── */
.mailbox-dot-red{background:var(--rd) !important;animation:pulse-red 1.5s infinite}
.mailbox-dot-yellow{background:var(--yl) !important}
.mailbox-dot-blue{background:var(--ac) !important}
@keyframes pulse-red{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.6;transform:scale(1.3)}}
.mailbox-badge{position:absolute;top:-4px;right:-4px;background:var(--ac);color:#000;
  font-size:.6rem;min-width:16px;height:16px;line-height:16px;text-align:center;
  border-radius:50%;font-weight:700}

/* ── Team mailbox section ── */
.mailbox-section{margin-top:16px;padding:16px;background:var(--sf);border-radius:var(--r);border:1px solid var(--bd)}
.mailbox-section h3{font-size:1rem;margin-bottom:10px;color:var(--mu)}
.mailbox-msg{padding:10px;border-radius:8px;margin-bottom:8px;background:var(--bg);
  border-left:4px solid var(--bd);cursor:pointer;transition:background .15s}
.mailbox-msg:hover{background:#1c2128}
.mailbox-msg.severity-code_red{border-left-color:var(--rd)}
.mailbox-msg.severity-code_red .mailbox-severity{color:var(--rd);font-weight:700}
.mailbox-msg.severity-warning{border-left-color:var(--yl)}
.mailbox-msg.severity-warning .mailbox-severity{color:var(--yl)}
.mailbox-msg.severity-info{border-left-color:var(--mu)}
.mailbox-msg-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.mailbox-from{font-weight:600;font-size:.85rem}
.mailbox-severity{font-size:.7rem;text-transform:uppercase;letter-spacing:.5px}
.mailbox-subject{font-size:.85rem;color:var(--tx)}
.mailbox-time{font-size:.7rem;color:var(--mu)}
.mailbox-body{font-size:.8rem;color:var(--mu);margin-top:6px;display:none;white-space:pre-wrap}
.mailbox-msg.expanded .mailbox-body{display:block}
.mailbox-actions{margin-top:6px;display:none;gap:8px}
.mailbox-msg.expanded .mailbox-actions{display:flex}
.mailbox-btn{background:var(--bd);border:none;color:var(--tx);padding:4px 10px;
  border-radius:4px;font-size:.75rem;cursor:pointer}
.mailbox-btn:hover{background:var(--ac);color:#000}
.mailbox-unread{font-weight:700}
.mailbox-read{opacity:.6}

/* ── Compose bar ── */
.compose-bar{
  position:sticky;bottom:0;z-index:80;
  background:var(--sf);border-top:1px solid var(--bd);
  padding:12px 16px;
}
.compose-row{
  display:flex;gap:8px;align-items:center;flex-wrap:wrap;
}
.compose-row select,.compose-row .compose-priority{
  background:var(--bg);color:var(--tx);border:1px solid var(--bd);
  border-radius:6px;padding:6px 10px;font-size:.8rem;
  min-height:36px;appearance:auto;
}
.compose-subject{
  width:100%;margin-top:8px;background:var(--bg);color:var(--tx);
  border:1px solid var(--bd);border-radius:6px;padding:8px 10px;
  font-size:.85rem;font-family:inherit;
}
.compose-body{
  width:100%;margin-top:6px;background:var(--bg);color:var(--tx);
  border:1px solid var(--bd);border-radius:6px;padding:8px 10px;
  font-size:.85rem;font-family:inherit;resize:vertical;
  min-height:2.4em;transition:min-height .2s;
}
.compose-body:focus{min-height:4.8em}
.compose-send{
  background:var(--ac);color:#000;border:none;border-radius:6px;
  padding:6px 18px;font-size:.85rem;font-weight:600;cursor:pointer;
  min-height:36px;white-space:nowrap;
}
.compose-send:hover{opacity:.85}
.compose-send:disabled{opacity:.5;cursor:not-allowed}
.compose-toast{
  position:fixed;bottom:80px;left:50%;transform:translateX(-50%);
  background:var(--gn);color:#000;padding:8px 20px;border-radius:8px;
  font-size:.85rem;font-weight:600;z-index:100;
  opacity:0;transition:opacity .3s;pointer-events:none;
}
.compose-toast.show{opacity:1}
.compose-toast.error{background:var(--rd);color:#fff}
@media(max-width:600px){
  .compose-row{flex-direction:column;align-items:stretch}
  .compose-row select,.compose-row .compose-priority,.compose-send{width:100%}
}
"""

# ── JS ──────────────────────────────────────────────────────────────

JS = r"""
// ── State ──
let currentView='crew';
let timePeriod='today';
let agentsData=[];
let teamsData=[];
let refreshTimer=null;
let elapsed=0;
const REFRESH_SEC=30;
let currentFilters={type:'all',agent:'all'};
let currentAgentSpaceType=null;

// ── Helpers ──
function esc(s){return s==null?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function priBadge(p){return '<span class="pri-'+p+'">'+esc(p)+'</span>'}
function statusBadge(s){return '<span class="badge badge-'+s+'">'+esc(s)+'</span>'}

function timeAgo(ts){
  if(!ts)return '';
  var d=new Date(ts.endsWith&&ts.endsWith('Z')?ts:ts+'Z');
  var sec=Math.floor((Date.now()-d)/1000);
  if(sec<0)sec=0;
  if(sec<60)return sec+'s ago';
  if(sec<3600)return Math.floor(sec/60)+'m ago';
  if(sec<86400)return Math.floor(sec/3600)+'h ago';
  return Math.floor(sec/86400)+'d ago';
}

async function api(path){return(await fetch(path)).json()}
async function apiPost(path,data){
  return(await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data||{})})).json();
}

function dotClass(status,agent_type,checkIn){
  if(status==='quarantined')return 'dot-yellow';
  if(status==='terminated')return 'dot-red';
  if(agent_type==='security'&&checkIn){
    var ago=(Date.now()-new Date(checkIn.endsWith&&checkIn.endsWith('Z')?checkIn:checkIn+'Z'))/60000;
    if(ago>65)return 'dot-yellow';
  }
  return 'dot-green';
}

function burnoutDotColor(score){
  if(score<=3)return 'var(--gn)';
  if(score<=6)return 'var(--yl)';
  return 'var(--rd)';
}

function accentColor(type){
  var m={'right_hand':'#ffffff','security':'#4dd0b8','wellness':'#ffab57','strategy':'#66d97a','financial':'#64b5f6'};
  return m[type]||'#ffffff';
}

function personalName(a){
  var m={'right_hand':'Crew Boss','security':'Friend & Family Helper','wellness':'Health Buddy','strategy':'Growth Coach','financial':'Life Assistant','help':'Help','human':'You'};
  return m[a.agent_type]||a.name||'Agent';
}

// FIX 4: map for display names used in Messages dropdown
var DISPLAY_NAMES={'right_hand':'Crew Boss','security':'Friend & Family Helper','wellness':'Health Buddy','strategy':'Growth Coach','financial':'Life Assistant','help':'Help','human':'You'};
var CORE_TYPES_SET={'right_hand':1,'security':1,'wellness':1,'strategy':1,'financial':1};

// ── Auto-refresh ──
function startRefresh(){
  var bar=document.getElementById('refresh-bar');
  if(refreshTimer)clearInterval(refreshTimer);
  elapsed=0;
  refreshTimer=setInterval(function(){
    elapsed++;
    if(bar)bar.style.width=((elapsed/REFRESH_SEC)*100)+'%';
    if(elapsed>=REFRESH_SEC){
      elapsed=0;if(bar)bar.style.width='0%';
      loadCurrentView();
    }
  },1000);
}

// ── Navigation ──
function showView(name){
  currentView=name;
  document.querySelectorAll('.view').forEach(function(v){v.classList.remove('active')});
  var el=document.getElementById('view-'+name);
  if(el)el.classList.add('active');
  document.querySelectorAll('.topbar .nav-pill').forEach(function(p){
    p.classList.toggle('active',p.dataset.view===name);
  });
  loadCurrentView();
}

function loadCurrentView(){
  if(currentView==='crew')loadCircle();
  else if(currentView==='messages')loadMessages();
  else if(currentView==='decisions')loadDecisions();
  else if(currentView==='audit')loadAudit();
  else if(currentView==='team'){}  // team dash loads separately
}

// ══════════ MAIN CIRCLE ══════════

async function loadCircle(){
  var stats=await api('/api/stats');
  var agents=await api('/api/agents?period='+timePeriod);
  agentsData=agents;

  var boss=agents.find(function(a){return a.agent_type==='right_hand'});
  var guard=agents.find(function(a){return a.agent_type==='security'});
  var well=agents.find(function(a){return a.agent_type==='wellness'});
  var ideas=agents.find(function(a){return a.agent_type==='strategy'});
  var wallet=agents.find(function(a){return a.agent_type==='financial'});
  var muse=agents.find(function(a){return a.agent_type==='creative'});

  var guardCI='';
  try{var cid=await api('/api/guard/checkin');guardCI=cid.last_checkin||''}catch(e){}

  renderBubble('bubble-boss',boss,null);
  renderBubble('bubble-family',guard,null);
  renderBubble('bubble-muse',muse,null);
  renderBubble('bubble-health',well,null);
  renderBubble('bubble-growth',ideas,null);
  renderBubble('bubble-life',wallet,null);

  var trustEl=document.getElementById('trust-val');
  var burnoutDot=document.getElementById('burnout-dot');
  // Update popup sliders too
  var trustSlider=document.getElementById('trust-slider');
  var burnoutSlider=document.getElementById('burnout-slider');
  if(trustEl)trustEl.textContent=stats.trust_score||1;
  if(burnoutDot)burnoutDot.style.background=burnoutDotColor(stats.burnout_score||5);
  if(trustSlider)trustSlider.value=stats.trust_score||1;
  if(burnoutSlider)burnoutSlider.value=stats.burnout_score||5;
  var td=document.getElementById('tb-trust-display');
  if(td)td.textContent=stats.trust_score||1;

  loadTeams();
}

function renderBubble(id,agent,sub){
  var el=document.getElementById(id);
  if(!el)return;
  if(!agent){
    /* Agent not in DB yet — show bubble as-is (static placeholder) */
    var dot=el.querySelector('.status-dot');
    if(dot)dot.className='status-dot dot-yellow';
    return;
  }
  el.onclick=function(){openAgentSpace(agent.id)};
  var dot=el.querySelector('.status-dot');
  if(dot)dot.className='status-dot '+dotClass(agent.status,agent.agent_type,null);
  var countEl=el.querySelector('.bubble-count');
  if(countEl){var c=agent.period_count||agent.unread_count||0;countEl.textContent=c>0?c+' msgs':''}
  var subEl=el.querySelector('.bubble-sub');
  if(subEl)subEl.textContent=sub||'';
}

function setTimePeriod(p,el){
  timePeriod=p;
  document.querySelectorAll('.time-pill').forEach(function(b){b.classList.remove('active')});
  if(el)el.classList.add('active');
  loadCircle();
}

// FIX 3: Trust/Burnout popup instead of old sliders
function openTBPopup(){
  document.getElementById('tb-popup-overlay').classList.add('open');
  document.getElementById('tb-popup').classList.add('open');
}
function closeTBPopup(){
  document.getElementById('tb-popup-overlay').classList.remove('open');
  document.getElementById('tb-popup').classList.remove('open');
}

async function onTrustChange(val){
  var td=document.getElementById('tb-trust-display');
  if(td)td.textContent=val;
  await apiPost('/api/trust',{score:parseInt(val)});
  loadCircle();
}

async function onBurnoutChange(val){
  await apiPost('/api/burnout',{score:parseInt(val)});
  loadCircle();
}

// ══════════ AGENT SPACE ══════════

async function openAgentSpace(agentId){
  var space=document.getElementById('agent-space');
  if(!space)return;
  space.classList.remove('closing');
  space.classList.add('open');
  space.dataset.agentId=agentId;

  // Set name immediately from cache for instant feedback
  var cached=agentsData.find(function(a){return a.id==agentId;});
  if(cached){
    document.getElementById('as-name').textContent=personalName(cached);
    document.getElementById('as-name').style.color=accentColor(cached.agent_type);
  }

  var agent=await api('/api/agent/'+agentId);
  if(!agent||agent.error){agent=cached||{name:'Agent',agent_type:'worker'};}
  var activity=[];try{activity=await api('/api/agent/'+agentId+'/activity');}catch(e){}
  var chat=[];try{chat=await api('/api/agent/'+agentId+'/chat');}catch(e){}

  var color=accentColor(agent.agent_type);
  var name=personalName(agent);
  currentAgentSpaceType=agent.agent_type;

  document.getElementById('as-name').textContent=name;
  document.getElementById('as-name').style.color=color;
  var asDot=document.getElementById('as-status-dot');
  asDot.className='as-dot '+dotClass(agent.status,agent.agent_type,null);

  var intro=document.getElementById('as-intro');
  intro.style.borderColor=color+'44';
  intro.innerHTML='<p>'+esc(agent.description||descFor(agent.agent_type))+'</p>';

  var feedEl=document.getElementById('as-activity');
  if(!activity||activity.length===0){
    feedEl.innerHTML='<h3>Recent Activity</h3><p style="color:var(--mu);font-size:.85rem">Nothing yet.</p>';
  }else{
    feedEl.innerHTML='<h3>Recent Activity</h3>'+activity.map(function(a){
      return '<div class="activity-item"><div class="activity-time">'+timeAgo(a.time)+'</div>'+
        '<div class="activity-body">'+esc(a.summary)+'</div></div>';
    }).join('');
  }

  // FIX 6: personalized placeholder and accent-colored Send button
  var chatInput=document.getElementById('chat-input');
  if(chatInput)chatInput.placeholder='Talk to '+name+'...';
  var sendBtn=document.getElementById('chat-send-btn');
  if(sendBtn)sendBtn.style.color=color;

  renderChat(chat||[]);

  // Check if there's an active private session with this agent
  checkPrivateStatus(agentId);

  // Load Guard activation status and skills for this agent
  loadGuardAndSkills(agentId, agent.agent_type);

  // Start chat auto-refresh polling
  startChatPoll();
}

// ══════════ GUARD ACTIVATION + SKILLS ══════════

async function loadGuardAndSkills(agentId, agentType){
  var guardStatus=await api('/api/guard/status');
  var activated=guardStatus&&guardStatus.activated;

  // Guard-specific section (only on Guard agent card)
  var guardEl=document.getElementById('as-guard-section');
  if(guardEl){
    if(agentType==='security'){
      guardEl.style.display='block';
      if(activated){
        guardEl.innerHTML='<div style="display:flex;align-items:center;gap:8px;padding:12px;background:#1a2e1a;border-radius:8px;border:1px solid #2ea04366">'+
          '<span style="font-size:1.3rem">\u{1F513}</span>'+
          '<div><div style="color:#2ea043;font-weight:600">Guard Active \u2014 Skills Enabled</div>'+
          '<div style="color:var(--mu);font-size:.8rem">\u2705 Activated '+(guardStatus.activated_at?timeAgo(guardStatus.activated_at):'')+'</div></div></div>';
      }else{
        guardEl.innerHTML='<div style="padding:12px;background:#2a2000;border-radius:8px;border:1px solid #d1861644">'+
          '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'+
          '<span style="font-size:1.3rem">\u{1F512}</span>'+
          '<span style="color:#d18616;font-weight:600">Skills Locked</span></div>'+
          '<a href="https://crew-bus.dev/activate" target="_blank" class="btn" style="display:block;text-align:center;background:#d18616;color:#000;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600;margin-bottom:10px;text-decoration:none">Activate Guard \u2014 $5 one-time</a>'+
          '<div style="display:flex;gap:6px"><input id="guard-key-input" type="text" placeholder="Paste activation key here" style="flex:1;background:var(--bg);border:1px solid var(--br);border-radius:6px;padding:6px 10px;color:var(--fg);font-size:.85rem">'+
          '<button onclick="submitGuardKey()" class="btn" style="background:var(--ac);color:#000;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-weight:600">Submit</button></div>'+
          '<div id="guard-key-msg" style="margin-top:6px;font-size:.8rem"></div></div>';
      }
    }else{
      guardEl.style.display='none';
    }
  }

  // Skills section (on every agent card)
  var skillsEl=document.getElementById('as-skills-section');
  if(skillsEl){
    var skills=[];try{skills=await api('/api/skills/'+agentId);}catch(e){}
    var html='<h3>Skills</h3>';
    if(skills&&skills.length>0){
      html+=skills.map(function(s){
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--br)">'+
          '<span style="color:var(--fg)">'+esc(s.skill_name)+'</span>'+
          '<span style="color:var(--mu);font-size:.75rem">'+timeAgo(s.added_at)+'</span></div>';
      }).join('');
    }else{
      html+='<p style="color:var(--mu);font-size:.85rem">No skills added</p>';
    }
    if(activated){
      html+='<button onclick="openAddSkillForm('+agentId+')" class="btn" style="margin-top:8px;background:var(--ac);color:#000;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.85rem">+ Add Skill</button>';
      html+='<div id="add-skill-form" style="display:none;margin-top:8px">'+
        '<input id="new-skill-name" type="text" placeholder="Skill name" style="width:100%;background:var(--bg);border:1px solid var(--br);border-radius:6px;padding:6px 10px;color:var(--fg);font-size:.85rem;margin-bottom:6px">'+
        '<div style="display:flex;gap:6px"><button onclick="submitNewSkill('+agentId+')" class="btn" style="background:#2ea043;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.85rem">Save</button>'+
        '<button onclick="document.getElementById(\'add-skill-form\').style.display=\'none\'" class="btn" style="background:var(--s2);color:var(--fg);border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.85rem">Cancel</button></div>'+
        '<div id="add-skill-msg" style="margin-top:4px;font-size:.8rem"></div></div>';
    }else{
      html+='<p style="color:var(--mu);font-size:.8rem;margin-top:4px">Activate Guard to add skills \u2192</p>';
    }
    skillsEl.innerHTML=html;
  }
}

async function submitGuardKey(){
  var input=document.getElementById('guard-key-input');
  var msg=document.getElementById('guard-key-msg');
  if(!input||!input.value.trim()){if(msg)msg.textContent='Please paste a key.';return;}
  msg.textContent='Verifying...';msg.style.color='var(--mu)';
  var res=await apiPost('/api/guard/activate',{key:input.value.trim()});
  if(res&&res.success){
    msg.textContent=res.message;msg.style.color='#2ea043';
    var agentId=document.getElementById('agent-space').dataset.agentId;
    setTimeout(function(){loadGuardAndSkills(agentId,'security');},500);
  }else{
    msg.textContent=(res&&res.message)||'Activation failed';msg.style.color='#f85149';
  }
}

function openAddSkillForm(agentId){
  document.getElementById('add-skill-form').style.display='block';
  document.getElementById('new-skill-name').focus();
}

async function submitNewSkill(agentId){
  var nameEl=document.getElementById('new-skill-name');
  var msg=document.getElementById('add-skill-msg');
  if(!nameEl||!nameEl.value.trim()){if(msg)msg.textContent='Enter a skill name.';return;}
  var res=await apiPost('/api/skills/add',{agent_id:agentId,skill_name:nameEl.value.trim()});
  if(res&&res.success){
    nameEl.value='';
    document.getElementById('add-skill-form').style.display='none';
    loadGuardAndSkills(agentId,currentAgentSpaceType);
  }else{
    if(msg){msg.textContent=(res&&res.message)||'Failed';msg.style.color='#f85149';}
  }
}

function descFor(type){
  var d={
    'right_hand':'Your friendly right-hand who handles 80% of everything so you don\u2019t have to. The only agent that talks to you directly \u2014 warm, reliable, always has your back.',
    'security':'Shared chores, kid reminders, homework nudges, family calendar \u2014 keeps everyone on the same page without nagging.',
    'wellness':'Watches your energy and wellbeing. Gentle burnout nudges, quiet hours, and steps in if you really need a break \U0001F49A',
    'strategy':'Helps you build great habits, break big ideas into small steps, and grow at your own pace \U0001F331',
    'financial':'Meals, shopping lists, daily logistics, errands, and all the little stuff that keeps life running smoothly \u26A1',
    'help':'Welcome to crew-bus \u2014 your friendly AI crew!\\n\\n' +
      '\u2728 Crew Boss \u2014 Your friendly right-hand. Handles everything, talks to you directly.\\n' +
      '\U0001F3E0 Friend & Family Helper \u2014 Chores, reminders, family calendar.\\n' +
      '\U0001F49A Health Buddy \u2014 Watches your wellbeing. Talk privately using the \U0001F512 button.\\n' +
      '\U0001F331 Growth Coach \u2014 Habits, goals, and personal growth.\\n' +
      '\u26A1 Life Assistant \u2014 Meals, shopping, daily logistics.\\n\\n' +
      'Teams \u2014 Add teams for work, household, or anything you need.\\n\\n' +
      'Trust Score \u2014 Controls how much Crew Boss handles on their own (1 = asks about everything, 10 = full autopilot).\\n' +
      'Burnout \u2014 When high, Crew Boss holds non-urgent messages for better timing.\\n\\n' +
      'Privacy \u2014 The \U0001F512 button starts a private conversation. No other agent can see it.\\n\\n' +
      'crew-bus is free, open source, and runs on your hardware. Your data never leaves your machine.',
  };
  return d[type]||'A helpful member of your crew.';
}

async function openHelpAgent(){
  if(agentsData.length===0) agentsData=await api('/api/agents');
  var help=agentsData.find(function(a){return a.agent_type==='help';});
  if(help) openAgentSpace(help.id);
}

function renderChat(messages){
  var wrap=document.getElementById('as-chat-msgs');
  if(!wrap)return;
  wrap.innerHTML=messages.map(function(m){
    var cls=m.direction==='from_human'?'from-human':'from-agent';
    if(m.private)cls+=' private';
    return '<div class="chat-msg '+cls+'"><div>'+esc(m.text)+'</div>'+
      '<div class="chat-time">'+timeAgo(m.time)+'</div></div>';
  }).join('');
  wrap.scrollTop=wrap.scrollHeight;
}

function closeAgentSpace(){
  stopChatPoll();
  var space=document.getElementById('agent-space');
  space.classList.add('closing');
  setTimeout(function(){space.classList.remove('open','closing')},200);
}
function chatKeydown(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat()}}

// ══════════ TEAMS ══════════

async function loadTeams(){
  teamsData=await api('/api/teams');
  var el=document.getElementById('teams-list');
  if(!el)return;
  if(teamsData.length===0){
    el.innerHTML='<p style="color:var(--mu);font-size:.85rem;text-align:center;padding:12px">No teams yet. Add one to expand your crew.</p>';
    return;
  }
  // FIX 1: team click opens team dashboard instead of messages
  // Fetch mailbox summaries for each team
  var summaryPromises=teamsData.map(function(t){
    return api('/api/teams/'+t.id+'/mailbox/summary').catch(function(){return {unread_count:0,code_red_count:0,warning_count:0}});
  });
  Promise.all(summaryPromises).then(function(summaries){
    el.innerHTML=teamsData.map(function(t,i){
      var s=summaries[i]||{};
      var dotCls='dot-green';
      var badgeHtml='';
      if(s.code_red_count>0){dotCls='mailbox-dot-red'}
      else if(s.warning_count>0){dotCls='mailbox-dot-yellow'}
      else if(s.unread_count>0){dotCls='mailbox-dot-blue';badgeHtml='<span class="mailbox-badge">'+s.unread_count+'</span>'}
      return '<div class="team-card" onclick="openTeamDash('+t.id+')" style="position:relative">'+
        '<span class="team-icon">'+esc(t.icon||'\u{1F4C1}')+'</span>'+
        '<div class="team-info"><div class="team-name">'+esc(t.name)+'</div>'+
        '<div class="team-meta">'+t.agent_count+' agents</div></div>'+
        '<span class="status-dot '+dotCls+'" style="width:8px;height:8px;border-radius:50%;flex-shrink:0;position:relative">'+badgeHtml+'</span></div>';
    }).join('');
  });
}

function openTemplatePicker(){document.getElementById('template-modal').classList.add('open')}
function closeTemplatePicker(){document.getElementById('template-modal').classList.remove('open')}
async function createTeam(name){await apiPost('/api/teams',{template:name});closeTemplatePicker();loadTeams()}

// ══════════ TEAM DASHBOARD (FIX 1) ══════════

async function openTeamDash(teamId){
  // Switch to team view
  currentView='team';
  document.querySelectorAll('.view').forEach(function(v){v.classList.remove('active')});
  document.getElementById('view-team').classList.add('active');
  document.querySelectorAll('.topbar .nav-pill').forEach(function(p){p.classList.remove('active')});

  try{
    var team=await api('/api/teams/'+teamId);
    var teamAgents=await api('/api/teams/'+teamId+'/agents');
  }catch(e){
    document.getElementById('team-dash-content').innerHTML='<p style="color:var(--mu)">Could not load team.</p>';
    return;
  }

  var mgr=teamAgents.find(function(a){return a.agent_type==='manager'});
  var workers=teamAgents.filter(function(a){return a.agent_type!=='manager'});

  var html='<div class="team-dash-header">'+
    '<button class="team-dash-back" onclick="showView(\'crew\')">\u2190</button>'+
    '<span class="team-dash-title">'+esc(team.name)+'</span>'+
    '<span class="badge badge-active">'+team.agent_count+' agents</span></div>';

  // Manager bubble
  if(mgr){
    html+='<div class="team-mgr-wrap"><div class="team-mgr-bubble" onclick="openAgentSpace('+mgr.id+')">'+
      '<div class="team-mgr-circle">\u{1F464}<span class="status-dot '+dotClass(mgr.status,mgr.agent_type,null)+'" style="position:absolute;top:3px;right:3px;width:10px;height:10px;border-radius:50%;border:2px solid var(--sf)"></span></div>'+
      '<span class="team-mgr-label">'+esc(mgr.name)+'</span>'+
      '<span class="team-mgr-sub">Manager</span></div></div>';
  }

  // SVG connector lines
  if(workers.length>0&&mgr){
    var svgW=Math.min(workers.length*100,400);
    var cx=svgW/2;
    html+='<svg class="team-line-svg" viewBox="0 0 '+svgW+' 40" preserveAspectRatio="xMidYMid meet">';
    for(var i=0;i<workers.length;i++){
      var wx=(i+0.5)*(svgW/workers.length);
      html+='<line x1="'+cx+'" y1="0" x2="'+wx+'" y2="40"/>';
    }
    html+='</svg>';
  }

  // Worker bubbles
  html+='<div class="team-workers">';
  workers.forEach(function(w){
    html+='<div class="team-worker-bubble" onclick="openAgentSpace('+w.id+')">'+
      '<div class="team-worker-circle">\u{1F6E0}\uFE0F<span class="team-worker-dot '+dotClass(w.status,w.agent_type,null)+'"></span></div>'+
      '<span class="team-worker-label">'+esc(w.name)+'</span></div>';
  });
  html+='</div>';

  // Mailbox section
  html+='<div class="mailbox-section"><h3>\u{1F4EC} Mailbox</h3><div class="mailbox-msgs" id="mailbox-msgs-'+teamId+'"></div></div>';

  document.getElementById('team-dash-content').innerHTML=html;

  // Load mailbox messages
  var mailboxContainer=document.getElementById('mailbox-msgs-'+teamId);
  if(mailboxContainer)loadTeamMailbox(teamId,mailboxContainer);
}

// ══════════ LEGACY: MESSAGES ══════════

async function loadMessages(){
  if(agentsData.length===0)agentsData=await api('/api/agents');

  // FIX 4: Filter dropdown to core agents (with display names) + team agents only
  var sel=document.getElementById('agent-filter');
  if(sel&&sel.options.length<=1){
    // First add core agents with display names
    var coreOrder=['right_hand','security','wellness','strategy','financial'];
    coreOrder.forEach(function(ctype){
      var a=agentsData.find(function(ag){return ag.agent_type===ctype});
      if(a){
        var o=document.createElement('option');
        o.value=a.name;
        o.textContent=DISPLAY_NAMES[ctype]||a.name;
        sel.appendChild(o);
      }
    });
    // Then add team agents (managers and workers — they have parent agents or are managers)
    agentsData.forEach(function(a){
      if(a.agent_type==='manager'||a.agent_type==='worker'){
        var o=document.createElement('option');
        o.value=a.name;
        o.textContent=a.name;
        sel.appendChild(o);
      }
    });
  }
  var params='?limit=100';
  if(currentFilters.type!=='all')params+='&type='+currentFilters.type;
  if(currentFilters.agent!=='all')params+='&agent='+currentFilters.agent;
  var msgs=await api('/api/messages'+params);
  var tbody=document.getElementById('msg-body');
  if(!tbody)return;
  tbody.innerHTML=msgs.map(function(m){
    return '<tr class="msg-row" onclick="toggleMsgBody(this)" data-body="'+
      esc(m.body).replace(/"/g,'&quot;')+'">'+
      '<td>'+timeAgo(m.created_at)+'</td><td>'+esc(m.from_name)+'</td>'+
      '<td>'+esc(m.to_name)+'</td><td>'+esc(m.message_type)+'</td>'+
      '<td>'+esc(m.subject)+'</td><td>'+priBadge(m.priority)+'</td>'+
      '<td>'+esc(m.status)+'</td></tr>';
  }).join('');
}

function setTypeFilter(type,el){
  currentFilters.type=type;
  document.querySelectorAll('.type-filter').forEach(function(b){b.classList.remove('active')});
  if(el)el.classList.add('active');loadMessages();
}
function setAgentFilter(val){currentFilters.agent=val;loadMessages()}
function toggleMsgBody(row){
  var body=row.dataset.body;if(!body)return;
  var next=row.nextElementSibling;
  if(next&&next.classList.contains('msg-expand')){next.remove();return}
  var tr=document.createElement('tr');tr.className='msg-expand';
  tr.innerHTML='<td colspan="7" style="white-space:pre-wrap;color:var(--mu);font-size:.8rem;padding:10px">'+body+'</td>';
  row.after(tr);
}

// ══════════ LEGACY: DECISIONS ══════════

async function loadDecisions(){
  var decs=await api('/api/decisions?limit=100');
  var tbody=document.getElementById('dec-body');
  if(!tbody)return;
  tbody.innerHTML=decs.map(function(d){
    var ov=d.human_override===1;var cls=ov?' class="override"':'';
    var ov_col=ov?'<span style="color:var(--yl)">YES</span>':
      (d.human_override===0&&d.human_action!==null?'<span style="color:var(--gn)">No</span>':'\u2014');
    var ctx='';
    try{var c=JSON.parse(d.context||'{}');ctx=c.subject||c.message_type||JSON.stringify(c).substring(0,50)}
    catch(e){ctx=String(d.context||'').substring(0,50)}
    var acts='';
    if(d.human_override===null||(d.human_override===0&&d.human_action===null)){
      acts='<button class="btn btn-success" onclick="approveDec('+d.id+');event.stopPropagation()">Approve</button> '+
        '<button class="btn btn-danger" onclick="showOverride('+d.id+');event.stopPropagation()">Override</button>';
    }
    return '<tr'+cls+'><td>'+d.id+'</td><td>'+esc(d.decision_type)+'</td>'+
      '<td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">'+esc(ctx)+'</td>'+
      '<td>'+esc(d.right_hand_action)+'</td><td>'+ov_col+'</td>'+
      '<td>'+timeAgo(d.created_at)+'</td><td>'+acts+'</td></tr>';
  }).join('');
  var total=decs.length;
  var reviewed=decs.filter(function(d){return d.human_override!==null&&d.human_action!==null}).length;
  var overridden=decs.filter(function(d){return d.human_override===1}).length;
  var accuracy=reviewed>0?(((reviewed-overridden)/reviewed)*100).toFixed(0):'\u2014';
  var st=document.getElementById('dec-stats');
  if(st)st.innerHTML=
    '<div class="stat-card"><div class="stat-val">'+total+'</div><div class="stat-lbl">Total</div></div>'+
    '<div class="stat-card"><div class="stat-val" style="color:var(--gn)">'+reviewed+'</div><div class="stat-lbl">Reviewed</div></div>'+
    '<div class="stat-card"><div class="stat-val" style="color:var(--yl)">'+overridden+'</div><div class="stat-lbl">Overridden</div></div>'+
    '<div class="stat-card"><div class="stat-val" style="color:var(--ac)">'+accuracy+'%</div><div class="stat-lbl">Accuracy</div></div>';
}

async function approveDec(id){await apiPost('/api/decision/'+id+'/approve');loadDecisions()}
function showOverride(id){var m=document.getElementById('override-modal');m.dataset.decisionId=id;m.classList.add('open')}
function closeOverride(){document.getElementById('override-modal').classList.remove('open')}
async function submitOverride(){
  var m=document.getElementById('override-modal');
  var note=document.getElementById('override-note').value;
  await apiPost('/api/decision/'+m.dataset.decisionId+'/override',{note:note});
  closeOverride();document.getElementById('override-note').value='';loadDecisions();
}

// ══════════ LEGACY: AUDIT ══════════

let allAudit=[];
async function loadAudit(){allAudit=await api('/api/audit?limit=200');renderAudit(allAudit)}
function renderAudit(data){
  var tbody=document.getElementById('audit-body');if(!tbody)return;
  tbody.innerHTML=data.map(function(e){
    var d='';try{d=typeof e.details==='string'?e.details:JSON.stringify(e.details)}catch(ex){d=''}
    if(d.length>60)d=d.substring(0,60)+'...';
    return '<tr><td>'+e.id+'</td><td>'+esc(e.event_type)+'</td>'+
      '<td>'+esc(e.agent_name||'')+'</td>'+
      '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(d)+'</td>'+
      '<td>'+timeAgo(e.timestamp)+'</td></tr>';
  }).join('');
}
function filterAudit(){
  var q=(document.getElementById('audit-search')||{}).value||'';q=q.toLowerCase();
  if(!q)return renderAudit(allAudit);
  renderAudit(allAudit.filter(function(e){
    return(e.event_type+' '+(e.agent_name||'')+' '+JSON.stringify(e.details)).toLowerCase().indexOf(q)>=0;
  }));
}
function exportAuditCSV(){
  var rows=[['id','event_type','agent_id','agent_name','details','timestamp']];
  allAudit.forEach(function(e){rows.push([e.id,e.event_type,e.agent_id||'',e.agent_name||'',JSON.stringify(e.details||''),e.timestamp])});
  var csv=rows.map(function(r){return r.map(function(c){return '"'+String(c).replace(/"/g,'""')+'"'}).join(',')}).join('\n');
  var b=new Blob([csv],{type:'text/csv'});
  var a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download='crew_bus_audit_'+new Date().toISOString().slice(0,10)+'.csv';a.click();
}

// ══════════ PRIVATE SESSIONS ══════════

let privateSessionActive=false;
let privateSessionId=null;

async function togglePrivateSession(){
  var agentId=document.getElementById('agent-space').dataset.agentId;
  if(privateSessionActive){
    await apiPost('/api/agent/'+agentId+'/private/end');
    privateSessionActive=false;
    privateSessionId=null;
    updatePrivateUI(false);
  }else{
    var res=await apiPost('/api/agent/'+agentId+'/private/start');
    if(res.session_id){
      privateSessionActive=true;
      privateSessionId=res.session_id;
      updatePrivateUI(true);
    }
  }
}

function updatePrivateUI(active){
  var btn=document.getElementById('private-toggle-btn');
  var inputRow=document.querySelector('.chat-input-row');
  var chatInput=document.getElementById('chat-input');
  var name=document.getElementById('as-name').textContent;
  if(btn)btn.classList.toggle('active',active);
  if(inputRow)inputRow.classList.toggle('private-mode',active);
  if(chatInput)chatInput.placeholder=active?'\u{1F512} Private message to '+name+'...':'Talk to '+name+'...';
}

async function sendChat(){
  var input=document.getElementById('chat-input');
  var text=input.value.trim();if(!text)return;
  var agentId=document.getElementById('agent-space').dataset.agentId;
  input.value='';

  // Optimistically show the sent message immediately
  var wrap=document.getElementById('as-chat-msgs');
  if(wrap){
    var bubble=document.createElement('div');
    bubble.className='chat-msg from-human';
    bubble.innerHTML='<div>'+esc(text)+'</div><div class="chat-time">just now</div>';
    wrap.appendChild(bubble);
    wrap.scrollTop=wrap.scrollHeight;
  }

  try{
    if(privateSessionActive&&privateSessionId){
      await apiPost('/api/agent/'+agentId+'/private/message',{text:text});
    }else{
      await apiPost('/api/agent/'+agentId+'/chat',{text:text});
    }
    // Real agent responses arrive asynchronously via bus — chat auto-refresh will pick them up
  }catch(e){
    // If fetch failed, at least the optimistic message is visible
    console.error('sendChat error:',e);
  }
}

async function checkPrivateStatus(agentId){
  try{
    var status=await api('/api/agent/'+agentId+'/private/status');
    if(status&&status.session_id){
      privateSessionActive=true;
      privateSessionId=status.session_id;
      updatePrivateUI(true);
    }else{
      privateSessionActive=false;
      privateSessionId=null;
      updatePrivateUI(false);
    }
  }catch(e){
    privateSessionActive=false;
    privateSessionId=null;
    updatePrivateUI(false);
  }
}

// ══════════ TEAM MAILBOX ══════════

async function loadTeamMailbox(teamId,container){
  try{
    var msgs=await api('/api/teams/'+teamId+'/mailbox');
    if(!msgs||msgs.length===0){
      container.innerHTML='<p style="color:var(--mu);font-size:.85rem;text-align:center;padding:8px">No mailbox messages.</p>';
      return;
    }
    container.innerHTML=msgs.map(function(m){
      var cls='mailbox-msg severity-'+m.severity+(m.read?' mailbox-read':' mailbox-unread');
      return '<div class="'+cls+'" onclick="toggleMailboxMsg(this)">'+
        '<div class="mailbox-msg-header">'+
        '<span class="mailbox-from">'+esc(m.from_agent_name)+'</span>'+
        '<span class="mailbox-severity">'+esc(m.severity.replace('_',' '))+'</span></div>'+
        '<div class="mailbox-subject">'+esc(m.subject)+'</div>'+
        '<div class="mailbox-time">'+timeAgo(m.created_at)+'</div>'+
        '<div class="mailbox-body">'+esc(m.body)+'</div>'+
        '<div class="mailbox-actions">'+
        (m.read?'':'<button class="mailbox-btn" onclick="markMailboxRead(event,'+m.id+','+teamId+')">Mark Read</button>')+
        '<button class="mailbox-btn" onclick="replyFromMailbox(event,'+m.from_agent_id+')">Reply (Private)</button>'+
        '</div></div>';
    }).join('');
  }catch(e){
    container.innerHTML='<p style="color:var(--mu);font-size:.85rem">Could not load mailbox.</p>';
  }
}

function toggleMailboxMsg(el){el.classList.toggle('expanded')}

async function markMailboxRead(event,msgId,teamId){
  event.stopPropagation();
  await apiPost('/api/teams/'+teamId+'/mailbox/'+msgId+'/read');
  var section=event.target.closest('.mailbox-section');
  if(section){
    var container=section.querySelector('.mailbox-msgs');
    if(container)loadTeamMailbox(teamId,container);
  }
}

function replyFromMailbox(event,agentId){
  event.stopPropagation();
  openAgentSpace(agentId);
  setTimeout(function(){togglePrivateSession()},500);
}

// ── Compose bar ──
async function loadComposeAgents(){
  try{
    var agents=await api('/api/compose/agents');
    var sel=document.getElementById('compose-agent');
    if(!sel)return;
    sel.innerHTML='<option value="">To...</option>';
    agents.forEach(function(a){
      var opt=document.createElement('option');
      opt.value=a.name;
      opt.textContent=a.display||a.name;
      sel.appendChild(opt);
    });
  }catch(e){console.error('loadComposeAgents:',e);}
}

function composeToast(msg,isError){
  var el=document.getElementById('compose-toast');
  if(!el)return;
  el.textContent=msg;
  el.className='compose-toast'+(isError?' error':'')+' show';
  setTimeout(function(){el.classList.remove('show')},2500);
}

async function composeSend(){
  var agent=document.getElementById('compose-agent').value;
  var type=document.getElementById('compose-type').value;
  var subject=document.getElementById('compose-subject').value.trim();
  var body=document.getElementById('compose-body').value.trim();
  var priority=document.getElementById('compose-priority').value;
  if(!agent){composeToast('Select a recipient','error');return;}
  if(!subject){composeToast('Enter a subject','error');return;}
  var btn=document.getElementById('compose-send-btn');
  btn.disabled=true;
  try{
    var res=await apiPost('/api/compose',{
      to_agent:agent,message_type:type,subject:subject,body:body,priority:priority
    });
    if(res.ok){
      composeToast('Sent to '+agent);
      document.getElementById('compose-subject').value='';
      document.getElementById('compose-body').value='';
      startRefresh();
    }else{
      composeToast(res.error||'Send failed',true);
    }
  }catch(e){composeToast('Network error',true);}
  finally{btn.disabled=false;}
}

// ── Chat auto-refresh ──
var chatPollTimer=null;
var chatPollCount=0;

function startChatPoll(){
  stopChatPoll();
  chatPollCount=0;
  doChatPoll();
  chatPollTimer=setInterval(doChatPoll,5000);
}

function stopChatPoll(){
  if(chatPollTimer){clearInterval(chatPollTimer);chatPollTimer=null;}
}

async function doChatPoll(){
  var space=document.getElementById('agent-space');
  if(!space||!space.classList.contains('open')){stopChatPoll();return;}
  var agentId=space.dataset.agentId;
  if(!agentId)return;
  try{
    var chat=await api('/api/agent/'+agentId+'/chat');
    var wrap=document.getElementById('as-chat-msgs');
    if(!wrap)return;
    var oldCount=wrap.children.length;
    renderChat(chat);
    if(chat.length>oldCount){wrap.scrollTop=wrap.scrollHeight;}
  }catch(e){}
}

// ── Boot ──
document.addEventListener('DOMContentLoaded',function(){showView('crew');startRefresh();loadComposeAgents()});
"""

# ── HTML ────────────────────────────────────────────────────────────

def _build_html():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>crew-bus</title>
<style>{CSS}</style>
</head>
<body data-page="crew">
<div id="refresh-bar" class="refresh-bar"></div>

<div class="topbar">
  <span class="brand">crew-bus</span>
  <span class="spacer"></span>
  <button class="nav-pill active" data-view="crew" onclick="showView('crew')">Crew</button>
  <button class="nav-pill" data-view="messages" onclick="showView('messages')">Messages</button>
  <button class="nav-pill" data-view="decisions" onclick="showView('decisions')">Decisions</button>
  <button class="nav-pill" data-view="audit" onclick="showView('audit')">Audit</button>
  <button class="nav-pill" onclick="openHelpAgent()" title="Help" style="font-size:1rem;padding:5px 10px">?</button>
</div>

<!-- ══════════ CREW VIEW ══════════ -->
<div id="view-crew" class="view active">
<div class="main-layout">
<div class="main-left">
  <div class="time-bar">
    <button class="time-pill active" onclick="setTimePeriod('today',this)">Today</button>
    <button class="time-pill" onclick="setTimePeriod('3days',this)">3 Days</button>
    <button class="time-pill" onclick="setTimePeriod('week',this)">Week</button>
    <button class="time-pill" onclick="setTimePeriod('month',this)">Month</button>
  </div>
  <div class="circle-wrap">
    <svg class="lines" viewBox="0 0 540 490" preserveAspectRatio="xMidYMid meet">
      <!-- 5-point star: center(270,245) to pentagon vertices R=195 -->
      <line x1="270" y1="245" x2="270" y2="50"  stroke="#4dd0b8"/>
      <line x1="270" y1="245" x2="455" y2="185" stroke="#b388ff"/>
      <line x1="270" y1="245" x2="384" y2="403" stroke="#66d97a"/>
      <line x1="270" y1="245" x2="156" y2="403" stroke="#64b5f6"/>
      <line x1="270" y1="245" x2="85"  y2="185" stroke="#ffab57"/>
    </svg>
    <!-- Crew Boss — center star -->
    <div class="bubble center" id="bubble-boss" style="left:50%;top:50%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\u2729</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Crew Boss</span><span class="bubble-count"></span>
    </div>
    <!-- Pentagon: top, upper-right, lower-right, lower-left, upper-left -->
    <div class="bubble outer" id="bubble-family" style="left:50%;top:10.2%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f3e0</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Friend & Family</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-muse" style="left:84.3%;top:37.7%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f3a8</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Muse</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-growth" style="left:71.2%;top:82.2%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f331</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Growth Coach</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-life" style="left:28.8%;top:82.2%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\u26a1</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Life Assistant</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-health" style="left:15.7%;top:37.7%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f49a</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Health Buddy</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
  </div>
  <!-- FIX 3: indicators click opens popup, no more bottom sheet -->
  <div class="indicators">
    <div class="indicator" onclick="openTBPopup()">
      <label>Trust</label><span class="val" id="trust-val" style="color:#fff">5</span>
    </div>
    <div class="indicator" onclick="openTBPopup()">
      <label>Energy</label><span class="burnout-dot" id="burnout-dot" style="background:var(--gn)"></span>
    </div>
  </div>
</div>
<div class="main-right">
  <div class="teams-section">
    <div class="teams-header"><h2>Teams</h2>
      <button class="btn-add" onclick="openTemplatePicker()">+ Add Team</button>
    </div>
    <div id="teams-list"></div>
  </div>
</div>
</div>
<!-- ══════════ COMPOSE BAR ══════════ -->
<div class="compose-bar" id="compose-bar">
  <div class="compose-row">
    <select id="compose-agent"><option value="">To...</option></select>
    <select id="compose-type">
      <option value="task">Task</option>
      <option value="report">Report</option>
      <option value="alert">Alert</option>
      <option value="idea">Idea</option>
    </select>
    <select id="compose-priority" class="compose-priority">
      <option value="normal">Normal</option>
      <option value="high">High</option>
      <option value="critical">Critical</option>
    </select>
    <button class="compose-send" id="compose-send-btn" onclick="composeSend()">Send</button>
  </div>
  <input class="compose-subject" id="compose-subject" placeholder="Subject">
  <textarea class="compose-body" id="compose-body" placeholder="Message body (optional)" rows="2"></textarea>
</div>
<div class="compose-toast" id="compose-toast"></div>
</div>

<!-- FIX 3: Trust/Burnout popup (replaces old bottom-sheet sliders) -->
<!-- IDs trust-slider and burnout-slider kept for test compat -->
<div class="tb-popup-overlay" id="tb-popup-overlay" onclick="closeTBPopup()"></div>
<div class="tb-popup" id="tb-popup">
  <h3>Adjust Settings</h3>
  <label>Trust Score</label>
  <div class="tb-val" id="tb-trust-display">5</div>
  <input type="range" id="trust-slider" min="1" max="10" value="5"
    oninput="document.getElementById('tb-trust-display').textContent=this.value"
    onchange="onTrustChange(this.value)">
  <label>Burnout Score</label>
  <input type="range" id="burnout-slider" min="1" max="10" value="5"
    onchange="onBurnoutChange(this.value)">
  <button class="tb-close" onclick="closeTBPopup()">Done</button>
</div>

<!-- ══════════ AGENT SPACE (FIX 2: full-screen mobile, left-half desktop) ══════════ -->
<div id="agent-space" class="agent-space">
  <div class="as-topbar">
    <button class="as-back" onclick="closeAgentSpace()">\u2190</button>
    <span class="as-title" id="as-name">Agent</span>
    <span class="as-dot dot-green" id="as-status-dot"></span>
    <button class="private-toggle" id="private-toggle-btn" onclick="togglePrivateSession()" title="Toggle private session">\U0001f512</button>
  </div>
  <div class="as-body">
    <div class="as-intro" id="as-intro"></div>
    <div id="as-guard-section" style="display:none;margin-bottom:12px"></div>
    <div id="as-skills-section" style="margin-bottom:12px"></div>
    <div class="activity-feed" id="as-activity"></div>
    <div class="chat-wrap">
      <div class="chat-msgs" id="as-chat-msgs"></div>
      <div class="chat-input-row">
        <input class="chat-input" id="chat-input" placeholder="Talk to this agent..." onkeydown="chatKeydown(event)">
        <button class="chat-send" id="chat-send-btn" onclick="sendChat()">Send</button>
      </div>
    </div>
  </div>
</div>

<!-- ══════════ MESSAGES VIEW ══════════ -->
<div id="view-messages" class="view" data-page="messages">
<div class="legacy-container">
  <h1>Message Feed</h1>
  <div class="filter-bar">
    <button class="filter-btn type-filter active" onclick="setTypeFilter('all',this)">All</button>
    <button class="filter-btn type-filter" onclick="setTypeFilter('report',this)">Reports</button>
    <button class="filter-btn type-filter" onclick="setTypeFilter('task',this)">Tasks</button>
    <button class="filter-btn type-filter" onclick="setTypeFilter('alert',this)">Alerts</button>
    <button class="filter-btn type-filter" onclick="setTypeFilter('escalation',this)">Escalations</button>
    <select id="agent-filter" onchange="setAgentFilter(this.value)"><option value="all">All Agents</option></select>
  </div>
  <table><thead><tr>
    <th>Time</th><th>From</th><th>To</th><th>Type</th><th>Subject</th><th>Priority</th><th>Status</th>
  </tr></thead><tbody id="msg-body"></tbody></table>
</div></div>

<!-- ══════════ DECISIONS VIEW ══════════ -->
<div id="view-decisions" class="view" data-page="decisions">
<div class="legacy-container">
  <h1>Decisions</h1>
  <div id="dec-stats" class="stats-row"></div>
  <table><thead><tr>
    <th>ID</th><th>Type</th><th>Context</th><th>Action</th><th>Override?</th><th>Time</th><th>Actions</th>
  </tr></thead><tbody id="dec-body"></tbody></table>
</div></div>

<!-- ══════════ AUDIT VIEW ══════════ -->
<div id="view-audit" class="view" data-page="audit">
<div class="legacy-container">
  <h1>Audit Trail</h1>
  <div class="filter-bar">
    <input type="text" id="audit-search" placeholder="Search events..." oninput="filterAudit()">
    <button class="btn btn-accent" onclick="exportAuditCSV()">Export CSV</button>
  </div>
  <table><thead><tr>
    <th>ID</th><th>Event</th><th>Agent</th><th>Details</th><th>Time</th>
  </tr></thead><tbody id="audit-body"></tbody></table>
</div></div>

<!-- ══════════ TEAM DASHBOARD VIEW (FIX 1) ══════════ -->
<div id="view-team" class="view" data-page="team">
<div class="legacy-container team-dash" id="team-dash-content"></div>
</div>

<!-- Template picker -->
<div class="modal-overlay" id="template-modal">
  <div class="modal-sheet">
    <div class="handle"></div>
    <h3>Add a Team</h3>
    <div class="template-card" onclick="createTeam('business')"><span class="template-icon">\U0001f3e2</span><div><div class="template-name">Business</div><div class="template-desc">Strategy, Sales, Operations + Workers</div></div></div>
    <div class="template-card" onclick="createTeam('department')"><span class="template-icon">\U0001f3d7\ufe0f</span><div><div class="template-name">New Department</div><div class="template-desc">Manager + Workers</div></div></div>
    <div class="template-card" onclick="createTeam('freelance')"><span class="template-icon">\U0001f4bc</span><div><div class="template-name">Freelance</div><div class="template-desc">Lead Finder, Invoice Bot, Client Follow-up</div></div></div>
    <div class="template-card" onclick="createTeam('sidehustle')"><span class="template-icon">\U0001f4b0</span><div><div class="template-name">Side Hustle</div><div class="template-desc">Market Scout, Content Creator, Sales Tracker</div></div></div>
    <div class="template-card" onclick="createTeam('school')"><span class="template-icon">\U0001f4da</span><div><div class="template-name">School</div><div class="template-desc">Tutor, Research Assistant, Study Planner</div></div></div>
    <div class="template-card" onclick="createTeam('passion')"><span class="template-icon">\U0001f3b8</span><div><div class="template-name">Passion Project</div><div class="template-desc">Project Planner, Skill Coach, Progress Tracker</div></div></div>
    <div class="template-card" onclick="createTeam('household')"><span class="template-icon">\U0001f3e0</span><div><div class="template-name">Household</div><div class="template-desc">Meal Planner, Budget Tracker, Schedule</div></div></div>
    <div class="template-card" onclick="createTeam('custom')"><span class="template-icon">\u2699\ufe0f</span><div><div class="template-name">Custom</div><div class="template-desc">You name it, pick the agents</div></div></div>
    <button class="btn" onclick="closeTemplatePicker()" style="width:100%;margin-top:8px">Cancel</button>
  </div>
</div>

<!-- Override modal -->
<div class="override-modal" id="override-modal">
  <div class="override-box">
    <h3>Override Decision</h3>
    <textarea id="override-note" placeholder="Why are you overriding this?"></textarea>
    <div class="override-actions">
      <button class="btn" onclick="closeOverride()">Cancel</button>
      <button class="btn btn-danger" onclick="submitOverride()">Override</button>
    </div>
  </div>
</div>

<script>{JS}</script>
</body>
</html>"""


PAGE_HTML = _build_html()


# ── API Helpers ─────────────────────────────────────────────────────

def _json_response(handler, data, status=200):
    body = json.dumps(data, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler, html, status=200):
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length))


# ── Data fetchers ──────────────────────────────────────────────────

def _period_to_hours(period):
    return {"today": 24, "3days": 72, "week": 168, "month": 720}.get(period, 24)


def _get_stats(db_path):
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT * FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        rh = conn.execute("SELECT * FROM agents WHERE agent_type='right_hand' LIMIT 1").fetchone()
        agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        decision_count = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
        return {
            "crew_name": (human["name"] + "'s Crew") if human else "Crew",
            "human_name": human["name"] if human else "",
            "human_id": human["id"] if human else None,
            "trust_score": rh["trust_score"] if rh else 1,
            "burnout_score": human["burnout_score"] if human else 5,
            "agent_count": agent_count,
            "message_count": msg_count,
            "decision_count": decision_count,
        }
    finally:
        conn.close()


def _get_agents_api(db_path, period=None):
    conn = bus.get_conn(db_path)
    try:
        hours = _period_to_hours(period) if period else 24
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute("""
            SELECT a.*, p.name AS parent_name,
              (SELECT COUNT(*) FROM messages m
               WHERE m.to_agent_id=a.id AND m.status IN ('queued','delivered')) AS unread_count,
              (SELECT MAX(m2.created_at) FROM messages m2
               WHERE m2.from_agent_id=a.id OR m2.to_agent_id=a.id) AS last_message_time,
              (SELECT COUNT(*) FROM messages m3
               WHERE (m3.from_agent_id=a.id OR m3.to_agent_id=a.id)
               AND m3.created_at>=?) AS period_count
            FROM agents a
            LEFT JOIN agents p ON a.parent_agent_id=p.id
            ORDER BY CASE a.agent_type
              WHEN 'human' THEN 0 WHEN 'right_hand' THEN 1
              WHEN 'security' THEN 2 WHEN 'strategy' THEN 3
              WHEN 'wellness' THEN 4 WHEN 'financial' THEN 5
              WHEN 'legal' THEN 6 WHEN 'knowledge' THEN 7
              WHEN 'communications' THEN 8 WHEN 'manager' THEN 9
              WHEN 'worker' THEN 10 ELSE 11 END, a.name
        """, (cutoff,)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["display_name"] = PERSONAL_NAMES.get(d.get("agent_type"), d["name"])
            results.append(d)
        return results
    finally:
        conn.close()


def _get_agent_detail(db_path, agent_id):
    conn = bus.get_conn(db_path)
    try:
        row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["display_name"] = PERSONAL_NAMES.get(d.get("agent_type"), d["name"])
        d["inbox_unread"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent_id=? AND status IN ('queued','delivered')",
            (agent_id,)).fetchone()[0]
        parent = conn.execute("SELECT name, agent_type FROM agents WHERE id=?",
                              (row["parent_agent_id"],)).fetchone() if row["parent_agent_id"] else None
        d["parent_name"] = PERSONAL_NAMES.get(parent["agent_type"], parent["name"]) if parent else None
        return d
    finally:
        conn.close()


def _get_agent_activity(db_path, agent_id, limit=20):
    conn = bus.get_conn(db_path)
    try:
        rows = conn.execute("""
            SELECT m.id, m.message_type, m.subject, m.body, m.priority, m.created_at,
                   a.name AS to_name, a.agent_type AS to_type
            FROM messages m LEFT JOIN agents a ON m.to_agent_id=a.id
            WHERE m.from_agent_id=?
            ORDER BY m.created_at DESC LIMIT ?
        """, (agent_id, limit)).fetchall()
        return [{"id": r["id"], "type": r["message_type"],
                 "summary": f"[{r['message_type']}] {r['subject']}",
                 "time": r["created_at"],
                 "to": PERSONAL_NAMES.get(r["to_type"], r["to_name"])} for r in rows]
    finally:
        conn.close()


def _get_agent_chat(db_path, agent_id, limit=50):
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return []
        hid = human["id"]
        rows = conn.execute("""
            SELECT m.id, m.from_agent_id, m.subject, m.body, m.created_at, m.private_session_id
            FROM messages m
            WHERE (m.from_agent_id=? AND m.to_agent_id=?)
               OR (m.from_agent_id=? AND m.to_agent_id=?)
            ORDER BY m.created_at ASC LIMIT ?
        """, (hid, agent_id, agent_id, hid, limit)).fetchall()
        return [{"id": r["id"],
                 "direction": "from_human" if r["from_agent_id"] == hid else "from_agent",
                 "text": r["body"] if r["body"] else r["subject"],
                 "time": r["created_at"],
                 "private": r["private_session_id"] is not None} for r in rows]
    finally:
        conn.close()


def _send_chat(db_path, agent_id, text):
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return {"ok": False, "error": "no human agent"}
        agent = conn.execute("SELECT id, agent_type FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            return {"ok": False, "error": "agent not found"}
    finally:
        conn.close()
    try:
        result = bus.send_message(
            from_id=human["id"], to_id=agent_id,
            message_type="task", subject="Chat message",
            body=text, priority="normal", db_path=db_path)
    except (PermissionError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "message_id": result["message_id"]}


def _compose_message(db_path, to_name, message_type, subject, body, priority):
    """Send a message from the human to any agent by name."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute(
            "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
        ).fetchone()
        agent = conn.execute(
            "SELECT id, name, status FROM agents WHERE name=? AND status='active'",
            (to_name,)
        ).fetchone()
        if not human:
            return {"ok": False, "error": "no human agent"}
        if not agent:
            return {"ok": False, "error": f"agent '{to_name}' not found or not active"}
    finally:
        conn.close()

    try:
        result = bus.send_message(
            from_id=human["id"], to_id=agent["id"],
            message_type=message_type, subject=subject,
            body=body, priority=priority, db_path=db_path)
        return {"ok": True, "message_id": result["message_id"], "to": to_name}
    except (PermissionError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def _get_compose_agents(db_path):
    """Return active, messageable agents for the compose dropdown."""
    conn = bus.get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name, agent_type, status FROM agents "
            "WHERE status='active' AND agent_type NOT IN ('human', 'help') "
            "ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    agents = []
    for r in rows:
        if "Flint" in r["name"]:
            continue
        agents.append({
            "id": r["id"],
            "name": r["name"],
            "type": r["agent_type"],
            "display": PERSONAL_NAMES.get(r["agent_type"], r["name"]),
        })
    return agents


def _get_teams(db_path):
    conn = bus.get_conn(db_path)
    try:
        managers = conn.execute("SELECT * FROM agents WHERE agent_type='manager' ORDER BY name").fetchall()
        teams = []
        for mgr in managers:
            workers = conn.execute("SELECT COUNT(*) FROM agents WHERE parent_agent_id=?",
                                   (mgr["id"],)).fetchone()[0]
            teams.append({"id": mgr["id"],
                          "name": mgr["name"].replace("-Manager", "").replace("Manager", "Team"),
                          "icon": "\U0001f3e2", "agent_count": workers + 1,
                          "manager": mgr["name"], "status": mgr["status"]})
        return teams
    finally:
        conn.close()


def _get_team_agents(db_path, team_id):
    """Get all agents belonging to a team (the manager + its workers)."""
    conn = bus.get_conn(db_path)
    try:
        mgr = conn.execute("SELECT * FROM agents WHERE id=? AND agent_type='manager'",
                           (team_id,)).fetchone()
        if not mgr:
            return []
        agents = [dict(mgr)]
        workers = conn.execute("SELECT * FROM agents WHERE parent_agent_id=? ORDER BY name",
                               (team_id,)).fetchall()
        for w in workers:
            agents.append(dict(w))
        return agents
    finally:
        conn.close()


def _create_team(db_path, template):
    return {"ok": True, "template": template, "message": f"Team from '{template}' template queued for setup."}


def _get_guard_checkin(db_path):
    conn = bus.get_conn(db_path)
    try:
        guard = conn.execute("SELECT id FROM agents WHERE agent_type='security' LIMIT 1").fetchone()
        if not guard:
            return {"last_checkin": None}
        row = conn.execute("SELECT timestamp FROM audit_log WHERE agent_id=? ORDER BY timestamp DESC LIMIT 1",
                           (guard["id"],)).fetchone()
        return {"last_checkin": row["timestamp"] if row else None, "guard_id": guard["id"]}
    finally:
        conn.close()


def _get_private_session_status(db_path, agent_id):
    """Get active private session status for human <-> agent."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return None
        session = bus.get_active_private_session(human["id"], agent_id, db_path=db_path)
        return session
    finally:
        conn.close()


def _start_private_session(db_path, agent_id):
    """Start a private session between human and agent."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return {"ok": False, "error": "no human agent"}
    finally:
        conn.close()
    return bus.start_private_session(human["id"], agent_id, channel="web", db_path=db_path)


def _end_private_session(db_path, agent_id):
    """End active private session between human and agent."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return {"ok": False, "error": "no human agent"}
    finally:
        conn.close()
    session = bus.get_active_private_session(human["id"], agent_id, db_path=db_path)
    if not session:
        return {"ok": False, "error": "no active session"}
    return bus.end_private_session(session["id"], ended_by="human", db_path=db_path)


def _send_private_message(db_path, agent_id, text):
    """Send a private message in an active session."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
        if not human:
            return {"ok": False, "error": "no human agent"}
    finally:
        conn.close()
    session = bus.get_active_private_session(human["id"], agent_id, db_path=db_path)
    if not session:
        return {"ok": False, "error": "no active session"}
    return bus.send_private_message(session["id"], human["id"], text, db_path=db_path)


def _get_messages_api(db_path, msg_type=None, agent_name=None, limit=50):
    conn = bus.get_conn(db_path)
    try:
        sql = """SELECT m.*, a1.name AS from_name, a1.agent_type AS from_type,
                        a2.name AS to_name, a2.agent_type AS to_type
            FROM messages m
            LEFT JOIN agents a1 ON m.from_agent_id=a1.id
            LEFT JOIN agents a2 ON m.to_agent_id=a2.id WHERE 1=1"""
        params = []
        if msg_type and msg_type != "all":
            sql += " AND m.message_type=?"
            params.append(msg_type)
        if agent_name and agent_name != "all":
            sql += " AND (a1.name=? OR a2.name=?)"
            params.extend([agent_name, agent_name])
        sql += " ORDER BY m.created_at DESC LIMIT ?"
        params.append(limit)
        results = [dict(r) for r in conn.execute(sql, params).fetchall()]
        for msg in results:
            if msg.get("from_type") in PERSONAL_NAMES:
                msg["from_name"] = PERSONAL_NAMES[msg["from_type"]]
            if msg.get("to_type") in PERSONAL_NAMES:
                msg["to_name"] = PERSONAL_NAMES[msg["to_type"]]
        return results
    finally:
        conn.close()


def _get_decisions_api(db_path, limit=50):
    conn = bus.get_conn(db_path)
    try:
        rows = conn.execute("""SELECT d.*, rh.name AS rh_name, h.name AS human_name
            FROM decision_log d
            LEFT JOIN agents rh ON d.right_hand_id=rh.id
            LEFT JOIN agents h ON d.human_id=h.id
            ORDER BY d.created_at DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_audit_api(db_path, limit=200, agent_name=None):
    conn = bus.get_conn(db_path)
    try:
        sql = "SELECT l.*, a.name AS agent_name, a.agent_type FROM audit_log l LEFT JOIN agents a ON l.agent_id=a.id"
        params = []
        if agent_name and agent_name != "all":
            sql += " WHERE a.name=?"
            params.append(agent_name)
        sql += " ORDER BY l.timestamp DESC LIMIT ?"
        params.append(limit)
        results = []
        for r in conn.execute(sql, params).fetchall():
            entry = dict(r)
            try:
                entry["details"] = json.loads(entry.get("details", "{}"))
            except (json.JSONDecodeError, TypeError):
                entry["details"] = entry.get("details", "")
            if entry.get("agent_type") in PERSONAL_NAMES:
                entry["agent_name"] = PERSONAL_NAMES[entry["agent_type"]]
            results.append(entry)
        return results
    finally:
        conn.close()


# ── Request Handler ─────────────────────────────────────────────────

# ── Auth Helpers ────────────────────────────────────────────────────

def _hash_password(password):
    """Hash a password with a random salt using SHA-256."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt + ":" + h


def _verify_password(password, stored):
    """Verify a password against a stored salt:hash pair."""
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return h == expected


def _get_auth_user(handler):
    """Extract user from Authorization: Bearer token header."""
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    return bus.validate_session(token, db_path=handler.db_path)


# ── Stripe Checkout Helpers ──────────────────────────────────────────

def _generate_activation_key():
    """Generate a unique Guard activation key."""
    raw = secrets.token_hex(16)
    return f"GUARD-{raw[:8].upper()}-{raw[8:16].upper()}-{raw[16:24].upper()}-{raw[24:].upper()}"


def _stripe_create_guard_checkout(handler):
    """Create a Stripe Checkout session for Guard activation."""
    if not STRIPE_AVAILABLE:
        return _json_response(handler, {"error": "Stripe not configured"}, 503)
    if not STRIPE_SECRET_KEY:
        return _json_response(handler, {"error": "Stripe not configured"}, 503)

    stripe.api_key = STRIPE_SECRET_KEY
    try:
        checkout_params = {
            "mode": "payment",
            "success_url": f"{SITE_URL}/activate/success.html?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{SITE_URL}/activate",
            "line_items": [],
        }
        if STRIPE_GUARD_PRICE_ID:
            checkout_params["line_items"].append({
                "price": STRIPE_GUARD_PRICE_ID,
                "quantity": 1,
            })
        else:
            checkout_params["line_items"].append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "crew-bus Security Guard",
                        "description": "Lifetime activation — anomaly detection, threat monitoring, automatic escalation",
                    },
                    "unit_amount": 2000,
                },
                "quantity": 1,
            })

        session = stripe.checkout.Session.create(**checkout_params)
        return _json_response(handler, {"url": session.url})
    except Exception as e:
        return _json_response(handler, {"error": str(e)}, 500)


def _stripe_verify_session(handler, session_id):
    """Verify a completed Stripe Checkout session and return activation key."""
    if not session_id:
        return _json_response(handler, {"error": "missing session_id"}, 400)
    if not STRIPE_AVAILABLE or not STRIPE_SECRET_KEY:
        return _json_response(handler, {"error": "Stripe not configured"}, 503)

    stripe.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            key = _generate_activation_key()
            # Activate guard in the database
            bus.activate_guard(key, db_path=handler.db_path)
            return _json_response(handler, {"activation_key": key, "status": "paid"})
        return _json_response(handler, {"error": "payment not completed", "status": session.payment_status}, 402)
    except Exception as e:
        return _json_response(handler, {"error": str(e)}, 500)


def _stripe_webhook(handler):
    """Handle Stripe webhook events (payment confirmations, etc.)."""
    if not STRIPE_AVAILABLE:
        return _json_response(handler, {"error": "Stripe not configured"}, 503)

    content_length = int(handler.headers.get("Content-Length", 0))
    payload = handler.rfile.read(content_length)
    sig_header = handler.headers.get("Stripe-Signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            return _json_response(handler, {"error": "invalid signature"}, 400)
    else:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return _json_response(handler, {"error": "invalid JSON"}, 400)

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            key = _generate_activation_key()
            bus.activate_guard(key, db_path=handler.db_path)
            # In production: send activation key via email to session customer_email

    return _json_response(handler, {"received": True})


class CrewBusHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB

    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Pages — SPA serves same HTML for all routes
        if path in ("/", "/messages", "/decisions", "/audit") or path.startswith("/team/"):
            return _html_response(self, PAGE_HTML)

        if path == "/api/stats":
            return _json_response(self, _get_stats(self.db_path))
        if path == "/api/agents":
            return _json_response(self, _get_agents_api(self.db_path, period=qs.get("period", [None])[0]))

        m = re.match(r"^/api/agent/(\d+)$", path)
        if m:
            agent = _get_agent_detail(self.db_path, int(m.group(1)))
            return _json_response(self, agent or {"error": "not found"}, 200 if agent else 404)

        m = re.match(r"^/api/agent/(\d+)/activity$", path)
        if m:
            return _json_response(self, _get_agent_activity(self.db_path, int(m.group(1))))

        m = re.match(r"^/api/agent/(\d+)/chat$", path)
        if m:
            return _json_response(self, _get_agent_chat(self.db_path, int(m.group(1))))

        # Private session status
        m = re.match(r"^/api/agent/(\d+)/private/status$", path)
        if m:
            status = _get_private_session_status(self.db_path, int(m.group(1)))
            return _json_response(self, status or {})

        if path == "/api/compose/agents":
            return _json_response(self, _get_compose_agents(self.db_path))

        if path == "/api/teams":
            return _json_response(self, _get_teams(self.db_path))

        m = re.match(r"^/api/teams/(\d+)$", path)
        if m:
            teams = _get_teams(self.db_path)
            team = next((t for t in teams if t["id"] == int(m.group(1))), None)
            return _json_response(self, team or {"error": "not found"}, 200 if team else 404)

        # NEW: team agents endpoint for team dashboard
        m = re.match(r"^/api/teams/(\d+)/agents$", path)
        if m:
            return _json_response(self, _get_team_agents(self.db_path, int(m.group(1))))

        # Team mailbox endpoints
        m = re.match(r"^/api/teams/(\d+)/mailbox/summary$", path)
        if m:
            return _json_response(self, bus.get_team_mailbox_summary(int(m.group(1)), db_path=self.db_path))

        m = re.match(r"^/api/teams/(\d+)/mailbox$", path)
        if m:
            unread = qs.get("unread", ["0"])[0] == "1"
            return _json_response(self, bus.get_team_mailbox(int(m.group(1)), unread_only=unread, db_path=self.db_path))

        if path == "/api/guard/checkin":
            return _json_response(self, _get_guard_checkin(self.db_path))

        if path == "/api/guard/status":
            activated = bus.is_guard_activated(db_path=self.db_path)
            info = bus.get_guard_activation_status(db_path=self.db_path)
            return _json_response(self, {
                "activated": activated,
                "activated_at": info["activated_at"] if info else None,
            })

        m = re.match(r"^/api/skills/(\d+)$", path)
        if m:
            skills = bus.get_agent_skills(int(m.group(1)), db_path=self.db_path)
            return _json_response(self, skills)

        if path == "/api/messages":
            return _json_response(self, _get_messages_api(
                self.db_path, msg_type=qs.get("type", [None])[0],
                agent_name=qs.get("agent", [None])[0],
                limit=int(qs.get("limit", [50])[0])))

        if path == "/api/decisions":
            return _json_response(self, _get_decisions_api(self.db_path, limit=int(qs.get("limit", [50])[0])))

        if path == "/api/audit":
            return _json_response(self, _get_audit_api(
                self.db_path, limit=int(qs.get("limit", [200])[0]),
                agent_name=qs.get("agent", [None])[0]))

        if path == "/api/health":
            return _json_response(self, {"status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "db_path": str(self.db_path)})

        # Stripe checkout session verification — returns activation key
        if path == "/api/checkout/verify":
            session_id = qs.get("session_id", [None])[0]
            return _stripe_verify_session(self, session_id)

        # ── Marketplace API (GET) ──

        if path == "/api/installers":
            postal = qs.get("postal_code", [""])[0]
            country = qs.get("country", [""])[0]
            specialty = qs.get("specialty", [""])[0]
            min_rating = float(qs.get("min_rating", ["0"])[0])
            techies = bus.list_techies(db_path=self.db_path)
            if postal:
                techies = [t for t in techies if t.get("postal_code", "").startswith(postal)]
            if country:
                techies = [t for t in techies if t.get("country", "") == country]
            if specialty:
                techies = [t for t in techies if specialty in (t.get("specialties") or "")]
            if min_rating > 0:
                techies = [t for t in techies if (t.get("rating_avg") or 0) >= min_rating]
            return _json_response(self, {"installers": techies})

        m = re.match(r"^/api/installers/([^/]+)$", path)
        if m and m.group(1) != "signup":
            profile = bus.get_techie_profile(m.group(1), db_path=self.db_path)
            return _json_response(self, profile or {"error": "not found"}, 200 if profile else 404)

        if path == "/api/jobs":
            status_f = qs.get("status", ["open"])[0]
            postal = qs.get("postal_code", [""])[0]
            urgency = qs.get("urgency", [""])[0]
            jobs = bus.list_jobs(status=status_f, postal_code=postal,
                                urgency=urgency, db_path=self.db_path)
            return _json_response(self, {"jobs": jobs})

        m = re.match(r"^/api/jobs/(\d+)$", path)
        if m:
            job = bus.get_job(int(m.group(1)), db_path=self.db_path)
            return _json_response(self, job or {"error": "not found"}, 200 if job else 404)

        if path == "/api/meet-requests":
            user = _get_auth_user(self)
            if not user:
                return _json_response(self, {"error": "unauthorized"}, 401)
            techie_id = qs.get("techie_id", [""])[0]
            requests = bus.list_meet_requests(
                techie_id=techie_id,
                client_user_id=user["user_id"] if not techie_id else None,
                db_path=self.db_path)
            return _json_response(self, {"requests": requests})

        if path == "/api/auth/me":
            user = _get_auth_user(self)
            if not user:
                return _json_response(self, {"error": "unauthorized"}, 401)
            return _json_response(self, {
                "user_id": user["user_id"], "email": user["email"],
                "user_type": user["user_type"], "display_name": user["display_name"],
                "techie_id": user.get("techie_id"),
            })

        _json_response(self, {"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            data = _read_json_body(self)
        except Exception as e:
            return _json_response(self, {"error": f"invalid JSON: {e}"}, 400)

        if path == "/api/trust":
            score = data.get("score")
            if score is None:
                return _json_response(self, {"error": "need score"}, 400)
            score = int(score)
            conn = bus.get_conn(self.db_path)
            try:
                human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
                if not human:
                    return _json_response(self, {"error": "no human agent — load a config first"}, 500)
            finally:
                conn.close()
            try:
                bus.update_trust_score(human["id"], score, db_path=self.db_path)
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)
            return _json_response(self, {"ok": True, "trust_score": score})

        if path == "/api/burnout":
            score = data.get("score")
            if score is None:
                return _json_response(self, {"error": "need score"}, 400)
            score = int(score)
            conn = bus.get_conn(self.db_path)
            try:
                human = conn.execute("SELECT id FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
                if not human:
                    return _json_response(self, {"error": "no human agent — load a config first"}, 500)
            finally:
                conn.close()
            try:
                bus.update_burnout_score(human["id"], score, db_path=self.db_path)
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)
            return _json_response(self, {"ok": True, "burnout_score": score})

        m = re.match(r"^/api/quarantine/(\d+)$", path)
        if m:
            try:
                bus.quarantine_agent(int(m.group(1)), db_path=self.db_path)
                return _json_response(self, {"ok": True, "status": "quarantined"})
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)

        m = re.match(r"^/api/restore/(\d+)$", path)
        if m:
            try:
                bus.restore_agent(int(m.group(1)), db_path=self.db_path)
                return _json_response(self, {"ok": True, "status": "active"})
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)

        m = re.match(r"^/api/decision/(\d+)/approve$", path)
        if m:
            try:
                bus.record_human_feedback(int(m.group(1)), override=False,
                    human_action="approved via dashboard",
                    note="Approved from web dashboard", db_path=self.db_path)
                return _json_response(self, {"ok": True, "decision_id": int(m.group(1)), "action": "approved"})
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)

        m = re.match(r"^/api/decision/(\d+)/override$", path)
        if m:
            note = data.get("note", "Overridden via dashboard")
            try:
                bus.record_human_feedback(int(m.group(1)), override=True,
                    human_action="overridden via dashboard",
                    note=note, db_path=self.db_path)
                return _json_response(self, {"ok": True, "decision_id": int(m.group(1)), "action": "overridden"})
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)

        if path == "/api/compose":
            result = _compose_message(
                self.db_path,
                data.get("to_agent", ""),
                data.get("message_type", "task"),
                data.get("subject", ""),
                data.get("body", ""),
                data.get("priority", "normal"),
            )
            return _json_response(self, result, 201 if result.get("ok") else 400)

        m = re.match(r"^/api/agent/(\d+)/chat$", path)
        if m:
            text = data.get("text", "").strip()
            if not text:
                return _json_response(self, {"error": "need text"}, 400)
            result = _send_chat(self.db_path, int(m.group(1)), text)
            return _json_response(self, result, 201 if result.get("ok") else 400)

        # Private session endpoints
        m = re.match(r"^/api/agent/(\d+)/private/start$", path)
        if m:
            result = _start_private_session(self.db_path, int(m.group(1)))
            return _json_response(self, result, 201 if result.get("session_id") else 400)

        m = re.match(r"^/api/agent/(\d+)/private/message$", path)
        if m:
            text = data.get("text", "").strip()
            if not text:
                return _json_response(self, {"error": "need text"}, 400)
            result = _send_private_message(self.db_path, int(m.group(1)), text)
            return _json_response(self, result, 201 if result.get("ok") else 400)

        m = re.match(r"^/api/agent/(\d+)/private/end$", path)
        if m:
            result = _end_private_session(self.db_path, int(m.group(1)))
            return _json_response(self, result)

        # Team mailbox endpoints
        m = re.match(r"^/api/teams/(\d+)/mailbox/(\d+)/read$", path)
        if m:
            result = bus.mark_mailbox_read(int(m.group(2)), db_path=self.db_path)
            return _json_response(self, result)

        if path == "/api/guard/activate":
            key = data.get("key", "").strip()
            if not key:
                return _json_response(self, {"success": False, "message": "No activation key provided"}, 400)
            success, message = bus.activate_guard(key, db_path=self.db_path)
            return _json_response(self, {"success": success, "message": message},
                                  200 if success else 400)

        if path == "/api/skills/add":
            agent_id = data.get("agent_id")
            skill_name = data.get("skill_name", "").strip()
            skill_config = data.get("skill_config", "{}")
            if not agent_id or not skill_name:
                return _json_response(self, {"success": False, "message": "need agent_id and skill_name"}, 400)
            success, message = bus.add_skill_to_agent(
                int(agent_id), skill_name, skill_config, db_path=self.db_path)
            return _json_response(self, {"success": success, "message": message},
                                  200 if success else 400)

        if path == "/api/mailbox":
            agent_id = data.get("from_agent_id")
            subject = data.get("subject", "")
            body = data.get("body", "")
            severity = data.get("severity", "info")
            if not agent_id or not subject or not body:
                return _json_response(self, {"error": "need from_agent_id, subject, body"}, 400)
            result = bus.send_to_team_mailbox(agent_id, subject, body, severity=severity, db_path=self.db_path)
            return _json_response(self, result, 201 if result.get("ok") else 400)

        if path == "/api/teams":
            return _json_response(self, _create_team(self.db_path, data.get("template", "custom")), 201)

        if path == "/api/message":
            required = ("from_agent", "to_agent", "message_type", "subject", "body")
            missing = [k for k in required if k not in data]
            if missing:
                return _json_response(self, {"error": f"missing: {missing}"}, 400)
            from_ag = bus.get_agent_by_name(data["from_agent"], db_path=self.db_path)
            to_ag = bus.get_agent_by_name(data["to_agent"], db_path=self.db_path)
            if not from_ag:
                return _json_response(self, {"error": f"unknown: {data['from_agent']}"}, 404)
            if not to_ag:
                return _json_response(self, {"error": f"unknown: {data['to_agent']}"}, 404)
            try:
                result = bus.send_message(
                    from_id=from_ag["id"], to_id=to_ag["id"],
                    message_type=data["message_type"],
                    subject=data["subject"], body=data["body"],
                    priority=data.get("priority", "normal"), db_path=self.db_path)
                return _json_response(self, {"ok": True, "message_id": result["message_id"]}, 201)
            except (PermissionError, ValueError) as e:
                return _json_response(self, {"error": str(e)}, 400)

        # Stripe checkout — create session for Guard activation ($20)
        if path == "/api/checkout/guard":
            return _stripe_create_guard_checkout(self)

        # Stripe webhook — handle payment events
        if path == "/api/stripe/webhook":
            return _stripe_webhook(self)

        # ── Auth API (POST) ──

        if path == "/api/auth/signup":
            email = data.get("email", "").strip()
            password = data.get("password", "")
            user_type = data.get("user_type", "client")
            display_name = data.get("display_name", "")
            if not email or not password:
                return _json_response(self, {"error": "email and password required"}, 400)
            if len(password) < 8:
                return _json_response(self, {"error": "password must be at least 8 characters"}, 400)
            if user_type not in ("client", "installer"):
                return _json_response(self, {"error": "user_type must be client or installer"}, 400)
            try:
                user = bus.create_user(email, _hash_password(password),
                                       user_type=user_type, display_name=display_name,
                                       db_path=self.db_path)
                token = bus.create_session(user["id"], db_path=self.db_path)
                return _json_response(self, {"ok": True, "token": token,
                    "user_id": user["id"], "email": email, "user_type": user_type}, 201)
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 409)

        if path == "/api/auth/login":
            email = data.get("email", "").strip()
            password = data.get("password", "")
            if not email or not password:
                return _json_response(self, {"error": "email and password required"}, 400)
            user = bus.get_user_by_email(email, db_path=self.db_path)
            if not user or not _verify_password(password, user["password_hash"]):
                return _json_response(self, {"error": "invalid email or password"}, 401)
            token = bus.create_session(user["id"], db_path=self.db_path)
            return _json_response(self, {"ok": True, "token": token,
                "user_id": user["id"], "email": user["email"],
                "user_type": user["user_type"], "display_name": user["display_name"],
                "techie_id": user.get("techie_id")})

        if path == "/api/auth/logout":
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                bus.delete_session(auth[7:], db_path=self.db_path)
            return _json_response(self, {"ok": True})

        # ── Installer Signup (POST) ──

        if path == "/api/installers/signup":
            display_name = data.get("display_name", "").strip()
            email = data.get("email", "").strip()
            if not display_name or not email:
                return _json_response(self, {"error": "display_name and email required"}, 400)
            import uuid as _uuid
            techie_id = "INST-" + _uuid.uuid4().hex[:12].upper()
            try:
                result = bus.register_techie(techie_id, display_name, email,
                                             db_path=self.db_path)
                # Store extra fields
                conn = bus.get_conn(self.db_path)
                extras = {k: data.get(k, "") for k in
                    ("phone", "bio", "specialties", "country", "postal_code",
                     "service_radius", "service_type", "id_type", "id_hash")}
                for key, val in extras.items():
                    try:
                        conn.execute(
                            f"ALTER TABLE authorized_techies ADD COLUMN {key} TEXT DEFAULT ''")
                    except Exception:
                        pass
                    conn.execute(
                        f"UPDATE authorized_techies SET {key}=? WHERE techie_id=?",
                        (val, techie_id))
                conn.commit()
                conn.close()
                return _json_response(self, {"ok": True, "techie_id": techie_id}, 201)
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 409)

        if path == "/api/installers/profile":
            user = _get_auth_user(self)
            if not user or not user.get("techie_id"):
                return _json_response(self, {"error": "unauthorized"}, 401)
            conn = bus.get_conn(self.db_path)
            for key in ("display_name", "bio", "specialties", "postal_code", "service_radius"):
                if key in data:
                    conn.execute(
                        f"UPDATE authorized_techies SET {key}=? WHERE techie_id=?",
                        (data[key], user["techie_id"]))
            conn.commit()
            conn.close()
            return _json_response(self, {"ok": True})

        # ── Jobs API (POST) ──

        if path == "/api/jobs":
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            if not title or not description:
                return _json_response(self, {"error": "title and description required"}, 400)
            user = _get_auth_user(self)
            result = bus.create_job(
                title=title, description=description,
                needs=data.get("needs", ""),
                postal_code=data.get("postal_code", ""),
                country=data.get("country", ""),
                urgency=data.get("urgency", "standard"),
                budget=data.get("budget", "negotiable"),
                contact_name=data.get("contact_name", ""),
                contact_email=data.get("contact_email", ""),
                posted_by=user["user_id"] if user else None,
                db_path=self.db_path)
            return _json_response(self, result, 201)

        m = re.match(r"^/api/jobs/(\d+)/claim$", path)
        if m:
            user = _get_auth_user(self)
            if not user or not user.get("techie_id"):
                return _json_response(self, {"error": "must be a verified installer"}, 403)
            try:
                result = bus.claim_job(int(m.group(1)), user["techie_id"],
                                       db_path=self.db_path)
                return _json_response(self, result)
            except ValueError as e:
                return _json_response(self, {"error": str(e)}, 400)

        m = re.match(r"^/api/jobs/(\d+)/complete$", path)
        if m:
            result = bus.complete_job(int(m.group(1)), db_path=self.db_path)
            return _json_response(self, result)

        # ── Meet & Greet API (POST) ──

        if path == "/api/meet-requests":
            techie_id = data.get("techie_id", "").strip()
            if not techie_id:
                return _json_response(self, {"error": "techie_id required"}, 400)
            user = _get_auth_user(self)
            result = bus.create_meet_request(
                techie_id=techie_id,
                client_user_id=user["user_id"] if user else None,
                job_id=data.get("job_id"),
                proposed_times=json.dumps(data.get("proposed_times", [])),
                notes=data.get("notes", ""),
                db_path=self.db_path)
            return _json_response(self, result, 201)

        m = re.match(r"^/api/meet-requests/(\d+)/respond$", path)
        if m:
            accept = data.get("accept", False)
            result = bus.respond_meet_request(
                int(m.group(1)), accept=accept,
                accepted_time=data.get("accepted_time", ""),
                meeting_link=data.get("meeting_link", ""),
                db_path=self.db_path)
            return _json_response(self, result)

        _json_response(self, {"error": "not found"}, 404)


# ── Server ──────────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _auto_load_hierarchy(db_path):
    """Load hierarchy from configs/ if DB has no agents.

    Prefers example_stack.yaml if present (default for new installs).
    Falls back to first .yaml/.yml file found.
    """
    conn = bus.get_conn(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    finally:
        conn.close()
    if count > 0:
        return  # already populated
    configs_dir = Path(__file__).parent / "configs"
    if not configs_dir.is_dir():
        return
    # Prefer example_stack.yaml (ships with repo)
    example = configs_dir / "example_stack.yaml"
    if example.is_file():
        bus.load_hierarchy(str(example), db_path=db_path)
        print(f"Auto-loaded config: {example.name}")
        return
    # Fallback: first yaml found
    yamls = sorted(configs_dir.glob("*.yaml")) + sorted(configs_dir.glob("*.yml"))
    if yamls:
        bus.load_hierarchy(str(yamls[0]), db_path=db_path)
        print(f"Auto-loaded config: {yamls[0].name}")


def create_server(port=DEFAULT_PORT, db_path=None, config=None, host="0.0.0.0"):
    if db_path is None:
        db_path = DEFAULT_DB
    bus.init_db(db_path=db_path)
    if config:
        bus.load_hierarchy(config, db_path=db_path)
    else:
        _auto_load_hierarchy(db_path)
    handler = type("Handler", (CrewBusHandler,), {"db_path": db_path})
    return ThreadedHTTPServer((host, port), handler)


def run_server(port=DEFAULT_PORT, db_path=None, config=None, host="0.0.0.0"):
    server = create_server(port=port, db_path=db_path, config=config, host=host)
    actual_db = server.RequestHandlerClass.db_path
    print(f"crew-bus dashboard running on http://{host}:{port}")
    print(f"Database: {actual_db}")

    # Start the AI agent worker (Ollama-powered responses)
    agent_worker.start_worker(db_path=actual_db)

    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        agent_worker.stop_worker()
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="crew-bus Personal Edition Dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--db", type=str, default=None)
    parser.add_argument("--config", type=str, default=None,
                        help="Path to YAML config file (auto-detected from configs/ if omitted)")
    args = parser.parse_args()
    db = Path(args.db) if args.db else None
    run_server(port=args.port, db_path=db, config=args.config, host=args.host)
