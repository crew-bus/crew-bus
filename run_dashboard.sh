#!/usr/bin/env bash
# Start the crew-bus Command Center dashboard
# Usage: ./run_dashboard.sh
# Runs on http://localhost:8420

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
elif [ -f "/c/Python314/python.exe" ]; then
    PYTHON="/c/Python314/python.exe"
elif [ -f "C:\\Python314\\python.exe" ]; then
    PYTHON="C:\\Python314\\python.exe"
fi

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install Python 3.10+ first."
    exit 1
fi

echo "=================================================="
echo "  CREW-BUS COMMAND CENTER"
echo "  Starting on http://localhost:8420"
echo "  Python: $PYTHON"
echo "=================================================="

export PYTHONPATH="$SCRIPT_DIR:$HOME/Lib/site-packages"
exec $PYTHON "$SCRIPT_DIR/dashboard.py"
