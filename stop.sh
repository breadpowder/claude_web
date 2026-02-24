#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.claude-web.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Claude Web stopped (PID $PID)"
    else
        echo "Process $PID already stopped"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found. Checking port 8000..."
    if lsof -ti:8000 >/dev/null 2>&1; then
        lsof -ti:8000 | xargs kill -9
        echo "Killed process on port 8000"
    else
        echo "Nothing running on port 8000"
    fi
fi
