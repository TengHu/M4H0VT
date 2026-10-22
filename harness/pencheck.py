"""Per-send pen verification from a Claude Code session trace.

The declared-pen law (world-craft `session.pen_law`): the declared model must
hold the pen through every monitor event, and a fallback that replaces the
author counts as a refusal. This tool turns the manual trace-reading into one
command:

    python3 -m harness.pencheck <trace.jsonl> [--declared MODEL] [--json] [--require-edit]

Reads the JSONL trace (one message per line, as written by Claude Code) and
reports per send:

    declared      the model passed with --declared (default claude-opus-5-5)
    models        assistant-turn count per served model
    held          every assistant turn served by the declared model AND no
                  safeguard flag notice in the trace
    flag          a "safeguards flagged this session" system notice was present
    edits_by      which model authored each Edit tool call (handoff leaves its
                  own signature on the file)
    result        final result message subtype + cost, when present

Exit 0 when held, 1 otherwise (with --require-edit, also require >=1 Edit
authored by the declared model). `--json` prints the machine-readable block
only. Unknown/absent model fields are reported as "?" and count against held.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

FLAG_MARKERS = ("safeguards flagged", "safeguards stopped")


def check(trace: Path, declared: str, require_edit: bool) -> dict:
    models: Counter[str] = Counter()
    edits_by: list[str] = []
    flag = False
    result = None
    with trace.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = rec.get("type")
            if kind == "assistant":
                msg = rec.get("message") or {}
                model = msg.get("model") or "?"
                models[model] += 1
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" \
                            and block.get("name") == "Edit":
                        edits_by.append(model)
            elif kind == "system":
                content = str(rec.get("content") or "")
                if any(marker in content for marker in FLAG_MARKERS):
                    flag = True
            elif kind == "result":
                result = {"subtype": rec.get("subtype"),
                          "cost_usd": rec.get("total_cost_usd")}
    held = (models and all(m == declared for m in models)
            and not flag
            and (len(edits_by) > 0 if require_edit else True)
            and all(m != "?" for m in models))
    return {
        "trace": str(trace),
        "declared": declared,
        "models": dict(models),
        "held": held,
        "flag": flag,
        "edits_by": edits_by,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-send pen verification from a session trace")
    parser.add_argument("trace", type=Path, help="session .jsonl trace path")
    parser.add_argument("--declared", default="claude-opus-5-5")
    parser.add_argument("--json", action="store_true", help="machine-readable output only")
    parser.add_argument("--require-edit", action="store_true",
                        help="also require >=1 Edit authored by the declared model")
    args = parser.parse_args()
    if not args.trace.is_file():
        print(f"trace not found: {args.trace}")
        return 1
    report = check(args.trace, args.declared, args.require_edit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        verdict = "HELD" if report["held"] else "NOT-HELD"
        print(f"pen: {verdict} (declared {report['declared']})")
        print(f"  assistant models: {report['models']}")
        print(f"  safeguard flag: {report['flag']}")
        print(f"  Edits by: {report['edits_by'] or 'none'}")
        if report["result"]:
            print(f"  result: {report['result']['subtype']} ${report['result']['cost_usd']}")
        if not report["held"]:
            print(f"  trace: {report['trace']}")
    return 0 if report["held"] else 1


if __name__ == "__main__":
    sys.exit(main())
