"""Builds site/data.js from a recorded agent run, so the page replays real output.

Usage: python site/build_data.py output/page_bundle.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
load = lambda n: json.load(open(D / n))

bundle = json.load(open(sys.argv[1]))
incoming = {r["registration_id"]: r for r in load("incoming_registrations.json")}
expected = {e["registration_id"]: e for e in load("expected_outcomes.json")}
partners = {p["partner_id"]: p for p in load("partners.json")}
accounts = {a["account_id"]: a for a in load("accounts.json")}


def j(text):
    try:
        return json.loads(text)
    except Exception:
        return text


def summarize(name, args, result):
    r = j(result)
    if name == "get_rulebook":
        return "Loaded the rulebook", None
    if name == "get_program_context":
        return "Loaded program settings", f"As of {r['as_of_date']}. Minimum ACV ${r['minimum_acv']:,}. Large deal ${r['large_deal_acv']:,}."
    if name == "get_registration":
        return "Read the registration", None
    if name == "get_partner":
        return "Looked up the partner", f"{r['name']} · {r['tier']} tier · {r['status']}" + (" · public sector authorized" if r.get("public_sector_authorized") else "")
    if name == "find_accounts":
        dm, nm = r["domain_matches"], r["name_matches"]
        q = " / ".join(x for x in [args.get("name"), args.get("domain")] if x)
        if dm:
            s = "Domain match: " + ", ".join(f"{a['name']} ({a['domain']})" for a in dm)
        elif nm:
            s = "No domain match. Name matches: " + ", ".join(f"{a['name']} ({a['domain']})" for a in nm)
        else:
            s = "No match in the CRM"
        return f"Searched the CRM for {q}", s
    if name == "get_account":
        return "Opened the account", f"{r['name']} · {r['segment']} · {r['customer_status']}" + (" · direct only" if r.get("direct_only") else "")
    if name == "get_open_opportunities":
        what = f"Checked direct opportunities" + (f" for {args['product']}" if args.get("product") else "")
        if not r:
            return what, "None open"
        return what, "; ".join(
            f"{o['opportunity_id']} ({o['product']}, {o['stage']}) created {o['days_created_before_reference']} days before the registration, last activity {o['days_since_last_activity']} days before" for o in r)
    if name == "get_partner_registrations":
        what = "Checked other partner registrations" + (f" for {args['product']}" if args.get("product") else "")
        if not r:
            return what, "None"
        out = []
        for x in r:
            s = f"{x['registration_id']} · {x['partner_name']} · {x.get('partner_role','Resale')} · {x['status']}"
            if x.get("expires_on"):
                s += f" · protected until {x['expires_on']}" if x.get("protection_active") else f" · expired {x['expires_on']}"
            if x.get("hours_between_submissions") is not None and x["status"] == "Pending":
                s += f" · submitted {x['hours_between_submissions']} hours apart"
            out.append(s)
        return what, "; ".join(out)
    if name == "get_internal_activity":
        notes = r if isinstance(r, list) else []
        if not notes:
            return "Checked our own team's notes", "No internal notes"
        return "Checked our own team's notes", " | ".join(f"{n['author_role']}, {n['date']}: {n['note']}" for n in notes)
    if name == "record_decision":
        return "Recorded the decision", None
    return name, None


cases = []
for rid, reg in incoming.items():
    d = bundle["decisions"][rid]
    steps = []
    calls = {}
    for turn in bundle["transcripts"].get(rid, []):
        for c in turn["content"]:
            if c.get("type") == "tool_use":
                calls[c["id"]] = c
            elif c.get("type") == "tool_result":
                call = calls.get(c["tool_use_id"])
                if call:
                    title, detail = summarize(call["name"], call["input"], c["content"])
                    steps.append({"tool": call["name"], "title": title, "detail": detail})
    p = partners[reg["partner_id"]]
    e = expected[rid]
    b = bundle["baseline"][rid]
    cases.append({
        "id": rid,
        "hard": bool(e.get("hard_case")),
        "partner": f"{p['name']} ({p['tier']})",
        "role": reg.get("partner_role", "Resale"),
        "customer": reg.get("end_customer_name"),
        "domain": reg.get("end_customer_domain"),
        "product": reg.get("product"),
        "acv": reg.get("estimated_acv"),
        "currency": reg.get("currency", "USD"),
        "close": reg.get("expected_close_date"),
        "contact": (reg.get("customer_contact") or {}).get("name") if reg.get("customer_contact") else None,
        "channel": reg.get("submission_channel", "Partner portal"),
        "submitted": reg["submitted_at"],
        "notes": reg.get("partner_notes") or "",
        "raw": reg.get("raw_submission"),
        "decision": d["decision"],
        "rules": d.get("rule_ids", []),
        "route": d.get("route_to"),
        "reasoning": d["reasoning"],
        "message": d["partner_message"],
        "expected": e["expected_decision"],
        "why": e["why"],
        "baseline": b["decision"],
        "steps": steps,
    })

out = ROOT / "site" / "data.js"
out.write_text("window.CASES = " + json.dumps(cases, indent=0) + ";\n")
print(f"wrote {out} with {len(cases)} cases, {out.stat().st_size} bytes")
