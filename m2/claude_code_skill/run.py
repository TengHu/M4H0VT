#!/usr/bin/env python3
"""Run one Claude Code prompt in a directory and return the path of its trace.

    python run.py "<task>" --cwd <folder> --policy-file <policy.json>

Claude Code itself logs every session to
~/.claude/projects/<project key of cwd>/<session id>.jsonl (every prompt, reply,
thinking block, tool call and tool result), with subagents under
<session id>/subagents/. This script writes no log of its own: it picks the
session id, so it knows that path before the session starts.

stdout is the trace path, the session's reply, then the same block on every
run, whether the session succeeded, failed, or crashed:

    --- <status> | session <id> | $<cost> ---
    denied: <tool>: <reason>        (one per call the policy blocked)
    subagent traces: <dir>          (only if it started subagents)
    <LAST_LINE, defined below>

LAST_LINE always ends the output, unless the session never started and there is
no trace to read.

Exit code 0 when the status is "success", 1 otherwise.

The policy file is the session's only configuration: no settings files,
CLAUDE.md, skills, or hooks load from anywhere else. See policy.py.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
import uuid
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, project_key_for_directory, query
from claude_agent_sdk.types import HookMatcher, ResultMessage

from policy import Policy

# The most important message this script returns, and the only place it is written:
# the last line of every run's output.
LAST_LINE = (
    "REQUIRED: the reply above is only the session's own summary. You must read the full trace "
    "(JSONL, one message per line, with every tool call's full input and result), and any subagent "
    "traces listed above, before your next step: {trace}"
)


def _options(args: argparse.Namespace, policy: Policy, session_id: str) -> ClaudeAgentOptions:
    system_prompt: dict = {"type": "preset", "preset": "claude_code"}
    if args.append:
        system_prompt["append"] = args.append
    tools = policy.visible_tools()  # [] means no tools, so only None falls back to the preset
    thinking: dict | None = None
    if args.thinking == "enabled":
        thinking = {"type": "enabled", "budget_tokens": args.thinking_tokens, "display": "summarized"}
    elif args.thinking == "adaptive":
        thinking = {"type": "adaptive", "display": "summarized"}
    elif args.thinking == "disabled":
        thinking = {"type": "disabled"}
    return ClaudeAgentOptions(
        cwd=os.path.abspath(args.cwd),
        model=args.model,
        # pen law: a monitor stop retries in-model — the declared model
        # holds the pen; the fallback never replaces the author
        fallback_model=args.model,
        thinking=thinking,  # type: ignore[arg-type]
        system_prompt=system_prompt,
        tools=tools if tools is not None else {"type": "preset", "preset": "claude_code"},
        mcp_servers=policy.mcp_servers,
        strict_mcp_config=not policy.inherit_mcp,
        sandbox=policy.sandbox_settings(args.cwd),  # type: ignore[arg-type]
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[policy.hook])]},
        permission_mode=policy.permission_mode(),  # type: ignore[arg-type]
        allowed_tools=policy.preapproved(),
        # policy.setting_sources names the sources that load (default none:
        # no settings files, CLAUDE.md, skills, or hooks from anywhere)
        setting_sources=policy.setting_sources or [],
        resume=args.resume,
        session_id=None if args.resume else session_id,  # a resumed session keeps its id
    )


def _trace_path(session_id: str, cwd: str) -> Path:
    """Where Claude Code writes this session's trace."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return home / "projects" / project_key_for_directory(cwd) / f"{session_id}.jsonl"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Claude Code prompt in any directory", allow_abbrev=False)
    parser.add_argument("prompt")
    parser.add_argument("--policy-file", required=True, help="path to the session policy JSON (see policy.py)")
    parser.add_argument("--cwd", default=os.getcwd(), help="directory to run in (default: here)")
    parser.add_argument("--model", default=os.environ.get("MODEL", "claude-fable-5-1"))
    parser.add_argument("--append", help="extra instructions appended to Claude Code's prompt")
    parser.add_argument("--resume", help="session id from a previous run")
    parser.add_argument("--thinking", choices=["enabled", "adaptive", "disabled"], default="enabled",
                        help="thinking mode (default enabled: full persistence into the trace)")
    parser.add_argument("--thinking-tokens", type=int, default=16000, help="thinking budget when --thinking enabled")
    args = parser.parse_args()
    if not Path(args.policy_file).is_file():
        parser.error(f"policy file not found: {args.policy_file}")
    return args


async def _main() -> int:
    args = _args()
    policy = Policy.from_file(args.policy_file)
    session_id = args.resume or str(uuid.uuid4())
    trace = _trace_path(session_id, args.cwd)
    print(f"trace: {trace}", flush=True)  # first as well as last: a run killed midway has still returned it
    status, cost, reply = "no result", 0.0, ""
    try:
        async for message in query(prompt=args.prompt, options=_options(args, policy, session_id)):
            if isinstance(message, ResultMessage):
                status, cost, reply = message.subtype, message.total_cost_usd or 0.0, message.result or ""
    except Exception as error:
        status = f"crashed: {type(error).__name__}: {error}"
        traceback.print_exc()
    print(reply)
    print(f"--- {status} | session {session_id} | ${cost:.4f} ---")
    for denial in policy.denied:
        print(f"denied: {denial}")
    if (trace.with_suffix("") / "subagents").is_dir():
        print(f"subagent traces: {trace.with_suffix('') / 'subagents'}")
    if trace.is_file():
        print(LAST_LINE.format(trace=trace))
    else:
        print("No trace to read: the session did not start.")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
