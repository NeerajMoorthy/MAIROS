#!/usr/bin/env python3
"""Publish the MAIROS demo: the API on this PC, behind the Vercel website.

    .venv\\Scripts\\python scripts\\publish_demo.py                 # start what is not running
    .venv\\Scripts\\python scripts\\publish_demo.py --restart-api   # load code changes into the API
    .venv\\Scripts\\python scripts\\publish_demo.py --stop          # stop what this script started

The website (https://mairos.vercel.app) forwards every /api request to
MAIROS_API_URL, which Next.js reads at build time. For this demo that address
is a Cloudflare quick tunnel to an API server on this machine. A quick tunnel
needs no Cloudflare account, but it gets a new random address every time it
starts — so whenever this script opens a new tunnel it stores the address on
the Vercel project and redeploys the site (a minute or two). A tunnel it
started earlier that still answers is reused, and nothing is redeployed.

The API and the tunnel run in the background and keep running after this
script ends. Their logs and process ids live in the demo's data folder, which
is separate from apps/api/data, so local projects are never published.

Needs: the backend's virtual environment (.venv), cloudflared, and Node.js
with the Vercel CLI logged in to the account that owns the project
(`npx vercel login`, once).
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SITE_URL = "https://mairos.vercel.app"
VERCEL_CLI = "vercel@65.2.0"
WINDOWS = os.name == "nt"
# cloudflared prints the tunnel's address once it has one. api.trycloudflare.com
# is the service it asks for that address, not the address itself.
TUNNEL_ADDRESS = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")


def healthy(base_url: str) -> bool:
    """Whether the MAIROS API answers its health check at ``base_url``."""
    request = urllib.request.Request(
        f"{base_url}/api/health", headers={"User-Agent": "mairos-publish-demo"}
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
            capture_output=True, text=True,
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
        subprocess.run(["taskkill", "/PID", str(entry["pid"]), "/T", "/F"], capture_output=True)
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


def tunnel_address(log: Path) -> str:
    match = TUNNEL_ADDRESS.search(log.read_text(encoding="utf-8", errors="replace"))
    return match.group(0) if match else ""


def vercel(*args: str) -> None:
    """Run the pinned Vercel CLI in apps/web, the directory linked to the project."""
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found: install Node.js 18 or later.")
    result = subprocess.run([npx, "--yes", VERCEL_CLI, *args], cwd=ROOT / "apps" / "web")
    if result.returncode != 0:
        raise SystemExit(
            f"vercel {args[0]} failed (exit {result.returncode}); see the output above. "
            "If you are logged out, run: npx vercel login"
        )


def save(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


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
    parser.add_argument("--cloudflared", type=Path, help="path to cloudflared")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / "publish_demo.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    api_url = f"http://127.0.0.1:{args.port}"

    if args.stop:
        for name in ("tunnel", "api"):
            if running(state.get(name)):
                stop(state[name])
                print(f"Stopped the {name} (process {state[name]['pid']}).")
        if "api" not in state and healthy(api_url):
            print(f"The API on {api_url} was not started by this script; stop it where it runs.")
        state_file.unlink(missing_ok=True)
        print(f"{SITE_URL} stays up but shows the backend as offline until this script runs again.")
        return

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

    # 2. The tunnel: reused while it answers, otherwise replaced.
    tunnel = state.get("tunnel")
    if running(tunnel) and healthy(tunnel["url"]):
        print(f"Tunnel   still up at {tunnel['url']}")
        new_address = False
    else:
        if running(tunnel):
            stop(tunnel)  # alive but no longer answering
        cloudflared = find_cloudflared(args.cloudflared)
        log = logs / "tunnel.log"
        process = start_background(
            [str(cloudflared), "tunnel", "--url", api_url, "--no-autoupdate"], log
        )
        tunnel = {"pid": process.pid, "image": cloudflared.name, "url": ""}
        state["tunnel"] = tunnel
        save(state_file, state)
        print("Tunnel   opening a quick tunnel ...")
        wait_for(lambda: bool(tunnel_address(log)), 60, "the tunnel's address", process, f"See {log}.")
        tunnel["url"] = tunnel_address(log)
        save(state_file, state)
        wait_for(
            lambda: healthy(tunnel["url"]), 90, "the API to answer through the tunnel",
            process, f"See {log}.",
        )
        print(f"Tunnel   up at {tunnel['url']}")
        new_address = True

    # 3. The website, rebuilt only when the address it forwards to changed.
    if new_address or args.redeploy:
        print("Vercel   storing the address and redeploying the site (1-2 minutes) ...")
        vercel(
            "env", "add", "MAIROS_API_URL", "--environment", "production",
            "--environment", "preview", "--value", tunnel["url"],
            "--no-sensitive", "--force", "--yes",
        )
        vercel("deploy", "--prod", "--yes")
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
