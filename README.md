# local-services

Process manager config for local development servers. Uses [Supervisor](http://supervisord.org/) to manage all services; a single launchd entry boots Supervisor at login.

## Structure

```
local-services/
├── supervisord.conf          # Main supervisord daemon config
├── conf.d/
│   └── bookmark-processor.conf  # One file per managed service
├── launchd/
│   └── com.local-services.plist # Single launchd entry that boots supervisord
└── README.md
```

## One-time setup

```bash
# 1. Install Supervisor
brew install supervisor

# 2. Create log directory
mkdir -p ~/Library/Logs/supervisor

# 3. Copy the launchd plist and load it
cp launchd/com.local-services.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.local-services.plist

# 4. Verify supervisord started and services are running
supervisorctl status
```

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
```

## Adding a new service

1. Create `conf.d/my-app.conf` following the same pattern as `bookmark-processor.conf`
2. Tell Supervisor to pick it up (no restart needed):

```bash
supervisorctl reread && supervisorctl update
```

That's it — no new launchd plists required.

## Removing a service

1. Delete its `conf.d/*.conf` file
2. Run `supervisorctl reread && supervisorctl update`
