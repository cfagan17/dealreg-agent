"""Plumbing test: runs the full agent loop and MCP server with a scripted fake model
(no API key needed). The fake model calls a few tools and then records the rules-engine
baseline decision, so this checks wiring only. It says nothing about Claude's accuracy.

Usage: python tests/test_plumbing.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
os.environ["DEALREG_OUTPUT_DIR"] = tempfile.mkdtemp(prefix="dealreg-test-")
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))

import baseline_rules  # noqa: E402
import triage  # noqa: E402
import crm  # noqa: E402  (on sys.path via baseline_rules)


def _tool_use(i, name, args):
    return SimpleNamespace(type="tool_use", id=f"tu_{i}", name=name, input=args,
                           model_dump=lambda: {"type": "tool_use", "id": f"tu_{i}", "name": name, "input": args})


class FakeMessages:
    def create(self, *, messages, tools, **kw):
        assert {t["name"] for t in tools} >= {"get_rulebook", "find_accounts", "record_decision"}
        reg_id = messages[0]["content"].split()[-1].rstrip(".")
        step = sum(1 for m in messages if m["role"] == "assistant")
        reg = crm.get_registration(reg_id)
        if step == 0:
            calls = [_tool_use(0, "get_rulebook", {}), _tool_use(1, "get_registration", {"registration_id": reg_id})]
        elif step == 1:
            calls = [_tool_use(2, "find_accounts", {"name": reg["end_customer_name"] or "", "domain": reg["end_customer_domain"] or ""})]
        else:
            decision, rule = baseline_rules.decide(reg)
            calls = [_tool_use(3, "record_decision", {
                "registration_id": reg_id, "decision": decision, "rule_ids": [rule],
                "reasoning": "scripted test", "partner_message": "test",
                "route_to": "Partner manager" if decision == "ESCALATE" else ""})]
        return SimpleNamespace(content=calls, stop_reason="tool_use")


async def main():
    fake = SimpleNamespace(messages=FakeMessages())
    decisions = await triage.run(None, "fake-model", client=fake)
    out = Path(os.environ["DEALREG_OUTPUT_DIR"])
    logged = [json.loads(l) for l in (out / "decisions.jsonl").read_text().splitlines()]
    queue = (out / "review_queue.jsonl").read_text().splitlines()
    n = len(crm.incoming_registrations())
    assert len(decisions) == n and len(logged) == n, "every registration gets exactly one decision"
    assert len(queue) == sum(d["decision"] == "ESCALATE" for d in logged), "escalations land in the review queue"
    assert len(list((out / "transcripts").glob("*.json"))) == n
    print(f"\nPLUMBING OK: {n} registrations, {len(queue)} escalations queued, output in {out}")


if __name__ == "__main__":
    asyncio.run(main())
