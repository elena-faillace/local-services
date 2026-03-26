# local-services

Process manager config for local development servers. Uses [Supervisor](http://supervisord.org/) to manage all services; a single launchd entry boots Supervisor at login.

## Structure

```
local-services/
├── supervisord.conf                        # Main supervisord daemon config
├── conf.d/
│   ├── bookmark-processor.conf.template   # Supervisor config template
│   ├── bookmark-processor.conf.vars       # Prompts and defaults for the template
│   └── bookmark-processor.conf            # Generated — gitignored, not committed
├── menubar/
│   └── app.py                             # macOS menu bar app (Python + rumps)
├── install.sh                              # One-time setup script
└── README.md
```

Each service in `conf.d/` is defined by two committed files:

- `<name>.conf.template` — Supervisor program config using `{{VARNAME}}` placeholders
- `<name>.conf.vars` — one line per user-supplied variable: `VARNAME|Prompt text|default value`

`install.sh` loops over all templates, prompts for any variables declared in the `.vars` file, and generates the final `<name>.conf`. The generated `.conf` files contain local paths and are gitignored.

## One-time setup

### 1. Install dependencies

```bash
brew install supervisor uv
```

### 2. Run the install script

```bash
cd /path/to/local-services
chmod +x install.sh
./install.sh
```

This will:
- Verify `supervisord` and `uv` are installed
- Create log and socket directories
- Generate `~/Library/LaunchAgents/com.local-services.plist` with your actual paths and load it (Supervisor starts now and auto-starts at every login)
- Add a `supervisorctl` alias to your shell rc file (`.zshrc` or `.bash_profile`) so it uses this repo's config automatically
- Loop over all `conf.d/*.conf.template` files, prompt for each service's variables (as declared in the companion `.vars` file), and generate the corresponding `conf.d/*.conf`
- Generate `~/Desktop/LocalServices.app` — a double-clickable app bundle that launches the menu bar UI
- Optionally register the menu bar app to launch at login

### 3. Reload your shell

```bash
source ~/.zshrc   # or ~/.bash_profile if using bash
```

### 4. Verify everything is running

```bash
supervisorctl status
```

You should see `bookmark-processor` with status `RUNNING`.

---

## Day-to-day usage

```bash
# Check status of all services
supervisorctl status

# Start a service
supervisorctl start bookmark-processor

# Stop a service (does not restart automatically until you start it again)
supervisorctl stop bookmark-processor

# Restart a service (stop + start in one command)
supervisorctl restart bookmark-processor

# Send a signal to a process (e.g. SIGINT to trigger a graceful shutdown)
supervisorctl signal INT bookmark-processor

# Stop all services at once
supervisorctl stop all

# View live stdout/stderr logs
tail -f ~/Library/Logs/supervisor/bookmark-processor.log
tail -f ~/Library/Logs/supervisor/bookmark-processor.error.log
```

---

## Adding a new service

1. Create `conf.d/my-app.conf.template` — a standard Supervisor `[program:...]` config, using `{{VARNAME}}` for any paths that differ per machine. `{{UV_BIN}}` and `{{REPO_DIR}}` are always available for free.
2. Create `conf.d/my-app.conf.vars` — one line per variable you used:

   ```text
   VARNAME|Human-readable prompt|/default/path
   ```

3. Re-run `./install.sh` to generate the `.conf` file, **or** fill in the values manually and drop the file into `conf.d/`.
4. Pick it up without restarting Supervisor:

```bash
supervisorctl reread && supervisorctl update
```

No new launchd plists required.

## Menu bar app

`menubar/app.py` is a macOS menu bar app that shows the status of all supervisord-managed services and lets you start, stop, and restart them without touching the terminal.

`install.sh` generates `~/Desktop/LocalServices.app` — double-click it (or drag it to the Dock) to launch the app. You can also run it directly:

```bash
uv run --python /opt/homebrew/bin/python3 menubar/app.py
```

The icon in the menu bar reflects overall status: `●` all running, `◐` partial, `○` all stopped, `!` supervisord unreachable.

Clicking a service shows its state and offers Start/Stop/Restart actions. **View Logs** opens a live `tail -f` in Terminal for any service's stdout, stderr, or the supervisord log itself.

---

## Removing a service

1. Delete its `conf.d/*.conf` file
2. Run:

```bash
supervisorctl reread && supervisorctl update
```
