#!/usr/bin/env npx tsx
/**
 * Crew Bus Code Reviewer
 * Uses @anthropic-ai/claude-agent-sdk to review a file or directory.
 *
 * Usage:
 *   npx tsx review.ts [path]          # review a file or directory
 *   npx tsx review.ts                 # reviews the parent crew-bus repo
 */

import { query } from "@anthropic-ai/claude-agent-sdk";
import { appendFile } from "fs/promises";
import { resolve, dirname } from "path";
import { statSync } from "fs";

const target = resolve(process.argv[2] ?? "..");
const isFile = statSync(target).isFile();
const cwd = isFile ? dirname(target) : target;
const auditLog = "./review-audit.log";

// ── Prompt ────────────────────────────────────────────────────────────────────

const PROMPT = `
You are a senior code reviewer. Thoroughly review the code at: ${target}

Focus on:
1. **Bugs** — logic errors, off-by-ones, race conditions, unhandled exceptions
2. **Security** — SQL injection, command injection, hardcoded secrets, path traversal
3. **Performance** — N+1 queries, unnecessary re-renders, blocking I/O
4. **Code quality** — dead code, naming, duplicated logic, missing error handling

Output a structured report:

## Summary
One paragraph overview.

## Critical Issues  (must fix)
- File:line — description + fix

## Warnings  (should fix)
- File:line — description + suggestion

## Suggestions  (nice to have)
- File:line — description

## Verdict
PASS / NEEDS WORK / FAIL with one sentence rationale.
`.trim();

// ── Hooks ─────────────────────────────────────────────────────────────────────

async function logToolUse(input: unknown): Promise<Record<string, unknown>> {
  const toolInput = (input as any)?.tool_input ?? {};
  const toolName = (input as any)?.tool_name ?? "unknown";
  const detail =
    toolInput.file_path ?? toolInput.pattern ?? toolInput.query ?? toolInput.command ?? "";
  const line = `${new Date().toISOString()} [${toolName}] ${detail}\n`;
  await appendFile(auditLog, line).catch(() => {});
  return {};
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log(`\nCrew Bus Code Reviewer`);
  console.log(`Target: ${target}\n`);
  console.log("─".repeat(60));

  let turnCount = 0;

  for await (const message of query({
    prompt: PROMPT,
    options: {
      cwd,
      allowedTools: ["Read", "Glob", "Grep", "Bash"],
      permissionMode: "bypassPermissions",
      maxTurns: 30,
      hooks: {
        PostToolUse: [
          {
            matcher: "Read|Glob|Grep|Bash",
            hooks: [logToolUse],
          },
        ],
      },
    },
  })) {
    if ((message as any).type === "system" && (message as any).subtype === "init") {
      console.log(`Session: ${(message as any).session_id}\n`);
    } else if ("result" in message) {
      console.log("\n" + "─".repeat(60));
      console.log(message.result);
      console.log("─".repeat(60));
      console.log(`\nTurns used: ${turnCount}`);
      console.log(`Audit log:  ${auditLog}`);
    } else if ((message as any).type === "assistant") {
      turnCount++;
      // Print a dot per turn so the user knows it's alive
      process.stdout.write(".");
    }
  }
}

main().catch((err) => {
  console.error("\nError:", err.message);
  process.exit(1);
});
