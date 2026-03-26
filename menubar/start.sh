#!/usr/bin/env bash
# Launch the menu bar app detached from the terminal.
# Closing this terminal window will NOT kill the app.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BREW_PYTHON=""
for candidate in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3; do
  if [ -x "$candidate" ] && otool -L "$candidate" 2>/dev/null | grep -q "Python.framework"; then
    BREW_PYTHON="$candidate"
    break
  fi
done

if [ -z "$BREW_PYTHON" ]; then
  echo "Error: no Homebrew framework Python found."
  exit 1
fi

LOG="$HOME/Library/Logs/supervisor/menubar.log"
nohup uv run --python "$BREW_PYTHON" "$REPO_DIR/menubar/app.py" >> "$LOG" 2>&1 &
disown
echo "LocalServices started. Logs: $LOG"
