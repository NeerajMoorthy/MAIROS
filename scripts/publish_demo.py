#!/usr/bin/env python3
"""Publish the MAIROS demo: the API on this PC, behind the Vercel website.

    .venv\\Scripts\\python scripts\\publish_demo.py                 # start what is not running
    .venv\\Scripts\\python scripts\\publish_demo.py --ngrok-domain x.ngrok-free.app   # once: use ngrok
    .venv\\Scripts\\python scripts\\publish_demo.py --localhost-run   # once: use localhost.run
    .venv\\Scripts\\python scripts\\publish_demo.py --restart-api   # load code changes into the API
    .venv\\Scripts\\python scripts\\publish_demo.py --stop          # stop what this script started
    .venv\\Scripts\\python scripts\\publish_demo.py --install-autostart   # once: keep it up on its own

The website (https://mairos.vercel.app) forwards every /api request to
MAIROS_API_URL, which Next.js reads at build time. For this demo that address
is a tunnel to an API server on this machine, one of:

- an **ngrok** fixed domain (free account; `--ngrok-domain`, remembered after
  the first run). The address never changes, and ngrok runs over ordinary
  HTTPS, so it also works on networks that block Cloudflare's tunnel ports;
- a **Cloudflare quick tunnel** (no account). It gets a new random address
  every time it starts;
- a **localhost.run** tunnel (no account, no install: the SSH client Windows
  ships with, over port 22). For networks that block both ngrok's binary and
  Cloudflare's tunnel ports. Like Cloudflare, the address changes each time it
  starts, and the free service may also move it while running; the script
  notices that the old address stopped answering and redeploys.

The script redeploys the site only when the address it forwards to has
changed (a minute or two): with ngrok, only the first time. A tunnel it started
earlier that still answers is reused.

`--install-autostart` (Windows) adds a scheduled task that runs this script
every minute without a window (`--watchdog`): after a restart, a sleep or a
dropped tunnel it brings the API and tunnel back and redeploys when the
address changed, so the site recovers on its own while this PC is on.

The API and the tunnel run in the background and keep running after this
script ends. Their logs and process ids live in the demo's data folder, which
is separate from apps/api/data, so local projects are never published.

Needs: the backend's virtual environment (.venv), ngrok with your authtoken
added (`ngrok config add-authtoken ...`), cloudflared, or an SSH client for
localhost.run, and Node.js with the
Vercel CLI logged in to the account that owns the project (`npx vercel login`).
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SITE_URL = "https://mairos.vercel.app"
VERCEL_CLI = "vercel@65.2.0"
WINDOWS = os.name == "nt"
# cloudflared prints the tunnel's address once it has one. api.trycloudflare.com
# is the service it asks for that address, not the address itself.
TUNNEL_ADDRESS = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
# localhost.run prints its address as https://<id>.lhr.life. Its banner also
# links to admin.localhost.run and localhost.run/docs, which are not tunnels.
LHR_ADDRESS = re.compile(r"https://[a-z0-9-]+\.lhr\.life")
TASK_NAME = "MAIROS demo"
# A free localhost.run address can vanish after ~10 minutes; checking every
# minute keeps the gap short. A run where everything answers takes a second.
WATCHDOG_MINUTES = 1
# Console programs started from pythonw.exe (the watchdog) would each flash a
# window of their own.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
# Set by --watchdog: where the Vercel CLI's output goes instead of a console.
watchdog_log = None


def healthy(base_url: str) -> bool:
    """Whether the MAIROS API answers its health check at ``base_url``."""
    request = urllib.request.Request(
        f"{base_url}/api/health",
        headers={"User-Agent": "mairos-publish-demo", "ngrok-skip-browser-warning": "1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response).get("status") == "ok"
    except (OSError, ValueError, http.client.HTTPException):
        return False


def wait_for(condition, seconds: float, what: str, process=None, hint: str = "") -> None:
    """Poll ``condition`` until it holds; stop early if ``process`` exits."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        if process is not None and process.poll() is not None:
            raise SystemExit(f"Gave up waiting for {what}: the process exited. {hint}".rstrip())
        time.sleep(2)
    raise SystemExit(f"Timed out after {seconds:g} s waiting for {what}. {hint}".rstrip())


def start_background(args: list[str], log: Path, cwd: Path | None = None, env=None):
    """Start a process that outlives this script, its output going to ``log``."""
    if WINDOWS:
        # Detached: no console of its own, so closing this terminal does not
        # stop it.
        options = {
            "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        }
    else:
        options = {"start_new_session": True}
    with open(log, "wb") as out:
        return subprocess.Popen(
            args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
            stderr=subprocess.STDOUT, **options,
        )


def running(entry: dict | None) -> bool:
    """Whether a process this script recorded is still that process."""
    if not entry:
        return False
    if WINDOWS:
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {entry['pid']}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, **NO_WINDOW,
        ).stdout
        # The image name guards against Windows reusing the id for another program.
        return f'"{entry["image"]}"'.lower() in listing.lower()
    try:
        os.kill(entry["pid"], 0)
    except OSError:
        return False
    return True


def stop(entry: dict) -> None:
    if WINDOWS:
        # /T stops the whole tree: the virtual environment's python.exe is a
        # launcher that runs the real interpreter as a child, and stopping the
        # launcher alone would leave the server holding the port.
        subprocess.run(["taskkill", "/PID", str(entry["pid"]), "/T", "/F"], capture_output=True, **NO_WINDOW)
    else:
        os.killpg(entry["pid"], signal.SIGTERM)


def find_cloudflared(given: Path | None) -> Path:
    """The cloudflared binary: --cloudflared, the workspace's copy, or PATH."""
    if given:
        if not given.is_file():
            raise SystemExit(f"--cloudflared: no file at {given}")
        return given
    bundled = WORKSPACE / "tools" / "cloudflared" / "cloudflared.exe"
    if bundled.is_file():
        return bundled
    on_path = shutil.which("cloudflared")
    if on_path:
        return Path(on_path)
    raise SystemExit(
        "cloudflared not found. Download it from "
        "https://github.com/cloudflare/cloudflared/releases and pass --cloudflared <path>."
    )


def find_ngrok(given: Path | None) -> Path:
    """The ngrok binary: --ngrok, PATH, or where winget installs it."""
    if given:
        if not given.is_file():
            raise SystemExit(f"--ngrok: no file at {given}")
        return given
    on_path = shutil.which("ngrok")
    if on_path:
        return Path(on_path)
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for candidate in sorted(winget.glob("Ngrok.Ngrok*/ngrok.exe")):
        return candidate
    raise SystemExit("ngrok not found. Install it (winget install Ngrok.Ngrok) or pass --ngrok <path>.")


def find_ssh(given: Path | None) -> Path:
    """The SSH client for localhost.run: --ssh, PATH, or Windows' built-in copy."""
    if given:
        if not given.is_file():
            raise SystemExit(f"--ssh: no file at {given}")
        return given
    on_path = shutil.which("ssh")
    if on_path:
        return Path(on_path)
    builtin = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    if builtin.is_file():
        return builtin
    raise SystemExit(
        "ssh not found. On Windows, add the optional feature 'OpenSSH Client', or pass --ssh <path>."
    )


def tunnel_address(log: Path, pattern: re.Pattern = TUNNEL_ADDRESS) -> str:
    """The latest tunnel address in ``log``; localhost.run may print a new one later."""
    matches = pattern.findall(log.read_text(encoding="utf-8", errors="replace"))
    return matches[-1] if matches else ""


def vercel(*args: str) -> None:
    """Run the pinned Vercel CLI in apps/web, the directory linked to the project."""
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found: install Node.js 18 or later.")
    # NO_UPDATE_NOTIFIER: the pinned CLI otherwise asks "Would you like to
    # upgrade now? (Y/n)" and waits for an answer nobody is there to give.
    options = {"env": {**os.environ, "NO_UPDATE_NOTIFIER": "1"}}
    if watchdog_log is not None:
        options.update(stdin=subprocess.DEVNULL, stdout=watchdog_log, stderr=subprocess.STDOUT, **NO_WINDOW)
    result = subprocess.run([npx, "--yes", VERCEL_CLI, *args], cwd=ROOT / "apps" / "web", **options)
    if result.returncode != 0:
        raise SystemExit(
            f"vercel {args[0]} failed (exit {result.returncode}); see the output above. "
            "If you are logged out, run: npx vercel login"
        )


def save(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def watchdog_task_xml(program: Path, arguments: str, workdir: Path, start: datetime) -> str:
    """Task Scheduler definition: run ``program`` every few minutes while signed in.

    Laptops matter here: schtasks' own defaults skip a task on battery power and
    stop it when the charger is pulled. A run still going when the next is due
    is left alone (IgnoreNew), and a run missed while asleep starts on waking.
    """
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Keeps the MAIROS demo (https://mairos.vercel.app) up: restarts the API and tunnel on this PC and redeploys when the tunnel's address changes.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Repetition>
        <Interval>PT{WATCHDOG_MINUTES}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
    <Hidden>false</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(program))}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install_autostart(port: int, data_dir: Path) -> None:
    if not WINDOWS:
        raise SystemExit("--install-autostart uses the Windows Task Scheduler; on other systems use cron.")
    # pythonw.exe runs without a console window, so nothing pops up every few minutes.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    program = pythonw if pythonw.is_file() else Path(sys.executable)
    arguments = subprocess.list2cmdline(
        [str(Path(__file__).resolve()), "--watchdog", "--port", str(port), "--data-dir", str(data_dir)]
    )
    definition = data_dir / "watchdog-task.xml"
    definition.write_text(watchdog_task_xml(program, arguments, ROOT, datetime.now()), encoding="utf-16")
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(definition), "/F"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Could not create the scheduled task: {(result.stderr or result.stdout).strip()}")
    print(f"Task     '{TASK_NAME}' runs every {WATCHDOG_MINUTES} minutes while you are signed in")
    # Asleep, the PC cannot answer anyone; never sleeping on the charger is
    # Windows' own setting (Settings > System > Power), so it is easy to undo.
    subprocess.run(["powercfg", "/change", "standby-timeout-ac", "0"], capture_output=True)
    print("Power    this PC no longer sleeps by itself while plugged in")
    print("         (undo: powercfg /change standby-timeout-ac 30); closing the lid may still sleep it")
    print(f"Log      {data_dir / 'logs' / 'watchdog.log'}")
    print("Remove   .venv\\Scripts\\python scripts\\publish_demo.py --remove-autostart")


def remove_autostart() -> None:
    result = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
    print(f"Removed the scheduled task '{TASK_NAME}'." if result.returncode == 0
          else f"No scheduled task '{TASK_NAME}' to remove.")


def open_watchdog_log(logs: Path):
    """The watchdog's log, appended to; started afresh once it passes 1 MB."""
    log = logs / "watchdog.log"
    if log.exists() and log.stat().st_size > 1_000_000:
        log.replace(logs / "watchdog.old.log")
    out = open(log, "a", encoding="utf-8", buffering=1)
    out.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stop", action="store_true", help="stop the API and tunnel this script started")
    parser.add_argument(
        "--redeploy", action="store_true",
        help="store the current tunnel address on Vercel and redeploy, even if the tunnel was reused",
    )
    parser.add_argument(
        "--restart-api", action="store_true",
        help="restart the API to load code changes; the tunnel and its address are kept",
    )
    parser.add_argument("--port", type=int, default=8010, help="port of the public API (default 8010)")
    parser.add_argument(
        "--data-dir", type=Path, default=WORKSPACE / "mairos-deploy-data",
        help="data folder of the public API (default: mairos-deploy-data beside the repository)",
    )
    parser.add_argument(
        "--ngrok-domain",
        help="your ngrok domain, e.g. name.ngrok-free.app; remembered, so give it once",
    )
    parser.add_argument("--cloudflare", action="store_true", help="go back to a Cloudflare quick tunnel")
    parser.add_argument(
        "--localhost-run", action="store_true",
        help="use a localhost.run tunnel over SSH (port 22); remembered, so give it once",
    )
    parser.add_argument("--ngrok", type=Path, help="path to ngrok")
    parser.add_argument("--cloudflared", type=Path, help="path to cloudflared")
    parser.add_argument("--ssh", type=Path, help="path to the ssh client (for --localhost-run)")
    parser.add_argument(
        "--install-autostart", action="store_true",
        help=f"Windows: run this script every {WATCHDOG_MINUTES} minutes in the background, "
        "so the demo recovers on its own",
    )
    parser.add_argument("--remove-autostart", action="store_true", help="remove the scheduled task again")
    parser.add_argument(
        "--watchdog", action="store_true",
        help="what the scheduled task runs: no console, output appended to logs/watchdog.log",
    )
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / "publish_demo.json"

    if args.remove_autostart:
        remove_autostart()
        return
    if args.install_autostart:
        install_autostart(args.port, data_dir)
        print("\nStarting the demo now as well:\n")
    if args.watchdog:
        global watchdog_log
        watchdog_log = open_watchdog_log(logs)
        # Errors land in the log too; the next run in a few minutes tries again.
        sys.stdout = sys.stderr = watchdog_log
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    api_url = f"http://127.0.0.1:{args.port}"

    if args.stop:
        for name in ("tunnel", "api"):
            if running(state.get(name)):
                stop(state[name])
                print(f"Stopped the {name} (process {state[name]['pid']}).")
        if "api" not in state and healthy(api_url):
            print(f"The API on {api_url} was not started by this script; stop it where it runs.")
        # The processes are gone; the ngrok domain and the deployed address are kept.
        state.pop("api", None)
        state.pop("tunnel", None)
        save(state_file, state)
        print(f"{SITE_URL} stays up but shows the backend as offline until this script runs again.")
        return

    if args.cloudflare:
        state.pop("ngrok_domain", None)
        state.pop("localhost_run", None)
    elif args.ngrok_domain:
        state["ngrok_domain"] = args.ngrok_domain.removeprefix("https://").strip("/")
        state.pop("localhost_run", None)
    elif args.localhost_run:
        state.pop("ngrok_domain", None)
        state["localhost_run"] = True
    ngrok_domain = state.get("ngrok_domain")
    localhost_run = bool(state.get("localhost_run"))

    # 1. The API, with the demo's own data folder.
    if args.restart_api:
        if running(state.get("api")):
            stop(state["api"])
            wait_for(lambda: not healthy(api_url), 30, "the old API to stop")
            print("API      stopped, to load the current code")
        elif healthy(api_url):
            raise SystemExit(f"The API on {api_url} was not started by this script; restart it where it runs.")
    if healthy(api_url):
        print(f"API      already answering on {api_url}")
    else:
        log = logs / "api.log"
        process = start_background(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
             "--port", str(args.port), "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"],
            log, cwd=ROOT / "apps" / "api", env={**os.environ, "DATA_DIR": str(data_dir)},
        )
        state["api"] = {"pid": process.pid, "image": Path(sys.executable).name}
        save(state_file, state)
        print(f"API      starting on {api_url} ...")
        wait_for(lambda: healthy(api_url), 180, "the API to start", process, f"See {log}.")
        print(f"API      up, data in {data_dir}")

    # 2. The tunnel: reused while it answers and is the kind asked for,
    # otherwise replaced.
    tunnel = state.get("tunnel")
    wanted = f"https://{ngrok_domain}" if ngrok_domain else None
    if wanted:
        kind_asked_for = tunnel and tunnel["url"] == wanted
    elif localhost_run:
        kind_asked_for = tunnel and tunnel["url"].endswith(".lhr.life")
    else:
        kind_asked_for = tunnel and "trycloudflare.com" in tunnel["url"]
    if running(tunnel) and kind_asked_for and healthy(tunnel["url"]):
        print(f"Tunnel   still up at {tunnel['url']}")
    else:
        if running(tunnel):
            stop(tunnel)  # not answering, or not the tunnel asked for
        log = logs / "tunnel.log"
        if ngrok_domain:
            ngrok = find_ngrok(args.ngrok)
            process = start_background(
                [str(ngrok), "http", str(args.port), f"--url={wanted}", "--log=stdout"], log
            )
            tunnel = {"pid": process.pid, "image": ngrok.name, "url": wanted}
            print(f"Tunnel   opening ngrok on {wanted} ...")
        elif localhost_run:
            ssh = find_ssh(args.ssh)
            process = start_background(
                [str(ssh), "-T", "-R", f"80:127.0.0.1:{args.port}",
                 "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30",
                 "-o", "ExitOnForwardFailure=yes", "nokey@localhost.run"],
                log,
            )
            tunnel = {"pid": process.pid, "image": ssh.name, "url": ""}
            print("Tunnel   opening a localhost.run tunnel over SSH ...")
            wait_for(
                lambda: bool(tunnel_address(log, LHR_ADDRESS)), 60, "the tunnel's address",
                process, f"See {log}.",
            )
            tunnel["url"] = tunnel_address(log, LHR_ADDRESS)
        else:
            cloudflared = find_cloudflared(args.cloudflared)
            process = start_background(
                [str(cloudflared), "tunnel", "--url", api_url, "--no-autoupdate"], log
            )
            tunnel = {"pid": process.pid, "image": cloudflared.name, "url": ""}
            print("Tunnel   opening a Cloudflare quick tunnel ...")
            wait_for(lambda: bool(tunnel_address(log)), 60, "the tunnel's address", process, f"See {log}.")
            tunnel["url"] = tunnel_address(log)
        state["tunnel"] = tunnel
        save(state_file, state)
        wait_for(
            lambda: healthy(tunnel["url"]), 90, "the API to answer through the tunnel",
            process, f"See {log}.",
        )
        print(f"Tunnel   up at {tunnel['url']}")

    # 3. The website, rebuilt only when the address it forwards to changed.
    if tunnel["url"] != state.get("deployed_url") or args.redeploy:
        print("Vercel   storing the address and redeploying the site (1-2 minutes) ...")
        vercel(
            "env", "add", "MAIROS_API_URL", "--environment", "production",
            "--environment", "preview", "--value", tunnel["url"],
            "--no-sensitive", "--force", "--yes",
        )
        vercel("deploy", "--prod", "--yes")
        state["deployed_url"] = tunnel["url"]
        save(state_file, state)
    else:
        print("Vercel   no redeploy needed")

    # A deployment Vercel reports as ready can take a few seconds more to
    # answer at its public address.
    wait_for(
        lambda: healthy(SITE_URL), 90, f"{SITE_URL}/api/health to answer",
        hint="If the site was redeployed by hand with another address, run this script again with --redeploy.",
    )
    print(f"\nMAIROS is published at {SITE_URL}")
    print(f"  logs  {logs}")
    print("  stop  .venv\\Scripts\\python scripts\\publish_demo.py --stop")


if __name__ == "__main__":
    main()
