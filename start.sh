#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Claude Web — Bootstrap & Start (No Docker)
# Run from repo root: ./start.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

PORT=8000

# ============================================================
# 1. Detect OS
# ============================================================
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_LIKE="${ID_LIKE:-$OS_ID}"
    elif [ "$(uname)" = "Darwin" ]; then
        OS_ID="macos"
        OS_LIKE="macos"
    else
        OS_ID="unknown"
        OS_LIKE="unknown"
    fi
}
detect_os

install_with_pkg_manager() {
    # $1 = package description, rest = install commands per OS
    local desc="$1"
    info "Installing $desc..."
    case "$OS_ID" in
        ubuntu|debian|pop)
            sudo apt-get update -qq && sudo apt-get install -y -qq "$2" ;;
        fedora)
            sudo dnf install -y "$2" ;;
        centos|rhel|amzn|rocky|alma)
            sudo yum install -y "$2" ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm "$2" ;;
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install "$2"
            else
                err "Homebrew not found. Install: https://brew.sh then re-run"
            fi ;;
        *)
            err "Cannot auto-install $desc on $OS_ID. Install manually and re-run." ;;
    esac
}

# ============================================================
# 2. Check & install system prerequisites
# ============================================================
info "Checking prerequisites..."

# --- Python 3.12+ ---
NEED_PYTHON=false
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MINOR" -lt 12 ]; then
        warn "Python $PY_VER found but 3.12+ required"
        NEED_PYTHON=true
    fi
else
    NEED_PYTHON=true
fi

if [ "$NEED_PYTHON" = true ]; then
    case "$OS_ID" in
        ubuntu|debian|pop)
            info "Installing Python 3.12 via deadsnakes PPA..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
            # Point python3 to 3.12 if needed
            if ! python3 -c "import sys; exit(0 if sys.version_info >= (3,12) else 1)" 2>/dev/null; then
                sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
            fi
            ;;
        fedora)
            sudo dnf install -y python3.12 ;;
        centos|rhel|amzn|rocky|alma)
            sudo yum install -y python3.12 || {
                warn "python3.12 not in repos — trying source build"
                sudo yum install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel make
                curl -sL https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tgz | tar xz
                cd Python-3.12.8 && ./configure --enable-optimizations --prefix=/usr/local && make -j"$(nproc)" && sudo make altinstall
                cd "$SCRIPT_DIR" && rm -rf Python-3.12.8
                sudo ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3
            } ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm python ;;
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install python@3.12
            else
                err "Install Homebrew (https://brew.sh) then re-run"
            fi ;;
        *)
            err "Cannot auto-install Python 3.12 on $OS_ID. Install manually: https://www.python.org/downloads/" ;;
    esac
fi

# Verify Python
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
[ "$PY_MINOR" -ge 12 ] || err "Python 3.12+ required (found $PY_VER after install attempt)"
ok "Python $PY_VER"

# --- Node.js 20+ ---
NEED_NODE=false
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 20 ]; then
        warn "Node v$(node -v) found but 20+ required"
        NEED_NODE=true
    fi
else
    NEED_NODE=true
fi

if [ "$NEED_NODE" = true ]; then
    case "$OS_ID" in
        ubuntu|debian|pop|centos|rhel|amzn|rocky|alma|fedora)
            info "Installing Node.js 20 via NodeSource..."
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null || \
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get install -y -qq nodejs
            else
                sudo yum install -y nodejs
            fi ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm nodejs npm ;;
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install node@20
            else
                err "Install Homebrew (https://brew.sh) then re-run"
            fi ;;
        *)
            err "Cannot auto-install Node.js on $OS_ID. Install: https://nodejs.org/" ;;
    esac
fi

# Verify Node
command -v node >/dev/null 2>&1 || err "Node.js installation failed"
NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
[ "$NODE_MAJOR" -ge 20 ] || err "Node 20+ required (found $(node -v) after install attempt)"
ok "Node $(node -v)"

command -v npm >/dev/null 2>&1 || err "npm not found"
ok "npm $(npm -v)"

# --- curl ---
if ! command -v curl >/dev/null 2>&1; then
    install_with_pkg_manager "curl" "curl"
fi

# --- uv (Python package manager) ---
if ! command -v uv >/dev/null 2>&1; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv ready"

# --- Claude Code CLI ---
if ! command -v claude >/dev/null 2>&1; then
    info "Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
fi
ok "Claude Code CLI ready"

# ============================================================
# 2. Ensure config.yaml exists
# ============================================================
if [ ! -f "$SCRIPT_DIR/config.yaml" ]; then
    if [ -f "$SCRIPT_DIR/config.example.yaml" ]; then
        warn "config.yaml not found — copying from config.example.yaml"
        cp "$SCRIPT_DIR/config.example.yaml" "$SCRIPT_DIR/config.yaml"
        echo ""
        echo -e "${YELLOW}>>> Edit config.yaml with your credentials:${NC}"
        echo "    $SCRIPT_DIR/config.yaml"
        echo ""
        echo "    For AWS Bedrock: fill in access_key_id, secret_access_key"
        echo "    For LiteLLM:     set provider: litellm and fill in api_key"
        echo ""
        read -rp "Press Enter after editing config.yaml (or Ctrl+C to abort)..."
    else
        err "Neither config.yaml nor config.example.yaml found"
    fi
fi
ok "config.yaml exists"

# ============================================================
# 3. Ensure .claude/ directory exists (skills + commands)
# ============================================================
CLAUDE_DIR="$SCRIPT_DIR/.claude"
if [ ! -d "$CLAUDE_DIR" ]; then
    if [ -d "$HOME/.claude" ]; then
        info "Symlinking ~/.claude -> $SCRIPT_DIR/.claude for skill discovery"
        ln -sf "$HOME/.claude" "$CLAUDE_DIR"
    else
        warn "No .claude/ directory found — creating empty (no skills loaded)"
        mkdir -p "$CLAUDE_DIR"
    fi
fi
ok "Skills directory: $CLAUDE_DIR"

# ============================================================
# 4. Install Python dependencies
# ============================================================
info "Installing Python dependencies..."
cd "$SCRIPT_DIR"
uv sync --quiet 2>/dev/null || uv sync
ok "Python dependencies installed"

# ============================================================
# 5. Build frontend
# ============================================================
info "Installing frontend dependencies..."
cd "$SCRIPT_DIR/frontend"
npm ci --silent 2>/dev/null || npm ci
ok "Frontend dependencies installed"

info "Building frontend..."
npm run build --silent 2>/dev/null || npm run build
ok "Frontend built -> frontend/dist/"

cd "$SCRIPT_DIR"

# ============================================================
# 6. Kill any existing process on the port
# ============================================================
if lsof -ti:$PORT >/dev/null 2>&1; then
    warn "Port $PORT is in use — stopping existing process"
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# ============================================================
# 7. Start backend (serves frontend as static files)
# ============================================================
info "Starting Claude Web on port $PORT..."

# Prevent nested session error
unset CLAUDECODE 2>/dev/null || true

LOG_FILE="$SCRIPT_DIR/.claude-web.log"
nohup uv run uvicorn src.main:get_app --factory --host 0.0.0.0 --port $PORT > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$SCRIPT_DIR/.claude-web.pid"

# ============================================================
# 8. Wait for healthy startup
# ============================================================
info "Waiting for service to be ready..."
MAX_WAIT=60
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/api/v1/health/live 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        break
    fi
    # Check if process died
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        err "Server process died. Check logs: $LOG_FILE"
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    printf "."
done
echo ""

if [ "$STATUS" != "200" ]; then
    warn "Service did not become healthy within ${MAX_WAIT}s"
    echo "Logs:"
    tail -20 "$LOG_FILE"
    exit 1
fi

# ============================================================
# 9. Show status & open browser
# ============================================================
URL="http://localhost:$PORT"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Claude Web is running!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "  URL:     ${CYAN}${URL}${NC}"
echo -e "  PID:     ${CYAN}${SERVER_PID}${NC}"
echo -e "  Logs:    ${CYAN}${LOG_FILE}${NC}"

# Show extensions count
EXT=$(curl -s "http://localhost:$PORT/api/v1/extensions" 2>/dev/null || echo "")
if [ -n "$EXT" ]; then
    SKILLS=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('total_count',0))" <<< "$EXT" 2>/dev/null || echo "?")
    echo -e "  Skills:  ${CYAN}${SKILLS} slash commands loaded${NC}"
fi

echo ""
echo -e "  Stop:    ${YELLOW}kill \$(cat $SCRIPT_DIR/.claude-web.pid)${NC}"
echo -e "           ${YELLOW}or: ./stop.sh${NC}"
echo ""

# Open browser
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" 2>/dev/null &
elif command -v open >/dev/null 2>&1; then
    open "$URL" 2>/dev/null &
else
    info "Open your browser to: $URL"
fi
