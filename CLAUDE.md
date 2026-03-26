# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Supervisor-based process manager for local development services on macOS. A single launchd agent boots `supervisord` at login; it in turn manages all services defined in `conf.d/`.

## Setup

```bash
./install.sh
```

This is the only setup command. It generates the launchd plist, adds a `supervisorctl` alias to the shell rc, and generates all `conf.d/*.conf` files from templates. Re-run it to add new services or after cloning on a new machine.

## Architecture

### How services are defined

Each service requires two committed files in `conf.d/`:

- `<name>.conf.template` — Supervisor `[program:...]` config with `{{VARNAME}}` placeholders
- `<name>.conf.vars` — one line per user-supplied variable: `VARNAME|Prompt|/default/path`

`install.sh` loops over all `*.conf.template` files and generates the corresponding `*.conf`. The generated `.conf` files and the launchd `.plist` are gitignored (they contain absolute local paths).

Two placeholders are always auto-resolved without a `.vars` entry:
- `{{UV_BIN}}` — path to the `uv` binary
- `{{REPO_DIR}}` — path to this repo

### supervisord.conf

Minimal daemon config. The key line is:

```ini
[include]
files = conf.d/*.conf
```

This means any `.conf` dropped into `conf.d/` is automatically picked up by Supervisor — no changes to `supervisord.conf` needed when adding services.

### menubar/app.py

A Python + [rumps](https://github.com/jaredks/rumps) macOS menu bar app. Talks to supervisord via XML-RPC over the Unix socket using a custom stdlib transport (`xmlrpc.client` + `http.client` + `socket.AF_UNIX`) — no additional deps beyond `rumps`. Polls every 5 seconds via `@rumps.timer`.

**Important: requires a Homebrew framework Python** — uv's managed Python is not linked against `Python.framework`, so macOS silently refuses to register a menu bar icon. `install.sh` auto-detects a suitable Homebrew Python (`otool -L` check for `Python.framework`). Run manually with:

```bash
uv run --python /opt/homebrew/bin/python3 menubar/app.py
```

Or use the detached launcher (survives terminal close):

```bash
menubar/start.sh
```

### /Applications/LocalServices.app

`install.sh` generates a minimal `.app` bundle at `/Applications/LocalServices.app`. Double-clicking it launches the menu bar app. The bundle's launch script uses `exec uv run --python <BREW_PYTHON> menubar/app.py` — the command must be inlined directly; macOS blocks `exec` of external scripts from `.app` bundles ("Operation not permitted").

The app includes a **Launch at Login** menu item that toggles a launchd plist at `~/Library/LaunchAgents/com.local-services.menubar.plist`. A PID-file lock (`~/.supervisor/menubar.pid`) prevents duplicate instances — stale PIDs from crashed processes are auto-detected and overwritten.

### Adding a new service

1. Add `conf.d/myservice.conf.template` and `conf.d/myservice.conf.vars`
2. Re-run `./install.sh` (or generate the `.conf` manually)
3. Run `supervisorctl reread && supervisorctl update`
