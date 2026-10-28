"""scripts/publish_demo.py: tunnel addresses read from the tunnel's log, and the watchdog task.

The script never sees the address it publishes except as text the tunnel
prints. localhost.run's banner also links to its own admin and docs pages, and
the free service can hand out a new address while running, so the address
read back must be the tunnel's own and the latest one.
"""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_demo.py"
_spec = importlib.util.spec_from_file_location("publish_demo", _SCRIPT)
publish_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish_demo)

LHR_BANNER = """\
===============================================================================
Welcome to localhost.run!

Follow your favourite reverse tunnel at [https://twitter.com/localhost_run].

To set up and manage custom domains go to https://admin.localhost.run/

More details on custom domains (and how to enable subdomains for your custom
domain) at https://localhost.run/docs/custom-domains

To explore using localhost.run visit the documentation site:
https://localhost.run/docs/
===============================================================================

** your connection id is 1f2e3d4c-0000-4000-8000-000000000000, please mention it if you send me a message about an issue. **

a1b2c3d4e5f6a7.lhr.life tunneled with tls termination, https://a1b2c3d4e5f6a7.lhr.life
"""


def _log(tmp_path: Path, text: str) -> Path:
    log = tmp_path / "tunnel.log"
    log.write_text(text, encoding="utf-8")
    return log


def test_localhost_run_address_skips_the_banner_links(tmp_path):
    log = _log(tmp_path, LHR_BANNER)
    assert publish_demo.tunnel_address(log, publish_demo.LHR_ADDRESS) == "https://a1b2c3d4e5f6a7.lhr.life"


def test_localhost_run_address_is_the_latest_one(tmp_path):
    moved = LHR_BANNER + "\n99ff88ee77dd66.lhr.life tunneled with tls termination, https://99ff88ee77dd66.lhr.life\n"
    log = _log(tmp_path, moved)
    assert publish_demo.tunnel_address(log, publish_demo.LHR_ADDRESS) == "https://99ff88ee77dd66.lhr.life"


def test_no_localhost_run_address_before_the_tunnel_is_up(tmp_path):
    log = _log(tmp_path, LHR_BANNER.split("** your connection")[0])
    assert publish_demo.tunnel_address(log, publish_demo.LHR_ADDRESS) == ""


def test_cloudflare_address_is_unchanged_by_default(tmp_path):
    log = _log(
        tmp_path,
        "INF Requesting new quick Tunnel on trycloudflare.com...\n"
        "INF |  https://riders-americas-strange-warnings.trycloudflare.com  |\n",
    )
    assert publish_demo.tunnel_address(log) == "https://riders-americas-strange-warnings.trycloudflare.com"


# --- The watchdog: a scheduled task that keeps the demo up on its own --------

_TASK_NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _task(program: str, arguments: str, workdir: str) -> ET.Element:
    xml = publish_demo.watchdog_task_xml(
        Path(program), arguments, Path(workdir), datetime(2026, 10, 28, 16, 5, 9)
    )
    # Written as UTF-16, as the declaration says and schtasks /XML expects.
    return ET.fromstring(xml.encode("utf-16"))


def test_watchdog_task_runs_on_battery_and_repeats_every_five_minutes():
    task = _task(r"C:\mairos\.venv\Scripts\pythonw.exe", "--watchdog", r"C:\mairos")
    settings = task.find("t:Settings", _TASK_NS)
    # schtasks' defaults would skip every run on a laptop that is not charging.
    assert settings.findtext("t:DisallowStartIfOnBatteries", namespaces=_TASK_NS) == "false"
    assert settings.findtext("t:StopIfGoingOnBatteries", namespaces=_TASK_NS) == "false"
    # A redeploy still running when the next run is due is not doubled up.
    assert settings.findtext("t:MultipleInstancesPolicy", namespaces=_TASK_NS) == "IgnoreNew"
    trigger = task.find("t:Triggers/t:TimeTrigger", _TASK_NS)
    assert trigger.findtext("t:StartBoundary", namespaces=_TASK_NS) == "2026-10-28T16:05:09"
    assert trigger.findtext("t:Repetition/t:Interval", namespaces=_TASK_NS) == "PT5M"
    assert trigger.find("t:Repetition/t:Duration", _TASK_NS) is None  # repeats indefinitely


def test_watchdog_task_keeps_paths_with_spaces_and_ampersands_intact():
    folder = r"C:\Users\moort\SEM THREE\R&D\mairos"
    arguments = f'"{folder}\\scripts\\publish_demo.py" --watchdog'
    task = _task(folder + r"\.venv\Scripts\pythonw.exe", arguments, folder)
    exec_ = task.find("t:Actions/t:Exec", _TASK_NS)
    assert exec_.findtext("t:Command", namespaces=_TASK_NS) == folder + r"\.venv\Scripts\pythonw.exe"
    assert exec_.findtext("t:Arguments", namespaces=_TASK_NS) == arguments
    assert exec_.findtext("t:WorkingDirectory", namespaces=_TASK_NS) == folder


def test_vercel_never_stops_at_the_upgrade_prompt(monkeypatch):
    # Vercel CLI 65 asks "Would you like to upgrade now? (Y/n)" unless
    # NO_UPDATE_NOTIFIER is set; under the watchdog nobody could answer.
    calls = []

    def fake_run(command, **options):
        calls.append((command, options))
        return publish_demo.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(publish_demo.shutil, "which", lambda name: "/usr/bin/npx")
    monkeypatch.setattr(publish_demo.subprocess, "run", fake_run)
    publish_demo.vercel("deploy", "--prod", "--yes")
    command, options = calls[0]
    assert command[-3:] == ["deploy", "--prod", "--yes"]
    assert options["env"]["NO_UPDATE_NOTIFIER"] == "1"


def test_watchdog_log_starts_afresh_past_one_megabyte(tmp_path):
    (tmp_path / "watchdog.log").write_text("x" * 1_000_001, encoding="utf-8")
    out = publish_demo.open_watchdog_log(tmp_path)
    out.write("API      already answering\n")
    out.close()
    assert (tmp_path / "watchdog.old.log").stat().st_size == 1_000_001
    text = (tmp_path / "watchdog.log").read_text(encoding="utf-8")
    assert text.startswith("\n--- ") and text.endswith("API      already answering\n")
