# local-services

Process manager config for local development servers. Uses [Supervisor](http://supervisord.org/) to manage all services; a single launchd entry boots Supervisor at login.

## Structure

```
local-services/
├── supervisord.conf          # Main supervisord daemon config
├── conf.d/
│   └── bookmark-processor.conf  # One file per managed service
├── install.sh                # One-time setup script
└── README.md
```

## One-time setup

### 1. Install Supervisor

```bash
brew install supervisor
```

### 2. Run the install script

```bash
cd /path/to/local-services
chmod +x install.sh
./install.sh
```

This will:
- Create the log directory at `~/Library/Logs/supervisor/`
- Generate `~/Library/LaunchAgents/com.local-services.plist` with your actual paths (not committed to the repo)
- Load the launchd agent so Supervisor starts now and auto-starts at every login

### 3. Add the supervisorctl alias

By default, `supervisorctl` connects to the Homebrew-managed socket, not this repo's config. Add an alias to your shell config (`~/.zshrc` or `~/.bashrc`):

```bash
alias supervisorctl='supervisorctl -c ~/Documents/all_code/local-services/supervisord.conf'
```

Then reload your shell:

```bash
source ~/.zshrc
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

# Stop / start / restart a service
supervisorctl stop bookmark-processor
supervisorctl start bookmark-processor
supervisorctl restart bookmark-processor

# View live logs
tail -f ~/Library/Logs/supervisor/bookmark-processor.log
tail -f ~/Library/Logs/supervisor/bookmark-processor.error.log
```

---

## Adding a new service

1. Create `conf.d/my-app.conf` following the same pattern as `bookmark-processor.conf`
2. Pick it up without restarting Supervisor:

```bash
supervisorctl reread && supervisorctl update
```

No new launchd plists required.

## Removing a service

1. Delete its `conf.d/*.conf` file
2. Run:

```bash
supervisorctl reread && supervisorctl update
```
