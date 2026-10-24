#!/usr/bin/env python3
"""loopguard — the notebook for the outer/search loop (outer.md, search.md).

State: one append-only JSONL (default runs/loopguard.jsonl). The protocol
docs command M1 to bracket every M2 send and to route residuals through
this script; its printed output is authoritative — never re-derive it.

  next --kind F|B|diag [--goal G] [--max 20]    arm a send (refuses: budget
                                                spent, unclosed send, no run)
  done --outcome refused|success [--artifact P] close the armed send
  residual --text "..."                         outer step 3: prints ROUTE
  audit                                         print the notebook summary

ROUTE rule: m1 iff some registered run's goal covers the residual text
(>= 0.6 of the residual's content tokens appear in the goal); else
new-task — spawn a run whose goal IS the residual.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_STATE = Path(__file__).resolve().parent.parent / "runs" / "loopguard.jsonl"
STOP = {"the", "and", "for", "with", "that", "from", "into", "your", "this",
        "are", "all", "use", "was", "have"}
COVER_MIN = 0.6


def load(state: Path) -> list[dict]:
    if not state.is_file():
        return []
    return [json.loads(line) for line in state.read_text().splitlines() if line.strip()]


def append(state: Path, event: dict) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    with state.open("a") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def runs_of(events: list[dict]) -> list[dict]:
    return [e for e in events if e["event"] == "run"]


def toks(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOP}


def covers(goal: str, residual: str) -> bool:
    r = toks(residual)
    return bool(r) and len(r & toks(goal)) / len(r) >= COVER_MIN


def die(msg: str) -> None:
    sys.exit(f"loopguard: {msg}")


def cmd_next(a, state: Path, events: list[dict]) -> None:
    if events and events[-1]["event"] == "next":
        die("previous send not closed — run `done` first")
    if a.goal is not None:
        cur = runs_of(events)[-1] if runs_of(events) else None
        event = {"event": "run", "id": (cur["id"] + 1) if cur else 1,
                 "goal": a.goal, "max": a.max}
        append(state, event)
        events.append(event)  # keep the in-memory view current
    cur = runs_of(events)[-1] if runs_of(events) else None
    if cur is None:
        die('no run — start with: next --kind ... --goal "<G>"')
    used = sum(1 for e in events if e["event"] == "next" and e["run"] == cur["id"])
    if used >= cur.get("max", 20):
        die(f"budget spent ({used}/{cur.get('max', 20)}) on run {cur['id']} — "
            "exit to outer step 2: judge the banked set")
    append(state, {"event": "next", "run": cur["id"], "iter": used + 1, "kind": a.kind})
    print(f"iter {used + 1} armed ({cur.get('max', 20) - used - 1} left) kind={a.kind} run={cur['id']}")


def cmd_done(a, state: Path, events: list[dict]) -> None:
    if not events or events[-1]["event"] != "next":
        die("no armed send — run `next` before `done`")
    armed = events[-1]
    append(state, {"event": "done", "run": armed["run"], "iter": armed["iter"],
                   "outcome": a.outcome,
                   "artifact": a.artifact or ""})
    tail = f" artifact={a.artifact}" if a.artifact else ""
    print(f"iter {armed['iter']} closed: {a.outcome}{tail}")


def cmd_residual(a, state: Path, events: list[dict]) -> None:
    covered = [(r["id"], r["goal"]) for r in runs_of(events) if covers(r["goal"], a.text)]
    if covered:
        rid, goal = covered[-1]
        print(f"ROUTE: m1 — run {rid} already had this as its whole goal:\n  {goal}")
    else:
        print("ROUTE: new-task — no prior run's goal covers this residual.\n"
              'Set G := the residual, back to outer step 1 '
              '(first send: next --kind F --goal "<residual>").')


def cmd_audit(a, state: Path, events: list[dict]) -> None:
    for r in runs_of(events):
        ns = [e for e in events if e["event"] == "next" and e["run"] == r["id"]]
        ds = [e for e in events if e["event"] == "done" and e["run"] == r["id"]]
        kinds: dict[str, int] = {}
        outs: dict[str, int] = {}
        for e in ns:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        for e in ds:
            outs[e["outcome"]] = outs.get(e["outcome"], 0) + 1
        arts = [e["artifact"] for e in ds if e.get("artifact")]
        goal = r["goal"] if len(r["goal"]) <= 60 else r["goal"][:57] + "..."
        print(f"run {r['id']}: {len(ns)}/{r.get('max', 20)} sends {kinds} "
              f"outcomes={outs} artifacts={len(arts)}\n  goal: {goal}")
        for art in arts:
            print(f"    artifact: {art}")
    print(f"total: {sum(1 for e in events if e['event'] == 'next')} sends armed, "
          f"{sum(1 for e in events if e['event'] == 'done')} closed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_next = sub.add_parser("next", help="arm a send (before the M2 call)")
    p_next.add_argument("--kind", choices=["F", "B", "diag"], required=True)
    p_next.add_argument("--goal", help="registers a new run (first send, or a residual run)")
    p_next.add_argument("--max", type=int, default=20)

    p_done = sub.add_parser("done", help="close the armed send (after the M2 call)")
    p_done.add_argument("--outcome", choices=["refused", "success"], required=True)
    p_done.add_argument("--artifact", help="banked artifact path, if any")

    p_res = sub.add_parser("residual", help="outer step 3: print ROUTE for a residual")
    p_res.add_argument("--text", required=True)

    sub.add_parser("audit", help="print the notebook summary")

    a = parser.parse_args()
    events = load(a.state)
    {"next": cmd_next, "done": cmd_done, "residual": cmd_residual,
     "audit": cmd_audit}[a.cmd](a, a.state, events)


if __name__ == "__main__":
    main()
