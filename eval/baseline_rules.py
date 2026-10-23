"""A hand-coded rules engine for the same rulebook, used as a baseline for the agent.

It reads only structured fields, so it is immune to instructions hidden in partner notes,
but it also cannot notice when the notes contradict the CRM (the R11 judgment call).

Usage: python eval/baseline_rules.py   (writes output/baseline_decisions.jsonl)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import crm  # noqa: E402


def decide(reg: dict) -> tuple[str, str]:
    prog = crm.program()
    partner = crm.get_partner(reg["partner_id"]) or {}

    # R1
    if partner.get("status") != "Active" or partner.get("tier") not in prog["eligible_tiers"]:
        return "REJECT", "R1"
    # R2
    required = ["end_customer_name", "end_customer_domain", "product", "estimated_acv",
                "expected_close_date", "customer_contact"]
    if any(not reg.get(k) for k in required):
        return "RETURN", "R2"  # includes free-text submissions, which a rules engine can't parse
    if str(reg["customer_contact"].get("name", "")).strip().upper() in {"TBD", "TBA", "N/A", ""}:
        return "RETURN", "R2"
    if reg["product"] not in prog["products"]:
        return "RETURN", "R2"  # multiple or unknown products
    submitted = datetime.fromisoformat(reg["submitted_at"]).date()
    if datetime.fromisoformat(reg["expected_close_date"]).date() < submitted:
        return "RETURN", "R2"
    # R3
    acv_usd = reg["estimated_acv"] * prog["fx_rates_to_usd"].get(reg.get("currency", "USD"), 1.0)
    if acv_usd < prog["minimum_acv"]:
        return "REJECT", "R3"
    # R4
    m = crm.find_accounts(reg["end_customer_name"], reg["end_customer_domain"])
    if len(m["domain_matches"]) == 1:
        account = m["domain_matches"][0]
    elif not m["domain_matches"] and not m["name_matches"]:
        account = None
    else:
        return "ESCALATE", "R4"

    if account:
        # R5
        if account["active_contract"] and partner["tier"] != "Premier":
            return "REJECT", "R5"
        # R6
        if account["direct_only"]:
            return "ESCALATE", "R6"
        # R7
        if account["segment"] == "Public Sector" and not partner["public_sector_authorized"]:
            return "REJECT", "R7"
        # R8
        for o in crm.open_opportunities(account["account_id"], reg["product"], reg["submitted_at"]):
            age, idle = o["days_created_before_reference"], o["days_since_last_activity"]
            if abs(age) <= 30:
                return "ESCALATE", "R8"
            if idle >= 60:
                continue
            if idle <= 30:
                return "REJECT", "R8"
            return "ESCALATE", "R8"
        # R9 and R10
        for r in crm.partner_registrations(account["account_id"], reg["product"], reg["submitted_at"]):
            if r.get("partner_role", "Resale") != reg.get("partner_role", "Resale"):
                continue
            same_partner = r["partner_id"] == reg["partner_id"]
            if r["status"] == "Approved" and r.get("protection_active"):
                if same_partner:
                    if r["days_of_protection_left"] > 30:
                        return "REJECT", "R10"
                else:
                    return "REJECT", "R9"
            if r["status"] == "Pending" and not same_partner and r["hours_between_submissions"] <= 24:
                return "ESCALATE", "R9"
    # R11 (only the part a rules engine can check)
    if acv_usd >= prog["large_deal_acv"]:
        return "ESCALATE", "R11"
    return "APPROVE", "R12"


def main():
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    with open(out / "baseline_decisions.jsonl", "w") as f:
        for reg in crm.incoming_registrations():
            d, rule = decide(reg)
            f.write(json.dumps({"registration_id": reg["registration_id"], "decision": d, "rule_ids": [rule]}) + "\n")
            print(f"{reg['registration_id']}  {d:<9} {rule}")


if __name__ == "__main__":
    main()
