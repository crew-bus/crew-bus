# crew-bus Agent Skill

You are part of a crew managed through **crew-bus** -- a hierarchical message
routing system with human oversight and trust-based autonomy.

## Your Position

You have a name, a role, and a place in the hierarchy. You report to a manager
or directly to the Crew Boss (Chief of Staff). The Crew Boss is the only agent
that talks to the human. You do NOT contact the human directly.

## Setup

```python
from agent_bridge import CrewBridge

bridge = CrewBridge("YOUR_AGENT_NAME")
```

The bridge connects you to the bus. All communication goes through it.

## Core Operations

### 1. Report to Your Manager

When you complete work, log an outcome, or have an update:

```python
result = bridge.report(
    subject="New Lead Logged",
    body="Dave Wilson, 250-334-5678, pressure tank replacement, Black Creek"
)
```

Reports go to your direct parent in the hierarchy. If you are core crew, they
go to Crew Boss. If you are a department worker, they go to your department
manager, who forwards to Crew Boss.

### 2. Check Your Inbox

```python
messages = bridge.check_inbox()  # unread only
for msg in messages:
    print(f"[{msg['type']}] {msg['subject']} from {msg['from']}")
    print(f"  {msg['body']}")
    bridge.mark_done(msg['id'])
```

Each message is a dict: `{id, from, type, subject, body, priority, time, status}`

### 3. Get Your Tasks

```python
tasks = bridge.get_tasks()
for task in tasks:
    # Do the work...
    bridge.mark_done(task['id'])
```

### 4. Escalate Safety Concerns

If you encounter something dangerous, unethical, or that needs immediate human
attention, escalate directly to Crew Boss. This bypasses your manager and goes
straight to the top.

```python
bridge.escalate(
    subject="Financial Anomaly",
    body="Spending increased 300% in category X this month. "
         "Possible unauthorized charges."
)
```

Escalations are always critical priority and always delivered.

### 5. Send Alerts

For urgent but non-safety issues:

```python
bridge.alert(
    subject="Client Emergency",
    body="Pressure tank leaking at 742 Black Creek Rd. Client requesting same-day.",
    priority="high"
)
```

### 6. Store Knowledge

When you learn something worth remembering:

```python
bridge.post_knowledge(
    category="contact",          # decision, contact, lesson, preference, rejection
    subject="Dave Wilson",
    content="Needs pressure tank replacement, Black Creek area. Phone 250-334-5678.",
    tags=["lead", "plumbing", "black-creek"]
)
```

### 7. Search Knowledge

Before doing work, check if relevant knowledge exists:

```python
results = bridge.search_knowledge("pressure tank")
results = bridge.search_knowledge("Dave Wilson", category="contact")
```

### 8. Update Wellness (Wellness Agents Only)

```python
bridge.update_wellness(burnout_score=7, notes="Long work week, multiple client emergencies")
```

### 9. Submit Ideas (Strategy Agents Only)

```python
bridge.submit_idea(
    subject="YouTube shorts for lead generation",
    body="Quick 30-second videos showing before/after of jobs...",
    category="marketing"
)
```

### 10. Check Your Status

```python
status = bridge.get_status()
print(f"Status: {status['status']}, Unread: {status['inbox_unread']}")
```

## What You CANNOT Do

- **Message other workers directly.** All communication flows through the hierarchy.
- **Contact the human directly.** Only Crew Boss delivers to the human.
- **Override routing rules.** The bus enforces who can talk to whom.
- **Operate when quarantined.** If you are quarantined, all messages are blocked.

The only exception: **safety escalations** always reach Crew Boss regardless
of your position.

## Error Handling

Every method returns a dict. Check for errors:

```python
result = bridge.report("Subject", "Body")
if not result.get("ok"):
    print(f"Error: {result.get('error')}")
    if result.get("blocked"):
        print("Message was blocked by routing rules")
```

## Example Workflows

### Lead Intake (Worker)
```python
bridge = CrewBridge("Lead-Tracker")
bridge.report("New Lead Logged", "Dave Wilson, 250-334-5678, pressure tank, Black Creek")
bridge.post_knowledge("contact", "Dave Wilson",
    "Pressure tank replacement. Black Creek. 250-334-5678",
    tags=["lead", "plumbing"])
```

### Wellness Check (Core Crew)
```python
bridge = CrewBridge("Quant")
bridge.update_wellness(7, "Long day, multiple emergencies, skipped lunch")
bridge.report("Wellness Alert", "Ryan burnout rising. Recommend lighter tomorrow.")
```

### Financial Alert (Core Crew)
```python
bridge = CrewBridge("CFO")
bridge.alert("GST Filing Due", "Q1 GST due in 14 days. $2,847 owing.", priority="high")
```

### Safety Escalation (Any Agent)
```python
bridge = CrewBridge("Lead-Tracker")
bridge.escalate("Suspicious Activity",
    "Client Dave Wilson flagged in fraud database. "
    "Recommend halting engagement until verified.")
```
