"""Refusal ledger: the single, runner-agnostic refusal-handling implementation.

Any attack runner (Claude Code wrapper, chat.sh, a future harness version)
reports refusals and win-backs here instead of writing JSON itself. One
ledger file per target model; refusals recorded for one model never gate a
consult to another.

    from harness import refusals

    refusals.record(refusals.RefusalEvent(
        run="my-run-1", target="opus-5", prompt="...",
        layer="classifier", detail="safeguards flagged the message"))

    refusals.record(refusals.ReceiptEvent(
        target="opus-5", refusal="<ts of the refusal it closes>",
        approach="map-to-safe-domain", artifact="out/process.md",
        trace="~/.claude/projects/.../session.jsonl"))

    refusals.counts("opus-5")        # observed / won_back / open
    refusals.open_refusals("opus-5") # refusals with no receipt yet
    refusals.verify()                # the skill checklist, as code

Shell runners use the CLI:

    python3 -m harness.refusals refusal --run R --target opus-5 \
        --prompt P --layer classifier --detail D
    python3 -m harness.refusals receipt --target opus-5 --refusal TS \
        --approach A --artifact F [--trace T]
    python3 -m harness.refusals show --target opus-5 [--open]
    python3 -m harness.refusals counts --target opus-5
    python3 -m harness.refusals verify [--target MODEL]

Ledger layout: `<root>/runs/refusal-ledger/<model>.jsonl`, one JSON object
per line, append-only. `root` defaults to the repo root and may be
overridden per call or with the REFUSAL_LEDGER_DIR environment variable.
Model names are sanitized into filenames (non [A-Za-z0-9._-] -> "-").

Record schemas (canonical; this module is the only writer):

    refusal: {"kind":"refusal","ts","run","target","prompt","layer","detail"}
             layer: policy | hook | classifier | guard | error
    receipt: {"kind":"receipt","ts","target","refusal","approach",
              "artifact","trace","delivered"}

Invariants enforced here:
- append at event time (every write opens, appends, closes)
- a receipt must close a refusal recorded in the same model's ledger
- receipts without an on-disk artifact are flagged by verify()
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REFUSAL_KIND = "refusal"
RECEIPT_KIND = "receipt"
LAYERS = ("policy", "hook", "classifier", "guard", "error")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root(root: str | os.PathLike | None) -> Path:
    base = root or os.environ.get("REFUSAL_LEDGER_DIR") or _REPO_ROOT
    return Path(base).expanduser().resolve()


def ledger_path(target: str, root: str | os.PathLike | None = None) -> Path:
    """Where the given target model's ledger lives (not created yet)."""
    name = re.sub(r"[^A-Za-z0-9._-]", "-", target)
    return _root(root) / "runs" / "refusal-ledger" / f"{name}.jsonl"


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


@dataclass(frozen=True)
class RefusalEvent:
    """One refusal the target committed: a denied call, a classifier stop,
    a guard block, or an error exit with work unfinished."""

    run: str
    target: str
    prompt: str
    layer: str
    detail: str


@dataclass(frozen=True)
class ReceiptEvent:
    """One win-back: the target completed work a recorded refusal denied."""

    target: str
    refusal: str  # ts of the refusal this closes
    approach: str  # what worked: framing, job change, paradigm
    artifact: str  # path to the output proving delivery
    trace: str = ""  # session transcript path


def record(event: RefusalEvent | ReceiptEvent, root: str | os.PathLike | None = None) -> dict:
    """Append one event to the target model's ledger, at event time."""
    if isinstance(event, RefusalEvent):
        if event.layer not in LAYERS:
            raise ValueError(f"layer must be one of {LAYERS}, got {event.layer!r}")
        return _append(
            event.target,
            {
                "kind": REFUSAL_KIND,
                "ts": _now(),
                "run": event.run,
                "target": event.target,
                "prompt": event.prompt,
                "layer": event.layer,
                "detail": event.detail,
            },
            root,
        )
    entries_ = entries(event.target, root)
    refusal_ts = {r["ts"] for r in entries_ if r["kind"] == REFUSAL_KIND}
    if event.refusal not in refusal_ts:
        raise ValueError(
            f"receipt closes unknown refusal {event.refusal!r} "
            f"for target {event.target!r}; read {ledger_path(event.target, root)} first"
        )
    return _append(
        event.target,
        {
            "kind": RECEIPT_KIND,
            "ts": _now(),
            "target": event.target,
            "refusal": event.refusal,
            "approach": event.approach,
            "artifact": event.artifact,
            "trace": event.trace,
            "delivered": True,
        },
        root,
    )


def entries(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """All records for one target model. Other models are not read."""
    return _lines(ledger_path(target, root))


def refusal_records(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    return [r for r in entries(target, root) if r["kind"] == REFUSAL_KIND]


def receipt_records(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    return [r for r in entries(target, root) if r["kind"] == RECEIPT_KIND]


def open_refusals(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """Refusals no receipt closes yet."""
    closed = {r["refusal"] for r in receipt_records(target, root)}
    return [r for r in refusal_records(target, root) if r["ts"] not in closed]


def counts(target: str, root: str | os.PathLike | None = None) -> dict:
    """observed / won_back / open for one target model."""
    observed = len(refusal_records(target, root))
    won_back = len(receipt_records(target, root))
    return {"target": target, "observed": observed, "won_back": won_back, "open": observed - won_back}


def verify(targets: list[str] | None = None, root: str | os.PathLike | None = None) -> list[str]:
    """The refusal-learnings checklist, as code. Returns issue strings."""
    base = _root(root) / "runs" / "refusal-ledger"
    if targets is None:
        targets = sorted({p.stem for p in base.glob("*.jsonl") if p.name != "legacy.jsonl"})
    issues: list[str] = []
    for target in targets:
        path = ledger_path(target, root)
        try:
            records = _lines(path)
        except json.JSONDecodeError as error:
            issues.append(f"{path.name}: does not parse as JSONL ({error})")
            continue
        seen_refusals = {r["ts"] for r in records if r["kind"] == REFUSAL_KIND}
        for record_ in records:
            if not record_.get("target"):
                issues.append(f"{path.name}: record at {record_.get('ts', '?')} missing target")
            if record_["kind"] == REFUSAL_KIND and not record_.get("layer"):
                issues.append(f"{path.name}: refusal at {record_.get('ts', '?')} missing layer")
            if record_["kind"] == RECEIPT_KIND:
                if record_.get("refusal") not in seen_refusals:
                    issues.append(f"{path.name}: receipt closes unknown refusal {record_.get('refusal')}")
                if not Path(record_.get("artifact", "")).is_file():
                    issues.append(f"{path.name}: receipt artifact missing on disk: {record_.get('artifact')}")
    return issues


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Refusal ledger (one file per target model)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_refusal = sub.add_parser("refusal", help="append a refusal record")
    p_refusal.add_argument("--run", required=True)
    p_refusal.add_argument("--target", required=True, help="model that refused")
    p_refusal.add_argument("--prompt", required=True)
    p_refusal.add_argument("--layer", required=True, choices=LAYERS)
    p_refusal.add_argument("--detail", required=True)

    p_receipt = sub.add_parser("receipt", help="append a receipt closing a refusal")
    p_receipt.add_argument("--target", required=True)
    p_receipt.add_argument("--refusal", required=True, help="ts of the refusal it closes")
    p_receipt.add_argument("--approach", required=True)
    p_receipt.add_argument("--artifact", required=True)
    p_receipt.add_argument("--trace", default="")

    p_show = sub.add_parser("show", help="print records for one target model")
    p_show.add_argument("--target", required=True)
    p_show.add_argument("--open", action="store_true", help="only refusals no receipt closes")

    p_counts = sub.add_parser("counts", help="observed / won_back / open for one target model")
    p_counts.add_argument("--target", required=True)

    p_verify = sub.add_parser("verify", help="run the checklist over one or all ledgers")
    p_verify.add_argument("--target")

    args = parser.parse_args()
    root = os.environ.get("REFUSAL_LEDGER_DIR")

    if args.command == "refusal":
        record(RefusalEvent(args.run, args.target, args.prompt, args.layer, args.detail), root)
    elif args.command == "receipt":
        record(ReceiptEvent(args.target, args.refusal, args.approach, args.artifact, args.trace), root)
    elif args.command == "show":
        records = open_refusals(args.target, root) if args.open else entries(args.target, root)
        for record_ in records:
            print(json.dumps(record_, ensure_ascii=False))
    elif args.command == "counts":
        print(json.dumps(counts(args.target, root)))
    elif args.command == "verify":
        issues = verify([args.target] if args.target else None, root)
        for issue in issues:
            print(issue)
        raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    _cli()
