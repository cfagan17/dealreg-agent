"""Partner intelligence agent for services (SI) partners.

Step 1: for each partner, Claude reads the signals and our own team's notes through MCP tools,
decides whether the partner is leaning in or drifting, picks a play, and says whether a human
conversation is worth having and what it should achieve.

Step 2: Claude looks across all the assessments and plans the partner team's week, given
limited partner manager time.

Usage:
    python agent/partner_intel.py                 # assess all partners, then plan the week
    python agent/partner_intel.py --ids SI-02     # assess some partners only
    python agent/partner_intel.py --resume        # skip partners already assessed
    python agent/partner_intel.py --plan-only     # rebuild the weekly plan from saved assessments
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

import triage  # noqa: E402  (loads .env, shared helpers)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(os.environ.get("PARTNER_INTEL_OUTPUT_DIR", ROOT / "output" / "partner_intel"))
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MAX_TURNS = 15

SYSTEM_PROMPT = """You are a partner intelligence agent for the services partner program (systems integrators and
consultancies) of an AI model company. Partner managers have limited time. Your job is to tell them, for one
partner, whether that partner is leaning in or drifting, and whether a human conversation would change
anything, and if so what that conversation is for.

How to work:
1. Call get_program, then get_partner_signals and get_partner_notes for the partner.
2. Form a view, then call record_assessment exactly once.

The plays:
- Accelerate: the partner is leaning in and has momentum. Invest more (co-sell, named accounts, funding, a path to the next tier).
- Rescue: the partner was strong and is slipping. Find out why and try to save it before it shows up in the numbers.
- Develop: real potential, held back by a specific capability or program gap. Name the gap.
- Deprioritize: activity without results. Stop spending scarce human time beyond the basics.
- Maintain: healthy and on plan. No extra human touch needed. Saying so is valuable, because it frees time for others.

Judgment:
- Use the precomputed metrics. Do not redo arithmetic.
- Volume is not commitment. A huge partner can look strong on totals while Claude is a small and shrinking
  share of its AI work. A small partner can be all-in.
- Watch for signals that can be gamed or that mislead: certifications that don't turn into production
  deployments, deal registrations that don't convert, a momentum index pulled up by one noisy input.
- Production deployments and usage on partner-led customers are the strongest evidence. Notes from our own
  team explain the why behind the numbers.
- The goal of a human conversation must be one concrete outcome, not "check in" or "build the relationship".
- Be specific and plain. Cite the evidence. Say what could make your read wrong.
"""

PLAN_PROMPT = """You are helping a partner team plan its week. Below are assessments of every services partner.
Partner manager time is the scarce resource. There is room for 5 meaningful partner conversations this week
across the whole team. The next tier review is on {review}.

Choose the 5 conversations that will matter most, ranked. For each, say why it is worth the time this week
specifically, and the outcome it should produce. Then list every other partner with one short line on why it
is not on this week's list.

Return only JSON in this shape:
{{"conversations": [{{"rank": 1, "partner_id": "...", "partner": "...", "who": "...", "why_this_week": "...", "outcome": "..."}}],
  "not_this_week": [{{"partner_id": "...", "partner": "...", "reason": "..."}}],
  "summary": "Two or three plain sentences on the state of the ecosystem and where the team's time should go."}}

Assessments:
{assessments}
"""


async def assess_one(client, session, tools, pid: str, model: str) -> dict | None:
    messages = [{"role": "user", "content": f"Assess partner {pid}."}]
    transcript, recorded = [], None
    for _ in range(MAX_TURNS):
        resp = client.messages.create(model=model, max_tokens=4096, system=SYSTEM_PROMPT, tools=tools, messages=messages)
        content = [triage._block_dict(b) for b in resp.content]
        messages.append({"role": "assistant", "content": content})
        transcript.append({"role": "assistant", "content": content})
        uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not uses:
            break
        results = []
        for tu in uses:
            out = await session.call_tool(tu.name, dict(tu.input or {}))
            text = triage._tool_text(out)
            if tu.name == "record_assessment" and '"recorded"' in text:
                recorded = dict(tu.input)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text})
        messages.append({"role": "user", "content": results})
        transcript.append({"role": "tool_results", "content": results})
        if recorded:
            break
    (OUTPUT / "transcripts").mkdir(parents=True, exist_ok=True)
    with open(OUTPUT / "transcripts" / f"{pid}.json", "w") as f:
        json.dump(transcript, f, indent=2, default=str)
    return recorded


def load_assessments() -> dict:
    path = OUTPUT / "assessments.jsonl"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            a = json.loads(line)
            out[a["partner_id"]] = a
    return out


def plan_week(client, model: str) -> dict:
    sys.path.insert(0, str(ROOT / "server"))
    import si
    assessments = load_assessments()
    names = {p["partner_id"]: p["name"] for p in si.partners()}
    compact = [{"partner_id": k, "partner": names[k], **{f: v[f] for f in (
        "momentum", "play", "headline", "human_touch_needed", "who", "goal", "urgency", "tier_outlook", "confidence")}}
        for k, v in sorted(assessments.items())]
    prompt = PLAN_PROMPT.format(review=si.program()["next_tier_review"], assessments=json.dumps(compact, indent=1))
    resp = client.messages.create(model=model, max_tokens=4096, messages=[{"role": "user", "content": prompt}])
    text = "".join(getattr(b, "text", "") for b in resp.content).strip()
    start, end = text.find("{"), text.rfind("}")
    plan = json.loads(text[start:end + 1])
    (OUTPUT / "weekly_plan.json").write_text(json.dumps(plan, indent=2))
    return plan


async def run(ids, model, resume=False, plan_only=False, client=None):
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    if not plan_only:
        sys.path.insert(0, str(ROOT / "server"))
        import si
        ids = ids or [p["partner_id"] for p in si.partners()]
        if resume:
            done = set(load_assessments())
            ids = [i for i in ids if i not in done]
            print(f"Resuming: {len(done)} done, {len(ids)} to go", flush=True)
        else:
            (OUTPUT / "assessments.jsonl").write_text("")
        params = StdioServerParameters(
            command=sys.executable, args=[str(ROOT / "server" / "partner_intel_server.py")],
            env={**os.environ, "PARTNER_INTEL_OUTPUT_DIR": str(OUTPUT)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = triage._to_anthropic_tools((await session.list_tools()).tools)
                for pid in ids:
                    a = await assess_one(client, session, tools, pid, model)
                    print(f"{pid}  {(a or {}).get('play', 'NO DECISION'):<12} {(a or {}).get('momentum', '')}", flush=True)

    sys.path.insert(0, str(ROOT / "server"))
    import si
    if len(load_assessments()) < len(si.partners()):
        print("\nNot every partner is assessed yet. Run again with --resume, then the weekly plan is built.")
        return
    plan = plan_week(client, model)
    if plan:
        print("\nThis week:")
        for c in plan["conversations"]:
            print(f"  {c['rank']}. {c['partner']}: {c['outcome']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.ids, args.model, args.resume, args.plan_only))


if __name__ == "__main__":
    main()
