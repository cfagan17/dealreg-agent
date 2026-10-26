"""Builds site/intel.js from the partner data and a recorded partner-intelligence run.

Usage: python site/build_intel.py site/runs/assessments.jsonl site/runs/weekly_plan.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import si  # noqa: E402

assess = {}
for line in open(sys.argv[1]):
    if line.strip():
        a = json.loads(line)
        assess[a["partner_id"]] = a
plan = json.load(open(sys.argv[2]))

partners = []
for p in si.partners():
    d = si.derived(p)
    partners.append({
        "id": p["partner_id"], "name": p["name"], "tier": p["tier"], "regions": p["regions_active"],
        "pm": p["partner_manager"],
        "share": d["claude_share_of_ai_book_pct"], "momentum": d["momentum_index"],
        "certified": p["certified_by_quarter"], "usage": p["usage_index_partner_led_customers_by_quarter"],
        "regs": p["deal_registrations_by_quarter"], "support": p["applied_ai_support_hours_by_quarter"],
        "prod12": p["production_deployments_12m"], "prod2q": p["production_deployments_last_2q"],
        "pilots": p["open_pilots"], "stalled": p["pilots_stalled_90d"], "stories": p["public_stories"],
        "ai2q": p["ai_engagements_last_2q_est"], "cl2q": p["claude_engagements_last_2q"], "clprior": p["claude_engagements_prior_2q"],
        "win": p["deal_registration_win_rate_12m"],
        "notes": si.notes(p["partner_id"]),
        "a": assess[p["partner_id"]],
    })

out = ROOT / "site" / "intel.js"
out.write_text("window.INTEL = " + json.dumps({"program": si.program(), "partners": partners, "plan": plan}) + ";\n")
print(f"wrote {out}, {out.stat().st_size} bytes")
