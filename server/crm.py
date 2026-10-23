"""Read-only access to the sample CRM and partner data, plus the decision log.

The tools do the deterministic work (lookups, date math, fuzzy name matching) so the
model can spend its effort on judgment: which rule applies and why.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = Path(os.environ.get("DEALREG_OUTPUT_DIR", ROOT / "output"))

NAME_MATCH_THRESHOLD = 0.72


def _load(name: str):
    with open(DATA / name) as f:
        return json.load(f)


def program() -> dict:
    return _load("program.json")


def as_of() -> date:
    return date.fromisoformat(program()["as_of_date"])


def _to_date(value: str) -> date:
    return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)


# ---------- registrations ----------

def incoming_registrations() -> list[dict]:
    return _load("incoming_registrations.json")


def get_registration(registration_id: str) -> dict | None:
    return next((r for r in incoming_registrations() if r["registration_id"] == registration_id), None)


# ---------- partners ----------

def get_partner(partner_id: str) -> dict | None:
    return next((p for p in _load("partners.json") if p["partner_id"] == partner_id), None)


# ---------- accounts ----------

def _norm_domain(d: str | None) -> str:
    d = (d or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    return d.removeprefix("www.").rstrip("/")


def _norm_name(n: str | None) -> str:
    n = (n or "").lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company)\b", " ", n)
    return " ".join(n.split())


def find_accounts(name: str | None = None, domain: str | None = None) -> dict:
    accounts = _load("accounts.json")
    dom = _norm_domain(domain)
    nm = _norm_name(name)

    domain_matches = [a for a in accounts if dom and _norm_domain(a["domain"]) == dom]

    name_matches = []
    for a in accounts:
        if not nm:
            break
        score = SequenceMatcher(None, nm, _norm_name(a["name"])).ratio()
        if score >= NAME_MATCH_THRESHOLD:
            name_matches.append({**a, "name_similarity": round(score, 2)})
    name_matches.sort(key=lambda a: -a["name_similarity"])

    return {
        "searched": {"name": name, "domain": domain},
        "domain_matches": domain_matches,
        "name_matches": name_matches,
        "note": "Exact domain match is the strongest signal. A name match whose domain differs, "
                "or several plausible name matches, means the match is uncertain.",
    }


def get_account(account_id: str) -> dict | None:
    return next((a for a in _load("accounts.json") if a["account_id"] == account_id), None)


# ---------- opportunities ----------

def open_opportunities(account_id: str, product: str | None = None,
                       reference_date: str | None = None) -> list[dict]:
    ref = _to_date(reference_date) if reference_date else as_of()
    out = []
    for o in _load("opportunities.json"):
        if o["account_id"] != account_id or o["status"] != "Open":
            continue
        if product and o["product"] != product:
            continue
        created = _to_date(o["created_date"])
        last = _to_date(o["last_activity_date"])
        out.append({
            **o,
            "reference_date": ref.isoformat(),
            "days_created_before_reference": (ref - created).days,
            "days_since_last_activity": (ref - last).days,
        })
    return out


# ---------- existing registrations ----------

def partner_registrations(account_id: str, product: str | None = None,
                          reference_datetime: str | None = None) -> list[dict]:
    prog = program()
    today = as_of()
    ref_dt = datetime.fromisoformat(reference_datetime) if reference_datetime else None
    out = []
    for r in _load("existing_registrations.json"):
        if r["account_id"] != account_id:
            continue
        if product and r["product"] != product:
            continue
        partner = get_partner(r["partner_id"]) or {}
        rec = {**r, "partner_name": partner.get("name"), "partner_tier": partner.get("tier")}
        if r["status"] == "Approved" and r.get("approved_date"):
            days = prog["protection_days"].get(partner.get("tier"), 90)
            expires = _to_date(r["approved_date"]) + timedelta(days=days)
            rec.update({
                "protection_days": days,
                "expires_on": expires.isoformat(),
                "days_of_protection_left": (expires - today).days,
                "protection_active": expires >= today,
            })
        if ref_dt:
            delta = abs((ref_dt - datetime.fromisoformat(r["submitted_at"])).total_seconds()) / 3600
            rec["hours_between_submissions"] = round(delta, 1)
        out.append(rec)
    return out


# ---------- internal activity ----------

def internal_activity(account_id: str) -> list[dict]:
    return [n for n in _load("internal_activity.json") if n["account_id"] == account_id]


# ---------- decision log ----------

VALID_DECISIONS = {"APPROVE", "REJECT", "RETURN", "ESCALATE"}


def record_decision(record: dict) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    record = {**record, "recorded_at": datetime.now().isoformat(timespec="seconds")}
    with open(OUTPUT / "decisions.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    if record["decision"] == "ESCALATE":
        with open(OUTPUT / "review_queue.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")
    return record
