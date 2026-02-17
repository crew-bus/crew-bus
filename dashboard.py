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

import json
import random
import re
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
import instructor

DEFAULT_PORT = 8080
DEFAULT_DB = bus.DB_PATH

# Agent-type to Personal Edition name mapping
PERSONAL_NAMES = {
    "right_hand": "Crew Boss",
    "security": "Guard",
    "wellness": "Wellness",
    "strategy": "Ideas",
    "financial": "Wallet",
    "help": "Help",
    "human": "You",
}

PERSONAL_COLORS = {
    "right_hand": "#58a6ff",
    "security": "#2ea043",
    "wellness": "#39d0d0",
    "strategy": "#d18616",
    "financial": "#bc8cff",
}

CORE_TYPES = ("right_hand", "security", "wellness", "strategy", "financial")

AGENT_ACKS = {
    "right_hand": [
        "Got it. I'll process this and get back to you.",
        "Noted. Working on it.",
        "Received. I'll handle this.",
        "Understood. On it.",
    ],
    "security": [
        "Acknowledged. Monitoring.",
        "Copy that. Scanning.",
        "Received. Staying alert.",
    ],
    "wellness": [
        "Heard you. Taking note.",
        "Thanks for sharing that with me.",
        "Noted. I'll check in with you later.",
    ],
    "strategy": [
        "Interesting thought. Let me explore this.",
        "Noted. I'll think on that.",
        "Good input. Processing.",
    ],
    "financial": [
        "Logged. Reviewing the numbers.",
        "Got it. Tracking this.",
        "Received. Checking finances.",
    ],
    "help": [
        "Good question! Check the info above for guidance.",
        "Take a look at the overview above — it covers most topics.",
        "I'm here to help! The info above should point you in the right direction.",
    ],
    "_default": [
        "Acknowledged. Processing your request.",
        "Got it. Working on this.",
        "Received. I'll follow up.",
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

/* ── Circle layout ── */
.circle-wrap{
  position:relative;width:100%;
  max-width:400px;margin:0 auto;
  aspect-ratio:1;padding:16px;
}
.circle-wrap svg.lines{
  position:absolute;top:0;left:0;width:100%;height:100%;
  pointer-events:none;z-index:1;
}
.circle-wrap svg.lines line{
  stroke:var(--bd);stroke-width:1.5;stroke-dasharray:6 4;
  opacity:.5;
}

/* Agent bubble */
.bubble{
  position:absolute;z-index:5;
  display:flex;flex-direction:column;align-items:center;
  cursor:pointer;-webkit-tap-highlight-color:transparent;
  transition:transform .2s;
}
.bubble:active{transform:scale(.94)}
.bubble-circle{
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  position:relative;transition:box-shadow .3s;
  background:var(--sf);border:2px solid var(--bd);
}
.bubble:hover .bubble-circle{box-shadow:0 0 20px rgba(88,166,255,.2)}
.bubble-circle .icon{font-size:1.4rem}
.bubble-circle .status-dot{
  position:absolute;top:2px;right:2px;width:10px;height:10px;
  border-radius:50%;border:2px solid var(--sf);
}
.dot-green{background:var(--gn)}
.dot-yellow{background:var(--yl)}
.dot-red{background:var(--rd)}
.bubble-label{
  margin-top:4px;font-size:.7rem;font-weight:600;color:var(--mu);
  text-align:center;white-space:nowrap;
}
.bubble-count{
  font-size:.65rem;color:var(--ac);margin-top:1px;
}
.bubble-sub{
  font-size:.6rem;color:var(--mu);margin-top:1px;
  max-width:90px;text-align:center;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;
}

/* Center (Crew Boss) — CSS diamond icon instead of emoji */
.bubble.center .bubble-circle{
  width:88px;height:88px;
  border-color:var(--ac);border-width:2.5px;
  background:linear-gradient(135deg,#161b22 0%,#1a2332 100%);
}
.bubble.center .bubble-circle .icon{font-size:2rem}
.bubble.center .bubble-label{font-size:.8rem;color:var(--tx)}
.boss-icon{
  width:28px;height:28px;position:relative;
}
.boss-icon::before{
  content:'';position:absolute;top:50%;left:50%;
  width:20px;height:20px;
  background:linear-gradient(135deg,var(--ac) 0%,#79c0ff 100%);
  transform:translate(-50%,-50%) rotate(45deg);
  border-radius:3px;
}
.boss-icon::after{
  content:'';position:absolute;top:50%;left:50%;
  width:8px;height:8px;
  background:linear-gradient(135deg,#1a2332 0%,#0d1117 100%);
  transform:translate(-50%,-50%) rotate(45deg);
  border-radius:1px;
}

/* Outer agents */
.bubble.outer .bubble-circle{width:68px;height:68px}

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
    display:flex;align-items:flex-start;justify-content:center;
    gap:32px;max-width:900px;margin:0 auto;padding:24px;
  }
  .main-left{flex:1;max-width:450px}
  .main-right{flex:1;max-width:400px}
  .circle-wrap{max-width:400px}
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

/* ── Agent Space Tabs (Chat/Learn) ── */
.as-tabs{
  display:flex;gap:0;background:var(--sf);border-bottom:1px solid var(--bd);
  flex-shrink:0;padding:0 16px;
}
.as-tab{
  padding:10px 20px;font-size:.85rem;font-weight:600;
  border:none;background:transparent;color:var(--mu);
  cursor:pointer;border-bottom:2px solid transparent;
  transition:all .2s;min-height:42px;
}
.as-tab:hover{color:var(--tx)}
.as-tab.active{color:var(--ac);border-bottom-color:var(--ac)}
.as-tab-gear{
  margin-left:auto;background:none;border:none;color:var(--mu);
  font-size:1.1rem;cursor:pointer;padding:8px;transition:color .2s;
}
.as-tab-gear:hover{color:var(--tx)}

/* ── Learn Tab ── */
.learn-start{text-align:center;padding:24px 16px}
.learn-topic-input{
  width:100%;background:var(--bg);border:1px solid var(--bd);
  border-radius:var(--r);padding:14px 16px;color:var(--tx);
  font-size:1rem;font-family:inherit;margin-bottom:12px;
  transition:border-color .2s;
}
.learn-topic-input:focus{outline:none;border-color:var(--ac)}
.learn-topic-input::placeholder{color:var(--mu)}
.learn-cat-row{
  display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin-bottom:16px;
}
.learn-cat-pill{
  padding:6px 14px;border-radius:20px;font-size:.78rem;
  border:1px solid var(--bd);background:transparent;color:var(--mu);
  cursor:pointer;transition:all .2s;min-height:32px;
}
.learn-cat-pill:hover,.learn-cat-pill.active{
  color:var(--tx);background:var(--bd);border-color:var(--mu);
}
.learn-go-btn{
  background:var(--ac);color:#000;border:none;border-radius:var(--r);
  padding:12px 32px;font-size:1rem;font-weight:700;cursor:pointer;
  min-height:48px;transition:opacity .2s;
}
.learn-go-btn:hover{opacity:.85}
.learn-go-btn:disabled{opacity:.4;cursor:not-allowed}

/* Session view */
.learn-session-header{
  padding:12px 16px;background:var(--sf);border:1px solid var(--bd);
  border-radius:var(--r);margin-bottom:12px;
}
.learn-session-topic{font-weight:700;font-size:1.1rem;margin-bottom:8px}
.learn-progress-bar{
  height:6px;background:var(--bd);border-radius:3px;overflow:hidden;
  margin-bottom:4px;
}
.learn-progress-fill{
  height:100%;background:var(--ac);border-radius:3px;
  transition:width .4s ease;
}
.learn-progress-text{font-size:.7rem;color:var(--mu);text-align:right}

/* Step card */
.learn-step-card{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:16px;margin-bottom:12px;
}
.learn-step-header{
  display:flex;justify-content:space-between;align-items:center;
  margin-bottom:12px;
}
.learn-step-num{
  font-size:.75rem;color:var(--ac);font-weight:600;
  background:rgba(88,166,255,.1);padding:3px 10px;border-radius:12px;
}
.learn-step-type{
  font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;
  padding:3px 10px;border-radius:12px;font-weight:600;
}
.learn-step-type-explain{color:var(--ac);background:rgba(88,166,255,.1)}
.learn-step-type-demonstrate{color:var(--pr);background:rgba(188,140,255,.1)}
.learn-step-type-practice{color:var(--gn);background:rgba(63,185,80,.1)}
.learn-step-type-quiz{color:var(--or);background:rgba(209,134,22,.1)}
.learn-step-type-checkpoint{color:var(--tl);background:rgba(57,208,208,.1)}
.learn-step-title{font-weight:700;font-size:1rem;margin-bottom:10px}
.learn-step-content{
  font-size:.88rem;color:var(--tx);line-height:1.7;
}
.learn-step-content h2{font-size:1rem;margin:12px 0 8px;color:var(--tx)}
.learn-step-content h3{font-size:.9rem;margin:10px 0 6px;color:var(--ac)}
.learn-step-content pre{
  background:var(--bg);border:1px solid var(--bd);border-radius:8px;
  padding:12px;overflow-x:auto;font-size:.82rem;line-height:1.5;
  margin:8px 0;
}
.learn-step-content code{
  background:var(--bg);padding:2px 6px;border-radius:4px;font-size:.82rem;
}
.learn-step-content pre code{background:none;padding:0}
.learn-step-content ul,.learn-step-content ol{padding-left:20px;margin:6px 0}
.learn-step-content li{margin:3px 0}
.learn-step-content blockquote{
  border-left:3px solid var(--ac);padding-left:12px;color:var(--mu);
  margin:8px 0;
}
.learn-step-content strong{color:var(--tx)}
.learn-step-content table{
  width:100%;border-collapse:collapse;margin:8px 0;font-size:.82rem;
}
.learn-step-content table th,.learn-step-content table td{
  padding:6px 10px;border:1px solid var(--bd);text-align:left;
}
.learn-step-content table th{background:var(--bg);font-weight:600}

/* Step actions */
.learn-step-actions{
  display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;
}
.learn-btn{
  padding:10px 20px;border-radius:8px;font-size:.85rem;font-weight:600;
  cursor:pointer;border:1px solid var(--bd);background:var(--sf);
  color:var(--tx);transition:all .2s;min-height:42px;
}
.learn-btn:hover{background:var(--bd)}
.learn-btn-primary{background:var(--ac);color:#000;border-color:var(--ac)}
.learn-btn-primary:hover{opacity:.85}
.learn-btn-success{background:var(--gn);color:#000;border-color:var(--gn)}
.learn-btn-success:hover{opacity:.85}
.learn-btn-danger{border-color:var(--rd);color:var(--rd)}
.learn-btn-danger:hover{background:rgba(248,81,73,.12)}
.learn-response-area{
  width:100%;background:var(--bg);border:1px solid var(--bd);
  border-radius:8px;padding:12px;color:var(--tx);font-family:inherit;
  font-size:.9rem;resize:vertical;min-height:80px;margin-top:10px;
}
.learn-response-area:focus{outline:none;border-color:var(--ac)}
.learn-confidence-wrap{margin-top:10px}
.learn-confidence-label{font-size:.8rem;color:var(--mu);margin-bottom:6px}
.learn-confidence-val{
  text-align:center;font-size:1.8rem;font-weight:700;color:var(--ac);
}
.learn-confidence-slider{
  width:100%;accent-color:var(--ac);cursor:pointer;
}

/* History cards */
.learn-history-header{
  font-size:.85rem;color:var(--mu);text-transform:uppercase;
  letter-spacing:.04em;margin:20px 0 8px;font-weight:600;
}
.learn-history-card{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;
  align-items:center;
}
.learn-history-topic{font-weight:600;font-size:.85rem}
.learn-history-meta{font-size:.72rem;color:var(--mu);margin-top:2px}
.learn-history-score{
  font-size:.8rem;font-weight:700;padding:4px 10px;
  border-radius:12px;white-space:nowrap;
}

/* Settings panel */
.learn-settings{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  padding:16px;margin-bottom:16px;
}
.learn-settings h3{font-size:.9rem;margin-bottom:12px;color:var(--ac)}
.learn-setting-row{margin-bottom:14px}
.learn-setting-label{
  font-size:.75rem;color:var(--mu);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:4px;
}
.learn-setting-select{
  width:100%;background:var(--bg);border:1px solid var(--bd);
  border-radius:8px;padding:8px 10px;color:var(--tx);
  font-size:.85rem;appearance:auto;
}
.learn-tags-wrap{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.learn-tag{
  background:var(--bd);color:var(--tx);padding:4px 10px;
  border-radius:14px;font-size:.78rem;display:inline-flex;
  align-items:center;gap:4px;
}
.learn-tag-remove{
  background:none;border:none;color:var(--mu);cursor:pointer;
  font-size:.9rem;padding:0 2px;
}
.learn-tag-remove:hover{color:var(--rd)}
.learn-tag-input{
  background:var(--bg);border:1px solid var(--bd);border-radius:8px;
  padding:6px 10px;color:var(--tx);font-size:.82rem;flex:1;min-width:120px;
}
.learn-tag-input:focus{outline:none;border-color:var(--ac)}
.learn-save-btn{
  background:var(--ac);color:#000;border:none;border-radius:8px;
  padding:8px 20px;font-size:.85rem;font-weight:600;cursor:pointer;
  margin-top:8px;min-height:38px;
}
.learn-save-btn:hover{opacity:.85}

/* ── Wizard (Agent Creation) ── */
.wizard-overlay{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:300;background:rgba(0,0,0,.6);align-items:center;
  justify-content:center;padding:16px;
}
.wizard-overlay.open{display:flex}
.wizard-panel{
  background:var(--sf);border:1px solid var(--bd);border-radius:var(--r);
  width:100%;max-width:520px;max-height:90vh;overflow-y:auto;
  padding:24px 20px;box-shadow:var(--sh);
  animation:wizardIn .2s ease;
}
@keyframes wizardIn{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:scale(1)}}
.wizard-panel h2{font-size:1.1rem;margin-bottom:4px}
.wizard-panel .wizard-sub{font-size:.8rem;color:var(--mu);margin-bottom:16px}
.wizard-steps{
  display:flex;gap:4px;margin-bottom:20px;
}
.wizard-step{
  flex:1;height:4px;border-radius:2px;background:var(--bd);
  transition:background .3s;
}
.wizard-step.done{background:var(--gn)}
.wizard-step.active{background:var(--ac)}
.wizard-body{min-height:160px}
.wizard-footer{
  display:flex;justify-content:space-between;align-items:center;
  margin-top:20px;gap:8px;
}
.wiz-btn{
  padding:8px 20px;border-radius:8px;font-size:.85rem;font-weight:600;
  cursor:pointer;border:1px solid var(--bd);background:transparent;
  color:var(--tx);transition:all .2s;min-height:40px;
}
.wiz-btn:hover{background:var(--bd)}
.wiz-btn.primary{background:var(--ac);color:#000;border-color:var(--ac)}
.wiz-btn.primary:hover{opacity:.85}
.wiz-btn.success{background:var(--gn);color:#000;border-color:var(--gn)}
.wiz-btn.success:hover{opacity:.85}
.wiz-btn:disabled{opacity:.4;cursor:not-allowed}
.wiz-input{
  width:100%;background:var(--bg);border:1px solid var(--bd);
  border-radius:8px;padding:10px 12px;color:var(--tx);
  font-size:.9rem;font-family:inherit;margin-bottom:10px;
  transition:border-color .2s;
}
.wiz-input:focus{outline:none;border-color:var(--ac)}
.wiz-input::placeholder{color:var(--mu)}
.wiz-label{font-size:.75rem;color:var(--mu);text-transform:uppercase;
  letter-spacing:.04em;display:block;margin-bottom:4px}
.wiz-template-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.wiz-tpl-card{
  background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);
  padding:12px;cursor:pointer;transition:all .2s;
}
.wiz-tpl-card:hover{border-color:var(--ac)}
.wiz-tpl-card.selected{border-color:var(--ac);background:#0d1f3c}
.wiz-tpl-name{font-weight:600;font-size:.85rem;margin-bottom:2px}
.wiz-tpl-desc{font-size:.72rem;color:var(--mu)}
.wiz-tpl-count{font-size:.68rem;color:var(--ac);margin-top:2px}
.wiz-worker-row{
  display:flex;gap:8px;align-items:center;margin-bottom:8px;
}
.wiz-worker-row .wiz-input{margin-bottom:0;flex:1}
.wiz-remove-btn{
  background:none;border:1px solid var(--bd);border-radius:6px;
  color:var(--rd);cursor:pointer;padding:6px 10px;font-size:.8rem;
  min-width:32px;height:38px;display:flex;align-items:center;
  justify-content:center;transition:all .2s;flex-shrink:0;
}
.wiz-remove-btn:hover{background:rgba(248,81,73,.12);border-color:var(--rd)}
.wiz-add-btn{
  background:none;border:1px dashed var(--bd);border-radius:8px;
  color:var(--ac);cursor:pointer;padding:8px;font-size:.85rem;
  width:100%;text-align:center;margin-top:4px;transition:all .2s;
}
.wiz-add-btn:hover{border-color:var(--ac);background:rgba(88,166,255,.06)}
.wiz-tree{
  background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);
  padding:16px;margin-bottom:8px;
}
.wiz-tree-boss{font-size:.8rem;color:var(--mu);margin-bottom:4px}
.wiz-tree-mgr{font-weight:600;font-size:.95rem;color:var(--ac);
  padding:6px 0;border-bottom:1px solid var(--bd);margin-bottom:6px}
.wiz-tree-worker{padding:4px 0 4px 20px;font-size:.85rem;color:var(--tx);
  border-left:2px solid var(--bd);margin-left:8px}
.wiz-tree-worker::before{content:'';display:inline-block;width:12px;
  border-bottom:1px solid var(--bd);margin-right:8px;vertical-align:middle}
.wiz-error{color:var(--rd);font-size:.8rem;margin-top:8px;display:none}
.wiz-error.show{display:block}
.wiz-success{
  text-align:center;padding:24px 16px;
}
.wiz-success-icon{font-size:2.5rem;margin-bottom:12px;display:block}
.wiz-success h3{color:var(--gn);margin-bottom:4px}
.wiz-success p{color:var(--mu);font-size:.85rem}

/* ── Team detail management buttons ── */
.team-mgmt-bar{
  display:flex;gap:8px;justify-content:center;margin-top:16px;padding:0 8px;flex-wrap:wrap;
}
.team-mgmt-btn{
  padding:6px 14px;border-radius:8px;font-size:.8rem;
  border:1px solid var(--bd);background:transparent;color:var(--ac);
  cursor:pointer;transition:all .2s;min-height:36px;
}
.team-mgmt-btn:hover{background:var(--bd)}
.team-mgmt-btn.danger{color:var(--rd);border-color:var(--bd)}
.team-mgmt-btn.danger:hover{background:rgba(248,81,73,.12);border-color:var(--rd)}
.inline-form{
  background:var(--bg);border:1px solid var(--bd);border-radius:var(--r);
  padding:12px;margin-top:12px;
}
.inline-form .wiz-input{margin-bottom:8px}
.inline-form-actions{display:flex;gap:8px;justify-content:flex-end}
@media(max-width:600px){
  .wiz-template-grid{grid-template-columns:1fr}
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
  var m={'right_hand':'#58a6ff','security':'#2ea043','wellness':'#39d0d0','strategy':'#d18616','financial':'#bc8cff'};
  return m[type]||'#58a6ff';
}

function personalName(a){
  var m={'right_hand':'Crew Boss','security':'Guard','wellness':'Wellness','strategy':'Ideas','financial':'Wallet','help':'Help','human':'You'};
  return m[a.agent_type]||a.name||'Agent';
}

// FIX 4: map for display names used in Messages dropdown
var DISPLAY_NAMES={'right_hand':'Crew Boss','security':'Guard','wellness':'Wellness','strategy':'Ideas','financial':'Wallet','help':'Help','human':'You'};
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

  var guardCI='';
  try{var cid=await api('/api/guard/checkin');guardCI=cid.last_checkin||''}catch(e){}

  // FIX 5: "Watching..." instead of "No check-in"
  renderBubble('bubble-boss',boss,null);
  renderBubble('bubble-guard',guard,guardCI?'Check-in: '+timeAgo(guardCI):'Watching...');
  renderBubble('bubble-well',well,null);
  renderBubble('bubble-ideas',ideas,null);
  renderBubble('bubble-wallet',wallet,null);

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
  if(!el||!agent)return;
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

  // Show tabs only for strategy agent
  var tabsEl=document.getElementById('as-tabs');
  var chatBody=document.getElementById('as-body-chat');
  var learnBody=document.getElementById('as-body-learn');
  var gearBtn=document.getElementById('learn-gear-btn');
  if(agent.agent_type==='strategy'){
    tabsEl.style.display='flex';
    // Reset to chat tab
    document.querySelectorAll('.as-tab').forEach(function(t){
      t.classList.toggle('active',t.dataset.tab==='chat');
    });
    chatBody.style.display='block';
    learnBody.style.display='none';
    if(gearBtn)gearBtn.style.display='none';
  }else{
    tabsEl.style.display='none';
    chatBody.style.display='block';
    learnBody.style.display='none';
    if(gearBtn)gearBtn.style.display='none';
  }

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
    'right_hand':'Your personal AI chief of staff. Handles all communication, memory, scheduling, and filtering. The only agent that talks to you directly.',
    'security':'Silent protector. Monitors for threats, scams, privacy concerns, and suspicious activity. Reports to Crew Boss, never bothers you directly.',
    'wellness':'Watches your health, energy, and work-life balance. Tracks patterns and suggests breaks before burnout hits.',
    'strategy':'Your idea generator. Learns what you care about and brings tailored opportunities, suggestions, and creative sparks.',
    'financial':'Quiet financial awareness. Tracks spending patterns, flags anything unusual, reminds about bills and deadlines.',
    'help':'Your guide to crew-bus. Create teams, add agents, and manage your crew hierarchy.\\n\\n' +
      'Click the ? button or + Add Team to open the Agent Creation Wizard.',
  };
  return d[type]||'An agent in your crew.';
}

async function openHelpAgent(){
  openWizard();
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

function openTemplatePicker(){openWizard()}
function closeTemplatePicker(){closeWizard()}

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
    var isTerminated=w.status==='terminated'||!w.active;
    html+='<div class="team-worker-bubble'+(isTerminated?' terminated':'')+'" onclick="openAgentSpace('+w.id+')">'+
      '<div class="team-worker-circle"'+(isTerminated?' style="opacity:.4"':'')+'>\u{1F6E0}\uFE0F<span class="team-worker-dot '+dotClass(w.status,w.agent_type,null)+'"></span></div>'+
      '<span class="team-worker-label">'+esc(w.name)+'</span></div>';
  });
  html+='</div>';

  // Management bar
  if(mgr){
    var mgrNameEsc=esc(mgr.name).replace(/'/g,"\\'");
    html+='<div class="team-mgmt-bar">'+
      '<button class="team-mgmt-btn" onclick="showAddWorkerForm('+teamId+',\''+mgrNameEsc+'\')">+ Add Worker</button></div>';

    // Add worker inline form (hidden by default)
    html+='<div class="inline-form" id="team-add-worker-form" style="display:none;max-width:400px;margin:12px auto 0">'+
      '<label class="wiz-label">Worker Name</label>'+
      '<input class="wiz-input" id="new-worker-name" placeholder="e.g. Analytics-Bot">'+
      '<label class="wiz-label">Description</label>'+
      '<input class="wiz-input" id="new-worker-desc" placeholder="What does this worker do?">'+
      '<div class="inline-form-actions">'+
      '<button class="wiz-btn" onclick="document.getElementById(\'team-add-worker-form\').style.display=\'none\'">Cancel</button>'+
      '<button class="wiz-btn primary" onclick="submitAddWorker('+teamId+',\''+mgrNameEsc+'\')">Create</button></div>'+
      '<div id="add-worker-msg" style="font-size:.8rem;margin-top:6px"></div></div>';

    // Worker detail cards with edit/deactivate
    html+='<div style="max-width:400px;margin:16px auto 0">';
    var activeWorkers=workers.filter(function(w){return w.status!=='terminated'&&w.active});
    if(activeWorkers.length>0){
      html+='<h3 style="font-size:.85rem;color:var(--mu);margin-bottom:8px">Manage Workers</h3>';
      activeWorkers.forEach(function(w){
        html+='<div style="background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px;margin-bottom:8px">'+
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'+
          '<strong style="font-size:.85rem">'+esc(w.name)+'</strong>'+
          '<button class="team-mgmt-btn danger" style="padding:3px 10px;font-size:.72rem" onclick="deactivateWorker('+teamId+','+w.id+',\''+esc(w.name).replace(/'/g,"\\'")+'\')">Deactivate</button></div>'+
          '<textarea class="wiz-input" id="edit-desc-'+w.id+'" rows="2" style="margin-bottom:4px;resize:vertical;min-height:40px">'+esc(w.description||'')+'</textarea>'+
          '<div style="display:flex;align-items:center;gap:8px"><button class="team-mgmt-btn" style="padding:3px 10px;font-size:.72rem" onclick="editAgentDesc('+w.id+')">Save Description</button>'+
          '<span id="edit-desc-msg-'+w.id+'" style="font-size:.75rem"></span></div></div>';
      });
    }
    html+='</div>';
  }

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

// ══════════ WIZARD: Agent Creation ══════════

var wizardState={step:0,templates:[],selected:null,teamName:'',teamDesc:'',
  mgrName:'',mgrDesc:'',workers:[]};

function openWizard(){
  wizardState={step:0,templates:[],selected:null,teamName:'',teamDesc:'',
    mgrName:'',mgrDesc:'',workers:[]};
  document.getElementById('wizard-overlay').classList.add('open');
  loadWizardTemplates();
}
function closeWizard(){
  document.getElementById('wizard-overlay').classList.remove('open');
}

async function loadWizardTemplates(){
  try{wizardState.templates=await api('/api/help/templates');}catch(e){wizardState.templates=[];}
  renderWizard();
}

function renderWizard(){
  var body=document.getElementById('wizard-body');
  var footer=document.getElementById('wizard-footer');
  var steps=document.querySelectorAll('.wizard-step');
  steps.forEach(function(s,i){
    s.className='wizard-step'+(i<wizardState.step?' done':'')+(i===wizardState.step?' active':'');
  });
  document.getElementById('wizard-error').className='wiz-error';
  document.getElementById('wizard-error').textContent='';

  if(wizardState.step===0) renderStep0(body,footer);
  else if(wizardState.step===1) renderStep1(body,footer);
  else if(wizardState.step===2) renderStep2(body,footer);
  else if(wizardState.step===3) renderStep3(body,footer);
  else if(wizardState.step===4) renderStepSuccess(body,footer);
}

function renderStep0(body,footer){
  var html='<h3 style="margin-bottom:12px">Choose a Template</h3>';
  html+='<div class="wiz-template-grid">';
  wizardState.templates.forEach(function(t){
    var sel=wizardState.selected===t.id?' selected':'';
    var cnt=t.id==='custom'?'Start fresh':(1+t.workers.length)+' agents';
    html+='<div class="wiz-tpl-card'+sel+'" onclick="selectTemplate(\''+t.id+'\')">'+
      '<div class="wiz-tpl-name">'+esc(t.name)+'</div>'+
      '<div class="wiz-tpl-desc">'+esc(t.description)+'</div>'+
      '<div class="wiz-tpl-count">'+cnt+'</div></div>';
  });
  html+='</div>';
  body.innerHTML=html;
  footer.innerHTML='<button class="wiz-btn" onclick="closeWizard()">Cancel</button>'+
    '<button class="wiz-btn primary" onclick="wizardNext()" '+(wizardState.selected?'':' disabled')+'>Next</button>';
}

function selectTemplate(id){
  wizardState.selected=id;
  var tpl=wizardState.templates.find(function(t){return t.id===id});
  if(tpl){
    wizardState.teamName=tpl.name||'';
    wizardState.teamDesc=tpl.description||'';
    wizardState.mgrName=tpl.manager.name||'';
    wizardState.mgrDesc=tpl.manager.description||'';
    wizardState.workers=(tpl.workers||[]).map(function(w){return{name:w.name||'',description:w.description||''}});
  }
  renderWizard();
}

function renderStep1(body,footer){
  body.innerHTML=
    '<label class="wiz-label">Team Name</label>'+
    '<input class="wiz-input" id="wiz-team-name" value="'+esc(wizardState.teamName)+'" placeholder="e.g. Marketing Team">'+
    '<label class="wiz-label">Team Description</label>'+
    '<input class="wiz-input" id="wiz-team-desc" value="'+esc(wizardState.teamDesc)+'" placeholder="What does this team do?">'+
    '<label class="wiz-label">Manager Name</label>'+
    '<input class="wiz-input" id="wiz-mgr-name" value="'+esc(wizardState.mgrName)+'" placeholder="e.g. Marketing-Lead">'+
    '<label class="wiz-label">Manager Description</label>'+
    '<input class="wiz-input" id="wiz-mgr-desc" value="'+esc(wizardState.mgrDesc)+'" placeholder="What does the manager do?">';
  footer.innerHTML='<button class="wiz-btn" onclick="wizardBack()">Back</button>'+
    '<button class="wiz-btn primary" onclick="wizardNext()">Next</button>';
}

function renderStep2(body,footer){
  var html='<h3 style="margin-bottom:12px">Workers</h3>';
  wizardState.workers.forEach(function(w,i){
    html+='<div class="wiz-worker-row">'+
      '<input class="wiz-input" placeholder="Worker name" value="'+esc(w.name)+'" oninput="wizardState.workers['+i+'].name=this.value">'+
      '<input class="wiz-input" placeholder="Description" value="'+esc(w.description)+'" oninput="wizardState.workers['+i+'].description=this.value">'+
      '<button class="wiz-remove-btn" onclick="removeWizWorker('+i+')" title="Remove">&times;</button></div>';
  });
  if(wizardState.workers.length<10){
    html+='<button class="wiz-add-btn" onclick="addWizWorker()">+ Add Worker</button>';
  }
  html+='<p style="color:var(--mu);font-size:.75rem;margin-top:8px">'+wizardState.workers.length+'/10 workers</p>';
  body.innerHTML=html;
  footer.innerHTML='<button class="wiz-btn" onclick="wizardBack()">Back</button>'+
    '<button class="wiz-btn primary" onclick="wizardNext()">Review</button>';
}

function addWizWorker(){
  if(wizardState.workers.length>=10)return;
  wizardState.workers.push({name:'',description:''});
  renderWizard();
}
function removeWizWorker(i){
  wizardState.workers.splice(i,1);
  renderWizard();
}

function renderStep3(body,footer){
  var html='<h3 style="margin-bottom:12px">Review</h3><div class="wiz-tree">';
  html+='<div class="wiz-tree-boss">Crew Boss</div>';
  html+='<div class="wiz-tree-mgr">'+esc(wizardState.mgrName||'(unnamed manager)')+'</div>';
  if(wizardState.workers.length===0){
    html+='<div style="color:var(--mu);font-size:.85rem;padding:4px 0 4px 20px">No workers (you can add them later)</div>';
  }
  wizardState.workers.forEach(function(w){
    html+='<div class="wiz-tree-worker">'+esc(w.name||'(unnamed)')+'</div>';
  });
  html+='</div>';
  html+='<div style="font-size:.85rem;color:var(--mu)"><strong>Team:</strong> '+esc(wizardState.teamName)+'</div>';
  if(wizardState.teamDesc)html+='<div style="font-size:.8rem;color:var(--mu)">'+esc(wizardState.teamDesc)+'</div>';
  body.innerHTML=html;
  footer.innerHTML='<button class="wiz-btn" onclick="wizardBack()">Back</button>'+
    '<button class="wiz-btn success" id="wiz-create-btn" onclick="wizardCreate()">Create Team</button>';
}

function renderStepSuccess(body,footer){
  body.innerHTML='<div class="wiz-success">'+
    '<span class="wiz-success-icon">&#10003;</span>'+
    '<h3>Team Created</h3>'+
    '<p>'+esc(wizardState.teamName)+' is ready with '+
    (1+wizardState.workers.length)+' agent'+(wizardState.workers.length!==0?'s':'')+'.</p></div>';
  footer.innerHTML='<button class="wiz-btn primary" onclick="closeWizard();loadTeams();showView(\'crew\')">Done</button>';
}

function saveWizStep1(){
  var n=document.getElementById('wiz-team-name');
  var d=document.getElementById('wiz-team-desc');
  var mn=document.getElementById('wiz-mgr-name');
  var md=document.getElementById('wiz-mgr-desc');
  if(n)wizardState.teamName=n.value;
  if(d)wizardState.teamDesc=d.value;
  if(mn)wizardState.mgrName=mn.value;
  if(md)wizardState.mgrDesc=md.value;
}

function wizardNext(){
  var errEl=document.getElementById('wizard-error');
  errEl.className='wiz-error';errEl.textContent='';

  if(wizardState.step===0){
    if(!wizardState.selected){showWizError('Please select a template.');return;}
    wizardState.step=1;
  }else if(wizardState.step===1){
    saveWizStep1();
    if(!wizardState.teamName.trim()){showWizError('Team name is required.');return;}
    if(!wizardState.mgrName.trim()){showWizError('Manager name is required.');return;}
    wizardState.step=2;
  }else if(wizardState.step===2){
    for(var i=0;i<wizardState.workers.length;i++){
      if(wizardState.workers[i].name&&!wizardState.workers[i].name.trim()){
        showWizError('Worker '+(i+1)+' has an empty name. Remove it or fill in a name.');return;
      }
    }
    // Remove workers with no name
    wizardState.workers=wizardState.workers.filter(function(w){return w.name&&w.name.trim()});
    wizardState.step=3;
  }
  renderWizard();
}

function wizardBack(){
  if(wizardState.step===1){saveWizStep1();}
  if(wizardState.step>0)wizardState.step--;
  renderWizard();
}

function showWizError(msg){
  var el=document.getElementById('wizard-error');
  el.textContent=msg;el.className='wiz-error show';
}

async function wizardCreate(){
  var btn=document.getElementById('wiz-create-btn');
  if(btn){btn.disabled=true;btn.textContent='Creating...';}
  var data={
    team_name:wizardState.teamName.trim(),
    description:wizardState.teamDesc.trim(),
    manager_name:wizardState.mgrName.trim(),
    manager_description:wizardState.mgrDesc.trim(),
    workers:wizardState.workers.filter(function(w){return w.name&&w.name.trim()}).map(function(w){
      return{name:w.name.trim(),description:(w.description||'').trim()};
    })
  };
  try{
    var res=await apiPost('/api/help/create-team',data);
    if(res&&res.ok){
      wizardState.step=4;
      renderWizard();
    }else{
      showWizError(res.error||'Failed to create team.');
      if(btn){btn.disabled=false;btn.textContent='Create Team';}
    }
  }catch(e){
    showWizError('Network error. Please try again.');
    if(btn){btn.disabled=false;btn.textContent='Create Team';}
  }
}

// ══════════ TEAM DETAIL: Management ══════════

function showAddWorkerForm(teamId,mgrName){
  var el=document.getElementById('team-add-worker-form');
  if(el){el.style.display=el.style.display==='none'?'block':'none';return;}
}

async function submitAddWorker(teamId,mgrName){
  var nameEl=document.getElementById('new-worker-name');
  var descEl=document.getElementById('new-worker-desc');
  var msgEl=document.getElementById('add-worker-msg');
  if(!nameEl||!nameEl.value.trim()){if(msgEl){msgEl.textContent='Name is required.';msgEl.style.color='var(--rd)';}return;}
  if(msgEl){msgEl.textContent='Creating...';msgEl.style.color='var(--mu)';}
  try{
    var res=await apiPost('/api/help/create-agent',{
      name:nameEl.value.trim(),
      agent_type:'worker',
      parent_name:mgrName,
      description:(descEl?descEl.value.trim():''),
      channel:'console'
    });
    if(res&&res.ok){
      if(msgEl){msgEl.textContent='Worker created!';msgEl.style.color='var(--gn)';}
      setTimeout(function(){openTeamDash(teamId)},600);
    }else{
      if(msgEl){msgEl.textContent=res.error||'Failed.';msgEl.style.color='var(--rd)';}
    }
  }catch(e){
    if(msgEl){msgEl.textContent='Network error.';msgEl.style.color='var(--rd)';}
  }
}

async function deactivateWorker(teamId,agentId,agentName){
  if(!confirm('Deactivate '+agentName+'? This will terminate the agent.'))return;
  try{
    var res=await apiPost('/api/agent/'+agentId+'/deactivate',{});
    if(res&&res.ok){openTeamDash(teamId);}
    else{alert(res.error||'Failed to deactivate agent.');}
  }catch(e){alert('Network error.');}
}

async function editAgentDesc(agentId){
  var el=document.getElementById('edit-desc-'+agentId);
  if(!el)return;
  var newDesc=el.value.trim();
  try{
    var res=await apiPost('/api/agent/'+agentId+'/description',{description:newDesc});
    if(res&&res.ok){
      var msg=document.getElementById('edit-desc-msg-'+agentId);
      if(msg){msg.textContent='Saved!';msg.style.color='var(--gn)';setTimeout(function(){msg.textContent=''},1500);}
    }
  }catch(e){}
}

async function apiDelete(path){
  return(await fetch(path,{method:'DELETE',headers:{'Content-Type':'application/json'}})).json();
}

// ══════════ LEARN TAB (Instruction Mode) ══════════

let learnCategory='general';
let learnSettingsOpen=false;
let activeLearnSession=null;

function switchAsTab(tab){
  document.querySelectorAll('.as-tab').forEach(function(t){
    t.classList.toggle('active',t.dataset.tab===tab);
  });
  var chatBody=document.getElementById('as-body-chat');
  var learnBody=document.getElementById('as-body-learn');
  var gearBtn=document.getElementById('learn-gear-btn');
  if(tab==='learn'){
    chatBody.style.display='none';
    learnBody.style.display='block';
    if(gearBtn)gearBtn.style.display='block';
    loadLearnTab();
  }else{
    chatBody.style.display='block';
    learnBody.style.display='none';
    if(gearBtn)gearBtn.style.display='none';
  }
}

async function loadLearnTab(){
  var el=document.getElementById('learn-content');
  if(!el)return;
  el.innerHTML='<p style="color:var(--mu);text-align:center;padding:24px">Loading...</p>';
  try{
    var active=await api('/api/instruct/active');
    if(active&&active.id){
      activeLearnSession=active;
      renderActiveSession(active);
      return;
    }
  }catch(e){}
  activeLearnSession=null;
  renderLearnStart();
}

function renderLearnStart(){
  var el=document.getElementById('learn-content');
  var cats=['tech','business','health','creative','trades','life_skills','other'];
  var html='<div class="learn-start">';
  html+='<h3 style="margin-bottom:16px;color:var(--tx)">What do you want to learn?</h3>';
  html+='<input class="learn-topic-input" id="learn-topic" placeholder="e.g. How to use Git for version control" onkeydown="if(event.key===\'Enter\')startLesson()">';
  html+='<div class="learn-cat-row">';
  cats.forEach(function(c){
    var label=c.replace('_',' ');
    label=label.charAt(0).toUpperCase()+label.slice(1);
    html+='<button class="learn-cat-pill'+(c===learnCategory?' active':'')+'" onclick="selectLearnCat(\''+c+'\',this)">'+label+'</button>';
  });
  html+='</div>';
  html+='<button class="learn-go-btn" onclick="startLesson()">Teach Me</button>';
  html+='</div>';

  // Load history
  html+='<div id="learn-history-area"></div>';
  el.innerHTML=html;
  loadLearnHistory();
}

function selectLearnCat(cat,btn){
  learnCategory=cat;
  document.querySelectorAll('.learn-cat-pill').forEach(function(p){p.classList.remove('active')});
  btn.classList.add('active');
}

async function startLesson(){
  var input=document.getElementById('learn-topic');
  if(!input||!input.value.trim())return;
  var topic=input.value.trim();
  var btn=document.querySelector('.learn-go-btn');
  if(btn){btn.disabled=true;btn.textContent='Starting...';}
  try{
    var session=await apiPost('/api/instruct/start',{topic:topic,category:learnCategory});
    if(session&&session.id){
      activeLearnSession=session;
      renderActiveSession(session);
    }else{
      if(btn){btn.disabled=false;btn.textContent='Teach Me';}
    }
  }catch(e){
    if(btn){btn.disabled=false;btn.textContent='Teach Me';}
  }
}

function renderActiveSession(session){
  var el=document.getElementById('learn-content');
  if(!el)return;
  var steps=session.steps||[];
  var completed=steps.filter(function(s){return s.completed});
  var total=steps.length;
  var pct=total>0?Math.round((completed.length/total)*100):0;

  // Find current (first incomplete) step
  var current=steps.find(function(s){return !s.completed});

  var html='<div class="learn-session-header">';
  html+='<div class="learn-session-topic">'+esc(session.topic)+'</div>';
  html+='<div class="learn-progress-bar"><div class="learn-progress-fill" style="width:'+pct+'%"></div></div>';
  html+='<div class="learn-progress-text">'+completed.length+' / '+total+' steps ('+pct+'%)</div>';
  html+='</div>';

  if(current){
    html+=renderStepCard(current,session);
  }else{
    // All steps done — show completion
    html+='<div style="text-align:center;padding:24px">';
    html+='<div style="font-size:2rem;margin-bottom:8px">&#10003;</div>';
    html+='<h3 style="margin-bottom:12px">All Steps Completed!</h3>';
    html+='<textarea class="learn-response-area" id="learn-feedback" placeholder="How was this session? Any feedback..."></textarea>';
    html+='<div class="learn-step-actions" style="justify-content:center;margin-top:12px">';
    html+='<button class="learn-btn learn-btn-success" onclick="completeSession('+session.id+')">Complete Session</button>';
    html+='</div></div>';
  }

  // Session controls
  html+='<div style="display:flex;gap:8px;justify-content:center;margin-top:16px">';
  html+='<button class="learn-btn learn-btn-danger" onclick="endSessionEarly('+session.id+')">I\'m Done</button>';
  html+='</div>';

  el.innerHTML=html;
  // Render markdown in step content
  renderLearnMarkdown();
}

function renderStepCard(step,session){
  var typeClass='learn-step-type-'+step.step_type;
  var html='<div class="learn-step-card">';
  html+='<div class="learn-step-header">';
  html+='<span class="learn-step-num">Step '+step.step_number+'</span>';
  html+='<span class="learn-step-type '+typeClass+'">'+esc(step.step_type)+'</span>';
  html+='</div>';
  html+='<div class="learn-step-title">'+esc(step.title)+'</div>';
  html+='<div class="learn-step-content" id="learn-step-md">'+esc(step.content)+'</div>';

  // Actions based on step type
  html+='<div class="learn-step-actions">';
  if(step.step_type==='explain'){
    html+='<button class="learn-btn learn-btn-primary" onclick="completeStep('+step.id+',null,null)">Got It</button>';
    html+='<button class="learn-btn" onclick="completeStep('+step.id+',\'Need more explanation\',2)">Explain More</button>';
  }else if(step.step_type==='demonstrate'){
    html+='<button class="learn-btn learn-btn-primary" onclick="completeStep('+step.id+',null,null)">Got It</button>';
    html+='<button class="learn-btn" onclick="completeStep('+step.id+',\'Need to see it again\',2)">Show Me Again</button>';
  }else if(step.step_type==='practice'){
    html+='<textarea class="learn-response-area" id="learn-practice-response" placeholder="Describe what you did and what happened..."></textarea>';
    html+='<button class="learn-btn learn-btn-success" onclick="submitPractice('+step.id+')">Check My Work</button>';
  }else if(step.step_type==='quiz'){
    html+='<textarea class="learn-response-area" id="learn-quiz-response" placeholder="Your answer..."></textarea>';
    html+='<button class="learn-btn learn-btn-primary" onclick="submitQuiz('+step.id+')">Submit</button>';
  }else if(step.step_type==='checkpoint'){
    html+='<div class="learn-confidence-wrap">';
    html+='<div class="learn-confidence-label">How confident do you feel?</div>';
    html+='<div class="learn-confidence-val" id="learn-conf-val">3</div>';
    html+='<input type="range" class="learn-confidence-slider" id="learn-conf-slider" min="1" max="5" value="3" oninput="document.getElementById(\'learn-conf-val\').textContent=this.value">';
    html+='</div>';
    html+='<button class="learn-btn learn-btn-primary" onclick="submitCheckpoint('+step.id+')">Continue</button>';
  }
  html+='</div></div>';
  return html;
}

async function completeStep(stepId,response,confidence){
  var data={};
  if(response)data.response=response;
  if(confidence!==null&&confidence!==undefined)data.confidence=confidence;
  await apiPost('/api/instruct/step/'+stepId+'/complete',data);
  // Reload session
  if(activeLearnSession){
    var session=await api('/api/instruct/session/'+activeLearnSession.id);
    if(session&&session.id){
      activeLearnSession=session;
      renderActiveSession(session);
    }
  }
}

async function submitPractice(stepId){
  var el=document.getElementById('learn-practice-response');
  var text=el?el.value.trim():'';
  await completeStep(stepId,text||'Completed practice',3);
}

async function submitQuiz(stepId){
  var el=document.getElementById('learn-quiz-response');
  var text=el?el.value.trim():'';
  await completeStep(stepId,text||'Submitted answer',3);
}

async function submitCheckpoint(stepId){
  var slider=document.getElementById('learn-conf-slider');
  var conf=slider?parseInt(slider.value):3;
  await completeStep(stepId,'Checkpoint confidence: '+conf,conf);
}

async function completeSession(sessionId){
  var el=document.getElementById('learn-feedback');
  var feedback=el?el.value.trim():'';
  await apiPost('/api/instruct/session/'+sessionId+'/complete',{feedback:feedback||null});
  activeLearnSession=null;
  renderLearnStart();
}

async function endSessionEarly(sessionId){
  await apiPost('/api/instruct/session/'+sessionId+'/complete',{feedback:'Ended early'});
  activeLearnSession=null;
  renderLearnStart();
}

async function loadLearnHistory(){
  var area=document.getElementById('learn-history-area');
  if(!area)return;
  try{
    var history=await api('/api/instruct/history');
    if(!history||history.length===0){
      area.innerHTML='';
      return;
    }
    var html='<div class="learn-history-header">Past Sessions</div>';
    history.forEach(function(h){
      var conf=h.avg_confidence?parseFloat(h.avg_confidence):0;
      var confColor=conf>=4?'var(--gn)':conf>=3?'var(--yl)':'var(--rd)';
      var confBg=conf>=4?'rgba(63,185,80,.12)':conf>=3?'rgba(210,153,34,.12)':'rgba(248,81,73,.12)';
      html+='<div class="learn-history-card">';
      html+='<div><div class="learn-history-topic">'+esc(h.topic)+'</div>';
      html+='<div class="learn-history-meta">'+esc(h.category)+' &middot; '+h.steps_completed+'/'+h.steps_total+' steps &middot; '+timeAgo(h.completed_at)+'</div></div>';
      if(conf>0){
        html+='<div class="learn-history-score" style="color:'+confColor+';background:'+confBg+'">'+conf.toFixed(1)+'/5</div>';
      }
      html+='</div>';
    });
    area.innerHTML=html;
  }catch(e){area.innerHTML='';}
}

function toggleLearnSettings(){
  learnSettingsOpen=!learnSettingsOpen;
  var panel=document.getElementById('learn-settings-panel');
  if(learnSettingsOpen){
    panel.style.display='block';
    loadLearnSettings();
  }else{
    panel.style.display='none';
  }
}

async function loadLearnSettings(){
  var panel=document.getElementById('learn-settings-panel');
  if(!panel)return;
  panel.innerHTML='<p style="color:var(--mu);text-align:center">Loading...</p>';
  try{
    var profile=await api('/api/learning-profile');
    renderLearnSettings(profile);
  }catch(e){
    panel.innerHTML='<p style="color:var(--rd)">Failed to load profile</p>';
  }
}

function renderLearnSettings(profile){
  var panel=document.getElementById('learn-settings-panel');
  if(!panel)return;
  var styles=['visual','auditory','reading','kinesthetic','adaptive'];
  var paces=['slow','moderate','fast'];
  var details=['high_detail','balanced','concise','just_steps'];

  var html='<div class="learn-settings">';
  html+='<h3>Learning Profile</h3>';

  html+='<div class="learn-setting-row"><div class="learn-setting-label">Learning Style</div>';
  html+='<select class="learn-setting-select" id="lp-style">';
  styles.forEach(function(s){
    var label=s.charAt(0).toUpperCase()+s.slice(1);
    if(s==='adaptive')label='Let the system adapt';
    html+='<option value="'+s+'"'+(profile.learning_style===s?' selected':'')+'>'+label+'</option>';
  });
  html+='</select></div>';

  html+='<div class="learn-setting-row"><div class="learn-setting-label">Pace</div>';
  html+='<select class="learn-setting-select" id="lp-pace">';
  paces.forEach(function(p){
    html+='<option value="'+p+'"'+(profile.pace===p?' selected':'')+'>'+p.charAt(0).toUpperCase()+p.slice(1)+'</option>';
  });
  html+='</select></div>';

  html+='<div class="learn-setting-row"><div class="learn-setting-label">Detail Level</div>';
  html+='<select class="learn-setting-select" id="lp-detail">';
  details.forEach(function(d){
    var label=d.replace('_',' ');label=label.charAt(0).toUpperCase()+label.slice(1);
    html+='<option value="'+d+'"'+(profile.detail_level===d?' selected':'')+'>'+label+'</option>';
  });
  html+='</select></div>';

  // Known skills tags
  html+='<div class="learn-setting-row"><div class="learn-setting-label">Known Skills</div>';
  html+='<div class="learn-tags-wrap" id="lp-skills-tags">';
  (profile.known_skills||[]).forEach(function(s){
    html+='<span class="learn-tag">'+esc(s)+'<button class="learn-tag-remove" onclick="removeLearnTag(\'skills\',\''+esc(s).replace(/'/g,"\\'")+'\')">x</button></span>';
  });
  html+='<input class="learn-tag-input" id="lp-skills-input" placeholder="Add skill..." onkeydown="if(event.key===\'Enter\'){addLearnTag(\'skills\');event.preventDefault()}">';
  html+='</div></div>';

  // Interests tags
  html+='<div class="learn-setting-row"><div class="learn-setting-label">Interests</div>';
  html+='<div class="learn-tags-wrap" id="lp-interests-tags">';
  (profile.interests||[]).forEach(function(s){
    html+='<span class="learn-tag">'+esc(s)+'<button class="learn-tag-remove" onclick="removeLearnTag(\'interests\',\''+esc(s).replace(/'/g,"\\'")+'\')">x</button></span>';
  });
  html+='<input class="learn-tag-input" id="lp-interests-input" placeholder="Add interest..." onkeydown="if(event.key===\'Enter\'){addLearnTag(\'interests\');event.preventDefault()}">';
  html+='</div></div>';

  // Disabilities / accessibility
  html+='<div class="learn-setting-row"><div class="learn-setting-label">Accessibility Needs</div>';
  html+='<textarea class="learn-response-area" id="lp-disabilities" placeholder="Any accessibility needs or learning accommodations..." style="min-height:60px">'+(profile.disabilities&&profile.disabilities.length?profile.disabilities.join(', '):'')+'</textarea>';
  html+='</div>';

  html+='<button class="learn-save-btn" onclick="saveLearnProfile()">Save Profile</button>';
  html+='<span id="lp-save-msg" style="margin-left:10px;font-size:.8rem"></span>';
  html+='</div>';
  panel.innerHTML=html;
}

var _learnProfileCache=null;
async function ensureLearnProfileCache(){
  if(!_learnProfileCache){
    _learnProfileCache=await api('/api/learning-profile');
  }
  return _learnProfileCache;
}

async function addLearnTag(field){
  var input=document.getElementById('lp-'+field+'-input');
  if(!input||!input.value.trim())return;
  var val=input.value.trim();
  input.value='';
  var profile=await ensureLearnProfileCache();
  var arr=profile[field==='skills'?'known_skills':'interests']||[];
  if(arr.indexOf(val)===-1)arr.push(val);
  var update={};
  update[field==='skills'?'known_skills':'interests']=arr;
  _learnProfileCache=await apiPost('/api/learning-profile',update);
  renderLearnSettings(_learnProfileCache);
}

async function removeLearnTag(field,val){
  var profile=await ensureLearnProfileCache();
  var key=field==='skills'?'known_skills':'interests';
  var arr=(profile[key]||[]).filter(function(s){return s!==val});
  var update={};update[key]=arr;
  _learnProfileCache=await apiPost('/api/learning-profile',update);
  renderLearnSettings(_learnProfileCache);
}

async function saveLearnProfile(){
  var update={};
  var styleEl=document.getElementById('lp-style');
  var paceEl=document.getElementById('lp-pace');
  var detailEl=document.getElementById('lp-detail');
  var disEl=document.getElementById('lp-disabilities');
  if(styleEl)update.learning_style=styleEl.value;
  if(paceEl)update.pace=paceEl.value;
  if(detailEl)update.detail_level=detailEl.value;
  if(disEl){
    var text=disEl.value.trim();
    update.disabilities=text?text.split(',').map(function(s){return s.trim()}).filter(Boolean):[];
  }
  _learnProfileCache=await apiPost('/api/learning-profile',update);
  var msg=document.getElementById('lp-save-msg');
  if(msg){msg.textContent='Saved!';msg.style.color='var(--gn)';setTimeout(function(){msg.textContent=''},2000);}
}

function renderLearnMarkdown(){
  var el=document.getElementById('learn-step-md');
  if(!el)return;
  var raw=el.textContent||el.innerText||'';
  el.innerHTML=simpleMarkdown(raw);
}

function simpleMarkdown(text){
  // Very basic markdown renderer — no external libs
  var lines=text.split('\n');
  var html='';var inPre=false;var inList=false;var listType='';
  for(var i=0;i<lines.length;i++){
    var line=lines[i];
    // Code blocks
    if(line.trim().indexOf('```')===0){
      if(inPre){html+='</code></pre>';inPre=false;}
      else{html+='<pre><code>';inPre=true;}
      continue;
    }
    if(inPre){html+=esc(line)+'\n';continue;}
    // Close list if not a list item
    if(inList&&!/^\s*[-*\d]/.test(line)&&line.trim()!==''){
      html+='</'+(listType==='ol'?'ol':'ul')+'>';inList=false;
    }
    // Headers
    if(/^### /.test(line)){html+='<h3>'+inlineMarkdown(line.slice(4))+'</h3>';continue;}
    if(/^## /.test(line)){html+='<h2>'+inlineMarkdown(line.slice(3))+'</h2>';continue;}
    if(/^# /.test(line)){html+='<h2>'+inlineMarkdown(line.slice(2))+'</h2>';continue;}
    // Blockquote
    if(/^> /.test(line)){html+='<blockquote>'+inlineMarkdown(line.slice(2))+'</blockquote>';continue;}
    // Unordered list
    if(/^\s*[-*] /.test(line)){
      if(!inList){html+='<ul>';inList=true;listType='ul';}
      html+='<li>'+inlineMarkdown(line.replace(/^\s*[-*] /,''))+'</li>';continue;
    }
    // Ordered list
    if(/^\s*\d+\.\s/.test(line)){
      if(!inList){html+='<ol>';inList=true;listType='ol';}
      html+='<li>'+inlineMarkdown(line.replace(/^\s*\d+\.\s/,''))+'</li>';continue;
    }
    // Table
    if(/^\|/.test(line)&&/\|$/.test(line.trim())){
      // Check if it's a separator row
      if(/^\|[\s-:|]+\|$/.test(line.trim()))continue;
      var cells=line.split('|').filter(function(c){return c.trim()!==''});
      var isHeader=i+1<lines.length&&/^\|[\s-:|]+\|$/.test(lines[i+1].trim());
      var tag=isHeader?'th':'td';
      html+='<table><tr>';
      cells.forEach(function(c){html+='<'+tag+'>'+inlineMarkdown(c.trim())+'</'+tag+'>';});
      html+='</tr></table>';
      continue;
    }
    // Empty line
    if(line.trim()===''){html+='<br>';continue;}
    // Normal paragraph
    html+='<p>'+inlineMarkdown(line)+'</p>';
  }
  if(inPre)html+='</code></pre>';
  if(inList)html+='</'+(listType==='ol'?'ol':'ul')+'>';
  return html;
}

function inlineMarkdown(text){
  // Bold
  text=text.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // Italic
  text=text.replace(/\*(.+?)\*/g,'<em>$1</em>');
  // Code
  text=text.replace(/`([^`]+)`/g,'<code>$1</code>');
  return text;
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
    <svg class="lines" viewBox="0 0 400 400" preserveAspectRatio="xMidYMid meet">
      <line x1="200" y1="200" x2="200" y2="60"/>
      <line x1="200" y1="200" x2="60"  y2="200"/>
      <line x1="200" y1="200" x2="340" y2="200"/>
      <line x1="200" y1="200" x2="200" y2="340"/>
    </svg>
    <!-- FIX 0: CSS diamond icon replaces brain emoji -->
    <div class="bubble center" id="bubble-boss" style="left:50%;top:50%;transform:translate(-50%,-50%)">
      <div class="bubble-circle"><div class="boss-icon"></div><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Crew Boss</span><span class="bubble-count"></span>
    </div>
    <div class="bubble outer" id="bubble-well" style="left:50%;top:5%;transform:translateX(-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f49a</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Wellness</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-guard" style="left:2%;top:50%;transform:translateY(-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f6e1\ufe0f</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Guard</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-ideas" style="right:2%;top:50%;transform:translateY(-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f4a1</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Ideas</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
    <div class="bubble outer" id="bubble-wallet" style="left:50%;bottom:5%;transform:translateX(-50%)">
      <div class="bubble-circle"><span class="icon">\U0001f4b0</span><span class="status-dot dot-green"></span></div>
      <span class="bubble-label">Wallet</span><span class="bubble-count"></span><span class="bubble-sub"></span>
    </div>
  </div>
  <!-- FIX 3: indicators click opens popup, no more bottom sheet -->
  <div class="indicators">
    <div class="indicator" onclick="openTBPopup()">
      <label>Trust</label><span class="val" id="trust-val" style="color:var(--ac)">5</span>
    </div>
    <div class="indicator" onclick="openTBPopup()">
      <label>Burnout</label><span class="burnout-dot" id="burnout-dot" style="background:var(--yl)"></span>
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
  <!-- Strategy agent tabs (Chat / Learn) -->
  <div class="as-tabs" id="as-tabs" style="display:none">
    <button class="as-tab active" data-tab="chat" onclick="switchAsTab('chat')">Chat</button>
    <button class="as-tab" data-tab="learn" onclick="switchAsTab('learn')">Learn</button>
    <button class="as-tab-gear" id="learn-gear-btn" onclick="toggleLearnSettings()" title="Learning Profile" style="display:none">&#9881;</button>
  </div>
  <div class="as-body" id="as-body-chat">
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
  <!-- Learn tab body (only for strategy agent) -->
  <div class="as-body" id="as-body-learn" style="display:none">
    <div id="learn-settings-panel" style="display:none"></div>
    <div id="learn-content"></div>
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

<!-- Agent Creation Wizard -->
<div class="wizard-overlay" id="wizard-overlay" onclick="if(event.target===this)closeWizard()">
  <div class="wizard-panel">
    <h2>Create a Team</h2>
    <p class="wizard-sub">Your guide to crew-bus. Build teams, add agents, manage your crew.</p>
    <div class="wizard-steps">
      <div class="wizard-step active"></div>
      <div class="wizard-step"></div>
      <div class="wizard-step"></div>
      <div class="wizard-step"></div>
    </div>
    <div class="wizard-body" id="wizard-body"></div>
    <div class="wiz-error" id="wizard-error"></div>
    <div class="wizard-footer" id="wizard-footer"></div>
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


def _get_human_id(db_path):
    """Get the human agent's ID."""
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute(
            "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
        ).fetchone()
        return human["id"] if human else None
    finally:
        conn.close()


def _get_strategy_agent_id(db_path):
    """Get the strategy (Ideas) agent's ID."""
    conn = bus.get_conn(db_path)
    try:
        agent = conn.execute(
            "SELECT id FROM agents WHERE agent_type='strategy' AND status='active' LIMIT 1"
        ).fetchone()
        return agent["id"] if agent else None
    finally:
        conn.close()


def _start_instruction(db_path, human_id, agent_id, topic, category):
    """Start a new instruction session with generated lesson plan."""
    session = bus.start_instruction_session(
        human_id, agent_id, topic, category=category, db_path=db_path)

    inst = instructor.Instructor(human_id, agent_id, db_path=db_path)
    steps = inst.generate_lesson_plan(topic, category=category)

    for step_data in steps:
        bus.add_instruction_step(
            session_id=session["id"],
            step_number=step_data["step_number"],
            title=step_data["title"],
            content=step_data["content"],
            step_type=step_data["step_type"],
            db_path=db_path,
        )

    return bus.get_instruction_session(session["id"], db_path=db_path)


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


def _load_team_templates():
    """Load team templates from configs/team_templates.json."""
    tpl_path = Path(__file__).parent / "configs" / "team_templates.json"
    if tpl_path.is_file():
        with open(tpl_path) as f:
            return json.load(f)
    return []


# ── Agent name / team validation ──────────────────────────────────

_AGENT_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]*$')
_RESERVED_TYPES = {"human", "right_hand", "security"}
_MAX_AGENTS = 50


def _validate_agent_name(name):
    """Return error string or None if valid."""
    if not name or not name.strip():
        return "Agent name is required."
    name = name.strip()
    if len(name) > 60:
        return "Agent name must be 60 characters or fewer."
    if not _AGENT_NAME_RE.match(name):
        return "Agent name can only contain letters, numbers, and hyphens, and must start with a letter or number."
    return None


def _check_agent_limit(conn):
    """Return error string if agent limit exceeded, else None."""
    count = conn.execute("SELECT COUNT(*) FROM agents WHERE active=1").fetchone()[0]
    if count >= _MAX_AGENTS:
        return f"Cannot create more agents. Limit is {_MAX_AGENTS} active agents."
    return None


def _check_unique_name(conn, name):
    """Return error string if name already taken, else None."""
    exists = conn.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
    if exists:
        return f"An agent named '{name}' already exists."
    return None


def _check_unique_team_name(conn, team_name):
    """Return error string if a team with this manager-name pattern already exists."""
    # Teams are identified by their manager, so check for manager named <Team>-Lead or similar
    # But we also check team_name as a concept — no two managers should share the derived team name
    managers = conn.execute("SELECT name FROM agents WHERE agent_type='manager' AND active=1").fetchall()
    for mgr in managers:
        existing_team = mgr["name"].replace("-Manager", "").replace("-Lead", "").replace("Manager", "").replace("Lead", "").strip()
        if existing_team.lower() == team_name.strip().lower():
            return f"A team named '{team_name}' already exists."
    return None


def _get_templates(db_path):
    """Return list of team templates."""
    return _load_team_templates()


def _create_team_from_wizard(db_path, data):
    """Create a full team (manager + workers) from wizard data.

    Expects:
        team_name: str
        description: str
        manager_name: str
        manager_description: str
        workers: [{name, description}, ...]
    """
    team_name = (data.get("team_name") or "").strip()
    manager_name = (data.get("manager_name") or "").strip()
    manager_desc = (data.get("manager_description") or "").strip()
    workers = data.get("workers") or []

    if not team_name:
        return {"ok": False, "error": "Team name is required."}
    if not manager_name:
        return {"ok": False, "error": "Manager name is required."}

    err = _validate_agent_name(manager_name)
    if err:
        return {"ok": False, "error": f"Manager name: {err}"}

    for i, w in enumerate(workers):
        wn = (w.get("name") or "").strip()
        if not wn:
            return {"ok": False, "error": f"Worker {i+1}: name is required."}
        err = _validate_agent_name(wn)
        if err:
            return {"ok": False, "error": f"Worker '{wn}': {err}"}

    if len(workers) > 10:
        return {"ok": False, "error": "Maximum 10 workers per team."}

    conn = bus.get_conn(db_path)
    try:
        # Check agent limit
        err = _check_agent_limit(conn)
        if err:
            return {"ok": False, "error": err}

        # Check uniqueness
        err = _check_unique_name(conn, manager_name)
        if err:
            return {"ok": False, "error": err}

        for w in workers:
            wn = w["name"].strip()
            err = _check_unique_name(conn, wn)
            if err:
                return {"ok": False, "error": err}

        # Also check no duplicate names within the request itself
        all_names = [manager_name] + [w["name"].strip() for w in workers]
        if len(set(n.lower() for n in all_names)) != len(all_names):
            return {"ok": False, "error": "Duplicate agent names in request."}

        # Check reserved types won't be used (agent_type is set by us, not user, so this is safe)
        # Find the right_hand agent (Crew Boss) as parent for manager
        rh = conn.execute("SELECT id, name FROM agents WHERE agent_type='right_hand' LIMIT 1").fetchone()
        if not rh:
            return {"ok": False, "error": "No Crew Boss found. Initialize crew-bus first (load a config)."}

        # Create manager
        mgr_id = bus._upsert_agent(conn, {
            "name": manager_name,
            "agent_type": "manager",
            "channel": "console",
            "description": manager_desc,
            "parent": rh["name"],
            "active": True,
        })

        # Create workers
        created_workers = []
        for w in workers:
            wn = w["name"].strip()
            wd = (w.get("description") or "").strip()
            wid = bus._upsert_agent(conn, {
                "name": wn,
                "agent_type": "worker",
                "channel": "console",
                "description": wd,
                "parent": manager_name,
                "active": True,
            })
            created_workers.append({"id": wid, "name": wn, "description": wd})

        # Audit
        bus._audit(conn, "team_created", mgr_id, {
            "team_name": team_name,
            "manager": manager_name,
            "workers": [w["name"] for w in created_workers],
        })
        conn.commit()

        return {
            "ok": True,
            "team_name": team_name,
            "manager": {"id": mgr_id, "name": manager_name, "description": manager_desc},
            "workers": created_workers,
            "agent_count": 1 + len(created_workers),
        }
    finally:
        conn.close()


def _create_single_agent(db_path, data):
    """Create a single agent with parent validation.

    Expects:
        name: str
        agent_type: str (worker or specialist)
        parent_name: str
        description: str
        channel: str (optional, default console)
    """
    name = (data.get("name") or "").strip()
    agent_type = (data.get("agent_type") or "worker").strip()
    parent_name = (data.get("parent_name") or "").strip()
    description = (data.get("description") or "").strip()
    channel = (data.get("channel") or "console").strip()

    if not name:
        return {"ok": False, "error": "Agent name is required."}

    err = _validate_agent_name(name)
    if err:
        return {"ok": False, "error": err}

    if agent_type in _RESERVED_TYPES:
        return {"ok": False, "error": f"Cannot create agents with reserved type '{agent_type}'."}

    if agent_type not in ("worker", "specialist", "manager"):
        return {"ok": False, "error": f"Invalid agent type '{agent_type}'. Use 'worker', 'specialist', or 'manager'."}

    if not parent_name:
        return {"ok": False, "error": "Parent agent name is required."}

    conn = bus.get_conn(db_path)
    try:
        err = _check_agent_limit(conn)
        if err:
            return {"ok": False, "error": err}

        err = _check_unique_name(conn, name)
        if err:
            return {"ok": False, "error": err}

        parent = conn.execute("SELECT * FROM agents WHERE name=?", (parent_name,)).fetchone()
        if not parent:
            return {"ok": False, "error": f"Parent agent '{parent_name}' not found."}

        # Validate parent type
        if agent_type == "manager" and parent["agent_type"] != "right_hand":
            return {"ok": False, "error": "Manager agents must report to Crew Boss (right_hand)."}
        if agent_type in ("worker", "specialist") and parent["agent_type"] not in ("manager", "right_hand"):
            return {"ok": False, "error": "Worker/specialist agents must report to a manager or Crew Boss."}

        agent_id = bus._upsert_agent(conn, {
            "name": name,
            "agent_type": agent_type,
            "channel": channel,
            "description": description,
            "parent": parent_name,
            "active": True,
        })

        bus._audit(conn, "agent_created", agent_id, {
            "name": name, "agent_type": agent_type,
            "parent": parent_name,
        })
        conn.commit()

        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return {"ok": True, "agent": dict(agent)}
    finally:
        conn.close()


def _deactivate_agent(db_path, agent_id):
    """Deactivate an agent (set active=0, status=terminated). Keep DB row for audit."""
    conn = bus.get_conn(db_path)
    try:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            return {"ok": False, "error": "Agent not found."}

        if agent["agent_type"] in ("human", "right_hand", "security"):
            return {"ok": False, "error": f"Cannot deactivate {agent['agent_type']} agent."}

        if agent["agent_type"] == "help":
            return {"ok": False, "error": "Cannot deactivate the Help agent."}

        conn.execute(
            "UPDATE agents SET active=0, status='terminated', "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
            (agent_id,),
        )
        bus._audit(conn, "agent_deactivated_wizard", agent_id, {
            "name": agent["name"], "agent_type": agent["agent_type"],
        })
        conn.commit()
        return {"ok": True, "agent_id": agent_id, "name": agent["name"]}
    finally:
        conn.close()


def _update_agent_description(db_path, agent_id, description):
    """Update an agent's description."""
    conn = bus.get_conn(db_path)
    try:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            return {"ok": False, "error": "Agent not found."}
        conn.execute(
            "UPDATE agents SET description=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
            (description, agent_id),
        )
        conn.commit()
        return {"ok": True, "agent_id": agent_id}
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

class CrewBusHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB

    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        m = re.match(r"^/api/agent/(\d+)$", path)
        if m:
            result = _deactivate_agent(self.db_path, int(m.group(1)))
            return _json_response(self, result, 200 if result.get("ok") else 400)

        _json_response(self, {"error": "not found"}, 404)

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

        if path == "/api/help/templates":
            return _json_response(self, _get_templates(self.db_path))

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

        # ── Learning / Instruction endpoints ──
        if path == "/api/learning-profile":
            hid = _get_human_id(self.db_path)
            if not hid:
                return _json_response(self, {"error": "no human agent"}, 500)
            return _json_response(self, bus.get_learning_profile(hid, db_path=self.db_path))

        if path == "/api/instruct/active":
            hid = _get_human_id(self.db_path)
            if not hid:
                return _json_response(self, {"error": "no human agent"}, 500)
            sessions = bus.list_instruction_sessions(hid, status="active", db_path=self.db_path)
            if sessions:
                session = bus.get_instruction_session(sessions[0]["id"], db_path=self.db_path)
                return _json_response(self, session or {})
            return _json_response(self, {})

        m = re.match(r"^/api/instruct/session/(\d+)$", path)
        if m:
            session = bus.get_instruction_session(int(m.group(1)), db_path=self.db_path)
            return _json_response(self, session or {"error": "not found"}, 200 if session else 404)

        if path == "/api/instruct/history":
            hid = _get_human_id(self.db_path)
            if not hid:
                return _json_response(self, {"error": "no human agent"}, 500)
            return _json_response(self, bus.get_instruction_history(hid, db_path=self.db_path))

        if path == "/api/health":
            return _json_response(self, {"status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "db_path": str(self.db_path)})

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

        if path == "/api/help/create-team":
            result = _create_team_from_wizard(self.db_path, data)
            return _json_response(self, result, 201 if result.get("ok") else 400)

        if path == "/api/help/create-agent":
            result = _create_single_agent(self.db_path, data)
            return _json_response(self, result, 201 if result.get("ok") else 400)

        m = re.match(r"^/api/agent/(\d+)/description$", path)
        if m:
            desc = (data.get("description") or "").strip()
            result = _update_agent_description(self.db_path, int(m.group(1)), desc)
            return _json_response(self, result, 200 if result.get("ok") else 400)

        m = re.match(r"^/api/agent/(\d+)/deactivate$", path)
        if m:
            result = _deactivate_agent(self.db_path, int(m.group(1)))
            return _json_response(self, result, 200 if result.get("ok") else 400)

        if path == "/api/teams":
            return _json_response(self, _create_team(self.db_path, data.get("template", "custom")), 201)

        # ── Learning / Instruction POST endpoints ──
        if path == "/api/learning-profile":
            hid = _get_human_id(self.db_path)
            if not hid:
                return _json_response(self, {"error": "no human agent"}, 500)
            result = bus.update_learning_profile(hid, data, db_path=self.db_path)
            return _json_response(self, result)

        if path == "/api/instruct/start":
            hid = _get_human_id(self.db_path)
            if not hid:
                return _json_response(self, {"error": "no human agent"}, 500)
            topic = data.get("topic", "").strip()
            if not topic:
                return _json_response(self, {"error": "need topic"}, 400)
            category = data.get("category", "general")
            # Find the strategy agent (Ideas)
            agent_id = _get_strategy_agent_id(self.db_path)
            if not agent_id:
                return _json_response(self, {"error": "no Ideas agent found"}, 500)
            result = _start_instruction(self.db_path, hid, agent_id, topic, category)
            return _json_response(self, result, 201)

        m = re.match(r"^/api/instruct/step/(\d+)/complete$", path)
        if m:
            step_id = int(m.group(1))
            response = data.get("response")
            confidence = data.get("confidence")
            if confidence is not None:
                confidence = int(confidence)
            result = bus.complete_instruction_step(
                step_id, human_response=response, confidence=confidence,
                db_path=self.db_path)
            # Adaptive step insertion based on confidence
            if confidence is not None:
                step = result
                session = bus.get_instruction_session(
                    step["session_id"], db_path=self.db_path)
                if session:
                    hid = session["human_id"]
                    agent_id = session["agent_id"]
                    inst = instructor.Instructor(hid, agent_id, db_path=self.db_path)
                    inst.adapt_next_step(step["session_id"], confidence)
            return _json_response(self, result)

        m = re.match(r"^/api/instruct/session/(\d+)/complete$", path)
        if m:
            session_id = int(m.group(1))
            feedback = data.get("feedback")
            result = bus.complete_instruction_session(
                session_id, human_feedback=feedback, db_path=self.db_path)
            # Generate summary and store knowledge
            session = bus.get_instruction_session(session_id, db_path=self.db_path)
            if session:
                inst = instructor.Instructor(
                    session["human_id"], session["agent_id"],
                    db_path=self.db_path)
                inst.summarize_session(session_id)
            return _json_response(self, result)

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
    print(f"crew-bus dashboard running on http://{host}:{port}")
    print(f"Database: {server.RequestHandlerClass.db_path}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
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
