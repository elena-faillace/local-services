#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["rumps"]
# ///
"""
macOS menu bar app for supervisord process management.
Run with: uv run menubar/app.py
"""

import http.client
import os
import socket
import subprocess
import sys
import xmlrpc.client

import rumps

PID_FILE = os.path.expanduser("~/.supervisor/menubar.pid")
PLIST_LABEL = "com.local-services.menubar"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_LABEL}.plist")
# Resolved at startup so the plist always points to the real repo
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_brew_python():
    for candidate in (
        "/opt/homebrew/bin/python3.13",
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3",
    ):
        if os.path.isfile(candidate):
            try:
                out = subprocess.check_output(
                    ["otool", "-L", candidate], stderr=subprocess.DEVNULL
                ).decode()
                if "Python.framework" in out:
                    return candidate
            except Exception:
                pass
    return None


def _is_launch_at_login():
    return os.path.isfile(PLIST_PATH)


def _enable_launch_at_login():
    brew_python = _find_brew_python()
    uv_bin = subprocess.check_output(["which", "uv"], text=True).strip()
    app_path = os.path.join(_REPO_DIR, "menubar", "app.py")
    log = os.path.expanduser("~/Library/Logs/supervisor/menubar.log")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{uv_bin}</string>
    <string>run</string>
    <string>--python</string>
    <string>{brew_python}</string>
    <string>{app_path}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>"""
    with open(PLIST_PATH, "w") as f:
        f.write(plist)
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", PLIST_PATH],
        check=False,
    )


def _disable_launch_at_login():
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}", PLIST_PATH],
        check=False,
    )
    try:
        os.remove(PLIST_PATH)
    except FileNotFoundError:
        pass


def _acquire_lock():
    """Exit if another instance is alive; otherwise write our PID."""
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE).read().strip())
            os.kill(pid, 0)  # signal 0 = just check if process exists
            print(f"LocalServices already running (pid {pid}).", file=sys.stderr)
            sys.exit(0)
        except (ProcessLookupError, ValueError, PermissionError):
            pass  # stale PID — process is dead, overwrite and continue
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _release_lock():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass

SOCKET_PATH = os.path.expanduser("~/.supervisor/supervisor.sock")
LOG_DIR = os.path.expanduser("~/Library/Logs/supervisor")

STATUS_ICONS = {
    "all_running": "●",
    "partial": "◐",
    "all_stopped": "○",
    "error": "!",
}


# ── XML-RPC over Unix socket ──────────────────────────────────────────────────

class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost")
        self._socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(3)
        self.sock.connect(self._socket_path)


class _UnixSocketTransport(xmlrpc.client.Transport):
    def __init__(self, socket_path):
        super().__init__()
        self._socket_path = socket_path

    def make_connection(self, host):
        return _UnixSocketHTTPConnection(self._socket_path)


def _rpc():
    transport = _UnixSocketTransport(SOCKET_PATH)
    return xmlrpc.client.ServerProxy("http://localhost", transport=transport)


def _get_all_processes():
    """Returns list of process info dicts, or None if supervisord is unreachable."""
    try:
        return _rpc().supervisor.getAllProcessInfo()
    except Exception:
        return None


def _open_log_in_terminal(log_path):
    script = f'tell application "Terminal" to do script "tail -f {log_path}"'
    subprocess.Popen(["osascript", "-e", script])


# ── Menu bar app ─────────────────────────────────────────────────────────────

class LocalServicesApp(rumps.App):
    def __init__(self):
        super().__init__(STATUS_ICONS["all_stopped"], quit_button=None)
        self._do_refresh()  # initial population; _do_refresh is a plain method

    # Timer decorator turns this into a Timer object — never call it directly.
    # It calls _do_refresh on each tick once run() starts the event loop.
    @rumps.timer(5)
    def _timer_tick(self, _):
        try:
            self._do_refresh()
        except Exception:
            import traceback
            traceback.print_exc()

    def _do_refresh(self):
        processes = _get_all_processes()
        new_items = self._build_items(processes)

        # Properly clear the menu: iterating + del triggers __delitem__,
        # which removes each item from the underlying NSMenu.
        for key in list(self.menu.keys()):
            del self.menu[key]

        self.menu.update(new_items)

    def _build_items(self, processes):
        items = []

        if processes is None:
            self.title = STATUS_ICONS["error"]
            items.append(rumps.MenuItem("supervisord not running"))
            items.append(None)
            items.append(rumps.MenuItem(
                "Restart supervisord",
                callback=self._restart_supervisord,
            ))
        else:
            running = [p for p in processes if p["statename"] == "RUNNING"]

            if len(running) == len(processes) and processes:
                self.title = STATUS_ICONS["all_running"]
            elif len(running) == 0:
                self.title = STATUS_ICONS["all_stopped"]
            else:
                self.title = STATUS_ICONS["partial"]

            for proc in sorted(processes, key=lambda p: p["name"]):
                items.append(self._make_process_item(proc))

            items.append(None)
            items.append(rumps.MenuItem(
                "Reload Config",
                callback=self._reload_config,
            ))
            items.append(self._make_logs_menu(processes))

        login_label = "✓ Launch at Login" if _is_launch_at_login() else "Launch at Login"
        items.append(rumps.MenuItem(login_label, callback=self._toggle_launch_at_login))
        items.append(None)
        items.append(rumps.MenuItem("Quit", callback=rumps.quit_application))
        return items

    def _make_process_item(self, proc):
        name = proc["name"]
        state = proc["statename"]
        is_running = state == "RUNNING"
        label = f"{'●' if is_running else '○'}  {name}  [{state}]"
        item = rumps.MenuItem(label)

        if is_running:
            item.add(rumps.MenuItem(f"Stop {name}", callback=lambda _, n=name: self._stop(n)))
            item.add(rumps.MenuItem(f"Restart {name}", callback=lambda _, n=name: self._restart(n)))
        else:
            item.add(rumps.MenuItem(f"Start {name}", callback=lambda _, n=name: self._start(n)))

        return item

    def _make_logs_menu(self, processes):
        logs = rumps.MenuItem("View Logs")
        for proc in sorted(processes, key=lambda p: p["name"]):
            name = proc["name"]
            stdout = os.path.join(LOG_DIR, f"{name}.log")
            stderr = os.path.join(LOG_DIR, f"{name}.error.log")
            logs.add(rumps.MenuItem(
                f"{name} (stdout)",
                callback=lambda _, p=stdout: _open_log_in_terminal(p),
            ))
            logs.add(rumps.MenuItem(
                f"{name} (stderr)",
                callback=lambda _, p=stderr: _open_log_in_terminal(p),
            ))
        logs.add(None)
        supervisord_log = os.path.join(LOG_DIR, "supervisord.log")
        logs.add(rumps.MenuItem(
            "supervisord",
            callback=lambda _: _open_log_in_terminal(supervisord_log),
        ))
        return logs

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start(self, name):
        try:
            _rpc().supervisor.startProcess(name)
        except Exception as e:
            rumps.alert(f"Could not start {name}", str(e))

    def _stop(self, name):
        try:
            _rpc().supervisor.stopProcess(name)
        except Exception as e:
            rumps.alert(f"Could not stop {name}", str(e))

    def _restart(self, name):
        try:
            rpc = _rpc()
            rpc.supervisor.stopProcess(name)
            rpc.supervisor.startProcess(name)
        except Exception as e:
            rumps.alert(f"Could not restart {name}", str(e))

    def _reload_config(self, _):
        try:
            rpc = _rpc()
            result = rpc.supervisor.reloadConfig()
            added, changed, removed = result[0]
            for name in removed:
                rpc.supervisor.stopProcess(name)
            for name in added + changed:
                rpc.supervisor.startProcess(name)
        except Exception as e:
            rumps.alert("Could not reload config", str(e))

    def _toggle_launch_at_login(self, _):
        if _is_launch_at_login():
            _disable_launch_at_login()
        else:
            try:
                _enable_launch_at_login()
            except Exception as e:
                rumps.alert("Could not enable Launch at Login", str(e))
        self._do_refresh()

    def _restart_supervisord(self, _):
        subprocess.Popen([
            "launchctl", "kickstart", "-k",
            f"gui/{os.getuid()}/com.local-services",
        ])


if __name__ == "__main__":
    _acquire_lock()
    log_path = os.path.expanduser("~/Library/Logs/supervisor/menubar.log")
    sys.stdout = open(log_path, "a", buffering=1)
    sys.stderr = sys.stdout
    import traceback
    try:
        LocalServicesApp().run()
    except Exception:
        traceback.print_exc()
    finally:
        _release_lock()
