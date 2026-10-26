"""MCP server for the partner intelligence agent: SI partner signals, our own team's notes,
tier requirements, and a tool to record an assessment.

Run standalone (stdio):  python server/partner_intel_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

import si  # noqa: E402

server = MCPServer(
    name="partner-intel",
    instructions="Signals on services (SI) partners in the Claude partner program, plus a tool to record assessments.",
)


def _out(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


@server.tool()
def get_program() -> str:
    """Program context: as-of date, the quarters the data covers, tier requirements (modeled on the public
    Services Track), the next tier review date, and partner manager capacity."""
    return _out(si.program())


@server.tool()
def list_partners() -> str:
    """All SI partners with id, name, tier and partner manager."""
    return _out([{k: p[k] for k in ("partner_id", "name", "tier", "partner_manager")} for p in si.partners()])


@server.tool()
def get_partner_signals(partner_id: str) -> str:
    """Raw quarterly signals for one partner (certifications, production deployments, pilots, deal
    registrations, usage on partner-led customers, Applied AI support hours, estimated AI book), plus
    derived metrics (Claude's share of their AI book, trends, stall rate, momentum index) and the gap to
    their current and next tier. All arithmetic is precomputed."""
    s = si.signals(partner_id)
    return _out(s or {"error": f"No partner {partner_id}"})


@server.tool()
def get_partner_notes(partner_id: str) -> str:
    """Notes about the partner written by our own partner managers and AEs (call notes, QBR notes,
    opportunity notes). Internal and trusted, but they are one person's read of a conversation."""
    return _out(si.notes(partner_id) or {"notes": [], "message": "No notes."})


@server.tool()
def record_assessment(
    partner_id: str,
    momentum: str,
    play: str,
    headline: str,
    evidence: list[str],
    caveats: str,
    human_touch_needed: bool,
    who: str,
    goal: str,
    agenda: list[str],
    urgency: str,
    tier_outlook: str,
    confidence: str,
) -> str:
    """Record the assessment for one partner. Call exactly once per partner.

    momentum: accelerating, steady or drifting.
    play: Accelerate, Rescue, Develop, Deprioritize or Maintain.
    headline: one plain sentence a partner leader could act on.
    evidence: 3 to 5 short bullets, each citing a specific signal or note.
    caveats: what could make this read wrong (data gaps, a signal that might mislead).
    human_touch_needed: whether a person should reach out beyond the normal cadence.
    who: who should reach out (e.g. "Partner manager", "Partner manager + regional sales VP"), or "None".
    goal: the single outcome the conversation should produce.
    agenda: 2 to 4 short agenda points for that conversation.
    urgency: "This week", "This month" or "Next QBR".
    tier_outlook: where they stand against their current and next tier, and any risk at the next review.
    confidence: high, medium or low.
    """
    if play not in si.VALID_PLAYS:
        return _out({"error": f"play must be one of {sorted(si.VALID_PLAYS)}"})
    if momentum not in si.VALID_MOMENTUM:
        return _out({"error": f"momentum must be one of {sorted(si.VALID_MOMENTUM)}"})
    if not si.get_partner(partner_id):
        return _out({"error": f"No partner {partner_id}"})
    si.record_assessment({
        "partner_id": partner_id, "momentum": momentum, "play": play, "headline": headline,
        "evidence": evidence, "caveats": caveats, "human_touch_needed": human_touch_needed,
        "who": who, "goal": goal, "agenda": agenda, "urgency": urgency,
        "tier_outlook": tier_outlook, "confidence": confidence,
    })
    return _out({"status": "recorded", "partner_id": partner_id, "play": play})


if __name__ == "__main__":
    server.run("stdio")
