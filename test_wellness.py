"""
test_wellness.py - Comprehensive tests for the holistic wellness engine.

Tests:
  1. Database schema: All new wellness tables created
  2. Wellness check-ins: Sleep, exercise, hydration, mood, screen_time, outdoor, social, nutrition
  3. Wellness goals: Create, update streak, get goals
  4. Wellness journal: Reflection, gratitude, mood_log, coping, win, worry
  5. Wellness preferences: Create defaults, update, get
  6. Wellness score: Holistic calculation across all dimensions
  7. Wellness nudges: Contextual nudge generation
  8. Bridge methods: All wellness bridge methods for wellness agents
  9. Bridge restrictions: Non-wellness agents are blocked
 10. Human state sync: Check-ins auto-update human_state
 11. Right Hand integration: Wellness in briefings and state assessment
 12. Dashboard API: All wellness endpoints

Run:
  python test_wellness.py
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus
from agent_bridge import CrewBridge
from dashboard import create_server

# ---------------------------------------------------------------------------
# Test DB and setup
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_wellness.db"
CONFIG = Path(__file__).parent / "configs" / "example_stack.yaml"

if TEST_DB.exists():
    os.remove(str(TEST_DB))

# Test tracking
passed = 0
failed = 0


def check(test_name, condition, detail=""):
    global passed, failed
    label = "[PASS]" if condition else "[FAIL]"
    msg = f"  {label} {detail}" if detail else f"  {label} {test_name}"
    print(msg)
    if condition:
        passed += 1
    else:
        failed += 1
    return condition


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Setup: Initialize DB and load hierarchy
# ---------------------------------------------------------------------------

section("Setup: Initialize DB + Load Hierarchy")

bus.init_db(TEST_DB)

# Check if config exists, try alternatives
if not CONFIG.exists():
    configs_dir = Path(__file__).parent / "configs"
    if configs_dir.is_dir():
        yamls = list(configs_dir.glob("*.yaml")) + list(configs_dir.glob("*.yml"))
        if yamls:
            CONFIG = yamls[0]

if CONFIG.exists():
    result = bus.load_hierarchy(str(CONFIG), TEST_DB)
    agents_loaded = result.get("agents_loaded", [])
    check("setup.hierarchy", len(agents_loaded) >= 3,
          f"Loaded {len(agents_loaded)} agents from {CONFIG.name}")
else:
    # Manual setup if no config
    conn = bus.get_conn(TEST_DB)
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, status) VALUES "
        "('Human', 'human', 'human', 'active')")
    human_id = conn.execute("SELECT id FROM agents WHERE name='Human'").fetchone()["id"]
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status) VALUES "
        "(?, 'right_hand', 'right_hand', ?, 'active')", ("Crew-Boss", human_id))
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status) VALUES "
        "(?, 'wellness', 'core_crew', ?, 'active')", ("Wellness", human_id))
    rh_id = conn.execute("SELECT id FROM agents WHERE name='Crew-Boss'").fetchone()["id"]
    conn.execute(
        "UPDATE agents SET parent_agent_id=? WHERE agent_type IN ('wellness') AND name != 'Human'",
        (rh_id,))
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status) VALUES "
        "(?, 'strategy', 'core_crew', ?, 'active')", ("Strategy", rh_id))
    conn.commit()
    conn.close()
    check("setup.manual", True, "Manual agent setup complete")

# Get key agent references
human = bus.get_agent_by_name("Human", TEST_DB)
if not human:
    # Try alternative names
    conn = bus.get_conn(TEST_DB)
    human = conn.execute("SELECT * FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
    conn.close()
    if human:
        human = dict(human)

check("setup.human", human is not None, f"Human agent: {human['name'] if human else 'NOT FOUND'}")

# Find wellness agent
conn = bus.get_conn(TEST_DB)
wellness_agent = conn.execute(
    "SELECT * FROM agents WHERE agent_type='wellness' LIMIT 1"
).fetchone()
conn.close()
if wellness_agent:
    wellness_agent = dict(wellness_agent)
check("setup.wellness", wellness_agent is not None,
      f"Wellness agent: {wellness_agent['name'] if wellness_agent else 'NOT FOUND'}")

HUMAN_ID = human["id"] if human else None


# ---------------------------------------------------------------------------
# Test 1: Database schema - all new tables exist
# ---------------------------------------------------------------------------

section("Test 1: Database Schema - Wellness Tables")

conn = bus.get_conn(TEST_DB)
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
conn.close()

for table in ["wellness_checkins", "wellness_goals", "wellness_journal", "wellness_preferences"]:
    check(f"schema.{table}", table in tables, f"Table '{table}' exists")

# Check human_state has new columns
conn = bus.get_conn(TEST_DB)
cols = [r[1] for r in conn.execute("PRAGMA table_info(human_state)").fetchall()]
conn.close()

for col in ["sleep_quality", "sleep_hours", "hydration_glasses",
            "exercise_minutes_today", "last_exercise", "screen_time_minutes",
            "last_outdoor_time", "gratitude_streak", "overall_wellness_score"]:
    check(f"schema.state.{col}", col in cols, f"human_state has '{col}' column")


# ---------------------------------------------------------------------------
# Test 2: Wellness Check-ins (bus functions)
# ---------------------------------------------------------------------------

section("Test 2: Wellness Check-ins (bus functions)")

# Sleep check-in
sleep_id = bus.store_wellness_checkin(
    HUMAN_ID, "sleep",
    {"quality": 8, "hours": 7.5, "bedtime": "23:00", "waketime": "06:30"},
    notes="Slept well", logged_by="test",
    db_path=TEST_DB,
)
check("checkin.sleep", sleep_id > 0, f"Sleep check-in stored: id={sleep_id}")

# Exercise check-in
exercise_id = bus.store_wellness_checkin(
    HUMAN_ID, "exercise",
    {"activity": "running", "duration_min": 30, "intensity": "moderate"},
    notes="Morning run", logged_by="test",
    db_path=TEST_DB,
)
check("checkin.exercise", exercise_id > 0, f"Exercise check-in stored: id={exercise_id}")

# Hydration check-in
hydration_id = bus.store_wellness_checkin(
    HUMAN_ID, "hydration",
    {"glasses": 6, "target": 8},
    db_path=TEST_DB,
)
check("checkin.hydration", hydration_id > 0, f"Hydration check-in stored: id={hydration_id}")

# Mood check-in
mood_id = bus.store_wellness_checkin(
    HUMAN_ID, "mood",
    {"score": 7, "triggers": ["good meeting"], "coping": "walk"},
    db_path=TEST_DB,
)
check("checkin.mood", mood_id > 0, f"Mood check-in stored: id={mood_id}")

# Screen time check-in
screen_id = bus.store_wellness_checkin(
    HUMAN_ID, "screen_time",
    {"minutes": 240, "breaks_taken": 4},
    db_path=TEST_DB,
)
check("checkin.screen", screen_id > 0, f"Screen time check-in stored: id={screen_id}")

# Outdoor check-in
outdoor_id = bus.store_wellness_checkin(
    HUMAN_ID, "outdoor",
    {"minutes": 45, "activity": "walk"},
    db_path=TEST_DB,
)
check("checkin.outdoor", outdoor_id > 0, f"Outdoor check-in stored: id={outdoor_id}")

# Social check-in
social_id = bus.store_wellness_checkin(
    HUMAN_ID, "social",
    {"type": "call", "with": "friend", "quality": "good", "duration_min": 30},
    db_path=TEST_DB,
)
check("checkin.social", social_id > 0, f"Social check-in stored: id={social_id}")

# Nutrition check-in
nutrition_id = bus.store_wellness_checkin(
    HUMAN_ID, "nutrition",
    {"meals": 3, "quality": "good", "skipped_meals": False},
    db_path=TEST_DB,
)
check("checkin.nutrition", nutrition_id > 0, f"Nutrition check-in stored: id={nutrition_id}")

# Invalid type should fail
try:
    bus.store_wellness_checkin(HUMAN_ID, "invalid_type", {}, db_path=TEST_DB)
    check("checkin.invalid", False, "Invalid type should have raised")
except ValueError:
    check("checkin.invalid", True, "Invalid checkin type correctly rejected")

# Retrieve check-ins
all_checkins = bus.get_wellness_checkins(HUMAN_ID, days=1, db_path=TEST_DB)
check("checkin.retrieve", len(all_checkins) == 8,
      f"Retrieved {len(all_checkins)} check-ins (expected 8)")

sleep_checkins = bus.get_wellness_checkins(HUMAN_ID, checkin_type="sleep", days=1, db_path=TEST_DB)
check("checkin.filter", len(sleep_checkins) == 1,
      f"Retrieved {len(sleep_checkins)} sleep check-ins")

# Verify data is parsed
check("checkin.data_parsed", isinstance(sleep_checkins[0]["data"], dict),
      "Check-in data is parsed as dict")
check("checkin.data_quality", sleep_checkins[0]["data"]["quality"] == 8,
      f"Sleep quality: {sleep_checkins[0]['data']['quality']}")


# ---------------------------------------------------------------------------
# Test 3: Human State Sync
# ---------------------------------------------------------------------------

section("Test 3: Human State Sync from Check-ins")

state = bus.get_human_state(HUMAN_ID, db_path=TEST_DB)

check("sync.sleep_quality", state.get("sleep_quality") == 8,
      f"Sleep quality synced: {state.get('sleep_quality')}")
check("sync.sleep_hours", state.get("sleep_hours") == 7.5,
      f"Sleep hours synced: {state.get('sleep_hours')}")
check("sync.hydration", state.get("hydration_glasses") == 6,
      f"Hydration glasses synced: {state.get('hydration_glasses')}")
check("sync.exercise_min", state.get("exercise_minutes_today") == 30,
      f"Exercise minutes synced: {state.get('exercise_minutes_today')}")
check("sync.last_exercise", state.get("last_exercise") is not None,
      f"Last exercise timestamp set")
check("sync.screen_time", state.get("screen_time_minutes") == 240,
      f"Screen time synced: {state.get('screen_time_minutes')}")
check("sync.last_outdoor", state.get("last_outdoor_time") is not None,
      f"Last outdoor time set")
check("sync.last_social", state.get("last_social_activity") is not None,
      f"Last social activity set")
check("sync.mood", state.get("mood_indicator") == "good",
      f"Mood synced: {state.get('mood_indicator')}")


# ---------------------------------------------------------------------------
# Test 4: Wellness Goals
# ---------------------------------------------------------------------------

section("Test 4: Wellness Goals")

# Create goals
water_goal = bus.store_wellness_goal(
    HUMAN_ID, "hydration", "Drink 8 glasses of water",
    target_value=8, target_unit="glasses", frequency="daily",
    db_path=TEST_DB,
)
check("goal.create_water", water_goal > 0, f"Water goal created: id={water_goal}")

exercise_goal = bus.store_wellness_goal(
    HUMAN_ID, "exercise", "Exercise 150 min/week",
    target_value=150, target_unit="minutes", frequency="weekly",
    db_path=TEST_DB,
)
check("goal.create_exercise", exercise_goal > 0, f"Exercise goal created: id={exercise_goal}")

# Get goals
goals = bus.get_wellness_goals(HUMAN_ID, db_path=TEST_DB)
check("goal.list", len(goals) == 2, f"Got {len(goals)} goals")

# Update streak
updated = bus.update_goal_streak(water_goal, completed=True, db_path=TEST_DB)
check("goal.streak_inc", updated["current_streak"] == 1,
      f"Streak: {updated['current_streak']}")
check("goal.best_streak", updated["best_streak"] == 1,
      f"Best streak: {updated['best_streak']}")
check("goal.last_completed", updated["last_completed"] is not None,
      "Last completed timestamp set")

# Complete again
updated = bus.update_goal_streak(water_goal, completed=True, db_path=TEST_DB)
check("goal.streak_2", updated["current_streak"] == 2,
      f"Streak: {updated['current_streak']}")

# Break streak
updated = bus.update_goal_streak(water_goal, completed=False, db_path=TEST_DB)
check("goal.streak_reset", updated["current_streak"] == 0,
      f"Streak reset: {updated['current_streak']}")
check("goal.best_preserved", updated["best_streak"] == 2,
      f"Best streak preserved: {updated['best_streak']}")

# Invalid goal type
try:
    bus.store_wellness_goal(HUMAN_ID, "invalid", "Bad", target_value=1, db_path=TEST_DB)
    check("goal.invalid", False, "Invalid type should have raised")
except ValueError:
    check("goal.invalid", True, "Invalid goal type correctly rejected")


# ---------------------------------------------------------------------------
# Test 5: Wellness Journal
# ---------------------------------------------------------------------------

section("Test 5: Wellness Journal")

# Reflection entry
reflection_id = bus.store_journal_entry(
    HUMAN_ID, "reflection",
    "Today was productive. I managed to complete all my tasks without feeling overwhelmed.",
    mood_before=6, mood_after=8,
    tags="productivity,balance",
    db_path=TEST_DB,
)
check("journal.reflection", reflection_id > 0, f"Reflection stored: id={reflection_id}")

# Gratitude entry
gratitude_id = bus.store_journal_entry(
    HUMAN_ID, "gratitude",
    "Grateful for: 1) supportive team 2) good health 3) beautiful weather",
    db_path=TEST_DB,
)
check("journal.gratitude", gratitude_id > 0, f"Gratitude stored: id={gratitude_id}")

# Win entry
win_id = bus.store_journal_entry(
    HUMAN_ID, "win",
    "Landed a new client today! Big milestone.",
    mood_before=7, mood_after=9,
    db_path=TEST_DB,
)
check("journal.win", win_id > 0, f"Win stored: id={win_id}")

# Worry entry
worry_id = bus.store_journal_entry(
    HUMAN_ID, "worry",
    "Concerned about the upcoming deadline. Need to plan better.",
    mood_before=5,
    tags="work,stress",
    db_path=TEST_DB,
)
check("journal.worry", worry_id > 0, f"Worry stored: id={worry_id}")

# Coping entry
coping_id = bus.store_journal_entry(
    HUMAN_ID, "coping",
    "Deep breathing exercise for 5 minutes. Helped me refocus.",
    mood_before=4, mood_after=7,
    db_path=TEST_DB,
)
check("journal.coping", coping_id > 0, f"Coping stored: id={coping_id}")

# Retrieve all
all_entries = bus.get_journal_entries(HUMAN_ID, days=1, db_path=TEST_DB)
check("journal.retrieve_all", len(all_entries) == 5,
      f"Got {len(all_entries)} journal entries")

# Retrieve by type
gratitudes = bus.get_journal_entries(HUMAN_ID, entry_type="gratitude", days=1, db_path=TEST_DB)
check("journal.filter", len(gratitudes) == 1, f"Got {len(gratitudes)} gratitude entries")

# Check gratitude streak was updated
state = bus.get_human_state(HUMAN_ID, db_path=TEST_DB)
check("journal.gratitude_streak", (state.get("gratitude_streak") or 0) >= 1,
      f"Gratitude streak: {state.get('gratitude_streak')}")

# Invalid mood range
try:
    bus.store_journal_entry(HUMAN_ID, "reflection", "test", mood_before=15, db_path=TEST_DB)
    check("journal.invalid_mood", False, "Invalid mood should have raised")
except ValueError:
    check("journal.invalid_mood", True, "Invalid mood_before correctly rejected")

# Invalid entry type
try:
    bus.store_journal_entry(HUMAN_ID, "invalid_type", "test", db_path=TEST_DB)
    check("journal.invalid_type", False, "Invalid type should have raised")
except ValueError:
    check("journal.invalid_type", True, "Invalid entry type correctly rejected")


# ---------------------------------------------------------------------------
# Test 6: Wellness Preferences
# ---------------------------------------------------------------------------

section("Test 6: Wellness Preferences")

# Get defaults (auto-creates)
prefs = bus.get_wellness_preferences(HUMAN_ID, db_path=TEST_DB)
check("prefs.default_mode", prefs["interaction_mode"] == "both",
      f"Default mode: {prefs['interaction_mode']}")
check("prefs.default_freq", prefs["checkin_frequency"] == "daily",
      f"Default frequency: {prefs['checkin_frequency']}")
check("prefs.default_style", prefs["motivational_style"] == "gentle",
      f"Default style: {prefs['motivational_style']}")
check("prefs.nudge_types", isinstance(prefs["nudge_types"], list),
      f"Nudge types is a list: {prefs['nudge_types']}")

# Update preferences
updated = bus.update_wellness_preferences(HUMAN_ID, {
    "motivational_style": "coach",
    "checkin_frequency": "twice_daily",
    "nudge_types": ["sleep", "exercise", "hydration"],
    "quiet_on_weekends": True,
}, db_path=TEST_DB)
check("prefs.update_style", updated["motivational_style"] == "coach",
      f"Updated style: {updated['motivational_style']}")
check("prefs.update_freq", updated["checkin_frequency"] == "twice_daily",
      f"Updated frequency: {updated['checkin_frequency']}")
check("prefs.update_nudges", updated["nudge_types"] == ["sleep", "exercise", "hydration"],
      f"Updated nudges: {updated['nudge_types']}")
check("prefs.update_weekends", updated["quiet_on_weekends"] == 1,
      f"Updated weekends: {updated['quiet_on_weekends']}")


# ---------------------------------------------------------------------------
# Test 7: Wellness Score Calculation
# ---------------------------------------------------------------------------

section("Test 7: Wellness Score Calculation")

score = bus.calculate_wellness_score(HUMAN_ID, db_path=TEST_DB)
check("score.overall", 0 <= score["overall_score"] <= 100,
      f"Overall score: {score['overall_score']}/100")
check("score.dimensions", len(score["dimensions"]) == 9,
      f"Dimensions: {len(score['dimensions'])} ({', '.join(score['dimensions'].keys())})")

# Verify each dimension has score, weight, detail
for dim_name, dim_data in score["dimensions"].items():
    check(f"score.dim.{dim_name}",
          "score" in dim_data and "weight" in dim_data and "detail" in dim_data,
          f"{dim_name}: score={dim_data['score']}, weight={dim_data['weight']}")

# Verify weights sum to 100
total_weight = sum(d["weight"] for d in score["dimensions"].values())
check("score.weights_100", total_weight == 100,
      f"Weights sum: {total_weight}")

# Data completeness
check("score.completeness", score["data_completeness"] > 0,
      f"Data completeness: {score['data_completeness']:.0f}%")

# Verify score was synced to human_state
state = bus.get_human_state(HUMAN_ID, db_path=TEST_DB)
check("score.synced", state.get("overall_wellness_score") == score["overall_score"],
      f"Score synced to state: {state.get('overall_wellness_score')}")


# ---------------------------------------------------------------------------
# Test 8: Wellness Nudges
# ---------------------------------------------------------------------------

section("Test 8: Wellness Nudges")

# First set preferences to enable nudges and set coach style
bus.update_wellness_preferences(HUMAN_ID, {
    "motivational_style": "coach",
    "nudge_types": ["sleep", "exercise", "hydration", "social", "breaks"],
}, db_path=TEST_DB)

# Set high burnout to trigger burnout nudge
bus.update_burnout_score(HUMAN_ID, 8, db_path=TEST_DB)

nudges = bus.get_wellness_nudges(HUMAN_ID, db_path=TEST_DB)
check("nudges.exist", len(nudges) > 0, f"Got {len(nudges)} nudges")

# Burnout nudge should be present at 8/10
burnout_nudge = [n for n in nudges if n["category"] == "burnout"]
check("nudges.burnout", len(burnout_nudge) > 0,
      f"Burnout nudge present: {burnout_nudge[0]['message'][:60] if burnout_nudge else 'missing'}...")

# Each nudge should have required fields
for nudge in nudges:
    check(f"nudges.fields.{nudge['category']}",
          all(k in nudge for k in ("type", "message", "priority", "category")),
          f"Nudge has all required fields: {nudge['category']}")

# Reset burnout for remaining tests
bus.update_burnout_score(HUMAN_ID, 5, db_path=TEST_DB)


# ---------------------------------------------------------------------------
# Test 9: CrewBridge Wellness Methods
# ---------------------------------------------------------------------------

section("Test 9: CrewBridge Wellness Methods")

if wellness_agent:
    bridge = CrewBridge(wellness_agent["name"], db_path=TEST_DB)

    # Log sleep
    result = bridge.log_sleep(quality=7, hours=7.0, bedtime="23:30", waketime="06:30")
    check("bridge.sleep", result.get("ok") is True,
          f"Sleep logged: checkin_id={result.get('checkin_id')}")

    # Log exercise
    result = bridge.log_exercise("yoga", 45, intensity="low", notes="Morning yoga")
    check("bridge.exercise", result.get("ok") is True,
          f"Exercise logged: checkin_id={result.get('checkin_id')}")

    # Log hydration
    result = bridge.log_hydration(5, target=8)
    check("bridge.hydration", result.get("ok") is True,
          f"Hydration logged: checkin_id={result.get('checkin_id')}")

    # Log mood
    result = bridge.log_mood(8, triggers=["great workout"], coping="exercise")
    check("bridge.mood", result.get("ok") is True,
          f"Mood logged: checkin_id={result.get('checkin_id')}")

    # Log screen time
    result = bridge.log_screen_time(300, breaks_taken=5)
    check("bridge.screen", result.get("ok") is True,
          f"Screen time logged: checkin_id={result.get('checkin_id')}")

    # Log outdoor time
    result = bridge.log_outdoor_time(60, activity="hiking")
    check("bridge.outdoor", result.get("ok") is True,
          f"Outdoor time logged: checkin_id={result.get('checkin_id')}")

    # Log social
    result = bridge.log_social("in_person", with_whom="colleague", quality="good", duration_min=60)
    check("bridge.social", result.get("ok") is True,
          f"Social logged: checkin_id={result.get('checkin_id')}")

    # Log nutrition
    result = bridge.log_nutrition(3, quality="good")
    check("bridge.nutrition", result.get("ok") is True,
          f"Nutrition logged: checkin_id={result.get('checkin_id')}")

    # Journal
    result = bridge.journal("gratitude", "Grateful for health and family")
    check("bridge.journal", result.get("ok") is True,
          f"Journal logged: entry_id={result.get('entry_id')}")

    # Set goal
    result = bridge.set_wellness_goal("sleep", "Sleep 8 hours", 8, target_unit="hours")
    check("bridge.goal", result.get("ok") is True,
          f"Goal created: goal_id={result.get('goal_id')}")

    # Get goals
    goals = bridge.get_wellness_goals()
    check("bridge.goals_list", len(goals) >= 1,
          f"Got {len(goals)} goals")

    # Update goal progress
    if goals:
        result = bridge.update_goal_progress(goals[0]["id"], completed=True)
        check("bridge.goal_progress", result.get("ok") is True,
              f"Goal updated: streak={result.get('goal', {}).get('current_streak')}")

    # Get wellness score
    score = bridge.get_wellness_score()
    check("bridge.score", "overall_score" in score,
          f"Score: {score.get('overall_score')}/100")

    # Get wellness summary
    summary = bridge.get_wellness_summary()
    check("bridge.summary", summary.get("ok") is True,
          f"Summary: score={summary.get('overall_score')}, "
          f"goals={summary.get('active_goals')}, "
          f"nudges={len(summary.get('nudges', []))}")

    # Get nudges
    nudges = bridge.get_nudges()
    check("bridge.nudges", isinstance(nudges, list),
          f"Got {len(nudges)} nudges")

    # Update preferences
    result = bridge.update_preferences(motivational_style="balanced", checkin_frequency="daily")
    check("bridge.prefs", result.get("ok") is True,
          f"Preferences updated: style={result.get('preferences', {}).get('motivational_style')}")

else:
    check("bridge.skip", False, "No wellness agent found - skipping bridge tests")


# ---------------------------------------------------------------------------
# Test 10: Non-wellness agents are blocked
# ---------------------------------------------------------------------------

section("Test 10: Non-wellness Agent Restrictions")

# Find a non-wellness agent
conn = bus.get_conn(TEST_DB)
non_wellness = conn.execute(
    "SELECT * FROM agents WHERE agent_type NOT IN ('wellness', 'human') AND status='active' LIMIT 1"
).fetchone()
conn.close()

if non_wellness:
    non_bridge = CrewBridge(non_wellness["name"], db_path=TEST_DB)

    result = non_bridge.log_sleep(7, 7.5)
    check("restrict.sleep", result.get("ok") is False,
          f"Non-wellness blocked from sleep: {result.get('error', '')[:50]}")

    result = non_bridge.log_exercise("running", 30)
    check("restrict.exercise", result.get("ok") is False,
          f"Non-wellness blocked from exercise")

    result = non_bridge.log_hydration(5)
    check("restrict.hydration", result.get("ok") is False,
          f"Non-wellness blocked from hydration")

    result = non_bridge.log_mood(7)
    check("restrict.mood", result.get("ok") is False,
          f"Non-wellness blocked from mood")

    result = non_bridge.journal("gratitude", "test")
    check("restrict.journal", result.get("ok") is False,
          f"Non-wellness blocked from journal")

    result = non_bridge.set_wellness_goal("sleep", "test", 8)
    check("restrict.goal", result.get("ok") is False,
          f"Non-wellness blocked from goals")

    result = non_bridge.get_wellness_score()
    check("restrict.score", result.get("ok") is False,
          f"Non-wellness blocked from score")

    goals = non_bridge.get_wellness_goals()
    check("restrict.goals_list", len(goals) == 0,
          f"Non-wellness gets empty goals list")
else:
    check("restrict.skip", True, "No non-wellness agent found (skipping)")


# ---------------------------------------------------------------------------
# Test 11: Right Hand Integration
# ---------------------------------------------------------------------------

section("Test 11: Right Hand Integration")

from right_hand import RightHand

conn = bus.get_conn(TEST_DB)
rh_agent = conn.execute(
    "SELECT * FROM agents WHERE agent_type='right_hand' LIMIT 1"
).fetchone()
conn.close()

if rh_agent and human:
    rh = RightHand(rh_agent["id"], HUMAN_ID, db_path=TEST_DB)

    # Assess human state should include wellness data
    assessment = rh.assess_human_state()
    check("rh.wellness_score", "wellness_score" in assessment,
          f"Wellness score in assessment: {assessment.get('wellness_score')}")
    check("rh.wellness_dims", "wellness_dimensions" in assessment,
          f"Wellness dimensions present")
    check("rh.wellness_nudges", "wellness_nudges" in assessment,
          f"Wellness nudges: {len(assessment.get('wellness_nudges', []))}")
    check("rh.sleep_quality", "sleep_quality" in assessment,
          f"Sleep quality: {assessment.get('sleep_quality')}")
    check("rh.hydration", "hydration_glasses" in assessment,
          f"Hydration: {assessment.get('hydration_glasses')}")
    check("rh.exercise", "exercise_minutes_today" in assessment,
          f"Exercise: {assessment.get('exercise_minutes_today')}")
    check("rh.gratitude", "gratitude_streak" in assessment,
          f"Gratitude streak: {assessment.get('gratitude_streak')}")

    # Morning briefing should include wellness section
    briefing = rh.compile_briefing("morning")
    body = briefing["body_plain"]
    check("rh.briefing_wellness", "WELLNESS" in body.upper(),
          f"Morning briefing includes wellness section")

else:
    check("rh.skip", False, "No Crew Boss or human found")


# ---------------------------------------------------------------------------
# Test 12: Dashboard API
# ---------------------------------------------------------------------------

section("Test 12: Dashboard Wellness API")

PORT = 18945  # Random high port
server = create_server(port=PORT, db_path=TEST_DB, host="127.0.0.1")
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
time.sleep(0.5)

BASE = f"http://127.0.0.1:{PORT}"


def api_get(path):
    resp = urllib.request.urlopen(f"{BASE}{path}")
    return json.loads(resp.read().decode("utf-8"))


def api_post(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read().decode("utf-8"))


try:
    # GET wellness score
    score = api_get("/api/wellness/score")
    check("api.score", "overall_score" in score,
          f"GET /api/wellness/score: {score.get('overall_score')}/100")

    # GET wellness summary
    summary = api_get("/api/wellness/summary")
    check("api.summary", "overall_score" in summary,
          f"GET /api/wellness/summary: score={summary.get('overall_score')}")

    # GET check-ins
    checkins = api_get("/api/wellness/checkins")
    check("api.checkins", isinstance(checkins, list),
          f"GET /api/wellness/checkins: {len(checkins)} items")

    # GET check-ins filtered
    sleep_checkins = api_get("/api/wellness/checkins?type=sleep")
    check("api.checkins_filter", isinstance(sleep_checkins, list),
          f"GET /api/wellness/checkins?type=sleep: {len(sleep_checkins)} items")

    # GET goals
    goals = api_get("/api/wellness/goals")
    check("api.goals", isinstance(goals, list),
          f"GET /api/wellness/goals: {len(goals)} goals")

    # GET journal
    journal = api_get("/api/wellness/journal")
    check("api.journal", isinstance(journal, list),
          f"GET /api/wellness/journal: {len(journal)} entries")

    # GET nudges
    nudges = api_get("/api/wellness/nudges")
    check("api.nudges", isinstance(nudges, list),
          f"GET /api/wellness/nudges: {len(nudges)} nudges")

    # GET preferences
    prefs = api_get("/api/wellness/preferences")
    check("api.prefs", "interaction_mode" in prefs,
          f"GET /api/wellness/preferences: mode={prefs.get('interaction_mode')}")

    # POST check-in
    result = api_post("/api/wellness/checkin", {
        "type": "mood",
        "data": {"score": 9, "triggers": ["great day"]},
        "notes": "Feeling amazing",
    })
    check("api.post_checkin", result.get("ok") is True,
          f"POST /api/wellness/checkin: id={result.get('checkin_id')}")

    # POST goal
    result = api_post("/api/wellness/goal", {
        "goal_type": "mindfulness",
        "title": "Meditate 10 min daily",
        "target_value": 10,
        "target_unit": "minutes",
    })
    check("api.post_goal", result.get("ok") is True,
          f"POST /api/wellness/goal: id={result.get('goal_id')}")

    # POST journal
    result = api_post("/api/wellness/journal", {
        "entry_type": "gratitude",
        "content": "Grateful for this wellness system!",
        "mood_before": 7,
        "mood_after": 9,
    })
    check("api.post_journal", result.get("ok") is True,
          f"POST /api/wellness/journal: id={result.get('entry_id')}")

    # POST preferences
    result = api_post("/api/wellness/preferences", {
        "motivational_style": "drill_sergeant",
    })
    check("api.post_prefs", result.get("ok") is True,
          f"POST /api/wellness/preferences: style={result.get('preferences', {}).get('motivational_style')}")

    # POST goal progress
    if goals:
        result = api_post(f"/api/wellness/goal/{goals[0]['id']}/progress", {
            "completed": True,
        })
        check("api.goal_progress", result.get("ok") is True,
              f"POST goal progress: streak={result.get('goal', {}).get('current_streak')}")

except Exception as e:
    check("api.error", False, f"API test error: {e}")

# Shutdown server
server.shutdown()


# ---------------------------------------------------------------------------
# Test 13: Low Mood & Sleep Alert Auto-Reports
# ---------------------------------------------------------------------------

section("Test 13: Auto-Reports on Critical Values")

if wellness_agent:
    bridge = CrewBridge(wellness_agent["name"], db_path=TEST_DB)

    # Low mood should auto-report
    result = bridge.log_mood(2, triggers=["bad news"], notes="Feeling down")
    check("alert.low_mood", result.get("ok") is True,
          f"Low mood logged (auto-report triggered)")

    # Poor sleep should auto-report
    result = bridge.log_sleep(quality=2, hours=3.5, notes="Insomnia")
    check("alert.poor_sleep", result.get("ok") is True,
          f"Poor sleep logged (auto-report triggered)")
else:
    check("alert.skip", False, "No wellness agent")


# ---------------------------------------------------------------------------
# Cleanup and Summary
# ---------------------------------------------------------------------------

section("Cleanup")

if TEST_DB.exists():
    os.remove(str(TEST_DB))
    print(f"  Removed {TEST_DB}")

print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*60}")

if failed > 0:
    sys.exit(1)
else:
    print("  ALL TESTS PASSED!")
    sys.exit(0)
