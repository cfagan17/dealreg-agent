"""SI partner signals for the partner intelligence agent.

Raw signals come from the (fictional) partner data. The derived metrics are computed here,
deterministically, so the model never does arithmetic and every number on the page can be
traced back to a formula.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = Path(os.environ.get("PARTNER_INTEL_OUTPUT_DIR", ROOT / "output" / "partner_intel"))


def _load(name):
    with open(DATA / name) as f:
        return json.load(f)


def program() -> dict:
    return _load("si_program.json")


def partners() -> list[dict]:
    return _load("si_partners.json")


def get_partner(pid: str) -> dict | None:
    return next((p for p in partners() if p["partner_id"] == pid), None)


def notes(pid: str) -> list[dict]:
    return [n for n in _load("si_partner_notes.json") if n["partner_id"] == pid]


def _pct(new, old):
    if not old:
        return None
    return round((new - old) / old * 100)


def _clamp(x, lo=-100, hi=100):
    return max(lo, min(hi, x))


def tier_gap(p: dict) -> dict:
    tiers = program()["tiers"]
    names = [t["tier"] for t in tiers]
    i = names.index(p["tier"])
    current = tiers[i]
    have = {
        "certified": p["certified_by_quarter"][-1],
        "production_deployments_12m": p["production_deployments_12m"],
        "public_stories": p["public_stories"],
        "regions": len(p["regions_active"]),
    }

    def gaps(t):
        return {k: t[k] - have[k] for k in have if have[k] < t.get(k, 0)}

    out = {"current_tier": p["tier"], "have": have,
           "short_of_current_tier": gaps(current) or None}
    if i + 1 < len(tiers):
        nxt = tiers[i + 1]
        out["next_tier"] = nxt["tier"]
        out["short_of_next_tier"] = gaps(nxt)
        if nxt.get("joint_business_plan"):
            out["short_of_next_tier"]["joint_business_plan"] = "required"
    return out


def derived(p: dict) -> dict:
    certs, usage, regs, sup = (p["certified_by_quarter"], p["usage_index_partner_led_customers_by_quarter"],
                               p["deal_registrations_by_quarter"], p["applied_ai_support_hours_by_quarter"])
    share_now = p["claude_engagements_last_2q"] / p["ai_engagements_last_2q_est"]
    d = {
        "claude_share_of_ai_book_pct": round(share_now * 100),
        "claude_engagements_change_vs_prior_2q_pct": _pct(p["claude_engagements_last_2q"], p["claude_engagements_prior_2q"]),
        "certified_change_last_quarter_pct": _pct(certs[-1], certs[-2]),
        "certified_change_3_quarters_pct": _pct(certs[-1], certs[0]),
        "usage_change_last_quarter_pct": _pct(usage[-1], usage[-2]),
        "usage_change_3_quarters_pct": _pct(usage[-1], usage[0]),
        "deal_registrations_change_last_quarter_pct": _pct(regs[-1], regs[-2]),
        "support_hours_change_last_quarter_pct": _pct(sup[-1], sup[-2]),
        "support_hours_per_claude_engagement": round(sum(sup[-2:]) / max(p["claude_engagements_last_2q"], 1), 1),
        "pilot_stall_rate_pct": round(p["pilots_stalled_90d"] / p["open_pilots"] * 100) if p["open_pilots"] else 0,
        "certified_people_per_production_deployment_12m": round(certs[-1] / max(p["production_deployments_12m"], 1), 1),
    }
    parts = [d["claude_engagements_change_vs_prior_2q_pct"], d["usage_change_last_quarter_pct"],
             d["certified_change_last_quarter_pct"], d["deal_registrations_change_last_quarter_pct"]]
    parts = [_clamp(x) for x in parts if x is not None]
    d["momentum_index"] = round(sum(parts) / len(parts)) if parts else 0
    d["momentum_index_definition"] = ("Average of last-period % change in Claude engagements, usage on partner-led "
                                     "customers, certified people and deal registrations, each capped at +/-100.")
    return d


def signals(pid: str) -> dict | None:
    p = get_partner(pid)
    if not p:
        return None
    return {"partner": p, "derived": derived(p), "tiers": tier_gap(p)}


VALID_PLAYS = {"Accelerate", "Rescue", "Develop", "Deprioritize", "Maintain"}
VALID_MOMENTUM = {"accelerating", "steady", "drifting"}


def record_assessment(rec: dict) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rec = {**rec, "recorded_at": datetime.now().isoformat(timespec="seconds")}
    with open(OUTPUT / "assessments.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
