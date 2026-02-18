"""
crew-bus core engine (v2 - Human-First Architecture).

Local message bus for AI agent coordination built around the Crew Boss pattern.
Every human has a personal AI Chief of Staff (Crew Boss) that sits between them
and all other agents. The Crew Boss filters, prioritizes, and manages cognitive
load based on trust score, burnout awareness, and timing rules.

The hierarchy is universal - same pattern for individuals, families, small
businesses, and enterprises. Only the config changes.

FREE AND OPEN SOURCE — crew-bus is free infrastructure for the world, like Linux.
The entire system, all core agents, and full features are free forever.

Security Guard module available separately — see security_guard.py
The Security Guard (encryption, kill switches, tamper detection, audit hardening)
activates with a paid license key. Everything else works without it.
"""

import base64
import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

DB_PATH = Path(__file__).parent / "crew_bus.db"

# Guard activation verification key (signing key lives on crew-bus.dev server)
GUARD_ACTIVATION_VERIFY_KEY = "PLACEHOLDER_REPLACE_BEFORE_LAUNCH"

# Agent types in the universal hierarchy
VALID_AGENT_TYPES = (
    "human", "right_hand", "security",
    "strategy", "wellness", "financial", "legal", "knowledge", "communications",
    "manager", "worker", "specialist", "help",
)

# Role is now derived from agent_type for routing purposes
VALID_ROLES = ("human", "right_hand", "security", "core_crew", "manager", "worker")

VALID_STATUSES = ("active", "quarantined", "terminated")
VALID_CHANNELS = ("telegram", "signal", "email", "console")
VALID_MESSAGE_TYPES = ("report", "task", "alert", "escalation", "idea", "briefing")
VALID_PRIORITIES = ("low", "normal", "high", "critical")
VALID_MESSAGE_STATUSES = ("queued", "delivered", "read", "archived")

# Core crew agent types (report to Crew Boss)
CORE_CREW_TYPES = ("strategy", "wellness", "financial", "legal", "knowledge", "communications")

# Decision types for the decision log
VALID_DECISION_TYPES = (
    "filter", "deliver", "handle", "queue", "escalate",
    "block", "reputation_protect",
)

# Threat domains for security events
VALID_THREAT_DOMAINS = (
    "physical", "digital", "financial", "legal",
    "reputation", "mutiny", "relationship",
)

# Security event severities
VALID_SEVERITY_LEVELS = ("info", "low", "medium", "high", "critical")

# Relationship types
VALID_RELATIONSHIP_TYPES = ("family", "friend", "professional", "client", "vendor")
VALID_RELATIONSHIP_STATUSES = ("healthy", "attention_needed", "at_risk", "stale")

# Knowledge categories
VALID_KNOWLEDGE_CATEGORIES = ("decision", "contact", "lesson", "preference", "rejection")

# Timing rule types
VALID_TIMING_RULES = ("quiet_hours", "busy_signal", "burnout_threshold", "focus_mode")


def _role_for_type(agent_type: str) -> str:
    """Map an agent_type to its routing role."""
    if agent_type == "human":
        return "human"
    if agent_type == "right_hand":
        return "right_hand"
    if agent_type == "security":
        return "security"
    if agent_type in CORE_CREW_TYPES:
        return "core_crew"
    if agent_type == "manager":
        return "manager"
    return "worker"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a connection to the crew-bus database with row factory enabled."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Create all tables and seed default routing rules.

    Safe to call multiple times - uses IF NOT EXISTS for all objects.
    """
    conn = get_conn(db_path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL UNIQUE,
            agent_type      TEXT    NOT NULL DEFAULT 'worker',
            role            TEXT    NOT NULL DEFAULT 'worker',
            parent_agent_id INTEGER REFERENCES agents(id),
            status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','quarantined','terminated')),
            channel         TEXT    NOT NULL DEFAULT 'console'
                            CHECK(channel IN ('telegram','signal','email','console')),
            channel_address TEXT,
            trust_score     INTEGER NOT NULL DEFAULT 1 CHECK(trust_score BETWEEN 1 AND 10),
            burnout_score   INTEGER NOT NULL DEFAULT 5 CHECK(burnout_score BETWEEN 1 AND 10),
            budget_limit    REAL    NOT NULL DEFAULT 0.0,
            quiet_hours_start TEXT,
            quiet_hours_end   TEXT,
            timezone        TEXT    NOT NULL DEFAULT 'UTC',
            active          INTEGER NOT NULL DEFAULT 1,
            capabilities    TEXT    NOT NULL DEFAULT '[]',
            description     TEXT    NOT NULL DEFAULT '',
            model           TEXT    NOT NULL DEFAULT '',
            created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS crew_config (
            key             TEXT    PRIMARY KEY,
            value           TEXT    NOT NULL DEFAULT '',
            updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent_id   INTEGER NOT NULL REFERENCES agents(id),
            to_agent_id     INTEGER NOT NULL REFERENCES agents(id),
            message_type    TEXT    NOT NULL
                            CHECK(message_type IN ('report','task','alert','escalation','idea','briefing')),
            subject         TEXT    NOT NULL,
            body            TEXT    NOT NULL DEFAULT '',
            priority        TEXT    NOT NULL DEFAULT 'normal'
                            CHECK(priority IN ('low','normal','high','critical')),
            status          TEXT    NOT NULL DEFAULT 'queued'
                            CHECK(status IN ('queued','delivered','read','archived')),
            private_session_id INTEGER DEFAULT NULL REFERENCES private_sessions(id),
            created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            delivered_at    TEXT,
            read_at         TEXT
        );

        CREATE TABLE IF NOT EXISTS routing_rules (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            from_role        TEXT NOT NULL,
            to_role          TEXT NOT NULL,
            allowed          INTEGER NOT NULL DEFAULT 1,
            require_approval INTEGER NOT NULL DEFAULT 0,
            description      TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT    NOT NULL,
            agent_id    INTEGER REFERENCES agents(id),
            details     TEXT    NOT NULL DEFAULT '{}',
            timestamp   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS timing_rules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    INTEGER NOT NULL REFERENCES agents(id),
            rule_type   TEXT    NOT NULL
                        CHECK(rule_type IN ('quiet_hours','busy_signal','burnout_threshold','focus_mode')),
            rule_config TEXT    NOT NULL DEFAULT '{}',
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS decision_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            right_hand_id       INTEGER NOT NULL REFERENCES agents(id),
            human_id            INTEGER NOT NULL REFERENCES agents(id),
            decision_type       TEXT    NOT NULL
                                CHECK(decision_type IN (
                                    'filter','deliver','handle','queue','escalate',
                                    'block','reputation_protect')),
            context             TEXT    NOT NULL DEFAULT '{}',
            right_hand_action   TEXT    NOT NULL DEFAULT '',
            right_hand_reasoning TEXT,
            human_override      INTEGER NOT NULL DEFAULT 0,
            human_action        TEXT,
            feedback_note       TEXT,
            pattern_tags        TEXT    NOT NULL DEFAULT '[]',
            created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS knowledge_store (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id          INTEGER NOT NULL REFERENCES agents(id),
            category          TEXT    NOT NULL
                              CHECK(category IN ('decision','contact','lesson','preference','rejection')),
            subject           TEXT    NOT NULL,
            content           TEXT    NOT NULL DEFAULT '{}',
            tags              TEXT    NOT NULL DEFAULT '',
            source_message_id INTEGER REFERENCES messages(id),
            created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        -- ========= Day 2 tables =========

        CREATE TABLE IF NOT EXISTS human_profile (
            human_id                INTEGER PRIMARY KEY REFERENCES agents(id),
            personality_type        TEXT    NOT NULL DEFAULT 'hybrid'
                                    CHECK(personality_type IN ('introvert','extrovert','hybrid')),
            work_style              TEXT    NOT NULL DEFAULT 'balanced'
                                    CHECK(work_style IN ('workaholic','balanced','avoider')),
            social_recharge         TEXT    NOT NULL DEFAULT 'mixed'
                                    CHECK(social_recharge IN ('alone','people','mixed')),
            quiet_hours_start       TEXT,
            quiet_hours_end         TEXT,
            timezone                TEXT    NOT NULL DEFAULT 'UTC',
            communication_preferences TEXT NOT NULL DEFAULT '{}',
            known_triggers          TEXT    NOT NULL DEFAULT '[]',
            seasonal_patterns       TEXT    NOT NULL DEFAULT '{}',
            relationship_priorities TEXT    NOT NULL DEFAULT '[]',
            notes                   TEXT    NOT NULL DEFAULT '',
            updated_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS trust_config (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            human_id        INTEGER NOT NULL REFERENCES agents(id),
            right_hand_id   INTEGER NOT NULL REFERENCES agents(id),
            trust_score     INTEGER NOT NULL DEFAULT 1 CHECK(trust_score BETWEEN 1 AND 10),
            autonomy_rules  TEXT    NOT NULL DEFAULT '{}',
            escalation_overrides TEXT NOT NULL DEFAULT '[]',
            updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_by      TEXT    NOT NULL DEFAULT 'system',
            UNIQUE(human_id, right_hand_id)
        );

        CREATE TABLE IF NOT EXISTS human_state (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            human_id                INTEGER NOT NULL REFERENCES agents(id),
            burnout_score           INTEGER NOT NULL DEFAULT 5 CHECK(burnout_score BETWEEN 1 AND 10),
            energy_level            TEXT    NOT NULL DEFAULT 'medium'
                                    CHECK(energy_level IN ('high','medium','low')),
            current_activity        TEXT    NOT NULL DEFAULT 'working'
                                    CHECK(current_activity IN (
                                        'working','meeting','driving','resting',
                                        'family_time','unavailable')),
            mood_indicator          TEXT    NOT NULL DEFAULT 'neutral'
                                    CHECK(mood_indicator IN (
                                        'good','neutral','stressed','frustrated','energized')),
            last_social_activity    TEXT,
            last_family_contact     TEXT,
            consecutive_work_days   INTEGER NOT NULL DEFAULT 0,
            updated_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_by              TEXT    NOT NULL DEFAULT 'system'
        );

        CREATE TABLE IF NOT EXISTS security_events (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            security_agent_id       INTEGER NOT NULL REFERENCES agents(id),
            threat_domain           TEXT    NOT NULL
                                    CHECK(threat_domain IN (
                                        'physical','digital','financial','legal',
                                        'reputation','mutiny','relationship')),
            severity                TEXT    NOT NULL DEFAULT 'info'
                                    CHECK(severity IN ('info','low','medium','high','critical')),
            title                   TEXT    NOT NULL,
            details                 TEXT    NOT NULL DEFAULT '{}',
            recommended_action      TEXT    NOT NULL DEFAULT '',
            delivered_to_right_hand INTEGER NOT NULL DEFAULT 0,
            delivered_to_human      INTEGER NOT NULL DEFAULT 0,
            resolution              TEXT,
            created_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            resolved_at             TEXT
        );

        CREATE TABLE IF NOT EXISTS relationship_tracker (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            human_id                INTEGER NOT NULL REFERENCES agents(id),
            contact_name            TEXT    NOT NULL,
            contact_type            TEXT    NOT NULL DEFAULT 'professional'
                                    CHECK(contact_type IN ('family','friend','professional','client','vendor')),
            importance              INTEGER NOT NULL DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            last_contact            TEXT,
            preferred_frequency_days INTEGER NOT NULL DEFAULT 30,
            notes                   TEXT    NOT NULL DEFAULT '',
            status                  TEXT    NOT NULL DEFAULT 'healthy'
                                    CHECK(status IN ('healthy','attention_needed','at_risk','stale')),
            updated_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        CREATE TABLE IF NOT EXISTS rejection_history (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            human_id            INTEGER NOT NULL REFERENCES agents(id),
            strategy_agent_id   INTEGER NOT NULL REFERENCES agents(id),
            idea_subject        TEXT    NOT NULL,
            idea_body           TEXT    NOT NULL DEFAULT '',
            rejection_reason    TEXT,
            created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        -- ========= Private Sessions =========

        CREATE TABLE IF NOT EXISTS private_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            human_id        INTEGER NOT NULL REFERENCES agents(id),
            agent_id        INTEGER NOT NULL REFERENCES agents(id),
            channel         TEXT    NOT NULL DEFAULT 'web',
            started_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            last_activity_at TEXT   NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            expires_at      TEXT    NOT NULL,
            timeout_minutes INTEGER NOT NULL DEFAULT 30,
            active          INTEGER NOT NULL DEFAULT 1,
            message_count   INTEGER NOT NULL DEFAULT 0,
            ended_by        TEXT    DEFAULT NULL,
            ended_at        TEXT    DEFAULT NULL
        );

        -- ========= Team Mailbox =========

        CREATE TABLE IF NOT EXISTS team_mailbox (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id         INTEGER NOT NULL,
            from_agent_id   INTEGER NOT NULL REFERENCES agents(id),
            severity        TEXT    NOT NULL DEFAULT 'info'
                            CHECK(severity IN ('info','warning','code_red')),
            subject         TEXT    NOT NULL,
            body            TEXT    NOT NULL,
            read            INTEGER NOT NULL DEFAULT 0,
            read_at         TEXT    DEFAULT NULL,
            created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );

        -- ========= Guard Activation =========

        CREATE TABLE IF NOT EXISTS guard_activation (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            activation_key  TEXT    UNIQUE NOT NULL,
            activated_at    TEXT    NOT NULL,
            key_fingerprint TEXT    NOT NULL
        );

        -- ========= Agent Skills =========

        CREATE TABLE IF NOT EXISTS agent_skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    INTEGER NOT NULL,
            skill_name  TEXT    NOT NULL,
            skill_config TEXT   DEFAULT '{}',
            added_at    TEXT    NOT NULL,
            added_by    TEXT    DEFAULT 'human',
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            UNIQUE(agent_id, skill_name)
        );

        -- ========= Techie Marketplace =========

        CREATE TABLE IF NOT EXISTS authorized_techies (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            techie_id           TEXT    UNIQUE NOT NULL,
            display_name        TEXT    NOT NULL,
            email               TEXT    NOT NULL,
            kyc_status          TEXT    DEFAULT 'pending',
            kyc_verified_at     TEXT,
            standing            TEXT    DEFAULT 'good',
            standing_notes      TEXT    DEFAULT '',
            total_keys_purchased INTEGER DEFAULT 0,
            total_jobs_completed INTEGER DEFAULT 0,
            rating_avg          REAL    DEFAULT 0.0,
            rating_count        INTEGER DEFAULT 0,
            created_at          TEXT    NOT NULL,
            revoked_at          TEXT,
            revocation_reason   TEXT
        );

        CREATE TABLE IF NOT EXISTS techie_keys (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            techie_id       TEXT    NOT NULL,
            key_value       TEXT    UNIQUE NOT NULL,
            purchased_at    TEXT    NOT NULL,
            used_at         TEXT,
            used_for_user   TEXT,
            FOREIGN KEY (techie_id) REFERENCES authorized_techies(techie_id)
        );

        CREATE TABLE IF NOT EXISTS techie_reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            techie_id       TEXT    NOT NULL,
            reviewer_id     TEXT    NOT NULL,
            rating          INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            review_text     TEXT    DEFAULT '',
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (techie_id) REFERENCES authorized_techies(techie_id)
        );

        -- ========= User Auth =========

        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT    UNIQUE NOT NULL,
            password_hash   TEXT    NOT NULL,
            user_type       TEXT    NOT NULL DEFAULT 'client',
            display_name    TEXT    DEFAULT '',
            email_verified  INTEGER DEFAULT 0,
            verify_token    TEXT,
            reset_token     TEXT,
            reset_expires   TEXT,
            techie_id       TEXT,
            created_at      TEXT    NOT NULL,
            last_login      TEXT,
            FOREIGN KEY (techie_id) REFERENCES authorized_techies(techie_id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            token           TEXT    UNIQUE NOT NULL,
            expires_at      TEXT    NOT NULL,
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- ========= Jobs =========

        CREATE TABLE IF NOT EXISTS jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            description     TEXT    NOT NULL,
            needs           TEXT    DEFAULT '',
            postal_code     TEXT    DEFAULT '',
            country         TEXT    DEFAULT '',
            urgency         TEXT    DEFAULT 'standard',
            budget          TEXT    DEFAULT 'negotiable',
            contact_name    TEXT    DEFAULT '',
            contact_email   TEXT    DEFAULT '',
            status          TEXT    DEFAULT 'open',
            posted_by       INTEGER,
            claimed_by      TEXT,
            claimed_at      TEXT,
            completed_at    TEXT,
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (posted_by) REFERENCES users(id),
            FOREIGN KEY (claimed_by) REFERENCES authorized_techies(techie_id)
        );

        -- ========= Meet & Greet =========

        CREATE TABLE IF NOT EXISTS meet_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_user_id  INTEGER,
            techie_id       TEXT    NOT NULL,
            job_id          INTEGER,
            status          TEXT    DEFAULT 'pending',
            proposed_times  TEXT    DEFAULT '[]',
            accepted_time   TEXT,
            meeting_link    TEXT,
            notes           TEXT    DEFAULT '',
            created_at      TEXT    NOT NULL,
            responded_at    TEXT,
            FOREIGN KEY (client_user_id) REFERENCES users(id),
            FOREIGN KEY (techie_id) REFERENCES authorized_techies(techie_id),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        -- ========= Indexes =========

        CREATE INDEX IF NOT EXISTS idx_messages_to      ON messages(to_agent_id, status);
        CREATE INDEX IF NOT EXISTS idx_messages_from    ON messages(from_agent_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_agent      ON audit_log(agent_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_timing_agent     ON timing_rules(agent_id, rule_type);
        CREATE INDEX IF NOT EXISTS idx_decision_human   ON decision_log(human_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_decision_rh      ON decision_log(right_hand_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_knowledge_cat    ON knowledge_store(category, subject);
        CREATE INDEX IF NOT EXISTS idx_knowledge_agent  ON knowledge_store(agent_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_tags   ON knowledge_store(tags);
        CREATE INDEX IF NOT EXISTS idx_security_domain  ON security_events(threat_domain, severity);
        CREATE INDEX IF NOT EXISTS idx_security_agent   ON security_events(security_agent_id);
        CREATE INDEX IF NOT EXISTS idx_relationship     ON relationship_tracker(human_id, status);
        CREATE INDEX IF NOT EXISTS idx_human_state      ON human_state(human_id);
        CREATE INDEX IF NOT EXISTS idx_trust_config     ON trust_config(human_id);
        CREATE INDEX IF NOT EXISTS idx_rejection_human  ON rejection_history(human_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_rejection_strat  ON rejection_history(strategy_agent_id, idea_subject);
        CREATE INDEX IF NOT EXISTS idx_private_sessions_active ON private_sessions(human_id, agent_id, active);
        CREATE INDEX IF NOT EXISTS idx_team_mailbox_unread ON team_mailbox(team_id, read, severity);
        CREATE INDEX IF NOT EXISTS idx_team_mailbox_agent_rate ON team_mailbox(from_agent_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_skills_agent ON agent_skills(agent_id, skill_name);
        CREATE INDEX IF NOT EXISTS idx_techie_standing    ON authorized_techies(kyc_status, standing);
        CREATE INDEX IF NOT EXISTS idx_techie_keys_techie ON techie_keys(techie_id);
        CREATE INDEX IF NOT EXISTS idx_techie_reviews     ON techie_reviews(techie_id);
        CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);
        CREATE INDEX IF NOT EXISTS idx_sessions_token     ON sessions(token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user      ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_status        ON jobs(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_jobs_postal        ON jobs(postal_code, status);
        CREATE INDEX IF NOT EXISTS idx_meet_techie        ON meet_requests(techie_id, status);
        CREATE INDEX IF NOT EXISTS idx_meet_client        ON meet_requests(client_user_id, status);
    """)

    # Migrate existing DBs: add model column to agents if missing
    cols = [r[1] for r in cur.execute("PRAGMA table_info(agents)").fetchall()]
    if "model" not in cols:
        cur.execute("ALTER TABLE agents ADD COLUMN model TEXT NOT NULL DEFAULT ''")

    # Seed default routing rules (skip if already populated)
    existing = cur.execute("SELECT COUNT(*) FROM routing_rules").fetchone()[0]
    if existing == 0:
        _seed_routing_rules(cur)

    conn.commit()
    conn.close()


def _seed_routing_rules(cur: sqlite3.Cursor) -> None:
    """Insert the default routing rules for the Human-First hierarchy.

    Core principle: Only Crew Boss talks to the human (with safety exceptions).
    """
    rules = [
        # Crew Boss is the gatekeeper
        ("right_hand", "human", 1, 0, "Crew Boss delivers to human"),
        ("right_hand", "core_crew", 1, 0, "Crew Boss manages core crew"),
        ("right_hand", "security", 1, 0, "Crew Boss manages security agent"),
        ("right_hand", "manager", 1, 0, "Crew Boss manages department managers"),
        ("right_hand", "worker", 1, 0, "Crew Boss can reach any worker"),

        # Human can message anyone (ultimate authority)
        ("human", "right_hand", 1, 0, "Human directs Crew Boss"),
        ("human", "security", 1, 0, "Human can reach security agent"),
        ("human", "core_crew", 1, 0, "Human can reach any agent"),
        ("human", "manager", 1, 0, "Human can reach any agent"),
        ("human", "worker", 1, 0, "Human can reach any agent"),

        # Security agent reports to Crew Boss only (unless direct feed enabled)
        ("security", "right_hand", 1, 0, "Security reports to Crew Boss"),
        ("security", "human", 0, 0, "Security must go through Crew Boss (unless direct feed)"),
        ("security", "core_crew", 0, 0, "Security cannot message core crew"),
        ("security", "manager", 0, 0, "Security cannot message managers"),
        ("security", "worker", 0, 0, "Security cannot message workers"),

        # Core crew reports to Crew Boss only
        ("core_crew", "right_hand", 1, 0, "Core crew reports to Crew Boss"),
        ("core_crew", "human", 0, 0, "Core crew must go through Crew Boss"),
        ("core_crew", "core_crew", 0, 0, "Core crew cannot message each other"),
        ("core_crew", "security", 0, 0, "Core crew cannot message security"),
        ("core_crew", "manager", 0, 0, "Core crew cannot message managers directly"),
        ("core_crew", "worker", 0, 0, "Core crew cannot message workers directly"),

        # Managers report to Crew Boss
        ("manager", "right_hand", 1, 0, "Managers report to Crew Boss"),
        ("manager", "worker", 1, 0, "Managers message their workers"),
        ("manager", "human", 0, 0, "Managers must go through Crew Boss"),
        ("manager", "manager", 0, 0, "Managers cannot message other managers"),
        ("manager", "core_crew", 0, 0, "Managers cannot message core crew"),
        ("manager", "security", 0, 0, "Managers cannot message security"),

        # Workers report to their manager
        ("worker", "manager", 1, 0, "Workers report to their manager"),
        ("worker", "right_hand", 1, 0, "Workers can safety-escalate to Crew Boss"),
        ("worker", "human", 0, 0, "Workers cannot message human directly"),
        ("worker", "worker", 0, 0, "Workers cannot message other workers"),
        ("worker", "core_crew", 0, 0, "Workers cannot message core crew"),
        ("worker", "security", 0, 0, "Workers cannot message security"),
    ]
    cur.executemany(
        "INSERT INTO routing_rules (from_role, to_role, allowed, require_approval, description) "
        "VALUES (?, ?, ?, ?, ?)",
        rules,
    )


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit(conn: sqlite3.Connection, event_type: str,
           agent_id: Optional[int], details: dict) -> None:
    """Write an entry to the audit log."""
    conn.execute(
        "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
        (event_type, agent_id, json.dumps(details)),
    )


# ---------------------------------------------------------------------------
# Hierarchy loading (v2 - nested YAML format)
# ---------------------------------------------------------------------------

def load_hierarchy(config_path: str, db_path: Optional[Path] = None) -> dict:
    """Parse a v2 YAML config file and register all agents into the database.

    Supports the nested hierarchy format with human, right_hand, core_crew,
    departments, and timing rules. Also supports the v1 flat format for
    backwards compatibility.

    Returns a summary dict of agents created.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Detect config format
    if "hierarchy" in config:
        return _load_v2_hierarchy(config, config_path, db_path)
    elif "human" in config and "right_hand" in config:
        # Spec format: organization + human/right_hand/core_crew/departments at top level
        # Wrap them under "hierarchy" key for the v2 loader
        org_name = config.get("organization", {}).get("name", "")
        wrapped = {
            "org_name": org_name,
            "hierarchy": {
                "human": config["human"],
                "right_hand": config["right_hand"],
                "core_crew": config.get("core_crew", {}),
                "departments": config.get("departments", []),
            },
        }
        return _load_v2_hierarchy(wrapped, config_path, db_path)
    elif "crew_boss" in config and "agents" in config:
        # Crew format: crew/crew_boss/agents (example crew YAMLs)
        return _load_crew_format(config, config_path, db_path)
    elif "agents" in config:
        return _load_v1_hierarchy(config, config_path, db_path)
    else:
        raise ValueError("Unrecognized config format: needs 'hierarchy', 'human', 'crew_boss', or 'agents' key")


def _load_v2_hierarchy(config: dict, config_path: str,
                       db_path: Optional[Path] = None) -> dict:
    """Load the v2 nested hierarchy format."""
    conn = get_conn(db_path)
    hier = config["hierarchy"]
    created = []

    # 1. Register the human
    human_def = hier["human"]
    qh = human_def.get("quiet_hours", {})
    human_id = _upsert_agent(conn, {
        "name": human_def["name"],
        "agent_type": "human",
        "channel": human_def.get("channel", "console"),
        "channel_address": human_def.get("channel_address"),
        "description": human_def.get("description", "Human principal"),
        "burnout_score": human_def.get("burnout_score", 5),
        "quiet_hours_start": qh.get("start"),
        "quiet_hours_end": qh.get("end"),
        "timezone": human_def.get("timezone", "UTC"),
    })
    created.append(human_def["name"])

    # Set up timing rules for the human
    if "quiet_hours" in human_def:
        _upsert_timing_rule(conn, human_id, "quiet_hours", {
            "start": human_def["quiet_hours"]["start"],
            "end": human_def["quiet_hours"]["end"],
            "timezone": human_def.get("timezone", "UTC"),
        })
    if "timezone" in human_def:
        _upsert_timing_rule(conn, human_id, "burnout_threshold", {
            "threshold": 7,
            "timezone": human_def["timezone"],
        })

    # 2. Register Crew Boss
    rh_def = hier["right_hand"]
    rh_id = _upsert_agent(conn, {
        "name": rh_def["name"],
        "agent_type": "right_hand",
        "channel": rh_def.get("channel", "console"),
        "channel_address": rh_def.get("channel_address"),
        "parent": human_def["name"],
        "trust_score": rh_def.get("trust_score", 1),
        "budget_limit": rh_def.get("budget_limit", 0.0),
        "description": rh_def.get("description", "AI Chief of Staff"),
    })
    created.append(rh_def["name"])

    # 2b. Register Security Agent (if present in core_crew)
    core_crew = hier.get("core_crew", {})
    sec_def = core_crew.get("security")
    if isinstance(sec_def, dict):
        _upsert_agent(conn, {
            "name": sec_def["name"],
            "agent_type": "security",
            "channel": sec_def.get("channel", "console"),
            "channel_address": sec_def.get("channel_address"),
            "parent": rh_def["name"],
            "active": sec_def.get("active", True),
            "description": sec_def.get("description", "Security monitor"),
        })
        created.append(sec_def["name"])

    # 2c. Set up human profile from config
    profile_data = {}
    personality = human_def.get("personality", {})
    if personality:
        profile_data["personality_type"] = personality.get("type", "hybrid")
        profile_data["work_style"] = personality.get("work_style", "balanced")
        profile_data["social_recharge"] = personality.get("social_recharge", "mixed")
    comms = human_def.get("communication", {})
    if comms:
        profile_data["communication_preferences"] = comms
    if "known_triggers" in human_def:
        profile_data["known_triggers"] = human_def["known_triggers"]
    if "timezone" in human_def:
        profile_data["timezone"] = human_def["timezone"]
    if "quiet_hours" in human_def:
        profile_data["quiet_hours_start"] = human_def["quiet_hours"]["start"]
        profile_data["quiet_hours_end"] = human_def["quiet_hours"]["end"]

    conn.commit()  # Ensure human exists before profile insert
    if profile_data:
        # Use direct SQL since set_human_profile needs its own conn
        existing_prof = conn.execute(
            "SELECT human_id FROM human_profile WHERE human_id=?", (human_id,)
        ).fetchone()
        if not existing_prof:
            conn.execute(
                "INSERT INTO human_profile "
                "(human_id, personality_type, work_style, social_recharge, "
                " quiet_hours_start, quiet_hours_end, timezone, "
                " communication_preferences, known_triggers, seasonal_patterns, "
                " relationship_priorities, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (human_id,
                 profile_data.get("personality_type", "hybrid"),
                 profile_data.get("work_style", "balanced"),
                 profile_data.get("social_recharge", "mixed"),
                 profile_data.get("quiet_hours_start"),
                 profile_data.get("quiet_hours_end"),
                 profile_data.get("timezone", "UTC"),
                 json.dumps(profile_data.get("communication_preferences", {})),
                 json.dumps(profile_data.get("known_triggers", [])),
                 json.dumps(profile_data.get("seasonal_patterns", {})),
                 json.dumps(profile_data.get("relationship_priorities", [])),
                 profile_data.get("notes", "")),
            )

    # 2d. Set up trust config
    rh_trust = rh_def.get("trust_score", 1)
    esc_overrides = rh_def.get("escalation_overrides", [])
    existing_tc = conn.execute(
        "SELECT id FROM trust_config WHERE human_id=? AND right_hand_id=?",
        (human_id, rh_id),
    ).fetchone()
    if not existing_tc:
        conn.execute(
            "INSERT INTO trust_config "
            "(human_id, right_hand_id, trust_score, autonomy_rules, "
            " escalation_overrides, updated_by) "
            "VALUES (?,?,?,?,?,?)",
            (human_id, rh_id, rh_trust, json.dumps({}),
             json.dumps(esc_overrides), "config"),
        )

    # 2e. Set up initial human state
    existing_hs = conn.execute(
        "SELECT id FROM human_state WHERE human_id=?", (human_id,)
    ).fetchone()
    if not existing_hs:
        conn.execute(
            "INSERT INTO human_state (human_id, burnout_score) VALUES (?, ?)",
            (human_id, human_def.get("burnout_score", 5)),
        )

    # 2f. Load relationships from config
    rel_priorities = human_def.get("relationship_priorities", [])
    for rel in rel_priorities:
        existing_rel = conn.execute(
            "SELECT id FROM relationship_tracker WHERE human_id=? AND contact_name=?",
            (human_id, rel["name"]),
        ).fetchone()
        if not existing_rel:
            conn.execute(
                "INSERT INTO relationship_tracker "
                "(human_id, contact_name, contact_type, importance, "
                " preferred_frequency_days, notes) "
                "VALUES (?,?,?,?,?,?)",
                (human_id, rel["name"],
                 rel.get("type", "professional"),
                 rel.get("importance", 5),
                 rel.get("preferred_frequency_days", 30),
                 rel.get("notes", "")),
            )

    conn.commit()

    # 3. Register core crew (excluding security, already handled above)
    for crew_type, crew_def in core_crew.items():
        if not isinstance(crew_def, dict):
            continue
        if crew_type == "security":
            continue  # Already handled above
        agent_type = crew_def.get("agent_type", crew_type)
        aid = _upsert_agent(conn, {
            "name": crew_def["name"],
            "agent_type": agent_type,
            "channel": crew_def.get("channel", "console"),
            "channel_address": crew_def.get("channel_address"),
            "parent": rh_def["name"],
            "active": crew_def.get("active", True),
            "description": crew_def.get("description", ""),
        })
        created.append(crew_def["name"])

    # 4. Register departments
    departments = hier.get("departments", [])
    for dept in departments:
        # Department manager
        mgr_def = dept["manager"]
        mgr_id = _upsert_agent(conn, {
            "name": mgr_def["name"],
            "agent_type": "manager",
            "channel": mgr_def.get("channel", "console"),
            "channel_address": mgr_def.get("channel_address"),
            "parent": mgr_def.get("reports_to", rh_def["name"]),
            "active": mgr_def.get("active", True),
            "description": mgr_def.get("description", f"Manager for {dept['name']}"),
        })
        created.append(mgr_def["name"])

        # Department workers
        for worker_def in dept.get("workers", []):
            _upsert_agent(conn, {
                "name": worker_def["name"],
                "agent_type": worker_def.get("agent_type", "worker"),
                "channel": worker_def.get("channel", "console"),
                "channel_address": worker_def.get("channel_address"),
                "parent": mgr_def["name"],
                "active": worker_def.get("active", True),
                "description": worker_def.get("description", ""),
            })
            created.append(worker_def["name"])

    # 5. Register Help agent (accessible from ? icon, not shown in circle)
    _upsert_agent(conn, {
        "name": "Help",
        "agent_type": "help",
        "channel": "console",
        "parent": rh_def["name"],
        "description": "Your guide to crew-bus. Ask me anything about how your crew works.",
    })
    created.append("Help")

    _audit(conn, "hierarchy_loaded", None, {
        "config": config_path,
        "org": config.get("org_name", hier.get("human", {}).get("name", "unknown")),
        "agents": created,
        "format": "v2",
    })

    conn.commit()
    conn.close()

    org_name = config.get("org_name", f"{human_def['name']}'s Crew")
    return {"org": org_name, "agents_loaded": created}


def _upsert_agent(conn: sqlite3.Connection, agent_def: dict) -> int:
    """Insert or update an agent. Returns the agent id."""
    name = agent_def["name"]
    agent_type = agent_def.get("agent_type", "worker")
    role = _role_for_type(agent_type)
    channel = agent_def.get("channel", "console")
    address = agent_def.get("channel_address")
    trust = agent_def.get("trust_score", 1)
    burnout = agent_def.get("burnout_score", 5)
    budget_limit = agent_def.get("budget_limit", 0.0)
    qh_start = agent_def.get("quiet_hours_start")
    qh_end = agent_def.get("quiet_hours_end")
    tz = agent_def.get("timezone", "UTC")
    is_active = 1 if agent_def.get("active", True) else 0
    caps = json.dumps(agent_def.get("capabilities", []))
    desc = agent_def.get("description", "")
    model = agent_def.get("model", "")

    existing = conn.execute("SELECT id FROM agents WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE agents SET agent_type=?, role=?, channel=?, channel_address=?, "
            "trust_score=?, burnout_score=?, budget_limit=?, "
            "quiet_hours_start=?, quiet_hours_end=?, timezone=?, "
            "active=?, capabilities=?, description=?, model=?, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE name=?",
            (agent_type, role, channel, address, trust, burnout, budget_limit,
             qh_start, qh_end, tz,
             is_active, caps, desc, model, name),
        )
        agent_id = existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO agents (name, agent_type, role, channel, channel_address, "
            "trust_score, burnout_score, budget_limit, "
            "quiet_hours_start, quiet_hours_end, timezone, "
            "active, capabilities, description, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, agent_type, role, channel, address, trust, burnout, budget_limit,
             qh_start, qh_end, tz,
             is_active, caps, desc, model),
        )
        agent_id = cur.lastrowid

    # Wire up parent if specified
    parent_name = agent_def.get("parent")
    if parent_name:
        parent = conn.execute("SELECT id FROM agents WHERE name = ?", (parent_name,)).fetchone()
        if parent:
            conn.execute(
                "UPDATE agents SET parent_agent_id=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE id=?",
                (parent["id"], agent_id),
            )

    return agent_id


# ---------------------------------------------------------------------------
# Public agent & team creation (used by Wizard and API)
# ---------------------------------------------------------------------------

def create_agent(name: str, agent_type: str = "worker",
                 description: str = "", parent_name: str = "",
                 model: str = "", db_path: Optional[Path] = None) -> dict:
    """Create a new agent in the crew. Returns {ok, agent_id} or {ok, error}.

    This is the public API for programmatic agent creation — used by the
    Wizard, dashboard API, and CrewBridge.
    """
    if not name or not name.strip():
        return {"ok": False, "error": "Agent name is required"}
    name = name.strip()
    if len(name) > 60:
        return {"ok": False, "error": "Name too long (max 60 chars)"}
    if agent_type not in VALID_AGENT_TYPES:
        return {"ok": False, "error": f"Invalid type '{agent_type}'. Valid: {', '.join(VALID_AGENT_TYPES)}"}

    db = db_path or DB_PATH
    conn = get_conn(db)
    try:
        existing = conn.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
        if existing:
            return {"ok": False, "error": f"Agent '{name}' already exists"}

        agent_def = {
            "name": name,
            "agent_type": agent_type,
            "description": description,
            "model": model,
        }
        if parent_name:
            agent_def["parent"] = parent_name

        agent_id = _upsert_agent(conn, agent_def)
        conn.commit()
        return {"ok": True, "agent_id": agent_id, "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def create_team(team_name: str, manager_name: str = "",
                worker_names: list = None, worker_descriptions: list = None,
                parent_name: str = "Crew-Boss", model: str = "",
                db_path: Optional[Path] = None) -> dict:
    """Create a team with a manager and optional workers.

    Returns {ok, team_id, manager_id, worker_ids} or {ok, error}.
    """
    if not team_name or not team_name.strip():
        return {"ok": False, "error": "Team name is required"}

    db = db_path or DB_PATH
    conn = get_conn(db)
    worker_names = worker_names or []
    worker_descriptions = worker_descriptions or []

    if not manager_name:
        manager_name = f"{team_name}-Manager"

    try:
        # Create manager
        mgr_def = {
            "name": manager_name,
            "agent_type": "manager",
            "description": f"Manages the {team_name} team.",
            "parent": parent_name,
            "model": model,
        }
        mgr_id = _upsert_agent(conn, mgr_def)

        # Create workers
        w_ids = []
        for i, wname in enumerate(worker_names):
            wdesc = worker_descriptions[i] if i < len(worker_descriptions) else ""
            w_def = {
                "name": wname,
                "agent_type": "worker",
                "description": wdesc,
                "parent": manager_name,
                "model": model,
            }
            w_ids.append(_upsert_agent(conn, w_def))

        # Insert into team_mailbox meta (team uses manager's id as team_id)
        conn.commit()
        return {
            "ok": True,
            "team_name": team_name,
            "manager_id": mgr_id,
            "manager_name": manager_name,
            "worker_ids": w_ids,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def delete_team(manager_id: int, db_path: Optional[Path] = None) -> dict:
    """Delete a team by terminating the manager and all its workers.

    Returns {ok, deleted_count} or {ok, error}.
    """
    db = db_path or DB_PATH
    conn = get_conn(db)
    try:
        mgr = conn.execute(
            "SELECT * FROM agents WHERE id=? AND agent_type='manager'",
            (manager_id,),
        ).fetchone()
        if not mgr:
            return {"ok": False, "error": "Team not found"}

        workers = conn.execute(
            "SELECT id FROM agents WHERE parent_agent_id=?",
            (manager_id,),
        ).fetchall()

        deleted = 0
        for w in workers:
            conn.execute(
                "UPDATE messages SET status='archived' "
                "WHERE from_agent_id=? OR to_agent_id=?",
                (w["id"], w["id"]),
            )
            conn.execute("DELETE FROM agents WHERE id=?", (w["id"],))
            deleted += 1

        conn.execute(
            "UPDATE messages SET status='archived' "
            "WHERE from_agent_id=? OR to_agent_id=?",
            (manager_id, manager_id),
        )
        conn.execute("DELETE FROM agents WHERE id=?", (manager_id,))
        deleted += 1

        _audit(conn, "team_deleted", manager_id, {
            "name": mgr["name"], "workers_deleted": deleted - 1,
        })
        conn.commit()
        return {"ok": True, "deleted_count": deleted}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Crew config (model keys, settings)
# ---------------------------------------------------------------------------

def set_config(key: str, value: str, db_path: Optional[Path] = None) -> None:
    """Set a crew config value (e.g. 'default_model', 'kimi_api_key')."""
    db = db_path or DB_PATH
    conn = get_conn(db)
    try:
        conn.execute(
            "INSERT INTO crew_config (key, value, updated_at) VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_config(key: str, default: str = "", db_path: Optional[Path] = None) -> str:
    """Get a crew config value."""
    db = db_path or DB_PATH
    conn = get_conn(db)
    try:
        row = conn.execute("SELECT value FROM crew_config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def _upsert_timing_rule(conn: sqlite3.Connection, agent_id: int,
                        rule_type: str, rule_config: dict) -> int:
    """Insert or update a timing rule for an agent."""
    existing = conn.execute(
        "SELECT id FROM timing_rules WHERE agent_id=? AND rule_type=?",
        (agent_id, rule_type),
    ).fetchone()
    config_json = json.dumps(rule_config)

    if existing:
        conn.execute(
            "UPDATE timing_rules SET rule_config=?, enabled=1 WHERE id=?",
            (config_json, existing["id"]),
        )
        return existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO timing_rules (agent_id, rule_type, rule_config) VALUES (?, ?, ?)",
            (agent_id, rule_type, config_json),
        )
        return cur.lastrowid


def _load_crew_format(config: dict, config_path: str,
                      db_path: Optional[Path] = None) -> dict:
    """Load the crew YAML format (crew/crew_boss/agents).

    This is the friendly format used by example crew YAMLs like
    family-crew.yaml, artist-passion-crew.yaml, launch-crew.yaml, etc.
    """
    conn = get_conn(db_path)
    created = []

    crew_def = config.get("crew", {})
    crew_name = crew_def.get("name", "My Crew")

    # --- Human (auto-create if missing) ---
    human_name = config.get("human", {}).get("name", "Human")
    human_id = _upsert_agent(conn, {
        "name": human_name,
        "agent_type": "human",
        "channel": "console",
        "description": "The human — always in charge.",
    })
    created.append(human_name)

    # --- Quiet hours (apply to human) ---
    qh = config.get("quiet_hours", {})
    if qh.get("enabled"):
        _upsert_timing_rule(conn, human_id, "quiet_hours", {
            "start": qh.get("start", "22:00"),
            "end": qh.get("end", "07:00"),
            "exceptions": qh.get("exceptions", ["urgent"]),
            "message": qh.get("message", ""),
        })

    # --- Crew Boss ---
    boss_def = config.get("crew_boss", {})
    boss_name = boss_def.get("name", "Crew Boss")
    boss_trust = boss_def.get("trust", 8)
    boss_desc = boss_def.get("description", "Your friendly right-hand assistant.")
    boss_id = _upsert_agent(conn, {
        "name": boss_name,
        "agent_type": "right_hand",
        "channel": "console",
        "trust_score": boss_trust,
        "parent": human_name,
        "description": boss_desc.strip() if isinstance(boss_desc, str) else str(boss_desc),
    })
    created.append(boss_name)

    # --- Agents ---
    for agent_def in config.get("agents", []):
        name = agent_def["name"]
        role = agent_def.get("role", "worker")
        trust = agent_def.get("trust", 5)
        desc = agent_def.get("description", "")
        icon = agent_def.get("icon", "")
        color = agent_def.get("color", "")

        agent_id = _upsert_agent(conn, {
            "name": name,
            "agent_type": role,
            "channel": "console",
            "trust_score": trust,
            "parent": boss_name,
            "description": desc.strip() if isinstance(desc, str) else str(desc),
            "capabilities": [c for c in agent_def.get("features", {}).keys()
                             if agent_def["features"].get(c)],
        })
        created.append(name)

        # Burnout rule from agent-level config
        burnout_def = agent_def.get("burnout", {})
        if burnout_def:
            _upsert_timing_rule(conn, agent_id, "burnout_threshold", {
                "threshold_minutes": burnout_def.get("threshold_minutes", 180),
                "nudge_style": burnout_def.get("nudge_style", "gentle"),
                "message": burnout_def.get("message", ""),
            })

    # --- Global burnout config ---
    global_burnout = config.get("burnout", {})
    if global_burnout.get("enabled"):
        _upsert_timing_rule(conn, human_id, "burnout_threshold", {
            "threshold_minutes": global_burnout.get("threshold_minutes", 180),
            "nudge_style": global_burnout.get("nudge_style", "warm"),
            "message": global_burnout.get("message", ""),
            "hard_limit_minutes": global_burnout.get("hard_limit_minutes"),
            "hard_limit_action": global_burnout.get("hard_limit_action"),
        })

    # --- Help agent ---
    _upsert_agent(conn, {
        "name": "Help",
        "agent_type": "help",
        "channel": "console",
        "parent": boss_name,
        "description": "Your guide to crew-bus. Ask me anything about how your crew works.",
    })
    created.append("Help")

    _audit(conn, "hierarchy_loaded", None, {
        "config": config_path,
        "org": crew_name,
        "agents": created,
        "format": "crew",
    })

    conn.commit()
    conn.close()
    return {"org": crew_name, "agents_loaded": created}


def _load_v1_hierarchy(config: dict, config_path: str,
                       db_path: Optional[Path] = None) -> dict:
    """Load the v1 flat agent list format (backwards compatible)."""
    conn = get_conn(db_path)
    created = []

    for agent_def in config["agents"]:
        name = agent_def["name"]
        role = agent_def.get("role", "worker")
        channel = agent_def.get("channel", "console")
        address = agent_def.get("channel_address")
        agent_type = agent_def.get("agent_type", role)

        existing = conn.execute("SELECT id FROM agents WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE agents SET agent_type=?, role=?, channel=?, channel_address=?, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE name=?",
                (agent_type, _role_for_type(agent_type), channel, address, name),
            )
        else:
            conn.execute(
                "INSERT INTO agents (name, agent_type, role, channel, channel_address) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, agent_type, _role_for_type(agent_type), channel, address),
            )
        created.append(name)

    # Wire parent links
    for agent_def in config["agents"]:
        parent_name = agent_def.get("parent")
        if parent_name:
            parent = conn.execute("SELECT id FROM agents WHERE name = ?", (parent_name,)).fetchone()
            if parent:
                conn.execute(
                    "UPDATE agents SET parent_agent_id=? WHERE name=?",
                    (parent["id"], agent_def["name"]),
                )

    # Register Help agent
    rh = conn.execute("SELECT name FROM agents WHERE agent_type='right_hand' LIMIT 1").fetchone()
    if rh:
        _upsert_agent(conn, {
            "name": "Help",
            "agent_type": "help",
            "channel": "console",
            "parent": rh["name"],
            "description": "Your guide to crew-bus. Ask me anything about how your crew works.",
        })
        created.append("Help")

    _audit(conn, "hierarchy_loaded", None, {
        "config": config_path,
        "org": config.get("org_name", "unknown"),
        "agents": created,
        "format": "v1",
    })

    conn.commit()
    conn.close()
    return {"org": config.get("org_name"), "agents_loaded": created}


# ---------------------------------------------------------------------------
# Routing validation (v2 - Crew Boss gatekeeper)
# ---------------------------------------------------------------------------

def _check_routing(conn: sqlite3.Connection,
                   sender: sqlite3.Row, recipient: sqlite3.Row) -> dict:
    """Validate whether sender is allowed to message recipient.

    V2 routing rules:
    - Only Crew Boss delivers to human (except wellness critical + safety escalation)
    - Crew Boss can message any agent
    - Core crew reports to Crew Boss only
    - Department workers report to their manager
    - Managers report to Crew Boss
    - Workers can safety-escalate to Crew Boss (bypassing manager)
    - Workers CANNOT message other workers

    Returns dict: {allowed: bool, require_approval: bool, reason: str}
    """
    from_type = sender["agent_type"]
    to_type = recipient["agent_type"]
    from_role = sender["role"]
    to_role = recipient["role"]

    # Private session override: if there's an active private session between
    # these two agents, allow direct communication regardless of normal rules
    if _has_active_private_session(sender["id"], recipient["id"], conn=conn):
        return {"allowed": True, "require_approval": False, "reason": "Active private session"}

    # Human can always send (ultimate authority)
    if from_type == "human":
        return {"allowed": True, "require_approval": False, "reason": "Human authority"}

    # Crew Boss can message any agent
    if from_type == "right_hand":
        return {"allowed": True, "require_approval": False, "reason": "Crew Boss authority"}

    # Security agent: can ONLY message Crew Boss (unless direct_security_feed)
    if from_type == "security":
        if to_type == "right_hand":
            return {"allowed": True, "require_approval": False,
                    "reason": "Security reports to Crew Boss"}
        # Check if direct human feed is enabled (stored in trust_config)
        if to_type == "human":
            tc = conn.execute(
                "SELECT escalation_overrides FROM trust_config WHERE human_id=?",
                (recipient["id"],)
            ).fetchone()
            if tc:
                import json as _json
                overrides = _json.loads(tc["escalation_overrides"]) if tc["escalation_overrides"] else []
                if "direct_security_feed" in [str(o).lower() for o in overrides]:
                    return {"allowed": True, "require_approval": False,
                            "reason": "Security direct feed to human enabled"}
            return {"allowed": False, "require_approval": False,
                    "reason": "Security must go through Crew Boss (direct feed not enabled)"}
        return {"allowed": False, "require_approval": False,
                "reason": "Security can only message Crew Boss"}

    # If recipient is human and sender is not right_hand/security, block (reroute to RH)
    if to_type == "human" and from_type not in ("right_hand", "wellness"):
        return {"allowed": False, "require_approval": False,
                "reason": f"Agent type '{from_type}' must go through Crew Boss to reach human"}

    # Check sender status
    if sender["status"] != "active":
        return {"allowed": False, "require_approval": False,
                "reason": f"Sender is {sender['status']}"}
    if recipient["status"] != "active":
        return {"allowed": False, "require_approval": False,
                "reason": f"Recipient is {recipient['status']}"}

    # Check if sender is active (deployed)
    if not sender["active"]:
        return {"allowed": False, "require_approval": False,
                "reason": f"Sender '{sender['name']}' is not activated"}

    # SPECIAL: Wellness agent can deliver critical alerts directly to human
    if from_type == "wellness" and to_type == "human":
        # This will be checked at send time - only critical priority allowed
        return {"allowed": True, "require_approval": False,
                "reason": "Wellness critical alert to human (must be critical priority)"}

    # SPECIAL: Any agent can safety-escalate to Crew Boss
    if to_type == "right_hand" and sender["parent_agent_id"] is not None:
        return {"allowed": True, "require_approval": False,
                "reason": "Safety escalation to Crew Boss"}

    # Direct parent/child always allowed (chain of command)
    if sender["parent_agent_id"] == recipient["id"]:
        return {"allowed": True, "require_approval": False,
                "reason": "Direct parent in hierarchy"}
    if recipient["parent_agent_id"] == sender["id"]:
        return {"allowed": True, "require_approval": False,
                "reason": "Direct report in hierarchy"}

    # Lookup role-based rule
    rule = conn.execute(
        "SELECT allowed, require_approval, description FROM routing_rules "
        "WHERE from_role = ? AND to_role = ?",
        (from_role, to_role),
    ).fetchone()

    if not rule:
        return {"allowed": False, "require_approval": False,
                "reason": f"No routing rule for {from_role} ({from_type}) -> {to_role} ({to_type})"}

    if not rule["allowed"]:
        return {"allowed": False, "require_approval": False,
                "reason": rule["description"]}

    # Worker -> manager: verify it's their own manager
    if from_role == "worker" and to_role == "manager":
        if sender["parent_agent_id"] != recipient["id"]:
            return {"allowed": False, "require_approval": False,
                    "reason": "Workers can only message their own manager"}

    # Manager -> worker: verify it's their own worker
    if from_role == "manager" and to_role == "worker":
        if recipient["parent_agent_id"] != sender["id"]:
            return {"allowed": False, "require_approval": False,
                    "reason": "Managers can only message their own workers"}

    return {
        "allowed": bool(rule["allowed"]),
        "require_approval": bool(rule["require_approval"]),
        "reason": rule["description"],
    }


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

def send_message(from_id: int, to_id: int, message_type: str,
                 subject: str, body: str = "",
                 priority: str = "normal",
                 db_path: Optional[Path] = None) -> dict:
    """Send a message between agents, enforcing routing rules.

    Returns dict with message id and routing result on success.
    Raises PermissionError if routing is blocked.
    Raises ValueError for invalid inputs.
    """
    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError(f"Invalid message_type '{message_type}'. Must be one of {VALID_MESSAGE_TYPES}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of {VALID_PRIORITIES}")

    conn = get_conn(db_path)

    sender = conn.execute("SELECT * FROM agents WHERE id = ?", (from_id,)).fetchone()
    if not sender:
        conn.close()
        raise ValueError(f"Sender agent id={from_id} not found")

    recipient = conn.execute("SELECT * FROM agents WHERE id = ?", (to_id,)).fetchone()
    if not recipient:
        conn.close()
        raise ValueError(f"Recipient agent id={to_id} not found")

    # Validate routing
    routing = _check_routing(conn, sender, recipient)

    # Extra check: wellness -> human only allowed for critical priority
    # (but private sessions override this restriction)
    if (sender["agent_type"] == "wellness" and recipient["agent_type"] == "human"
            and priority != "critical"
            and routing.get("reason") != "Active private session"):
        routing = {"allowed": False, "require_approval": False,
                   "reason": "Wellness can only message human with critical priority"}

    _audit(conn, "message_attempt", from_id, {
        "to": to_id,
        "type": message_type,
        "subject": subject,
        "priority": priority,
        "routing": routing,
    })

    if not routing["allowed"]:
        conn.commit()
        conn.close()
        raise PermissionError(
            f"Message blocked: {sender['name']} ({sender['agent_type']}) -> "
            f"{recipient['name']} ({recipient['agent_type']}): {routing['reason']}"
        )

    # Insert message
    cur = conn.execute(
        "INSERT INTO messages (from_agent_id, to_agent_id, message_type, subject, body, priority) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (from_id, to_id, message_type, subject, body, priority),
    )
    msg_id = cur.lastrowid

    _audit(conn, "message_sent", from_id, {
        "message_id": msg_id,
        "to": to_id,
        "type": message_type,
        "priority": priority,
    })

    conn.commit()
    conn.close()

    return {
        "message_id": msg_id,
        "from": sender["name"],
        "to": recipient["name"],
        "routing": routing,
        "require_approval": routing["require_approval"],
    }


def read_inbox(agent_id: int, status_filter: Optional[str] = None,
               db_path: Optional[Path] = None) -> list[dict]:
    """Return all messages addressed to an agent.

    Optionally filter by message status (queued, delivered, read, archived).
    """
    conn = get_conn(db_path)

    query = (
        "SELECT m.*, s.name AS from_name, s.role AS from_role, s.agent_type AS from_agent_type "
        "FROM messages m "
        "JOIN agents s ON m.from_agent_id = s.id "
        "WHERE m.to_agent_id = ?"
    )
    params: list = [agent_id]

    if status_filter:
        if status_filter not in VALID_MESSAGE_STATUSES:
            conn.close()
            raise ValueError(f"Invalid status filter '{status_filter}'")
        query += " AND m.status = ?"
        params.append(status_filter)

    query += " ORDER BY m.created_at DESC"
    rows = conn.execute(query, params).fetchall()

    _audit(conn, "inbox_read", agent_id, {"filter": status_filter, "count": len(rows)})
    conn.commit()
    conn.close()

    return [dict(r) for r in rows]


def mark_read(message_id: int, db_path: Optional[Path] = None) -> bool:
    """Mark a message as read. Returns True if updated, False if not found."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = conn.execute(
        "UPDATE messages SET status='read', read_at=? WHERE id=? AND status != 'archived'",
        (now, message_id),
    )
    updated = cur.rowcount > 0

    if updated:
        msg = conn.execute("SELECT to_agent_id FROM messages WHERE id=?", (message_id,)).fetchone()
        _audit(conn, "message_read", msg["to_agent_id"] if msg else None,
               {"message_id": message_id})

    conn.commit()
    conn.close()
    return updated


def mark_delivered(message_id: int, db_path: Optional[Path] = None) -> bool:
    """Mark a message as delivered. Returns True if updated."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = conn.execute(
        "UPDATE messages SET status='delivered', delivered_at=? WHERE id=? AND status='queued'",
        (now, message_id),
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------

def get_agent_status(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Return agent info along with message counts (inbox/sent)."""
    conn = get_conn(db_path)

    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")

    inbox_count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE to_agent_id=? AND status != 'archived'",
        (agent_id,),
    ).fetchone()[0]

    unread_count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE to_agent_id=? AND status IN ('queued','delivered')",
        (agent_id,),
    ).fetchone()[0]

    sent_count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE from_agent_id=?",
        (agent_id,),
    ).fetchone()[0]

    conn.close()

    return {
        **dict(agent),
        "inbox_total": inbox_count,
        "inbox_unread": unread_count,
        "sent_total": sent_count,
    }


def get_agent_by_name(name: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Look up an agent by name. Returns dict or None."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_agents(db_path: Optional[Path] = None) -> list[dict]:
    """Return all agents ordered by hierarchy: human, right_hand, core, managers, workers."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT a.*, p.name AS parent_name FROM agents a "
        "LEFT JOIN agents p ON a.parent_agent_id = p.id "
        "ORDER BY CASE a.agent_type "
        "  WHEN 'human' THEN 0 "
        "  WHEN 'right_hand' THEN 1 "
        "  WHEN 'strategy' THEN 2 "
        "  WHEN 'wellness' THEN 3 "
        "  WHEN 'financial' THEN 4 "
        "  WHEN 'legal' THEN 5 "
        "  WHEN 'knowledge' THEN 6 "
        "  WHEN 'communications' THEN 7 "
        "  WHEN 'manager' THEN 8 "
        "  WHEN 'worker' THEN 9 "
        "  WHEN 'specialist' THEN 10 "
        "  ELSE 11 END, a.name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def quarantine_agent(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Set an agent's status to quarantined - blocks all message send/receive."""
    conn = get_conn(db_path)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")
    if agent["status"] == "terminated":
        conn.close()
        raise ValueError(f"Cannot quarantine terminated agent '{agent['name']}'")
    if agent["agent_type"] == "human":
        conn.close()
        raise ValueError("Cannot quarantine the human principal")

    conn.execute(
        "UPDATE agents SET status='quarantined', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?", (agent_id,),
    )
    _audit(conn, "agent_quarantined", agent_id, {"previous_status": agent["status"]})
    conn.commit()

    updated = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(updated)


def restore_agent(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Restore a quarantined agent back to active status."""
    conn = get_conn(db_path)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")
    if agent["status"] == "terminated":
        conn.close()
        raise ValueError(f"Cannot restore terminated agent '{agent['name']}'")
    if agent["status"] == "active":
        conn.close()
        raise ValueError(f"Agent '{agent['name']}' is already active")

    conn.execute(
        "UPDATE agents SET status='active', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?", (agent_id,),
    )
    _audit(conn, "agent_restored", agent_id, {"previous_status": agent["status"]})
    conn.commit()

    updated = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(updated)


def terminate_agent(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Terminate an agent - archives all messages, sets status to terminated."""
    conn = get_conn(db_path)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")
    if agent["agent_type"] == "human":
        conn.close()
        raise ValueError("Cannot terminate the human principal")

    conn.execute(
        "UPDATE messages SET status='archived' WHERE from_agent_id=? OR to_agent_id=?",
        (agent_id, agent_id),
    )
    conn.execute(
        "UPDATE agents SET status='terminated', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?", (agent_id,),
    )
    _audit(conn, "agent_terminated", agent_id, {
        "previous_status": agent["status"], "name": agent["name"],
    })
    conn.commit()

    updated = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(updated)


def activate_agent(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Activate an inactive agent (deploy it)."""
    conn = get_conn(db_path)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")
    if agent["active"]:
        conn.close()
        raise ValueError(f"Agent '{agent['name']}' is already active")

    conn.execute(
        "UPDATE agents SET active=1, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
        (agent_id,),
    )
    _audit(conn, "agent_activated", agent_id, {"name": agent["name"]})
    conn.commit()

    updated = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(updated)


def deactivate_agent(agent_id: int, db_path: Optional[Path] = None) -> dict:
    """Deactivate an agent (softer than quarantine - just marks inactive)."""
    conn = get_conn(db_path)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise ValueError(f"Agent id={agent_id} not found")
    if agent["agent_type"] in ("human", "right_hand"):
        conn.close()
        raise ValueError(f"Cannot deactivate {agent['agent_type']} agent")
    if not agent["active"]:
        conn.close()
        raise ValueError(f"Agent '{agent['name']}' is already inactive")

    conn.execute(
        "UPDATE agents SET active=0, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
        (agent_id,),
    )
    _audit(conn, "agent_deactivated", agent_id, {"name": agent["name"]})
    conn.commit()

    updated = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(updated)


# ---------------------------------------------------------------------------
# Trust and Burnout
# ---------------------------------------------------------------------------

def update_trust_score(human_id: int, new_score: int,
                       db_path: Optional[Path] = None) -> None:
    """Update the trust score for the Crew Boss serving a human.

    The trust score is stored on the right_hand agent, not the human.
    Finds the Crew Boss for the given human and updates its trust_score.
    """
    if not 1 <= new_score <= 10:
        raise ValueError(f"Trust score must be 1-10, got {new_score}")

    conn = get_conn(db_path)
    rh = conn.execute(
        "SELECT * FROM agents WHERE parent_agent_id=? AND agent_type='right_hand'",
        (human_id,),
    ).fetchone()
    if not rh:
        conn.close()
        raise ValueError(f"No Crew Boss agent found for human id={human_id}")

    old_score = rh["trust_score"]
    conn.execute(
        "UPDATE agents SET trust_score=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?", (new_score, rh["id"]),
    )
    _audit(conn, "trust_score_updated", rh["id"], {
        "human_id": human_id, "old_score": old_score, "new_score": new_score,
    })
    conn.commit()
    conn.close()


def update_burnout_score(human_id: int, new_score: int,
                         db_path: Optional[Path] = None) -> None:
    """Update the burnout score for a human (called by wellness agent)."""
    if not 1 <= new_score <= 10:
        raise ValueError(f"Burnout score must be 1-10, got {new_score}")

    conn = get_conn(db_path)
    human = conn.execute("SELECT * FROM agents WHERE id=?", (human_id,)).fetchone()
    if not human:
        conn.close()
        raise ValueError(f"Agent id={human_id} not found")
    if human["agent_type"] != "human":
        conn.close()
        raise ValueError(f"Agent '{human['name']}' is not a human")

    old_score = human["burnout_score"]
    conn.execute(
        "UPDATE agents SET burnout_score=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?", (new_score, human_id),
    )
    _audit(conn, "burnout_score_updated", human_id, {
        "old_score": old_score, "new_score": new_score,
    })
    conn.commit()
    conn.close()


def get_autonomy_level(right_hand_id: int,
                       db_path: Optional[Path] = None) -> dict:
    """Return what actions are allowed at the current trust score.

    Trust Score Behavior:
    1-3: Deliver everything, cannot decide anything
    4-6: Handle routine, escalate novel situations
    7-8: Operational autonomy within limits
    9-10: Full chief of staff mode
    """
    conn = get_conn(db_path)
    rh = conn.execute("SELECT * FROM agents WHERE id=?", (right_hand_id,)).fetchone()
    if not rh:
        conn.close()
        raise ValueError(f"Agent id={right_hand_id} not found")
    if rh["agent_type"] != "right_hand":
        conn.close()
        raise ValueError(f"Agent '{rh['name']}' is not a right_hand")

    trust = rh["trust_score"]

    # Get decision accuracy stats
    total_decisions = conn.execute(
        "SELECT COUNT(*) FROM decision_log WHERE right_hand_id=?",
        (right_hand_id,),
    ).fetchone()[0]

    overrides = conn.execute(
        "SELECT COUNT(*) FROM decision_log WHERE right_hand_id=? AND human_override=1",
        (right_hand_id,),
    ).fetchone()[0]

    conn.close()

    accuracy = ((total_decisions - overrides) / total_decisions * 100) if total_decisions > 0 else 0

    if trust <= 3:
        level = "observer"
        abilities = {
            "deliver_all_messages": True,
            "make_decisions": False,
            "respond_on_behalf": False,
            "filter_ideas": False,
            "handle_escalations": False,
            "send_communications": False,
            "manage_budget": False,
        }
        description = "New relationship. Delivers everything to human. Cannot make decisions."
    elif trust <= 6:
        level = "assistant"
        abilities = {
            "deliver_all_messages": True,
            "make_decisions": True,
            "respond_on_behalf": False,
            "filter_ideas": True,
            "handle_escalations": True,
            "send_communications": False,
            "manage_budget": False,
        }
        description = "Building trust. Handles routine, escalates novel situations."
    elif trust <= 8:
        level = "operator"
        abilities = {
            "deliver_all_messages": True,
            "make_decisions": True,
            "respond_on_behalf": True,
            "filter_ideas": True,
            "handle_escalations": True,
            "send_communications": True,
            "manage_budget": True,
        }
        description = "Trusted operator. Makes operational decisions, drafts communications."
    else:
        level = "chief_of_staff"
        abilities = {
            "deliver_all_messages": False,
            "make_decisions": True,
            "respond_on_behalf": True,
            "filter_ideas": True,
            "handle_escalations": True,
            "send_communications": True,
            "manage_budget": True,
        }
        description = "Full autonomy. Human gets briefings only. Handles everything."

    # Determine if trust adjustment is recommended
    trust_recommendation = None
    if total_decisions >= 20:
        if accuracy >= 95 and trust < 10:
            trust_recommendation = f"Consider increasing trust to {min(trust + 1, 10)}: {accuracy:.0f}% accuracy over {total_decisions} decisions"
        elif accuracy < 70 and trust > 1:
            trust_recommendation = f"Consider decreasing trust to {max(trust - 1, 1)}: {accuracy:.0f}% accuracy over {total_decisions} decisions"

    return {
        "right_hand": rh["name"],
        "trust_score": trust,
        "level": level,
        "description": description,
        "abilities": abilities,
        "total_decisions": total_decisions,
        "overrides": overrides,
        "accuracy_pct": round(accuracy, 1),
        "trust_recommendation": trust_recommendation,
    }


# ---------------------------------------------------------------------------
# Timing / Delivery Assessment
# ---------------------------------------------------------------------------

def should_deliver_now(human_id: int, message_priority: str,
                       db_path: Optional[Path] = None) -> dict:
    """Check whether a message should be delivered to the human right now.

    Checks burnout score, quiet hours, busy signals, and message priority.
    Critical/safety messages ALWAYS deliver regardless of timing.

    Returns: {deliver: bool, reason: str, delay_until: str|None}
    """
    if message_priority == "critical":
        return {"deliver": True, "reason": "Critical priority overrides all timing rules",
                "delay_until": None}

    conn = get_conn(db_path)
    human = conn.execute("SELECT * FROM agents WHERE id=?", (human_id,)).fetchone()
    if not human:
        conn.close()
        raise ValueError(f"Agent id={human_id} not found")

    now = datetime.now(timezone.utc)
    burnout = human["burnout_score"]

    # Check burnout threshold
    if burnout >= 7 and message_priority in ("low", "normal"):
        conn.close()
        morning = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        return {
            "deliver": False,
            "reason": f"Burnout score is {burnout}/10. Queuing non-urgent message for morning.",
            "delay_until": morning.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Check quiet hours
    quiet_rule = conn.execute(
        "SELECT rule_config FROM timing_rules WHERE agent_id=? AND rule_type='quiet_hours' AND enabled=1",
        (human_id,),
    ).fetchone()

    if quiet_rule:
        qconfig = json.loads(quiet_rule["rule_config"])
        tz_name = qconfig.get("timezone", "UTC")
        start_str = qconfig["start"]  # "22:00"
        end_str = qconfig["end"]      # "07:00"

        # Simple hour-based check (timezone-naive for now, works for local ops)
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
        # Use UTC hour as proxy (proper tz support would need pytz/zoneinfo)
        current_h = now.hour

        in_quiet = False
        if start_h > end_h:
            # Quiet hours cross midnight (e.g., 22:00 - 07:00)
            in_quiet = current_h >= start_h or current_h < end_h
        else:
            in_quiet = start_h <= current_h < end_h

        if in_quiet and message_priority != "high":
            conn.close()
            # Delay until end of quiet hours
            delay = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            if delay <= now:
                delay += timedelta(days=1)
            return {
                "deliver": False,
                "reason": f"Quiet hours ({start_str}-{end_str}). Queuing for {end_str}.",
                "delay_until": delay.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

    # Check busy signal
    busy_rule = conn.execute(
        "SELECT rule_config FROM timing_rules WHERE agent_id=? AND rule_type='busy_signal' AND enabled=1",
        (human_id,),
    ).fetchone()

    if busy_rule:
        bconfig = json.loads(busy_rule["rule_config"])
        if bconfig.get("active", False):
            conn.close()
            return {
                "deliver": False,
                "reason": f"Human is busy: {bconfig.get('reason', 'busy')}. Queuing.",
                "delay_until": bconfig.get("until"),
            }

    # Check focus mode
    focus_rule = conn.execute(
        "SELECT rule_config FROM timing_rules WHERE agent_id=? AND rule_type='focus_mode' AND enabled=1",
        (human_id,),
    ).fetchone()

    if focus_rule:
        fconfig = json.loads(focus_rule["rule_config"])
        if fconfig.get("active", False) and message_priority == "low":
            conn.close()
            return {
                "deliver": False,
                "reason": "Focus mode active. Low-priority items queued.",
                "delay_until": fconfig.get("until"),
            }

    conn.close()
    return {"deliver": True, "reason": "All timing checks passed", "delay_until": None}


# ---------------------------------------------------------------------------
# Decision Log
# ---------------------------------------------------------------------------

def log_decision(right_hand_id: int, human_id: int, decision_type: str,
                 context: dict, action: str,
                 reasoning: Optional[str] = None,
                 pattern_tags: Optional[list] = None,
                 db_path: Optional[Path] = None) -> int:
    """Record a Crew Boss decision for audit and learning purposes.

    Args:
        right_hand_id: The Crew Boss agent making the decision.
        human_id: The human the decision is about.
        decision_type: One of VALID_DECISION_TYPES.
        context: JSON-serializable dict of decision context.
        action: What the Crew Boss decided to do.
        reasoning: Human-readable explanation of why (for learning).
        pattern_tags: Tags for pattern matching (e.g. ["rejected_idea", "high_burnout"]).

    Returns the decision_id.
    """
    if decision_type not in VALID_DECISION_TYPES:
        raise ValueError(f"Invalid decision_type '{decision_type}'")

    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO decision_log "
        "(right_hand_id, human_id, decision_type, context, right_hand_action, "
        " right_hand_reasoning, pattern_tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (right_hand_id, human_id, decision_type, json.dumps(context), action,
         reasoning, json.dumps(pattern_tags or [])),
    )
    decision_id = cur.lastrowid

    _audit(conn, "decision_logged", right_hand_id, {
        "decision_id": decision_id, "type": decision_type, "action": action,
    })
    conn.commit()
    conn.close()
    return decision_id


def record_human_feedback(decision_id: int, override: bool,
                          human_action: Optional[str] = None,
                          note: Optional[str] = None,
                          db_path: Optional[Path] = None) -> None:
    """Record whether the human agreed with or overrode a Crew Boss decision.

    This is the learning loop - patterns are stored for future matching.
    """
    conn = get_conn(db_path)

    decision = conn.execute("SELECT * FROM decision_log WHERE id=?", (decision_id,)).fetchone()
    if not decision:
        conn.close()
        raise ValueError(f"Decision id={decision_id} not found")

    conn.execute(
        "UPDATE decision_log SET human_override=?, human_action=?, feedback_note=? WHERE id=?",
        (1 if override else 0, human_action, note, decision_id),
    )

    _audit(conn, "human_feedback_recorded", decision["human_id"], {
        "decision_id": decision_id,
        "override": override,
        "human_action": human_action,
        "note": note,
    })

    # If this was an override of a strategy idea filter, store as rejection pattern
    if override and decision["decision_type"] == "filter":
        ctx = json.loads(decision["context"])
        if ctx.get("message_type") == "idea":
            conn.execute(
                "INSERT INTO knowledge_store (agent_id, category, subject, content, tags) "
                "VALUES (?, 'rejection', ?, ?, ?)",
                (decision["right_hand_id"],
                 f"Human overrode filter on idea: {ctx.get('subject', 'unknown')}",
                 json.dumps({"decision_id": decision_id, "context": ctx, "human_action": human_action}),
                 ctx.get("tags", "")),
            )

    conn.commit()
    conn.close()


def get_decision_history(human_id: Optional[int] = None,
                         category_filter: Optional[str] = None,
                         limit: int = 20,
                         db_path: Optional[Path] = None) -> list[dict]:
    """Return decision log entries, optionally filtered by human and/or type."""
    conn = get_conn(db_path)
    query = (
        "SELECT d.*, rh.name AS rh_name, h.name AS human_name "
        "FROM decision_log d "
        "JOIN agents rh ON d.right_hand_id = rh.id "
        "JOIN agents h ON d.human_id = h.id "
        "WHERE 1=1"
    )
    params: list = []

    if human_id is not None:
        query += " AND d.human_id = ?"
        params.append(human_id)
    if category_filter:
        query += " AND d.decision_type = ?"
        params.append(category_filter)

    query += " ORDER BY d.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        entry = dict(r)
        entry["context"] = json.loads(entry["context"])
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Knowledge Store
# ---------------------------------------------------------------------------

def store_knowledge(agent_id: int, category: str, subject: str,
                    content: dict, tags: str = "",
                    source_message_id: Optional[int] = None,
                    db_path: Optional[Path] = None) -> int:
    """Store a knowledge entry. Returns the knowledge_id.

    Categories: decision, contact, lesson, preference, rejection
    Tags: comma-separated string for search/matching
    """
    if category not in VALID_KNOWLEDGE_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of {VALID_KNOWLEDGE_CATEGORIES}")

    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO knowledge_store (agent_id, category, subject, content, tags, source_message_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, category, subject, json.dumps(content), tags, source_message_id),
    )
    kid = cur.lastrowid

    _audit(conn, "knowledge_stored", agent_id, {
        "knowledge_id": kid, "category": category, "subject": subject, "tags": tags,
    })
    conn.commit()
    conn.close()
    return kid


def search_knowledge(query: str, category_filter: Optional[str] = None,
                     limit: int = 20,
                     db_path: Optional[Path] = None) -> list[dict]:
    """Search the knowledge store by subject, content, and tags.

    Uses LIKE matching on subject, content, and tags fields.
    """
    conn = get_conn(db_path)
    sql = (
        "SELECT k.*, a.name AS agent_name "
        "FROM knowledge_store k "
        "JOIN agents a ON k.agent_id = a.id "
        "WHERE (k.subject LIKE ? OR k.content LIKE ? OR k.tags LIKE ?)"
    )
    pattern = f"%{query}%"
    params: list = [pattern, pattern, pattern]

    if category_filter:
        sql += " AND k.category = ?"
        params.append(category_filter)

    sql += " ORDER BY k.updated_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        entry = dict(r)
        entry["content"] = json.loads(entry["content"])
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Rejection History
# ---------------------------------------------------------------------------

def log_rejection(human_id: int, strategy_agent_id: int,
                  subject: str, body: str = "",
                  reason: Optional[str] = None,
                  db_path: Optional[Path] = None) -> int:
    """Record a rejected strategy idea for future pattern matching.

    The Crew Boss uses rejection history to filter similar future ideas
    before they reach the human. This is the foundation of recursive learning.

    Returns the rejection_id.
    """
    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO rejection_history "
        "(human_id, strategy_agent_id, idea_subject, idea_body, rejection_reason) "
        "VALUES (?, ?, ?, ?, ?)",
        (human_id, strategy_agent_id, subject, body, reason),
    )
    rejection_id = cur.lastrowid
    _audit(conn, "idea_rejected", human_id,
           {"rejection_id": rejection_id, "strategy_agent_id": strategy_agent_id,
            "subject": subject, "reason": reason})
    conn.commit()
    conn.close()
    return rejection_id


def get_rejection_history(human_id: int, limit: int = 20,
                          db_path: Optional[Path] = None) -> list[dict]:
    """Get the human's rejection history for strategy ideas.

    Returns list of rejection dicts sorted by most recent first.
    Used by Crew Boss to filter similar future ideas.
    """
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT r.*, a.name AS strategy_agent_name "
        "FROM rejection_history r "
        "JOIN agents a ON r.strategy_agent_id = a.id "
        "WHERE r.human_id = ? "
        "ORDER BY r.created_at DESC LIMIT ?",
        (human_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Strategy Idea Filtering
# ---------------------------------------------------------------------------

def filter_strategy_idea(right_hand_id: int, idea_message_id: int,
                         db_path: Optional[Path] = None) -> dict:
    """Check whether a strategy idea should be passed to the human.

    Looks at rejection history in knowledge_store to see if similar ideas
    have been rejected before. Also considers current burnout score.

    Returns: {action: "pass"|"filter"|"queue", reason: str}
    """
    conn = get_conn(db_path)

    msg = conn.execute("SELECT * FROM messages WHERE id=?", (idea_message_id,)).fetchone()
    if not msg:
        conn.close()
        raise ValueError(f"Message id={idea_message_id} not found")

    rh = conn.execute("SELECT * FROM agents WHERE id=?", (right_hand_id,)).fetchone()
    if not rh:
        conn.close()
        raise ValueError(f"Agent id={right_hand_id} not found")

    # Find the human
    human = conn.execute(
        "SELECT * FROM agents WHERE id=?", (rh["parent_agent_id"],),
    ).fetchone()

    subject = msg["subject"]
    body = msg["body"]

    # Check for similar past rejections - search using key words from
    # the idea subject to find related rejections.  We split on spaces
    # and look for any significant word (>3 chars) matching.
    stop_words = {"the", "a", "an", "for", "and", "or", "in", "of", "to", "with", "from"}
    words = [w.strip(".,!?;:") for w in subject.split()
             if len(w.strip(".,!?;:")) > 3 and w.lower() not in stop_words]

    rejections = []
    seen_ids = set()

    # Check dedicated rejection_history table first
    for word in words:
        rows = conn.execute(
            "SELECT * FROM rejection_history "
            "WHERE human_id = ? "
            "AND (idea_subject LIKE ? OR idea_body LIKE ?) "
            "ORDER BY created_at DESC LIMIT 5",
            (human["id"] if human else 0, f"%{word}%", f"%{word}%"),
        ).fetchall()
        for r in rows:
            key = ("rh", r["id"])
            if key not in seen_ids:
                rejections.append(r)
                seen_ids.add(key)

    # Also check knowledge_store for rejection category entries
    for word in words:
        rows = conn.execute(
            "SELECT * FROM knowledge_store WHERE category='rejection' "
            "AND (subject LIKE ? OR content LIKE ? OR tags LIKE ?) "
            "ORDER BY created_at DESC LIMIT 5",
            (f"%{word}%", f"%{word}%", f"%{word}%"),
        ).fetchall()
        for r in rows:
            key = ("ks", r["id"])
            if key not in seen_ids:
                rejections.append(r)
                seen_ids.add(key)

    conn.close()

    if len(rejections) >= 2:
        return {
            "action": "filter",
            "reason": f"Found {len(rejections)} similar past rejections. Filtering idea.",
            "similar_rejections": len(rejections),
        }

    # Check burnout
    if human and human["burnout_score"] >= 7:
        return {
            "action": "queue",
            "reason": f"Human burnout is {human['burnout_score']}/10. Queuing for lower-burnout moment.",
        }

    # Novel idea, low burnout - pass through
    return {
        "action": "pass",
        "reason": "Novel idea, no similar rejections found. Passing to human.",
    }


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def get_audit_trail(agent_id: Optional[int] = None,
                    start_time: Optional[str] = None,
                    end_time: Optional[str] = None,
                    db_path: Optional[Path] = None) -> list[dict]:
    """Return audit log entries filtered by agent and/or time range."""
    conn = get_conn(db_path)
    query = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []

    if agent_id is not None:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if start_time:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        entry = dict(r)
        entry["details"] = json.loads(entry["details"])
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Reports (v2 - works for Crew Boss and traditional directors)
# ---------------------------------------------------------------------------

def compile_director_report(director_id: int, hours: int = 24,
                            db_path: Optional[Path] = None) -> dict:
    """Pull all reports from subordinates for the last N hours.

    Works for right_hand, director, or manager roles.
    """
    conn = get_conn(db_path)

    director = conn.execute("SELECT * FROM agents WHERE id=?", (director_id,)).fetchone()
    if not director:
        conn.close()
        raise ValueError(f"Agent id={director_id} not found")

    allowed_types = ("right_hand", "manager")
    if director["agent_type"] not in allowed_types and director["role"] != "human":
        conn.close()
        raise ValueError(
            f"Agent '{director['name']}' is a {director['agent_type']}, "
            f"not a right_hand/manager/human"
        )

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    subordinates = _get_subordinates(conn, director_id)
    sub_ids = [s["id"] for s in subordinates]

    if not sub_ids:
        conn.close()
        return {
            "director": director["name"],
            "period_hours": hours,
            "cutoff": cutoff,
            "total_messages": 0,
            "workers": [],
            "summary": "No subordinates found.",
        }

    placeholders = ",".join("?" * len(sub_ids))
    messages = conn.execute(
        f"SELECT m.*, a.name AS from_name, a.agent_type AS from_type "
        f"FROM messages m JOIN agents a ON m.from_agent_id = a.id "
        f"WHERE m.from_agent_id IN ({placeholders}) "
        f"AND m.message_type = 'report' "
        f"AND m.created_at >= ? "
        f"ORDER BY m.created_at DESC",
        sub_ids + [cutoff],
    ).fetchall()

    worker_reports: dict[str, list] = {}
    for msg in messages:
        name = msg["from_name"]
        if name not in worker_reports:
            worker_reports[name] = []
        worker_reports[name].append({
            "subject": msg["subject"],
            "body": msg["body"],
            "priority": msg["priority"],
            "created_at": msg["created_at"],
        })

    _audit(conn, "director_report_compiled", director_id, {
        "period_hours": hours,
        "subordinate_count": len(subordinates),
        "message_count": len(messages),
    })
    conn.commit()
    conn.close()

    total = len(messages)
    worker_list = []
    for name, reports in worker_reports.items():
        worker_list.append({
            "name": name,
            "report_count": len(reports),
            "reports": reports,
        })

    lines = [f"Report: {director['name']}", f"Period: last {hours} hours", ""]
    if not worker_list:
        lines.append("No reports received from subordinates.")
    else:
        lines.append(f"Total reports received: {total}")
        lines.append(f"Reporting agents: {len(worker_list)}")
        lines.append("")
        for w in worker_list:
            lines.append(f"  [{w['name']}] - {w['report_count']} report(s)")
            for r in w["reports"]:
                pri = f" [{r['priority'].upper()}]" if r["priority"] != "normal" else ""
                lines.append(f"    * {r['subject']}{pri}")
                if r["body"]:
                    for bline in r["body"].split("\n")[:3]:
                        lines.append(f"      {bline}")

    return {
        "director": director["name"],
        "period_hours": hours,
        "cutoff": cutoff,
        "total_messages": total,
        "workers": worker_list,
        "summary": "\n".join(lines),
    }


def _get_subordinates(conn: sqlite3.Connection, agent_id: int) -> list[dict]:
    """Recursively get all agents under the given agent in the hierarchy."""
    direct = conn.execute(
        "SELECT * FROM agents WHERE parent_agent_id = ? AND status != 'terminated'",
        (agent_id,),
    ).fetchall()

    result = [dict(r) for r in direct]
    for child in direct:
        result.extend(_get_subordinates(conn, child["id"]))
    return result


# ---------------------------------------------------------------------------
# Human Profile (Day 2)
# ---------------------------------------------------------------------------

def set_human_profile(human_id: int, profile: dict,
                      db_path: Optional[Path] = None) -> None:
    """Create or update the human profile.

    profile dict keys (all optional):
        personality_type, work_style, social_recharge,
        quiet_hours_start, quiet_hours_end, timezone,
        communication_preferences (dict), known_triggers (list),
        seasonal_patterns (dict), relationship_priorities (list),
        notes (str)
    """
    conn = get_conn(db_path)
    existing = conn.execute(
        "SELECT human_id FROM human_profile WHERE human_id=?", (human_id,)
    ).fetchone()

    if existing:
        sets = []
        vals = []
        for key in ("personality_type", "work_style", "social_recharge",
                     "quiet_hours_start", "quiet_hours_end", "timezone", "notes"):
            if key in profile:
                sets.append(f"{key}=?")
                vals.append(profile[key])
        for key in ("communication_preferences", "known_triggers",
                     "seasonal_patterns", "relationship_priorities"):
            if key in profile:
                sets.append(f"{key}=?")
                vals.append(json.dumps(profile[key]))
        if sets:
            sets.append("updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')")
            conn.execute(
                f"UPDATE human_profile SET {', '.join(sets)} WHERE human_id=?",
                vals + [human_id],
            )
    else:
        conn.execute(
            "INSERT INTO human_profile "
            "(human_id, personality_type, work_style, social_recharge, "
            " quiet_hours_start, quiet_hours_end, timezone, "
            " communication_preferences, known_triggers, seasonal_patterns, "
            " relationship_priorities, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (human_id,
             profile.get("personality_type", "hybrid"),
             profile.get("work_style", "balanced"),
             profile.get("social_recharge", "mixed"),
             profile.get("quiet_hours_start"),
             profile.get("quiet_hours_end"),
             profile.get("timezone", "UTC"),
             json.dumps(profile.get("communication_preferences", {})),
             json.dumps(profile.get("known_triggers", [])),
             json.dumps(profile.get("seasonal_patterns", {})),
             json.dumps(profile.get("relationship_priorities", [])),
             profile.get("notes", "")),
        )

    _audit(conn, "human_profile_updated", human_id, {
        "fields": list(profile.keys()),
    })
    conn.commit()
    conn.close()


def get_human_profile(human_id: int,
                      db_path: Optional[Path] = None) -> Optional[dict]:
    """Return the human profile or None if not set."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM human_profile WHERE human_id=?", (human_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for key in ("communication_preferences", "known_triggers",
                "seasonal_patterns", "relationship_priorities"):
        if d.get(key):
            d[key] = json.loads(d[key])
    return d


# ---------------------------------------------------------------------------
# Trust Config (Day 2)
# ---------------------------------------------------------------------------

def set_trust_config(human_id: int, right_hand_id: int,
                     trust_score: int = 1,
                     autonomy_rules: Optional[dict] = None,
                     escalation_overrides: Optional[list] = None,
                     updated_by: str = "system",
                     db_path: Optional[Path] = None) -> None:
    """Create or update the trust configuration between human and Crew Boss."""
    if not 1 <= trust_score <= 10:
        raise ValueError(f"Trust score must be 1-10, got {trust_score}")

    conn = get_conn(db_path)
    existing = conn.execute(
        "SELECT id FROM trust_config WHERE human_id=? AND right_hand_id=?",
        (human_id, right_hand_id),
    ).fetchone()

    rules_json = json.dumps(autonomy_rules or {})
    overrides_json = json.dumps(escalation_overrides or [])

    if existing:
        conn.execute(
            "UPDATE trust_config SET trust_score=?, autonomy_rules=?, "
            "escalation_overrides=?, updated_by=?, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id=?",
            (trust_score, rules_json, overrides_json, updated_by, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO trust_config "
            "(human_id, right_hand_id, trust_score, autonomy_rules, "
            " escalation_overrides, updated_by) "
            "VALUES (?,?,?,?,?,?)",
            (human_id, right_hand_id, trust_score, rules_json,
             overrides_json, updated_by),
        )

    # Also sync to agents table
    conn.execute(
        "UPDATE agents SET trust_score=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?",
        (trust_score, right_hand_id),
    )

    _audit(conn, "trust_config_updated", right_hand_id, {
        "human_id": human_id, "trust_score": trust_score,
        "updated_by": updated_by,
    })
    conn.commit()
    conn.close()


def get_trust_config(human_id: int,
                     db_path: Optional[Path] = None) -> Optional[dict]:
    """Return the trust config for a human, or None."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM trust_config WHERE human_id=?", (human_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["autonomy_rules"] = json.loads(d["autonomy_rules"])
    d["escalation_overrides"] = json.loads(d["escalation_overrides"])
    return d


# ---------------------------------------------------------------------------
# Human State (Day 2)
# ---------------------------------------------------------------------------

def update_human_state(human_id: int, state: dict,
                       updated_by: str = "system",
                       db_path: Optional[Path] = None) -> dict:
    """Create or update the dynamic human state.

    state dict keys (all optional):
        burnout_score (1-10), energy_level (high/medium/low),
        current_activity (working/meeting/driving/resting/family_time/unavailable),
        mood_indicator (good/neutral/stressed/frustrated/energized),
        last_social_activity (ISO timestamp), last_family_contact (ISO timestamp),
        consecutive_work_days (int)
    """
    conn = get_conn(db_path)
    existing = conn.execute(
        "SELECT id FROM human_state WHERE human_id=?", (human_id,)
    ).fetchone()

    if existing:
        sets = []
        vals = []
        for key in ("burnout_score", "energy_level", "current_activity",
                     "mood_indicator", "last_social_activity",
                     "last_family_contact", "consecutive_work_days"):
            if key in state:
                sets.append(f"{key}=?")
                vals.append(state[key])
        sets.append("updated_by=?")
        vals.append(updated_by)
        sets.append("updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')")
        conn.execute(
            f"UPDATE human_state SET {', '.join(sets)} WHERE human_id=?",
            vals + [human_id],
        )
    else:
        conn.execute(
            "INSERT INTO human_state "
            "(human_id, burnout_score, energy_level, current_activity, "
            " mood_indicator, last_social_activity, last_family_contact, "
            " consecutive_work_days, updated_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (human_id,
             state.get("burnout_score", 5),
             state.get("energy_level", "medium"),
             state.get("current_activity", "working"),
             state.get("mood_indicator", "neutral"),
             state.get("last_social_activity"),
             state.get("last_family_contact"),
             state.get("consecutive_work_days", 0),
             updated_by),
        )

    # Also sync burnout to agents table
    if "burnout_score" in state:
        conn.execute(
            "UPDATE agents SET burnout_score=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id=?",
            (state["burnout_score"], human_id),
        )

    _audit(conn, "human_state_updated", human_id, {
        "fields": list(state.keys()), "updated_by": updated_by,
    })
    conn.commit()
    conn.close()

    return get_human_state(human_id, db_path)


def get_human_state(human_id: int,
                    db_path: Optional[Path] = None) -> dict:
    """Return current human state. Creates default if not exists."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM human_state WHERE human_id=?", (human_id,)
    ).fetchone()

    if not row:
        # Auto-create default state
        conn.execute(
            "INSERT INTO human_state (human_id) VALUES (?)", (human_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM human_state WHERE human_id=?", (human_id,)
        ).fetchone()

    conn.close()
    return dict(row)


# ---------------------------------------------------------------------------
# Security Events (Day 2)
# ---------------------------------------------------------------------------

def log_security_event(security_agent_id: int, threat_domain: str,
                       severity: str, title: str,
                       details: Optional[dict] = None,
                       recommended_action: str = "",
                       db_path: Optional[Path] = None) -> int:
    """Log a security event and return the event_id.

    threat_domain: physical, digital, financial, legal, reputation, mutiny, relationship
    severity: info, low, medium, high, critical
    """
    if threat_domain not in VALID_THREAT_DOMAINS:
        raise ValueError(f"Invalid threat_domain '{threat_domain}'")
    if severity not in VALID_SEVERITY_LEVELS:
        raise ValueError(f"Invalid severity '{severity}'")

    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO security_events "
        "(security_agent_id, threat_domain, severity, title, details, recommended_action) "
        "VALUES (?,?,?,?,?,?)",
        (security_agent_id, threat_domain, severity, title,
         json.dumps(details or {}), recommended_action),
    )
    event_id = cur.lastrowid

    _audit(conn, "security_event_logged", security_agent_id, {
        "event_id": event_id, "domain": threat_domain,
        "severity": severity, "title": title,
    })
    conn.commit()
    conn.close()
    return event_id


def get_security_events(severity_filter: Optional[str] = None,
                        domain_filter: Optional[str] = None,
                        unresolved_only: bool = False,
                        limit: int = 50,
                        db_path: Optional[Path] = None) -> list[dict]:
    """Query security events with optional filters."""
    conn = get_conn(db_path)
    query = (
        "SELECT se.*, a.name AS agent_name "
        "FROM security_events se "
        "JOIN agents a ON se.security_agent_id = a.id "
        "WHERE 1=1"
    )
    params: list = []

    if severity_filter:
        query += " AND se.severity = ?"
        params.append(severity_filter)
    if domain_filter:
        query += " AND se.threat_domain = ?"
        params.append(domain_filter)
    if unresolved_only:
        query += " AND se.resolved_at IS NULL"

    query += " ORDER BY se.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        entry = dict(r)
        entry["details"] = json.loads(entry["details"])
        results.append(entry)
    return results


def resolve_security_event(event_id: int, resolution: str,
                           db_path: Optional[Path] = None) -> None:
    """Mark a security event as resolved."""
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE security_events SET resolution=?, "
        "resolved_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
        (resolution, event_id),
    )
    conn.commit()
    conn.close()


def mark_security_delivered(event_id: int, to_right_hand: bool = False,
                            to_human: bool = False,
                            db_path: Optional[Path] = None) -> None:
    """Mark a security event as delivered to Crew Boss and/or human."""
    conn = get_conn(db_path)
    if to_right_hand:
        conn.execute(
            "UPDATE security_events SET delivered_to_right_hand=1 WHERE id=?",
            (event_id,),
        )
    if to_human:
        conn.execute(
            "UPDATE security_events SET delivered_to_human=1 WHERE id=?",
            (event_id,),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Relationship Tracker (Day 2)
# ---------------------------------------------------------------------------

def add_relationship(human_id: int, contact_name: str,
                     contact_type: str = "professional",
                     importance: int = 5,
                     preferred_frequency_days: int = 30,
                     notes: str = "",
                     db_path: Optional[Path] = None) -> int:
    """Add a relationship for tracking. Returns the relationship_id."""
    if contact_type not in VALID_RELATIONSHIP_TYPES:
        raise ValueError(f"Invalid contact_type '{contact_type}'")
    if not 1 <= importance <= 10:
        raise ValueError(f"Importance must be 1-10, got {importance}")

    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO relationship_tracker "
        "(human_id, contact_name, contact_type, importance, "
        " preferred_frequency_days, notes) "
        "VALUES (?,?,?,?,?,?)",
        (human_id, contact_name, contact_type, importance,
         preferred_frequency_days, notes),
    )
    rid = cur.lastrowid
    _audit(conn, "relationship_added", human_id, {
        "relationship_id": rid, "contact": contact_name,
        "type": contact_type, "importance": importance,
    })
    conn.commit()
    conn.close()
    return rid


def update_relationship_contact(relationship_id: int,
                                db_path: Optional[Path] = None) -> None:
    """Record a contact event (sets last_contact to now, updates status)."""
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE relationship_tracker SET last_contact=strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "status='healthy', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?",
        (relationship_id,),
    )
    conn.commit()
    conn.close()


def get_relationships(human_id: int, status_filter: Optional[str] = None,
                      db_path: Optional[Path] = None) -> list[dict]:
    """Get all tracked relationships for a human.

    Automatically computes status based on last_contact and preferred_frequency.
    """
    conn = get_conn(db_path)
    query = "SELECT * FROM relationship_tracker WHERE human_id=?"
    params: list = [human_id]
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    query += " ORDER BY importance DESC, contact_name ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    results = []
    for r in rows:
        entry = dict(r)
        # Compute days since last contact
        if entry["last_contact"]:
            try:
                lc = datetime.fromisoformat(entry["last_contact"].replace("Z", "+00:00"))
                days_since = (now - lc).days
            except (ValueError, TypeError):
                days_since = 999
        else:
            days_since = 999

        entry["days_since_contact"] = days_since

        # Auto-compute status
        freq = entry["preferred_frequency_days"]
        if days_since <= freq:
            computed = "healthy"
        elif days_since <= freq * 1.5:
            computed = "attention_needed"
        elif days_since <= freq * 2:
            computed = "at_risk"
        else:
            computed = "stale"
        entry["computed_status"] = computed
        results.append(entry)
    return results


def get_relationship_nudges(human_id: int,
                            db_path: Optional[Path] = None) -> list[dict]:
    """Return relationships that need attention, sorted by urgency."""
    rels = get_relationships(human_id, db_path=db_path)
    nudges = []
    for r in rels:
        if r["computed_status"] in ("attention_needed", "at_risk", "stale"):
            nudges.append({
                "contact_name": r["contact_name"],
                "contact_type": r["contact_type"],
                "importance": r["importance"],
                "days_since_contact": r["days_since_contact"],
                "preferred_frequency": r["preferred_frequency_days"],
                "status": r["computed_status"],
                "notes": r["notes"],
            })
    # Sort: stale first, then at_risk, then attention_needed; within each by importance
    status_order = {"stale": 0, "at_risk": 1, "attention_needed": 2}
    nudges.sort(key=lambda x: (status_order.get(x["status"], 3), -x["importance"]))
    return nudges


# ---------------------------------------------------------------------------
# Private Sessions
# ---------------------------------------------------------------------------

def _has_active_private_session(agent_id_1: int, agent_id_2: int,
                                 db_path: Optional[Path] = None,
                                 conn: Optional[sqlite3.Connection] = None) -> bool:
    """Check if there is an active, non-expired private session between two agents.

    Works regardless of which agent is the human and which is the other.
    Auto-closes expired sessions found during the check.
    """
    close_conn = False
    if conn is None:
        conn = get_conn(db_path)
        close_conn = True
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = conn.execute(
            "SELECT id, expires_at FROM private_sessions "
            "WHERE active=1 AND ("
            "  (human_id=? AND agent_id=?) OR (human_id=? AND agent_id=?)"
            ")",
            (agent_id_1, agent_id_2, agent_id_2, agent_id_1),
        ).fetchone()
        if not row:
            return False
        if row["expires_at"] < now:
            # Auto-close expired session
            conn.execute(
                "UPDATE private_sessions SET active=0, ended_by='timeout', "
                "ended_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
                (row["id"],),
            )
            conn.commit()
            return False
        return True
    finally:
        if close_conn:
            conn.close()


def start_private_session(human_id: int, agent_id: int,
                           channel: str = "web",
                           timeout_minutes: int = 30,
                           db_path: Optional[Path] = None) -> dict:
    """Start a private session between a human and an agent.

    Only ONE active session per human-agent pair at a time. If one exists,
    return it instead of creating a new one.

    Args:
        human_id: Database ID of the human.
        agent_id: Database ID of the agent.
        channel: Communication channel ('web', 'telegram', 'signal', 'app').
        timeout_minutes: Inactivity timeout in minutes (default 30).

    Returns:
        Dict with session_id, agent_id, channel, expires_at.
    """
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Check for existing active session
    existing = conn.execute(
        "SELECT * FROM private_sessions WHERE human_id=? AND agent_id=? AND active=1",
        (human_id, agent_id),
    ).fetchone()

    if existing:
        # Check if expired
        if existing["expires_at"] < now_iso:
            # Close expired, create new
            conn.execute(
                "UPDATE private_sessions SET active=0, ended_by='timeout', ended_at=? WHERE id=?",
                (now_iso, existing["id"]),
            )
            _audit(conn, "private_session_ended", human_id, {
                "session_id": existing["id"],
                "duration_minutes": _session_duration_minutes(existing["started_at"], now_iso),
                "message_count": existing["message_count"],
                "ended_by": "timeout",
            })
            conn.commit()
        else:
            # Return existing active session
            conn.close()
            return {
                "session_id": existing["id"],
                "agent_id": agent_id,
                "channel": existing["channel"],
                "expires_at": existing["expires_at"],
            }

    expires_at = (now + timedelta(minutes=timeout_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = conn.execute(
        "INSERT INTO private_sessions (human_id, agent_id, channel, expires_at, timeout_minutes) "
        "VALUES (?, ?, ?, ?, ?)",
        (human_id, agent_id, channel, expires_at, timeout_minutes),
    )
    session_id = cur.lastrowid

    _audit(conn, "private_session_started", human_id, {
        "session_id": session_id,
        "agent_id": agent_id,
        "channel": channel,
    })

    conn.commit()
    conn.close()
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "channel": channel,
        "expires_at": expires_at,
    }


def end_private_session(session_id: int, ended_by: str = "human",
                         db_path: Optional[Path] = None) -> dict:
    """End a private session.

    Args:
        session_id: The private session ID.
        ended_by: Who ended it ('human', 'timeout', 'system').

    Returns:
        Dict with ok and session_id.
    """
    conn = get_conn(db_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session = conn.execute(
        "SELECT * FROM private_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not session:
        conn.close()
        return {"ok": False, "error": f"Session {session_id} not found"}

    if not session["active"]:
        conn.close()
        return {"ok": True, "session_id": session_id, "note": "Already ended"}

    conn.execute(
        "UPDATE private_sessions SET active=0, ended_by=?, ended_at=? WHERE id=?",
        (ended_by, now_iso, session_id),
    )
    _audit(conn, "private_session_ended", session["human_id"], {
        "session_id": session_id,
        "duration_minutes": _session_duration_minutes(session["started_at"], now_iso),
        "message_count": session["message_count"],
        "ended_by": ended_by,
    })
    conn.commit()
    conn.close()
    return {"ok": True, "session_id": session_id}


def get_active_private_session(human_id: int, agent_id: int,
                                db_path: Optional[Path] = None) -> Optional[dict]:
    """Return the active private session between a human and agent, or None.

    Auto-closes expired sessions.
    """
    conn = get_conn(db_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session = conn.execute(
        "SELECT * FROM private_sessions WHERE human_id=? AND agent_id=? AND active=1",
        (human_id, agent_id),
    ).fetchone()

    if not session:
        conn.close()
        return None

    if session["expires_at"] < now_iso:
        # Auto-close expired
        conn.execute(
            "UPDATE private_sessions SET active=0, ended_by='timeout', ended_at=? WHERE id=?",
            (now_iso, session["id"]),
        )
        _audit(conn, "private_session_ended", human_id, {
            "session_id": session["id"],
            "duration_minutes": _session_duration_minutes(session["started_at"], now_iso),
            "message_count": session["message_count"],
            "ended_by": "timeout",
        })
        conn.commit()
        conn.close()
        return None

    result = dict(session)
    conn.close()
    return result


def send_private_message(session_id: int, from_id: int, text: str,
                          db_path: Optional[Path] = None) -> dict:
    """Send a private message within an active session.

    Bypasses normal routing — the session IS the authorization.
    Updates session last_activity_at, increments message_count, and extends
    expires_at by the timeout (sliding window).

    Args:
        session_id: The active private session ID.
        from_id: Agent ID of the sender (must be human or agent in session).
        text: Message text.

    Returns:
        Dict with ok and message_id.
    """
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    session = conn.execute(
        "SELECT * FROM private_sessions WHERE id=? AND active=1", (session_id,)
    ).fetchone()
    if not session:
        conn.close()
        return {"ok": False, "error": f"No active session {session_id}"}

    # Validate sender is part of this session
    if from_id not in (session["human_id"], session["agent_id"]):
        conn.close()
        return {"ok": False, "error": "Sender is not part of this private session"}

    # Check expiry
    if session["expires_at"] < now_iso:
        conn.execute(
            "UPDATE private_sessions SET active=0, ended_by='timeout', ended_at=? WHERE id=?",
            (now_iso, session_id),
        )
        conn.commit()
        conn.close()
        return {"ok": False, "error": "Session has expired"}

    # Determine recipient
    to_id = session["agent_id"] if from_id == session["human_id"] else session["human_id"]

    # Insert message with private_session_id set
    cur = conn.execute(
        "INSERT INTO messages (from_agent_id, to_agent_id, message_type, subject, "
        "body, priority, private_session_id) VALUES (?, ?, 'report', 'Private message', ?, 'normal', ?)",
        (from_id, to_id, text, session_id),
    )
    msg_id = cur.lastrowid

    # Update session: sliding window expiry
    new_expires = (now + timedelta(minutes=session["timeout_minutes"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE private_sessions SET last_activity_at=?, message_count=message_count+1, "
        "expires_at=? WHERE id=?",
        (now_iso, new_expires, session_id),
    )

    conn.commit()
    conn.close()
    return {"ok": True, "message_id": msg_id}


def cleanup_expired_sessions(db_path: Optional[Path] = None) -> int:
    """Find and close all expired private sessions. Returns count closed."""
    conn = get_conn(db_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    expired = conn.execute(
        "SELECT * FROM private_sessions WHERE active=1 AND expires_at < ?", (now_iso,)
    ).fetchall()

    for s in expired:
        conn.execute(
            "UPDATE private_sessions SET active=0, ended_by='timeout', ended_at=? WHERE id=?",
            (now_iso, s["id"]),
        )
        _audit(conn, "private_session_ended", s["human_id"], {
            "session_id": s["id"],
            "duration_minutes": _session_duration_minutes(s["started_at"], now_iso),
            "message_count": s["message_count"],
            "ended_by": "timeout",
        })

    conn.commit()
    conn.close()
    return len(expired)


def _session_duration_minutes(started_at: str, ended_at: str) -> int:
    """Calculate session duration in minutes."""
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        return max(0, int((end - start).total_seconds() / 60))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Team Mailbox
# ---------------------------------------------------------------------------

VALID_MAILBOX_SEVERITIES = ("info", "warning", "code_red")
MAILBOX_RATE_LIMIT = 3  # max messages per agent per 24 hours


def send_to_team_mailbox(from_agent_id: int, subject: str, body: str,
                          severity: str = "info",
                          db_path: Optional[Path] = None) -> dict:
    """Send a message to the team mailbox.

    Any agent in a team can drop a message in the mailbox. The human sees
    it directly — no routing rules, no filtering, no interception.

    Args:
        from_agent_id: Sending agent's database ID.
        subject: Message subject.
        body: Message body.
        severity: One of 'info', 'warning', 'code_red'.

    Returns:
        Dict with ok, mailbox_id, severity.
    """
    if severity not in VALID_MAILBOX_SEVERITIES:
        return {"ok": False, "error": f"Invalid severity '{severity}'. Must be one of {VALID_MAILBOX_SEVERITIES}"}

    conn = get_conn(db_path)

    # Validate agent exists
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (from_agent_id,)).fetchone()
    if not agent:
        conn.close()
        return {"ok": False, "error": f"Agent id={from_agent_id} not found"}

    # Determine team_id: agent's parent if worker, self if manager
    if agent["agent_type"] == "manager":
        team_id = agent["id"]
    elif agent["parent_agent_id"]:
        # Check if parent is a manager (team membership)
        parent = conn.execute("SELECT * FROM agents WHERE id=?", (agent["parent_agent_id"],)).fetchone()
        if parent and parent["agent_type"] == "manager":
            team_id = parent["id"]
        elif parent and parent["agent_type"] == "right_hand":
            # Core crew agents don't belong to a team
            conn.close()
            return {"ok": False, "error": f"Agent '{agent['name']}' is core crew, not in a team. Use normal messaging."}
        else:
            team_id = agent["parent_agent_id"]
    else:
        conn.close()
        return {"ok": False, "error": f"Agent '{agent['name']}' is not part of a team"}

    # Rate limiting: max 3 messages per agent per 24 hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = conn.execute(
        "SELECT COUNT(*) FROM team_mailbox WHERE from_agent_id=? AND created_at>=?",
        (from_agent_id, cutoff),
    ).fetchone()[0]

    if count >= MAILBOX_RATE_LIMIT:
        conn.close()
        return {"ok": False, "error": f"Rate limit: {agent['name']} has sent {count}/{MAILBOX_RATE_LIMIT} mailbox messages in the last 24h"}

    # Insert
    cur = conn.execute(
        "INSERT INTO team_mailbox (team_id, from_agent_id, severity, subject, body) "
        "VALUES (?, ?, ?, ?, ?)",
        (team_id, from_agent_id, severity, subject, body),
    )
    mailbox_id = cur.lastrowid

    # Audit: log existence but NOT content
    _audit(conn, "team_mailbox_message", from_agent_id, {
        "team_id": team_id,
        "from_agent_id": from_agent_id,
        "severity": severity,
    })

    conn.commit()
    conn.close()
    return {"ok": True, "mailbox_id": mailbox_id, "severity": severity}


def get_team_mailbox(team_id: int, unread_only: bool = False,
                      db_path: Optional[Path] = None) -> list[dict]:
    """Return mailbox messages for a team, newest first.

    Args:
        team_id: The manager agent's ID (team identifier).
        unread_only: If True, only return unread messages.

    Returns:
        List of dicts with id, from_agent_name, severity, subject, body,
        read, created_at.
    """
    conn = get_conn(db_path)
    query = (
        "SELECT tm.*, a.name AS from_agent_name "
        "FROM team_mailbox tm JOIN agents a ON tm.from_agent_id = a.id "
        "WHERE tm.team_id = ?"
    )
    params: list = [team_id]

    if unread_only:
        query += " AND tm.read = 0"

    query += " ORDER BY tm.created_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_mailbox_read(message_id: int, db_path: Optional[Path] = None) -> dict:
    """Mark a team mailbox message as read."""
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE team_mailbox SET read=1, read_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id=?",
        (message_id,),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def get_team_mailbox_summary(team_id: int,
                              db_path: Optional[Path] = None) -> dict:
    """Return unread counts and severity summary for a team mailbox.

    Used by the dashboard to show indicators on team cards.

    Returns:
        Dict with unread_count, code_red_count, warning_count, latest_severity.
    """
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT severity, COUNT(*) AS cnt FROM team_mailbox "
        "WHERE team_id=? AND read=0 GROUP BY severity",
        (team_id,),
    ).fetchall()
    conn.close()

    counts = {r["severity"]: r["cnt"] for r in rows}
    unread = sum(counts.values())
    code_red = counts.get("code_red", 0)
    warning = counts.get("warning", 0)

    if code_red > 0:
        latest = "code_red"
    elif warning > 0:
        latest = "warning"
    elif unread > 0:
        latest = "info"
    else:
        latest = None

    return {
        "unread_count": unread,
        "code_red_count": code_red,
        "warning_count": warning,
        "latest_severity": latest,
    }


# ---------------------------------------------------------------------------
# Guard Activation
# ---------------------------------------------------------------------------

def is_guard_activated(db_path: Optional[Path] = None) -> bool:
    """Check if Guard activation key has been registered."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT COUNT(*) FROM guard_activation").fetchone()
    conn.close()
    return row[0] > 0


def activate_guard(activation_key: str, db_path: Optional[Path] = None):
    """Validate and store a Guard activation key.

    Returns (True, message) on success, (False, error) on failure.
    """
    # 1. Parse key format: CREWBUS-<payload>-<signature>
    if not activation_key or not activation_key.startswith("CREWBUS-"):
        return (False, "Invalid key format: must start with CREWBUS-")

    parts = activation_key.split("-", 2)  # ["CREWBUS", "<payload>-<sig>" or just payload]
    if len(parts) < 3:
        return (False, "Invalid key format: expected CREWBUS-<payload>-<signature>")

    # The remainder after "CREWBUS-" contains payload-signature
    remainder = activation_key[len("CREWBUS-"):]
    # Split on last hyphen to separate payload from signature
    last_dash = remainder.rfind("-")
    if last_dash <= 0:
        return (False, "Invalid key format: missing signature")

    payload_b64 = remainder[:last_dash]
    signature = remainder[last_dash + 1:]

    if not payload_b64 or not signature:
        return (False, "Invalid key format: empty payload or signature")

    # 2. Verify HMAC signature against GUARD_ACTIVATION_VERIFY_KEY
    expected_sig = hmac.new(
        GUARD_ACTIVATION_VERIFY_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        return (False, "Invalid activation key: signature verification failed")

    # 3. Decode payload, check type == "guard"
    try:
        payload_json = base64.b64decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return (False, "Invalid activation key: malformed payload")

    if payload.get("type") != "guard":
        return (False, "Invalid activation key: not a guard key")

    # 4. Generate fingerprint for storage
    key_fingerprint = hashlib.sha256(activation_key.encode("utf-8")).hexdigest()[:16]

    # 5. Store in guard_activation table
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        conn.execute(
            "INSERT INTO guard_activation (activation_key, activated_at, key_fingerprint) "
            "VALUES (?, ?, ?)",
            (activation_key, now, key_fingerprint),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return (False, "This activation key has already been used")
    conn.close()

    return (True, "Guard activated successfully")


def get_guard_activation_status(db_path: Optional[Path] = None) -> Optional[dict]:
    """Return activation details or None if not activated."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT activated_at, key_fingerprint FROM guard_activation LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "activated": True,
        "activated_at": row["activated_at"],
        "key_fingerprint": row["key_fingerprint"],
    }


def generate_test_activation_key(verify_key: Optional[str] = None) -> str:
    """Generate a valid activation key for testing purposes.

    Uses the module-level GUARD_ACTIVATION_VERIFY_KEY unless overridden.
    """
    key = verify_key or GUARD_ACTIVATION_VERIFY_KEY
    payload_dict = {
        "type": "guard",
        "issued": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "id": str(uuid.uuid4()),
    }
    payload_b64 = base64.b64encode(json.dumps(payload_dict).encode("utf-8")).decode("utf-8")
    sig = hmac.new(
        key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"CREWBUS-{payload_b64}-{sig}"


# ---------------------------------------------------------------------------
# Agent Skills (gated by Guard activation)
# ---------------------------------------------------------------------------

def add_skill_to_agent(agent_id: int, skill_name: str, skill_config: str = "{}",
                       added_by: str = "human", db_path: Optional[Path] = None):
    """Add a skill to an agent. Requires Guard activation.

    Returns (True, message) on success, (False, error) on failure.
    """
    if not is_guard_activated(db_path):
        return (False, "Guard activation required. Visit crew-bus.dev/activate")

    if not skill_name or not skill_name.strip():
        return (False, "Skill name is required")

    conn = get_conn(db_path)
    # Validate agent exists
    agent = conn.execute("SELECT id, name FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        return (False, f"Agent id={agent_id} not found")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        conn.execute(
            "INSERT INTO agent_skills (agent_id, skill_name, skill_config, added_at, added_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (agent_id, skill_name.strip(), skill_config, now, added_by),
        )
        # Audit the skill addition
        conn.execute(
            "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
            ("skill_added", agent_id, json.dumps({
                "skill_name": skill_name.strip(),
                "added_by": added_by,
            })),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return (False, f"Skill '{skill_name.strip()}' already exists on agent {agent['name']}")
    conn.close()
    return (True, f"Skill '{skill_name.strip()}' added to {agent['name']}")


def get_agent_skills(agent_id: int, db_path: Optional[Path] = None) -> list:
    """Return list of skills for an agent."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT skill_name, skill_config, added_at, added_by "
        "FROM agent_skills WHERE agent_id = ? ORDER BY added_at",
        (agent_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_skill_from_agent(agent_id: int, skill_name: str,
                            db_path: Optional[Path] = None):
    """Remove a skill from an agent.

    Returns (True, message) on success, (False, error) on failure.
    """
    conn = get_conn(db_path)
    cur = conn.execute(
        "DELETE FROM agent_skills WHERE agent_id = ? AND skill_name = ?",
        (agent_id, skill_name),
    )
    if cur.rowcount == 0:
        conn.close()
        return (False, f"Skill '{skill_name}' not found on agent id={agent_id}")
    conn.execute(
        "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
        ("skill_removed", agent_id, json.dumps({"skill_name": skill_name})),
    )
    conn.commit()
    conn.close()
    return (True, f"Skill '{skill_name}' removed")


# ---------------------------------------------------------------------------
# Techie Marketplace
# ---------------------------------------------------------------------------

def register_techie(techie_id: str, display_name: str, email: str,
                    db_path: Optional[Path] = None) -> dict:
    """Register a new techie (KYC pending)."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        conn.execute(
            "INSERT INTO authorized_techies (techie_id, display_name, email, created_at) "
            "VALUES (?, ?, ?, ?)",
            (techie_id, display_name, email, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Techie '{techie_id}' already exists")
    conn.close()
    return {"techie_id": techie_id, "display_name": display_name, "kyc_status": "pending"}


def verify_techie_kyc(techie_id: str, db_path: Optional[Path] = None) -> dict:
    """Mark techie as KYC verified."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "UPDATE authorized_techies SET kyc_status='verified', kyc_verified_at=? "
        "WHERE techie_id=?",
        (now, techie_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise ValueError(f"Techie '{techie_id}' not found")
    conn.commit()
    conn.close()
    return {"techie_id": techie_id, "kyc_status": "verified", "kyc_verified_at": now}


def revoke_techie(techie_id: str, reason: str, db_path: Optional[Path] = None) -> dict:
    """Revoke a techie's authorization."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "UPDATE authorized_techies SET standing='revoked', revoked_at=?, revocation_reason=? "
        "WHERE techie_id=?",
        (now, reason, techie_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise ValueError(f"Techie '{techie_id}' not found")
    conn.commit()
    conn.close()
    return {"techie_id": techie_id, "standing": "revoked", "reason": reason}


def get_techie_profile(techie_id: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Get full techie profile including stats."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM authorized_techies WHERE techie_id=?", (techie_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def purchase_techie_key(techie_id: str, db_path: Optional[Path] = None) -> str:
    """Generate and store a new techie service key.

    Requires kyc_status='verified' and standing='good'.
    Returns the key value.
    """
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT kyc_status, standing FROM authorized_techies WHERE techie_id=?",
        (techie_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Techie '{techie_id}' not found")
    if row["kyc_status"] != "verified":
        conn.close()
        raise PermissionError(f"Techie '{techie_id}' is not KYC verified (status: {row['kyc_status']})")
    if row["standing"] != "good":
        conn.close()
        raise PermissionError(f"Techie '{techie_id}' standing is '{row['standing']}', must be 'good'")

    key_value = f"TECHIE-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO techie_keys (techie_id, key_value, purchased_at) VALUES (?, ?, ?)",
        (techie_id, key_value, now),
    )
    conn.execute(
        "UPDATE authorized_techies SET total_keys_purchased = total_keys_purchased + 1 "
        "WHERE techie_id=?",
        (techie_id,),
    )
    conn.commit()
    conn.close()
    return key_value


def use_techie_key(key_value: str, user_identifier: str,
                   db_path: Optional[Path] = None) -> dict:
    """Mark a techie key as used for a specific user."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT id, techie_id, used_at FROM techie_keys WHERE key_value=?", (key_value,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Key '{key_value}' not found")
    if row["used_at"] is not None:
        conn.close()
        raise ValueError(f"Key '{key_value}' has already been used")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE techie_keys SET used_at=?, used_for_user=? WHERE key_value=?",
        (now, user_identifier, key_value),
    )
    conn.execute(
        "UPDATE authorized_techies SET total_jobs_completed = total_jobs_completed + 1 "
        "WHERE techie_id=?",
        (row["techie_id"],),
    )
    conn.commit()
    conn.close()
    return {"key_value": key_value, "techie_id": row["techie_id"],
            "used_for_user": user_identifier, "used_at": now}


def add_techie_review(techie_id: str, reviewer_id: str, rating: int,
                      review_text: str = "", db_path: Optional[Path] = None) -> dict:
    """Add a review for a techie. Updates their average rating."""
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5")

    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT techie_id FROM authorized_techies WHERE techie_id=?", (techie_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Techie '{techie_id}' not found")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO techie_reviews (techie_id, reviewer_id, rating, review_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (techie_id, reviewer_id, rating, review_text, now),
    )

    # Recalculate average
    stats = conn.execute(
        "SELECT AVG(rating) AS avg_r, COUNT(*) AS cnt FROM techie_reviews WHERE techie_id=?",
        (techie_id,),
    ).fetchone()
    conn.execute(
        "UPDATE authorized_techies SET rating_avg=?, rating_count=? WHERE techie_id=?",
        (round(stats["avg_r"], 2), stats["cnt"], techie_id),
    )
    conn.commit()
    conn.close()
    return {"techie_id": techie_id, "rating": rating, "new_avg": round(stats["avg_r"], 2),
            "total_reviews": stats["cnt"]}


def list_techies(status: str = "verified", standing: str = "good",
                 db_path: Optional[Path] = None) -> list:
    """List techies filtered by KYC status and standing."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM authorized_techies WHERE kyc_status=? AND standing=? "
        "ORDER BY rating_avg DESC",
        (status, standing),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# User Authentication
# ---------------------------------------------------------------------------

def create_user(email: str, password_hash: str, user_type: str = "client",
                display_name: str = "", db_path: Optional[Path] = None) -> dict:
    """Create a new user account."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verify_token = uuid.uuid4().hex
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, user_type, display_name, "
            "verify_token, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (email.lower().strip(), password_hash, user_type, display_name,
             verify_token, now),
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError("Email already registered")
    conn.close()
    return {"id": user_id, "email": email, "user_type": user_type,
            "verify_token": verify_token}


def get_user_by_email(email: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Lookup user by email."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """Lookup user by ID."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_session(user_id: int, hours: int = 168,
                   db_path: Optional[Path] = None) -> str:
    """Create a session token. Default 7 days."""
    conn = get_conn(db_path)
    token = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=hours)
    conn.execute(
        "INSERT INTO sessions (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (user_id, token, expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
         now.strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()
    conn.close()
    return token


def validate_session(token: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Validate a session token, return user if valid."""
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT s.*, u.email, u.user_type, u.display_name, u.techie_id "
        "FROM sessions s JOIN users u ON s.user_id=u.id "
        "WHERE s.token=?", (token,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if row["expires_at"] < now:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
        return None
    conn.close()
    return dict(row)


def delete_session(token: str, db_path: Optional[Path] = None) -> None:
    """Delete a session token (logout)."""
    conn = get_conn(db_path)
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(title: str, description: str, needs: str = "",
               postal_code: str = "", country: str = "",
               urgency: str = "standard", budget: str = "negotiable",
               contact_name: str = "", contact_email: str = "",
               posted_by: Optional[int] = None,
               db_path: Optional[Path] = None) -> dict:
    """Create a new job posting."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO jobs (title, description, needs, postal_code, country, "
        "urgency, budget, contact_name, contact_email, posted_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, description, needs, postal_code, country, urgency, budget,
         contact_name, contact_email, posted_by, now),
    )
    job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": job_id, "title": title, "status": "open", "created_at": now}


def list_jobs(status: str = "open", postal_code: str = "",
              urgency: str = "", limit: int = 50,
              db_path: Optional[Path] = None) -> list:
    """List jobs with optional filters."""
    conn = get_conn(db_path)
    sql = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if status and status != "all":
        sql += " AND status=?"
        params.append(status)
    if postal_code:
        sql += " AND postal_code LIKE ?"
        params.append(postal_code + "%")
    if urgency:
        sql += " AND urgency=?"
        params.append(urgency)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """Get a single job by ID."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_job(job_id: int, techie_id: str,
              db_path: Optional[Path] = None) -> dict:
    """Installer claims a job."""
    conn = get_conn(db_path)
    row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("Job not found")
    if row["status"] != "open":
        conn.close()
        raise ValueError("Job is not open")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE jobs SET status='claimed', claimed_by=?, claimed_at=? WHERE id=?",
        (techie_id, now, job_id),
    )
    conn.commit()
    conn.close()
    return {"job_id": job_id, "status": "claimed", "claimed_by": techie_id}


def complete_job(job_id: int, db_path: Optional[Path] = None) -> dict:
    """Mark a job as completed."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE jobs SET status='completed', completed_at=? WHERE id=?",
        (now, job_id),
    )
    conn.commit()
    conn.close()
    return {"job_id": job_id, "status": "completed"}


# ---------------------------------------------------------------------------
# Meet & Greet
# ---------------------------------------------------------------------------

def create_meet_request(techie_id: str, client_user_id: Optional[int] = None,
                        job_id: Optional[int] = None, proposed_times: str = "[]",
                        notes: str = "", db_path: Optional[Path] = None) -> dict:
    """Client requests a meet & greet with an installer."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO meet_requests (client_user_id, techie_id, job_id, "
        "proposed_times, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (client_user_id, techie_id, job_id, proposed_times, notes, now),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": req_id, "techie_id": techie_id, "status": "pending"}


def respond_meet_request(request_id: int, accept: bool,
                         accepted_time: str = "", meeting_link: str = "",
                         db_path: Optional[Path] = None) -> dict:
    """Installer accepts or declines a meet & greet request."""
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status = "accepted" if accept else "declined"
    conn.execute(
        "UPDATE meet_requests SET status=?, accepted_time=?, meeting_link=?, "
        "responded_at=? WHERE id=?",
        (status, accepted_time, meeting_link, now, request_id),
    )
    conn.commit()
    conn.close()
    return {"id": request_id, "status": status}


def list_meet_requests(techie_id: str = "", client_user_id: Optional[int] = None,
                       status: str = "", db_path: Optional[Path] = None) -> list:
    """List meet & greet requests for an installer or client."""
    conn = get_conn(db_path)
    sql = "SELECT * FROM meet_requests WHERE 1=1"
    params = []
    if techie_id:
        sql += " AND techie_id=?"
        params.append(techie_id)
    if client_user_id:
        sql += " AND client_user_id=?"
        params.append(client_user_id)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
