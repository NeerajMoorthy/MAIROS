"""scripts/publish_demo.py: reading tunnel addresses out of the tunnel's log.

The script never sees the address it publishes except as text the tunnel
prints. localhost.run's banner also links to its own admin and docs pages, and
the free service can hand out a new address while running, so the address
read back must be the tunnel's own and the latest one.
"""

from __future__ import annotations

import importlib.util
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
