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

A Python + [rumps](https://github.com/jaredks/rumps) macOS menu bar app. Talks to supervisord via XML-RPC over the Unix socket using a custom stdlib transport (`xmlrpc.client` + `http.client` + `socket.AF_UNIX`) — no additional deps beyond `rumps`. Polls every 5 seconds via `@rumps.timer`. Run with `uv run menubar/app.py`.

`install.sh` also generates `~/Desktop/LocalServices.app` — a minimal shell-script `.app` bundle wrapping `uv run menubar/app.py`, so it can be double-clicked or placed in the Dock.

### Adding a new service

1. Add `conf.d/myservice.conf.template` and `conf.d/myservice.conf.vars`
2. Re-run `./install.sh` (or generate the `.conf` manually)
3. Run `supervisorctl reread && supervisorctl update`
