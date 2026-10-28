"""The Tasks page's agent map (apps/web/src/lib/agents.ts) matches the router.

The website draws the orchestrator's flows from a static copy so the map works
while the backend is offline. A flow added or reordered in router.py without
the copy would make the map describe a system that no longer exists.
"""

from __future__ import annotations

import re
from pathlib import Path

from services.agents.router import FLOWS

_AGENTS_TS = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "lib" / "agents.ts"


def _web_flows() -> dict[str, list[str]]:
    source = _AGENTS_TS.read_text(encoding="utf-8")
    block = source[source.index("export const FLOWS") :]
    flows = {}
    for match in re.finditer(r'id: "(\w+)",\s*label: "[^"]*",\s*agents: \[([^\]]*)\]', block):
        flows[match.group(1)] = re.findall(r'"(\w+)"', match.group(2))
    return flows


def _web_agents() -> set[str]:
    source = _AGENTS_TS.read_text(encoding="utf-8")
    block = source[source.index("export const AGENTS") : source.index("export interface FlowInfo")]
    return set(re.findall(r'id: "(\w+)"', block))


def test_every_flow_matches_the_router_in_order():
    assert _web_flows() == FLOWS


def test_the_map_shows_every_agent_a_flow_uses_and_the_router():
    used = {agent for agents in FLOWS.values() for agent in agents}
    assert _web_agents() == used | {"router"}
