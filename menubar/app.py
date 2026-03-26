#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["rumps"]
# ///
"""
macOS menu bar app for supervisord process management.
Run with: uv run menubar/app.py
"""

import fcntl
import http.client
import os
import socket
import subprocess
import sys
import xmlrpc.client

import rumps

LOCK_FILE = os.path.expanduser("~/.supervisor/menubar.lock")


def _acquire_lock():
    """Exit immediately if another instance is already running."""
    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("LocalServices menu bar app is already running.", file=sys.stderr)
        sys.exit(0)
    return f  # keep reference so the lock is held for the process lifetime

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
        self._do_refresh()

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

    def _restart_supervisord(self, _):
        subprocess.Popen([
            "launchctl", "kickstart", "-k",
            f"gui/{os.getuid()}/com.local-services",
        ])


if __name__ == "__main__":
    _lock = _acquire_lock()
    LocalServicesApp().run()
