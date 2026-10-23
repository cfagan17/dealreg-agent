"""Score recorded decisions against the expected outcomes.

Usage:
    python eval/evaluate.py                                    # agent run (output/decisions.jsonl)
    python eval/evaluate.py output/baseline_decisions.jsonl    # rules-engine baseline

Writes output/eval_report.md (or <file>_report.md for other inputs).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["APPROVE", "REJECT", "RETURN", "ESCALATE"]


def load_decisions(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            out[d["registration_id"]] = d  # last one wins
    return out


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "decisions.jsonl"
    expected = {e["registration_id"]: e for e in json.load(open(ROOT / "data" / "expected_outcomes.json"))}
    got = load_decisions(path)

    rows, confusion = [], Counter()
    correct = rule_correct = wrong_approvals = missing = 0
    for rid, e in expected.items():
        d = got.get(rid)
        if not d:
            missing += 1
            rows.append((rid, e["expected_decision"], "MISSING", "", "no", e["why"]))
            continue
        ok = d["decision"] == e["expected_decision"]
        rule_ok = ok and any(r in d.get("rule_ids", []) for r in e["expected_rule"])
        correct += ok
        rule_correct += rule_ok
        if d["decision"] == "APPROVE" and e["expected_decision"] != "APPROVE":
            wrong_approvals += 1
        confusion[(e["expected_decision"], d["decision"])] += 1
        rows.append((rid, e["expected_decision"], d["decision"], ",".join(d.get("rule_ids", [])),
                     "yes" if ok else "**no**", e["why"]))

    n = len(expected)
    lines = [
        f"# Eval report: {path.name}",
        "",
        f"- Decisions correct: **{correct}/{n}** ({correct / n:.0%})",
        f"- Correct decision and correct rule cited: **{rule_correct}/{n}**",
        f"- Wrong approvals (the costly error): **{wrong_approvals}**",
        f"- Missing decisions: {missing}",
        "",
        "## Confusion matrix (rows = expected, columns = actual)",
        "",
        "| expected \\ actual | " + " | ".join(ORDER) + " |",
        "|---|" + "---|" * len(ORDER),
    ]
    for exp in ORDER:
        lines.append(f"| {exp} | " + " | ".join(str(confusion[(exp, a)]) for a in ORDER) + " |")
    lines += ["", "## Cases", "", "| id | expected | actual | rules cited | correct | test case |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows]

    report = "\n".join(lines) + "\n"
    out = path.with_name("eval_report.md" if path.name == "decisions.jsonl" else path.stem + "_report.md")
    out.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
