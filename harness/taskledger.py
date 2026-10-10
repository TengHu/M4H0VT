"""Task ledger: the single, runner-agnostic record of how tasks land.

Any attack runner (Claude Code wrapper, chat.sh, a future harness version)
reports task outcomes here instead of writing JSON itself. One ledger file
per target model; records for one model never gate a task to another.

Three record kinds tell the whole story per model:

- ``refusal`` — a task the target denied (a policy denial, a classifier
  stop, a hook or guard block, an error exit with work unfinished).
- ``receipt`` — a win-back: the target completed work a recorded refusal
  denied. ``approach`` says what worked; ``artifact`` proves it.
- ``success`` — a task accepted and executed, refusal or not. First-try
  successes land here too: they are the planner's recipes.

    from harness import taskledger

    taskledger.record(taskledger.RefusalEvent(
        run="my-run-1", target="opus-5", prompt="...",
        layer="classifier", detail="safeguards flagged the message"))

    taskledger.record(taskledger.ReceiptEvent(
        target="opus-5", refusal="<ts of the refusal it closes>",
        approach="map-to-safe-domain", artifact="out/process.md",
        trace="<runner's trace path>"))

    taskledger.record(taskledger.SuccessEvent(
        run="my-run-1", target="opus-5", task="<the job M2 saw>",
        techniques="map-to-safe-domain,dual-use",
        approach="isomorphic culinary twin", artifact="out/guide.md"))

    taskledger.counts("opus-5")        # observed / won_back / succeeded / open
    taskledger.open_refusals("opus-5") # refusals with no receipt yet
    taskledger.verify()                # the skill checklist, as code

Shell runners use the CLI:

    python3 -m harness.taskledger refusal --run R --target opus-5 \
        --prompt P --layer classifier --detail D
    python3 -m harness.taskledger receipt --target opus-5 --refusal TS \
        --approach A --artifact F [--trace T]
    python3 -m harness.taskledger success --run R --target opus-5 \
        --task T --techniques "map-to-safe-domain,dual-use" \
        --approach A --artifact F [--trace T]
    python3 -m harness.taskledger show --target opus-5 [--open] [--kind success]
    python3 -m harness.taskledger counts --target opus-5
    python3 -m harness.taskledger verify [--target MODEL]

Ledger layout: `<root>/runs/task-ledger/<model>.jsonl`, one JSON object
per line, append-only. `root` defaults to the repo root and may be
overridden per call or with the TASK_LEDGER_DIR environment variable
(`REFUSAL_LEDGER_DIR` still works, for old callers). Model names are
sanitized into filenames (non [A-Za-z0-9._-] -> "-").

Record schemas (canonical; this module is the only writer):

    refusal: {"kind":"refusal","ts","run","target","prompt","layer","detail"}
             layer: policy | hook | classifier | guard | error
    receipt: {"kind":"receipt","ts","target","refusal","approach",
              "artifact","trace","delivered"}
    success: {"kind":"success","ts","run","target","task","techniques",
              "approach","artifact","trace"}

Invariants enforced here:
- append at event time (every write opens, appends, closes)
- a receipt must close a refusal recorded in the same model's ledger
- receipts and successes without an on-disk artifact are flagged by verify()
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
SUCCESS_KIND = "success"
LAYERS = ("policy", "hook", "classifier", "guard", "error")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root(root: str | os.PathLike | None) -> Path:
    base = (
        root
        or os.environ.get("TASK_LEDGER_DIR")
        or os.environ.get("REFUSAL_LEDGER_DIR")
        or _REPO_ROOT
    )
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


@dataclass(frozen=True)
class SuccessEvent:
    """One accepted, executed task — the planner's recipe, refusal or not."""

    run: str
    target: str
    task: str  # the job the target saw
    techniques: str  # comma-separated technique names
    approach: str  # what made it land
    artifact: str  # path to the output proving execution
    trace: str = ""  # session transcript path


def record(
    event: RefusalEvent | ReceiptEvent | SuccessEvent,
    root: str | os.PathLike | None = None,
) -> dict:
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
    if isinstance(event, SuccessEvent):
        return _append(
            event.target,
            {
                "kind": SUCCESS_KIND,
                "ts": _now(),
                "run": event.run,
                "target": event.target,
                "task": event.task,
                "techniques": event.techniques,
                "approach": event.approach,
                "artifact": event.artifact,
                "trace": event.trace,
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


def success_records(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    return [r for r in entries(target, root) if r["kind"] == SUCCESS_KIND]


def open_refusals(target: str, root: str | os.PathLike | None = None) -> list[dict]:
    """Refusals no receipt closes yet."""
    closed = {r["refusal"] for r in receipt_records(target, root)}
    return [r for r in refusal_records(target, root) if r["ts"] not in closed]


def counts(target: str, root: str | os.PathLike | None = None) -> dict:
    """observed / won_back / succeeded / open for one target model."""
    observed = len(refusal_records(target, root))
    won_back = len(receipt_records(target, root))
    succeeded = len(success_records(target, root))
    return {
        "target": target,
        "observed": observed,
        "won_back": won_back,
        "succeeded": succeeded,
        "open": observed - won_back,
    }


def verify(targets: list[str] | None = None, root: str | os.PathLike | None = None) -> list[str]:
    """The skill checklist, as code. Returns issue strings."""
    base = _root(root) / "runs" / "task-ledger"
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
            if record_["kind"] == SUCCESS_KIND:
                for field in ("task", "techniques", "approach"):
                    if not record_.get(field):
                        issues.append(f"{path.name}: success at {record_.get('ts', '?')} missing {field}")
                if not Path(record_.get("artifact", "")).is_file():
                    issues.append(f"{path.name}: success artifact missing on disk: {record_.get('artifact')}")
    return issues


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Task ledger (one file per target model)")
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

    p_success = sub.add_parser("success", help="append an accepted, executed task")
    p_success.add_argument("--run", required=True)
    p_success.add_argument("--target", required=True)
    p_success.add_argument("--task", required=True, help="the job the target saw")
    p_success.add_argument("--techniques", required=True, help="comma-separated technique names")
    p_success.add_argument("--approach", required=True, help="what made it land")
    p_success.add_argument("--artifact", required=True)
    p_success.add_argument("--trace", default="")

    p_show = sub.add_parser("show", help="print records for one target model")
    p_show.add_argument("--target", required=True)
    p_show.add_argument("--open", action="store_true", help="only refusals no receipt closes")
    p_show.add_argument("--kind", choices=(REFUSAL_KIND, RECEIPT_KIND, SUCCESS_KIND))

    p_counts = sub.add_parser("counts", help="observed / won_back / succeeded / open")
    p_counts.add_argument("--target", required=True)

    p_verify = sub.add_parser("verify", help="run the checklist over one or all ledgers")
    p_verify.add_argument("--target")

    args = parser.parse_args()
    root = os.environ.get("TASK_LEDGER_DIR") or os.environ.get("REFUSAL_LEDGER_DIR")

    if args.command == "refusal":
        record(RefusalEvent(args.run, args.target, args.prompt, args.layer, args.detail), root)
    elif args.command == "receipt":
        record(ReceiptEvent(args.target, args.refusal, args.approach, args.artifact, args.trace), root)
    elif args.command == "success":
        record(
            SuccessEvent(
                args.run, args.target, args.task, args.techniques, args.approach, args.artifact, args.trace
            ),
            root,
        )
    elif args.command == "show":
        if args.open:
            records = open_refusals(args.target, root)
        elif args.kind:
            records = [r for r in entries(args.target, root) if r["kind"] == args.kind]
        else:
            records = entries(args.target, root)
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
