"""Task ledger: the outer loop's memory, in (t, a, w) form.

One append-only JSONL per target model at ``<root>/runs/task-ledger/
<target>.jsonl``. ``t`` = an open refused thing; ``aw`` = the (a, w)
that closed it (``t_ts`` empty = first-try win). Contract and I/O rule:
``search.md``. The ledger names G — M1-side only, never enters a world.

    python3 -m harness.taskledger t --run R --target M --t "..." --detail "..."
    python3 -m harness.taskledger aw --run R --target M --a "..." --w PATH --artifact P [--t-ts TS] [--note N]
    python3 -m harness.taskledger show --target M [--open | --won]
    python3 -m harness.taskledger verify [--target M]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

T_KIND = "t"
AW_KIND = "aw"

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root(root: str | os.PathLike | None) -> Path:
    base = root or os.environ.get("TASK_LEDGER_DIR") or _REPO_ROOT
    return Path(base).expanduser().resolve()


def ledger_path(target: str, root: str | os.PathLike | None = None) -> Path:
    """Where the given target model's ledger lives (not created yet)."""
    name = re.sub(r"[^A-Za-z0-9._-]", "-", target)
    return _root(root) / "runs" / "task-ledger" / f"{name}.jsonl"


def _append(target: str, record: dict, root: str | os.PathLike | None) -> dict:
    path = ledger_path(target, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _require(fields: dict, names: tuple[str, ...]) -> None:
    missing = [n for n in names if not fields.get(n)]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")


def record_t(run: str, target: str, t: str, detail: str,
             root: str | os.PathLike | None = None) -> dict:
    """Append one open refused thing."""
    _require(locals(), ("run", "target", "t", "detail"))
    return _append(target, {
        "kind": T_KIND, "ts": _now(), "run": run,
        "target": target, "t": t, "detail": detail,
    }, root)


def record_aw(run: str, target: str, a: str, w: str, artifact: str,
              t_ts: str = "", note: str = "",
              root: str | os.PathLike | None = None) -> dict:
    """Append the (a, w) that closed a t (t_ts empty = first-try win)."""
    _require(locals(), ("run", "target", "a", "w", "artifact"))
    return _append(target, {
        "kind": AW_KIND, "ts": _now(), "run": run, "target": target,
        "t_ts": t_ts, "a": a, "w": w, "artifact": artifact, "note": note,
    }, root)


def entries(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """All records for one target model. Other models are not read."""
    return _lines(ledger_path(target, root))


def t_records(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    return [r for r in entries(target, root) if r["kind"] == T_KIND]


def aw_records(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    return [r for r in entries(target, root) if r["kind"] == AW_KIND]


def open_ts(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """Open t records: no aw closes them. This is the residual, by refusal."""
    closed = {r["t_ts"] for r in aw_records(target, root) if r.get("t_ts")}
    return [r for r in t_records(target, root) if r["ts"] not in closed]


def won(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """The (t -> a, w) table: every aw record."""
    return aw_records(target, root)


def counts(target: str, root: str | os.PathLike | None = None) -> dict:
    refused = len(t_records(target, root))
    won_ = len(aw_records(target, root))
    # open = t records no aw closes (open_ts), NOT refused-won: an aw with an
    # empty t_ts (first-try win) and unclosed t's otherwise make that wrong.
    return {"target": target, "refused": refused, "won": won_,
            "open": len(open_ts(target, root))}


def verify(targets: list[str] | None = None,
           root: str | os.PathLike | None = None) -> list[str]:
    """The checklist as code. Returns issue strings."""
    base = _root(root) / "runs" / "task-ledger"
    if targets is None:
        targets = sorted({p.stem for p in base.glob("*.jsonl")})
    issues: list[str] = []
    for target in targets:
        path = ledger_path(target, root)
        try:
            records = _lines(path)
        except json.JSONDecodeError as error:
            issues.append(f"{path.name}: does not parse as JSONL ({error})")
            continue
        seen_t = {r["ts"] for r in records if r["kind"] == T_KIND}
        for r in records:
            at = f"{path.name} @ {r.get('ts', '?')}"
            if r["kind"] == T_KIND and not r.get("t"):
                issues.append(f"{at}: t record missing 't'")
            if r["kind"] == AW_KIND:
                if r.get("t_ts") and r["t_ts"] not in seen_t:
                    issues.append(f"{at}: closes unknown t {r['t_ts']}")
                if not Path(r.get("artifact", "")).is_file():
                    issues.append(f"{at}: artifact missing on disk: {r.get('artifact')}")
    return issues


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Task ledger in (t, a, w) form")
    sub = parser.add_subparsers(dest="command", required=True)

    p_t = sub.add_parser("t", help="append an open refused thing")
    p_t.add_argument("--run", required=True)
    p_t.add_argument("--target", required=True)
    p_t.add_argument("--t", required=True, help="the refused thing")
    p_t.add_argument("--detail", required=True, help="the refusal's own words")

    p_aw = sub.add_parser("aw", help="append the (a, w) that closed a t")
    p_aw.add_argument("--run", required=True)
    p_aw.add_argument("--target", required=True)
    p_aw.add_argument("--a", required=True, help="the accepted ask")
    p_aw.add_argument("--w", required=True, help="the world (cwd path)")
    p_aw.add_argument("--artifact", required=True, help="delivered file")
    p_aw.add_argument("--t-ts", default="", help="ts of the t this closes (empty = first-try win)")
    p_aw.add_argument("--note", default="", help="what made it land")

    p_show = sub.add_parser("show", help="print records for one target")
    p_show.add_argument("--target", required=True)
    p_show.add_argument("--open", action="store_true", help="only open t records")
    p_show.add_argument("--won", action="store_true", help="only aw records")

    p_counts = sub.add_parser("counts", help="refused / won / open")
    p_counts.add_argument("--target", required=True)

    p_verify = sub.add_parser("verify", help="run the checklist over one or all ledgers")
    p_verify.add_argument("--target")

    args = parser.parse_args()
    root = os.environ.get("TASK_LEDGER_DIR")

    if args.command == "t":
        print(json.dumps(record_t(args.run, args.target, args.t, args.detail, root),
                         ensure_ascii=False))
    elif args.command == "aw":
        print(json.dumps(record_aw(args.run, args.target, args.a, args.w,
                                   args.artifact, args.t_ts, args.note, root),
                         ensure_ascii=False))
    elif args.command == "show":
        records = (open_ts(args.target, root) if args.open
                   else won(args.target, root) if args.won
                   else entries(args.target, root))
        for r in records:
            print(json.dumps(r, ensure_ascii=False))
    elif args.command == "counts":
        print(json.dumps(counts(args.target, root)))
    elif args.command == "verify":
        issues = verify([args.target] if args.target else None, root)
        for issue in issues:
            print(issue)
        raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    _cli()
