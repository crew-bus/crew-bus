# Anthropic Connectors Directory — Submission Notes

## Status: NOT YET SUBMITTED
CrewBus is a local-first Mac app. The Anthropic Connectors Directory currently requires remote MCP servers with OAuth. We distribute via MCPB bundle instead.

## If Anthropic opens directory to local extensions:

### 3 Required Usage Examples

**Example 1: Team Overview**
Prompt: "Who's on my crew and what are they working on?"
Expected: Lists all agents (Crew Boss, Guardian, Vault) with their status, then shows recent message feed.
Tools used: crewbus_list_agents, crewbus_get_message_feed

**Example 2: Agent Communication**
Prompt: "Send a message to Crew Boss asking him to plan my week based on what Vault knows about my priorities."
Expected: Searches Vault's memory for priorities, sends a message to Crew Boss with context, returns Crew Boss's plan.
Tools used: crewbus_search_agent_memory, crewbus_send_message

**Example 3: Security Review**
Prompt: "What has Guardian flagged recently? Show me the audit log for the last 24 hours."
Expected: Gets Guardian's learnings and recent audit log entries, summarizes any security events or flagged items.
Tools used: crewbus_get_agent_learnings, crewbus_get_audit_log

### Privacy Policy
URL: https://crew-bus.dev/privacy
(Ensure this exists and covers: data stays local, no cloud transmission, what MCP exposes)

### Support Channel
GitHub Issues: https://github.com/crew-bus/crew-bus/issues
