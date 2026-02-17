#!/bin/bash
# Post-write hook: run pytest after any Python file is edited/written.
# Configured in .claude/settings.json under hooks.PostToolUse.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.file_path // empty')

# Only run tests when a Python file was touched
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

RESULT=$(python -m pytest --tb=short -q 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "{\"systemMessage\": \"pytest passed after editing $FILE_PATH\"}"
else
  # Truncate output to keep it readable
  SHORT=$(echo "$RESULT" | tail -20)
  echo "{\"systemMessage\": \"pytest FAILED after editing $FILE_PATH:\\n$SHORT\"}"
fi

exit 0
