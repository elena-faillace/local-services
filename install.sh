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

# 2. Require uv to be installed
if ! command -v uv &>/dev/null; then
  echo "Error: uv not found. Install it first: brew install uv"
  exit 1
fi
UV_BIN="$(command -v uv)"

# 2a. Find a Homebrew framework Python (required for macOS GUI / menu bar apps)
BREW_PYTHON=""
for candidate in \
  /opt/homebrew/bin/python3.13 \
  /opt/homebrew/bin/python3.12 \
  /opt/homebrew/bin/python3; do
  if [ -x "$candidate" ]; then
    if otool -L "$candidate" 2>/dev/null | grep -q "Python.framework"; then
      BREW_PYTHON="$candidate"
      break
    fi
  fi
done
if [ -z "$BREW_PYTHON" ]; then
  echo "Error: no Homebrew framework Python found."
  echo "Install one with: brew install python@3.12"
  exit 1
fi
echo "Using framework Python: $BREW_PYTHON"

# 3. Create required directories
mkdir -p "$HOME/Library/Logs/supervisor"
mkdir -p "$HOME/.supervisor"
echo "Created log and socket directories"

# 4. Generate the launchd plist with real paths
mkdir -p "$HOME/Library/LaunchAgents"
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

# 5. Load (or reload) the launchd agent
GUI_TARGET="gui/$(id -u)"
if launchctl print "$GUI_TARGET/$PLIST_LABEL" &>/dev/null 2>&1; then
  launchctl bootout "$GUI_TARGET" "$PLIST_DEST"
fi
launchctl bootstrap "$GUI_TARGET" "$PLIST_DEST"
echo "Loaded launchd agent: $PLIST_LABEL"

# 6. Add supervisorctl alias to shell rc file
ALIAS_LINE="alias supervisorctl='supervisorctl -c $REPO_DIR/supervisord.conf'"
case "$SHELL" in
  */zsh)  RC_FILE="$HOME/.zshrc" ;;
  */bash) RC_FILE="$HOME/.bash_profile" ;;
  *)      RC_FILE="" ;;
esac

if [ -n "$RC_FILE" ] && ! grep -qF "$ALIAS_LINE" "$RC_FILE" 2>/dev/null; then
  printf '\n# local-services\n%s\n' "$ALIAS_LINE" >> "$RC_FILE"
  echo "Added supervisorctl alias to $RC_FILE"
  echo "Run: source $RC_FILE"
elif [ -n "$RC_FILE" ]; then
  echo "supervisorctl alias already present in $RC_FILE"
else
  echo "Unknown shell. Add this alias manually:"
  echo "  $ALIAS_LINE"
fi

# 7. Generate conf.d files from templates
for TEMPLATE in "$REPO_DIR/conf.d/"*.conf.template; do
  BASENAME="$(basename "$TEMPLATE" .conf.template)"
  VARS_FILE="$REPO_DIR/conf.d/$BASENAME.conf.vars"
  OUT="$REPO_DIR/conf.d/$BASENAME.conf"

  echo ""
  echo "Configuring $BASENAME..."

  # Start sed args with system-resolved variables
  SED_ARGS=(-e "s|{{UV_BIN}}|$UV_BIN|g" -e "s|{{REPO_DIR}}|$REPO_DIR|g")

  # Prompt for each user variable defined in the .vars file
  if [ -f "$VARS_FILE" ]; then
    while IFS='|' read -r VARNAME PROMPT DEFAULT; do
      # Expand $HOME in default value
      DEFAULT="${DEFAULT/\$HOME/$HOME}"
      echo "$PROMPT"
      echo "Press Enter to accept the default: $DEFAULT"
      read -r -p "$VARNAME: " VALUE </dev/tty
      VALUE="${VALUE:-$DEFAULT}"
      if [ ! -d "$VALUE" ]; then
        echo "Error: directory not found: $VALUE"
        echo "Supervisor is running but $BASENAME is not configured."
        echo "Re-run this script once the repo is cloned to finish setup."
        exit 1
      fi
      SED_ARGS+=(-e "s|{{$VARNAME}}|$VALUE|g")
    done < "$VARS_FILE"
  fi

  sed "${SED_ARGS[@]}" "$TEMPLATE" > "$OUT"
  echo "Generated conf.d/$BASENAME.conf"
done

# 8. Generate LocalServices.app in /Applications
APP_BUNDLE="/Applications/LocalServices.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cp "$REPO_DIR/menubar/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"

cat > "$APP_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>LocalServices</string>
  <key>CFBundleIdentifier</key>
  <string>com.local-services.menubar</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
EOF

cat > "$APP_BUNDLE/Contents/MacOS/launch" <<EOF
#!/usr/bin/env bash
exec "$UV_BIN" run --python "$BREW_PYTHON" "$REPO_DIR/menubar/app.py"
EOF
chmod +x "$APP_BUNDLE/Contents/MacOS/launch"
echo "Created /Applications/LocalServices.app"

# 9. Optionally launch menu bar app at login
MENUBAR_PLIST_LABEL="com.local-services.menubar"
MENUBAR_PLIST_DEST="$HOME/Library/LaunchAgents/$MENUBAR_PLIST_LABEL.plist"

echo ""
read -r -p "Launch the menu bar app automatically at login? [y/N] " AUTOLAUNCH
if [[ "$AUTOLAUNCH" =~ ^[Yy]$ ]]; then
  cat > "$MENUBAR_PLIST_DEST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$MENUBAR_PLIST_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UV_BIN</string>
    <string>run</string>
    <string>--python</string>
    <string>$BREW_PYTHON</string>
    <string>$REPO_DIR/menubar/app.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/supervisor/menubar.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/supervisor/menubar.error.log</string>
</dict>
</plist>
EOF
  GUI_TARGET="gui/$(id -u)"
  if launchctl print "$GUI_TARGET/$MENUBAR_PLIST_LABEL" &>/dev/null 2>&1; then
    launchctl bootout "$GUI_TARGET" "$MENUBAR_PLIST_DEST"
  fi
  launchctl bootstrap "$GUI_TARGET" "$MENUBAR_PLIST_DEST"
  echo "Menu bar app will launch at login."
fi

echo ""
echo "Done. Check service status with: supervisorctl status"
