#!/usr/bin/env bash
# Crew Bus — one-command installer
# Usage: curl -sL <raw-github-url>/install.sh | bash
set -e

echo ""
echo "  ✨ Crew Bus Installer"
echo "  ====================="
echo ""

# ── 1. Detect OS ──
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)
        echo "  ❌ Unsupported OS: $OS"
        echo "  Crew Bus supports macOS and Linux."
        exit 1
        ;;
esac
echo "  Platform: $PLATFORM"

# ── 2. Check Python 3.10+ ──
PYTHON=""
for cmd in python3 python python3.13 python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ❌ Python 3.10+ is required but not found."
    echo "  Install it from https://python.org or via your package manager."
    exit 1
fi
echo "  Python:   $($PYTHON --version)"

# ── 3. Clone or use current dir ──
INSTALL_DIR="$HOME/crew-bus"
if [ -f "bus.py" ] && [ -f "dashboard.py" ]; then
    INSTALL_DIR="$(pwd)"
    echo "  Repo:     using current directory"
elif [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Repo:     $INSTALL_DIR (already cloned)"
    cd "$INSTALL_DIR"
else
    echo "  Cloning to $INSTALL_DIR ..."
    git clone https://github.com/crew-bus/crew-bus.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 4. Create venv & install deps ──
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    $PYTHON -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  Installing dependencies..."
pip install -q -r requirements.txt

# ── 5. Install Ollama (local LLM) ──
if command -v ollama &>/dev/null; then
    echo "  Ollama:   already installed"
else
    echo "  Installing Ollama (local LLM)..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# ── 6. Pull default model based on available RAM ──
RAM_GB=0
if [ "$PLATFORM" = "macos" ]; then
    RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    RAM_GB=$((RAM_BYTES / 1073741824))
elif [ "$PLATFORM" = "linux" ]; then
    RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
    RAM_GB=$((RAM_KB / 1048576))
fi

MODEL="llama3.2"
if [ "$RAM_GB" -lt 6 ] && [ "$RAM_GB" -gt 0 ]; then
    MODEL="tinyllama"
    echo "  RAM:      ${RAM_GB}GB — using lightweight model ($MODEL)"
else
    echo "  RAM:      ${RAM_GB}GB — using default model ($MODEL)"
fi

# Check if model already pulled
if ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "  Model:    $MODEL (already downloaded)"
else
    echo "  Pulling $MODEL... (this may take a few minutes on first run)"
    ollama pull "$MODEL"
fi

# ── 7. Start Ollama if not running ──
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    echo "  Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 2
fi

# ── 8. Launch! ──
echo ""
echo "  ✅ Crew Bus installed successfully!"
echo "  Starting dashboard..."
echo ""
$PYTHON dashboard.py
