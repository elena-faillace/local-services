#!/usr/bin/env bash
# Sets up Supervisor as a launchd service.
# Run once after cloning this repo.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_LABEL="com.local-services"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# 1. Require Supervisor to be installed
if ! command -v supervisord &>/dev/null; then
  echo "Error: supervisord not found. Install it first: brew install supervisor"
  exit 1
fi

SUPERVISORD_BIN="$(command -v supervisord)"

# 2. Create log directory
mkdir -p "$HOME/Library/Logs/supervisor"
echo "Created log directory: $HOME/Library/Logs/supervisor"

# 3. Generate the launchd plist with real paths
cat > "$PLIST_DEST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SUPERVISORD_BIN</string>
    <string>-c</string>
    <string>$REPO_DIR/supervisord.conf</string>
    <string>-n</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/supervisor/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/supervisor/launchd.error.log</string>
</dict>
</plist>
EOF
echo "Generated plist: $PLIST_DEST"

# 4. Load (or reload) the launchd agent
if launchctl list | grep -q "$PLIST_LABEL"; then
  launchctl unload "$PLIST_DEST"
fi
launchctl load "$PLIST_DEST"
echo "Loaded launchd agent: $PLIST_LABEL"

echo ""
echo "Done. Check service status with: supervisorctl status"
