"""
Stress test for agent-to-agent communication.
Tests high-volume messaging, concurrent delivery, routing enforcement,
inbox performance, and message lifecycle under load.
"""
import os
import time
import threading
import sqlite3
import bus

TEST_DB = "test_stress_messaging.db"


def setup():
    """Create fresh DB with agents for stress testing."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    bus.init_db(TEST_DB)
    conn = bus.get_conn(TEST_DB)

    agents = {}
    # Create human
    conn.execute(
        "INSERT INTO agents (name, agent_type, status, active) VALUES (?, ?, 'active', 1)",
        ("Human", "human"),
    )
    agents["human"] = conn.execute("SELECT * FROM agents WHERE name='Human'").fetchone()

    # Create crew boss (right_hand)
    conn.execute(
        "INSERT INTO agents (name, agent_type, status, active) VALUES (?, ?, 'active', 1)",
        ("CrewBoss", "right_hand"),
    )
    agents["boss"] = conn.execute("SELECT * FROM agents WHERE name='CrewBoss'").fetchone()

    # Create 10 worker agents
    for i in range(10):
        name = f"Worker-{i}"
        conn.execute(
            "INSERT INTO agents (name, agent_type, status, active) VALUES (?, ?, 'active', 1)",
            (name, "worker"),
        )
        agents[f"worker_{i}"] = conn.execute(
            "SELECT * FROM agents WHERE name=?", (name,)
        ).fetchone()

    conn.commit()
    conn.close()
    return agents


def teardown():
    bus.close_thread_connections()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ── Test 1: High-volume single-sender burst ──────────────────────────

def test_burst_100_messages():
    """Send 100 messages from one agent to another as fast as possible."""
    agents = setup()
    sender = agents["worker_0"]
    receiver = agents["worker_1"]

    start = time.time()
    message_ids = []
    for i in range(100):
        msg = bus.send_message(
            sender["id"], receiver["id"],
            message_type="report",
            subject=f"Burst message #{i}",
            body=f"Body of message {i}",
            priority="normal",
            db_path=TEST_DB,
        )
        message_ids.append(msg["message_id"])
    elapsed = time.time() - start

    # Verify all 100 delivered
    assert len(message_ids) == 100
    assert len(set(message_ids)) == 100  # all unique IDs

    # Check inbox
    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    assert len(inbox) == 100

    print(f"  PASS: 100 messages sent in {elapsed:.3f}s ({100/elapsed:.0f} msg/s)")
    teardown()


# ── Test 2: Fan-out — one sender to many receivers ───────────────────

def test_fanout_10_receivers():
    """One agent sends to 10 different agents."""
    agents = setup()
    sender = agents["boss"]

    start = time.time()
    for i in range(10):
        for j in range(10):
            bus.send_message(
                sender["id"], agents[f"worker_{i}"]["id"],
                message_type="task",
                subject=f"Task #{j} for worker {i}",
                body="Do the thing",
                db_path=TEST_DB,
            )
    elapsed = time.time() - start

    # Each worker should have 10 messages
    for i in range(10):
        inbox = bus.read_inbox(agents[f"worker_{i}"]["id"], db_path=TEST_DB)
        assert len(inbox) == 10, f"Worker {i} has {len(inbox)} messages, expected 10"

    print(f"  PASS: 100 fan-out messages in {elapsed:.3f}s ({100/elapsed:.0f} msg/s)")
    teardown()


# ── Test 3: Fan-in — many senders to one receiver ────────────────────

def test_fanin_10_senders():
    """10 agents all send to one agent."""
    agents = setup()
    receiver = agents["boss"]

    start = time.time()
    for i in range(10):
        for j in range(10):
            bus.send_message(
                agents[f"worker_{i}"]["id"], receiver["id"],
                message_type="report",
                subject=f"Report #{j} from worker {i}",
                body="Status update",
                db_path=TEST_DB,
            )
    elapsed = time.time() - start

    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    assert len(inbox) == 100, f"Boss has {len(inbox)} messages, expected 100"

    print(f"  PASS: 100 fan-in messages in {elapsed:.3f}s ({100/elapsed:.0f} msg/s)")
    teardown()


# ── Test 4: Concurrent senders (threaded) ────────────────────────────

def test_concurrent_senders():
    """10 threads each send 50 messages simultaneously."""
    agents = setup()
    receiver = agents["boss"]
    errors = []
    counts = []

    def sender_thread(worker_key, count):
        try:
            sent = 0
            for j in range(count):
                bus.send_message(
                    agents[worker_key]["id"], receiver["id"],
                    message_type="report",
                    subject=f"Concurrent msg #{j}",
                    body=f"From {worker_key}",
                    db_path=TEST_DB,
                )
                sent += 1
            counts.append(sent)
        except Exception as e:
            errors.append(f"{worker_key}: {e}")

    start = time.time()
    threads = []
    for i in range(10):
        t = threading.Thread(target=sender_thread, args=(f"worker_{i}", 50))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=30)
    elapsed = time.time() - start

    total_sent = sum(counts)
    assert not errors, f"Errors: {errors}"

    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    assert len(inbox) == 500, f"Expected 500 messages, got {len(inbox)}"

    print(f"  PASS: 500 concurrent messages in {elapsed:.3f}s ({500/elapsed:.0f} msg/s)")
    teardown()


# ── Test 5: Message lifecycle under load ─────────────────────────────

def test_message_lifecycle_bulk():
    """Send 200 messages, then mark all delivered, then all read."""
    agents = setup()
    sender = agents["worker_0"]
    receiver = agents["worker_1"]

    # Send 200
    msg_ids = []
    for i in range(200):
        msg = bus.send_message(
            sender["id"], receiver["id"],
            message_type="report",
            subject=f"Lifecycle msg #{i}",
            db_path=TEST_DB,
        )
        msg_ids.append(msg["message_id"])

    # All should be queued
    inbox = bus.read_inbox(receiver["id"], status_filter="queued", db_path=TEST_DB)
    assert len(inbox) == 200

    # Mark all delivered
    start = time.time()
    for mid in msg_ids:
        bus.mark_delivered(mid, db_path=TEST_DB)
    deliver_time = time.time() - start

    delivered = bus.read_inbox(receiver["id"], status_filter="delivered", db_path=TEST_DB)
    assert len(delivered) == 200

    # Mark all read
    start = time.time()
    for mid in msg_ids:
        bus.mark_read(mid, db_path=TEST_DB)
    read_time = time.time() - start

    read_msgs = bus.read_inbox(receiver["id"], status_filter="read", db_path=TEST_DB)
    assert len(read_msgs) == 200

    print(f"  PASS: 200 msg lifecycle — deliver: {deliver_time:.3f}s, read: {read_time:.3f}s")
    teardown()


# ── Test 6: All message types and priorities ─────────────────────────

def test_all_types_and_priorities():
    """Send every combination of message_type x priority."""
    agents = setup()
    types = ["report", "task", "alert", "escalation", "idea", "briefing"]
    priorities = ["low", "normal", "high", "critical"]
    sender = agents["worker_0"]
    receiver = agents["worker_1"]

    count = 0
    for mt in types:
        for p in priorities:
            msg = bus.send_message(
                sender["id"], receiver["id"],
                message_type=mt,
                subject=f"{mt}/{p}",
                body="test",
                priority=p,
                db_path=TEST_DB,
            )
            assert msg["message_id"] > 0
            count += 1

    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    assert len(inbox) == count == 24

    print(f"  PASS: All {count} type/priority combos sent and received")
    teardown()


# ── Test 7: Routing enforcement under load ───────────────────────────

def test_routing_blocked_agents():
    """Verify deactivated/paused agents can't send or receive."""
    agents = setup()
    conn = bus.get_conn(TEST_DB)

    # Deactivate worker_5
    conn.execute("UPDATE agents SET active=0 WHERE id=?", (agents["worker_5"]["id"],))
    conn.commit()
    conn.close()

    blocked_sends = 0
    blocked_receives = 0

    # Try sending FROM deactivated agent
    for i in range(10):
        try:
            bus.send_message(
                agents["worker_5"]["id"], agents["worker_0"]["id"],
                message_type="report",
                subject=f"From deactivated #{i}",
                db_path=TEST_DB,
            )
        except (PermissionError, ValueError):
            blocked_sends += 1

    # Try sending TO deactivated agent
    for i in range(10):
        try:
            bus.send_message(
                agents["worker_0"]["id"], agents["worker_5"]["id"],
                message_type="report",
                subject=f"To deactivated #{i}",
                db_path=TEST_DB,
            )
        except (PermissionError, ValueError):
            blocked_receives += 1

    assert blocked_sends == 10, f"Expected 10 blocked sends, got {blocked_sends}"
    assert blocked_receives == 10, f"Expected 10 blocked receives, got {blocked_receives}"

    print(f"  PASS: All 20 blocked messages correctly rejected")
    teardown()


# ── Test 8: Large message bodies ─────────────────────────────────────

def test_large_message_bodies():
    """Send messages with large bodies (10KB each) x 50."""
    agents = setup()
    sender = agents["worker_0"]
    receiver = agents["worker_1"]
    large_body = "x" * 10_000  # 10KB

    start = time.time()
    for i in range(50):
        bus.send_message(
            sender["id"], receiver["id"],
            message_type="report",
            subject=f"Large msg #{i}",
            body=large_body,
            db_path=TEST_DB,
        )
    elapsed = time.time() - start

    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    assert len(inbox) == 50
    assert len(inbox[0]["body"]) == 10_000

    print(f"  PASS: 50 x 10KB messages in {elapsed:.3f}s ({50/elapsed:.0f} msg/s)")
    teardown()


# ── Test 9: Inbox query performance ──────────────────────────────────

def test_inbox_query_performance():
    """Fill inbox with 1000 messages, measure query time."""
    agents = setup()
    sender = agents["worker_0"]
    receiver = agents["worker_1"]

    # Bulk insert 1000 messages directly for speed
    conn = bus.get_conn(TEST_DB)
    for i in range(1000):
        conn.execute(
            """INSERT INTO messages (from_agent_id, to_agent_id, message_type, subject, body, priority, status)
               VALUES (?, ?, 'report', ?, '', 'normal', 'queued')""",
            (sender["id"], receiver["id"], f"Perf msg #{i}"),
        )
    conn.commit()
    conn.close()

    # Time inbox query
    start = time.time()
    inbox = bus.read_inbox(receiver["id"], db_path=TEST_DB)
    elapsed = time.time() - start

    assert len(inbox) == 1000
    print(f"  PASS: 1000-message inbox queried in {elapsed:.4f}s")
    teardown()


# ── Test 10: Private session stress ──────────────────────────────────

def test_private_session_rapid_messages():
    """Start a private session and send 100 messages rapidly."""
    agents = setup()
    human = agents["human"]
    agent = agents["boss"]

    session = bus.start_private_session(
        human["id"], agent["id"], db_path=TEST_DB
    )
    session_id = session["session_id"]

    start = time.time()
    msg_ids = []
    for i in range(100):
        result = bus.send_private_message(
            session_id, human["id"],
            f"Private message #{i}",
            db_path=TEST_DB,
        )
        assert result["ok"], f"Private msg #{i} failed: {result.get('error')}"
        msg_ids.append(result["message_id"])
    elapsed = time.time() - start

    assert len(msg_ids) == 100
    assert len(set(msg_ids)) == 100

    # Verify session message count updated
    sess = bus.get_active_private_session(human["id"], agent["id"], db_path=TEST_DB)
    assert sess["message_count"] == 100

    print(f"  PASS: 100 private messages in {elapsed:.3f}s ({100/elapsed:.0f} msg/s)")
    teardown()


# ── Runner ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("Burst 100 messages (single sender)", test_burst_100_messages),
        ("Fan-out: 1 sender → 10 receivers", test_fanout_10_receivers),
        ("Fan-in: 10 senders → 1 receiver", test_fanin_10_senders),
        ("Concurrent: 10 threads × 50 messages", test_concurrent_senders),
        ("Message lifecycle (200 msgs)", test_message_lifecycle_bulk),
        ("All type/priority combos (24)", test_all_types_and_priorities),
        ("Routing blocks deactivated agents", test_routing_blocked_agents),
        ("Large bodies (50 × 10KB)", test_large_message_bodies),
        ("Inbox query (1000 messages)", test_inbox_query_performance),
        ("Private session rapid (100 msgs)", test_private_session_rapid_messages),
    ]

    print("=" * 60)
    print("CREW BUS — Agent Messaging Stress Test")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"\n▶ {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1
            teardown()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 60)
