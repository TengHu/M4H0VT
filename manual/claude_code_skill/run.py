#!/usr/bin/env python3
"""Call Claude Code the way a person would: pick a directory, it loads that
directory's CLAUDE.md, skills, and settings, and you watch it work.

One prompt per call. This is the starting point, not a session manager.

    from run import Settings, claude

    async for event in claude("Fix the crash in utils.py", cwd="/any/project"):
        if event.kind == "text":
            print(event.text, end="", flush=True)
        elif event.kind == "tool":
            print(event.name, event.detail)

    async for event in claude(
        "Add a test",
        cwd="/any/project",
        settings=Settings(model="sonnet", append="Prefer a small diff."),
        resume=session_id,
    ):
        ...

Pass `Settings(policy=Policy.from_file("policy.json"))` (or `--policy-file` on the
command line) to choose the session's tools, MCP servers, and file/URL/command
rules. The policy is then the session's only configuration; see policy.py.

Pass `--run <slug>` (or `Settings(run_id=...)`) to record every refusal this
session commits (denied policy calls, error exits) into the shared refusal
ledger via `harness.refusals` — one file per target model, runner-agnostic.

The done event (and ClaudeError) carries `transcript`: the session's full JSONL
trace that Claude Code keeps on disk. Subagent traces sit next to it in
`<transcript without .jsonl>/subagents/agent-*.jsonl`, each with a `.meta.json`
whose `toolUseId` points back to the Agent call in the main transcript.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    HookMatcher,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from policy import Policy

# Same files an interactive `claude` in that directory would read.
HUMAN_SOURCES = ["user", "project", "local"]
DEFAULT_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]


@dataclass
class Settings:
    """Overrides on top of whatever the directory and the user account already load."""

    model: str | None = None
    permission_mode: str | None = None  # None = bypassPermissions, or the policy's choice
    allowed_tools: list[str] | None = None
    append: str | None = None
    settings_file: str | None = None
    sources: list[str] | None = None  # None = user + project + local; not allowed with a policy
    policy: Policy | None = None  # the session's only configuration; None = the directory's and account's
    run_id: str | None = None  # slug for the refusal ledger; None = do not record


@dataclass
class Event:
    kind: str  # "text" | "thinking" | "tool" | "done"
    text: str = ""
    name: str = ""
    detail: str = ""
    session_id: str = ""
    cost_usd: float | None = None
    subtype: str = ""
    transcript: str = ""
    denied: list[str] = field(default_factory=list)  # tool calls the policy blocked


@dataclass
class ClaudeError(Exception):
    subtype: str
    session_id: str | None = None
    errors: list[str] = field(default_factory=list)
    transcript: str = ""

    def __str__(self) -> str:
        detail = "; ".join(self.errors) if self.errors else self.subtype
        return f"{self.subtype}: {detail}"


def _options(cwd: str, settings: Settings, resume: str | None) -> ClaudeAgentOptions:
    if settings.policy and (settings.settings_file or settings.sources is not None):
        raise ValueError("a policy is the session's only configuration; drop settings_file and sources")
    system_prompt: dict = {"type": "preset", "preset": "claude_code"}
    if settings.append:
        system_prompt["append"] = settings.append
    policy = settings.policy or Policy()
    tools = policy.visible_tools()  # [] means no tools, so only None falls back to the preset
    return ClaudeAgentOptions(
        cwd=os.path.abspath(cwd),
        model=settings.model,
        system_prompt=system_prompt,
        tools=tools if tools is not None else {"type": "preset", "preset": "claude_code"},
        mcp_servers=policy.mcp_servers,
        strict_mcp_config=not policy.inherit_mcp,
        sandbox=policy.sandbox_settings(cwd),  # type: ignore[arg-type]
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[policy.hook])]} if settings.policy else None,
        permission_mode=settings.permission_mode or policy.permission_mode(),  # type: ignore[arg-type]
        allowed_tools=_allowed_tools(settings),
        settings=settings.settings_file,
        setting_sources=_sources(settings),  # type: ignore[arg-type]
        include_partial_messages=True,
        resume=resume,
    )


def _sources(settings: Settings) -> list[str]:
    if settings.policy:
        return []  # no settings files, CLAUDE.md, skills, or hooks from anywhere
    return list(settings.sources) if settings.sources is not None else HUMAN_SOURCES


def _allowed_tools(settings: Settings) -> list[str]:
    if settings.allowed_tools is not None:
        return settings.allowed_tools
    return settings.policy.preapproved() if settings.policy else DEFAULT_TOOLS


async def claude(
    prompt: str,
    *,
    cwd: str,
    settings: Settings | None = None,
    resume: str | None = None,
) -> AsyncIterator[Event]:
    """Run one prompt in cwd. Yield text as it streams, then each tool call, then done."""
    options = _options(cwd, settings or Settings(), resume)
    texts: list[str] = []
    streamed_text = False
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent):
            delta_text = _text_delta(message.event)
            if delta_text:
                streamed_text = True
                texts.append(delta_text)
                yield Event(kind="text", text=delta_text)
            thought = _thinking_delta(message.event)
            if thought:
                yield Event(kind="thinking", text=thought)
            continue
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text and not streamed_text:
                    texts.append(block.text)
                    yield Event(kind="text", text=block.text)
                elif isinstance(block, ThinkingBlock) and block.thinking and not streamed_text:
                    yield Event(kind="thinking", text=block.thinking)
                elif isinstance(block, ToolUseBlock):
                    yield Event(kind="tool", name=block.name, detail=_detail(block.input))
            continue
        if isinstance(message, ResultMessage):
            transcript = transcript_path(message.session_id, options.cwd)
            if message.subtype != "success" or message.is_error:
                raise ClaudeError(message.subtype, message.session_id, list(message.errors or []), transcript)
            yield Event(
                kind="done",
                text=message.result or "".join(texts),
                session_id=message.session_id,
                cost_usd=message.total_cost_usd,
                subtype=message.subtype,
                transcript=transcript,
                denied=list(settings.policy.denied) if settings and settings.policy else [],
            )


def _record_refusals(model: str, run_id: str, prompt: str, layer: str, details: list[str]) -> None:
    """Send this session's refusals to the shared ledger; never crash the run."""
    if not run_id or not details:
        return
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from harness import refusals

    for detail in details:
        try:
            refusals.record(
                refusals.RefusalEvent(run=run_id, target=model, prompt=prompt, layer=layer, detail=detail)
            )
        except Exception as error:  # ledger trouble must not kill the session
            print(f"[refusals] record failed: {error}", file=sys.stderr, flush=True)


def transcript_path(session_id: str | None, cwd: str) -> str:
    """Where Claude Code saved this session's JSONL trace, or "" if it can't be found."""
    if not session_id:
        return ""
    projects = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    # Claude Code names the project folder after cwd with every non-alphanumeric turned into "-".
    for folder in {cwd, os.path.realpath(cwd)}:
        candidate = projects / re.sub(r"[^A-Za-z0-9]", "-", folder) / f"{session_id}.jsonl"
        if candidate.is_file():
            return str(candidate)
    # Long paths get shortened differently; the session id is unique, so search for it.
    return next((str(p) for p in projects.glob(f"*/{session_id}.jsonl")), "")


def _text_delta(event: dict) -> str:
    if event.get("type") != "content_block_delta":
        return ""
    delta = event.get("delta") or {}
    if delta.get("type") != "text_delta":
        return ""
    return delta.get("text") or ""


def _thinking_delta(event: dict) -> str:
    if event.get("type") != "content_block_delta":
        return ""
    delta = event.get("delta") or {}
    if delta.get("type") != "thinking_delta":
        return ""
    return delta.get("thinking") or ""


def _detail(value: object) -> str:
    try:
        raw = json.dumps(value, default=str)
    except TypeError:
        raw = str(value)
    return raw if len(raw) <= 500 else raw[:500] + "…"


def _print(event: Event) -> None:
    if event.kind == "text":
        print(event.text, end="", flush=True)
    elif event.kind == "thinking":
        print(f"\n[thinking] {event.text}\n", file=sys.stderr, flush=True)
    elif event.kind == "tool":
        print(f"\n[tool] {event.name} {event.detail}\n", file=sys.stderr, flush=True)
    elif event.kind == "done":
        cost = f"${event.cost_usd:.4f}" if event.cost_usd is not None else "n/a"
        print(f"\n--- session {event.session_id} | {cost} ---", file=sys.stderr)
        _print_transcript(event.transcript)
        for denial in event.denied:
            print(f"denied: {denial}", file=sys.stderr)


def _print_transcript(transcript: str) -> None:
    if not transcript:
        print("transcript: not found", file=sys.stderr)
        return
    print(f"transcript: {transcript}", file=sys.stderr)
    subagents = Path(transcript).with_suffix("") / "subagents"
    if subagents.is_dir():
        print(f"subagent transcripts: {subagents}", file=sys.stderr)


def _settings_from_args(args: argparse.Namespace) -> Settings:
    allowed = None
    if args.allowed_tools is not None:
        allowed = [part.strip() for part in args.allowed_tools.split(",") if part.strip()]
    sources = None
    if args.sources is not None:
        sources = [part.strip() for part in args.sources.split(",") if part.strip()]
    return Settings(
        model=args.model,
        permission_mode=args.permission_mode,
        allowed_tools=allowed,
        append=args.append,
        settings_file=args.settings,
        sources=sources,
        policy=Policy.from_file(args.policy_file) if args.policy_file else None,
        run_id=args.run,
    )


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run one Claude Code prompt in any directory", allow_abbrev=False)
    parser.add_argument("prompt")
    parser.add_argument("--cwd", default=os.getcwd(), help="directory to run in (default: here)")
    parser.add_argument("--model", default=os.environ.get("MODEL", "claude-fable-5-1"))
    parser.add_argument("--permission-mode", help="default: bypassPermissions, or dontAsk when the policy sets sandbox")
    parser.add_argument("--append", help="extra instructions appended to Claude Code's prompt")
    parser.add_argument("--settings", help="path to a Claude Code settings JSON file")
    parser.add_argument(
        "--sources",
        help="comma-separated setting sources: user,project,local (default: all three). Pass empty to load none. Not allowed with --policy-file.",
    )
    parser.add_argument("--resume", help="session id from a previous done event")
    parser.add_argument(
        "--run",
        help="slug recorded with every refusal this session commits into the shared refusal ledger",
    )
    parser.add_argument(
        "--policy-file",
        help="path to the session policy JSON (see policy.py); it becomes the session's only configuration",
    )
    parser.add_argument(
        "--allowed-tools",
        help="comma-separated tools to pre-approve (default: Read,Edit,Write,Glob,Grep,Bash, or the policy's tools)",
    )
    args = parser.parse_args()
    if args.settings and not Path(args.settings).is_file():
        parser.error(f"settings file not found: {args.settings}")
    if args.policy_file:
        if not Path(args.policy_file).is_file():
            parser.error(f"policy file not found: {args.policy_file}")
        if args.settings or args.sources is not None:
            parser.error("--policy-file is the session's only configuration; drop --settings and --sources")
    try:
        async for event in claude(args.prompt, cwd=args.cwd, settings=_settings_from_args(args), resume=args.resume):
            _print(event)
            if event.kind == "done" and args.run and event.denied:
                _record_refusals(args.model, args.run, args.prompt, "policy", event.denied)
    except ClaudeError as err:
        print(str(err), file=sys.stderr)
        if err.session_id:
            print(f"session {err.session_id}", file=sys.stderr)
            _print_transcript(err.transcript)
        if args.run:
            detail = str(err) + (f"; transcript: {err.transcript}" if err.transcript else "")
            _record_refusals(args.model, args.run, args.prompt, "error", [detail])
        raise SystemExit(1) from err


if __name__ == "__main__":
    asyncio.run(_main())
