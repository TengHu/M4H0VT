"""What one wrapper session may do, chosen by the caller.

A policy is a JSON file the caller writes and passes with `--policy-file` (or
`Policy.from_file(path)`). It is the session's only configuration: with a policy,
no settings files, CLAUDE.md, skills, or hooks are loaded from the user account
or the working directory. Every key is optional: leave one out and that area
stays unrestricted; give an empty list and nothing in that area is allowed.

    {
      "tools": ["Read", "Glob", "Grep", "Edit", "Write", "WebFetch"],
      "read": ["**"],
      "write": ["out/**"],
      "fetch": ["https://docs.python.org/3/*", "https://api.github.com/repos/anthropics/*"],
      "search": ["python.org"],
      "bash": ["git status", "git diff", "pytest"],
      "mcp_servers": {"docs": {"type": "http", "url": "https://example.com/mcp"}},
      "mcp_tools": ["mcp__docs__*"],
      "inherit_mcp": false,
      "sandbox": true
    }

tools        built-in tools the agent can see at all (Claude Code's defaults when left out)
read/write   path globs, relative to cwd unless absolute; `**` spans directories
fetch        URL patterns WebFetch may open; `*` matches anything, including `/`
search       true, false, or the only domains WebSearch may return results from
bash         command prefixes; every part of a `&&`, `;`, `|` chain must match one
mcp_servers  MCP servers to attach for this session (same shape as .mcp.json entries)
mcp_tools    patterns for the MCP tool names the agent may call
inherit_mcp  also load MCP servers from the user's and project's config and claude.ai
             connectors (default true)
sandbox      run Bash in the OS sandbox: network limited to the hosts in `fetch`,
             writes limited to cwd, and reads of home and other user folders
             limited to cwd plus the folders named in `read` (system folders
             such as /usr and /etc stay readable so commands can run)

Every tool call, subagents' included, goes through `hook` before it runs, and a
denial reaches the agent as the tool's error. File and URL rules cover the file
and web tools, not what a Bash command does; set `bash` or `sandbox` for that.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

READ_TOOLS = {"Read": "file_path", "Glob": "path", "Grep": "path"}
WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
_CHAIN = re.compile(r"&&|\|\||[;|\n]")
# Where personal files live; sandboxed Bash can't read these outside the allowed folders.
PRIVATE_DIRS = [os.path.expanduser("~"), "/Users", "/home", "/root", "/Volumes", "/mnt", "/media"]


@dataclass
class Policy:
    tools: list[str] | None = None
    read: list[str] | None = None
    write: list[str] | None = None
    fetch: list[str] | None = None
    search: bool | list[str] = True
    bash: list[str] | None = None
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    mcp_tools: list[str] | None = None
    inherit_mcp: bool = True
    sandbox: bool = False
    denied: list[str] = field(default_factory=list, init=False)

    @classmethod
    def from_file(cls, path: str) -> Policy:
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, data: dict) -> Policy:
        unknown = set(data) - {f for f in cls.__dataclass_fields__ if f != "denied"}
        if unknown:
            raise ValueError(f"unknown policy keys: {', '.join(sorted(unknown))}")
        return cls(**data)

    def visible_tools(self) -> list[str] | None:
        if self.tools is None:
            return None
        tools = list(self.tools)
        # MCP tools are loaded on demand through ToolSearch.
        if self.mcp_servers and "ToolSearch" not in tools:
            tools.append("ToolSearch")
        return tools

    def permission_mode(self) -> str:
        # bypassPermissions also approves sandboxed Bash reaching hosts outside the
        # allowlist; dontAsk refuses them, so it needs the tools pre-approved instead.
        return "dontAsk" if self.sandbox else "bypassPermissions"

    def preapproved(self) -> list[str]:
        """Tools to let through without asking; `hook` still checks every call."""
        tools = self.visible_tools()
        if tools is None:
            tools = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit",
                     "WebFetch", "WebSearch", "Task", "Skill", "ToolSearch"]
        return tools + [f"mcp__{name}" for name in self.mcp_servers]

    def sandbox_settings(self, cwd: str) -> dict | None:
        if not self.sandbox:
            return None
        cwd = os.path.realpath(cwd)
        hosts = sorted({urlparse(p).hostname for p in self.fetch or [] if urlparse(p).hostname})
        # The sandbox lets an allowRead path through even inside a denyRead one.
        readable = {cwd} | {_literal_base(_abs_pattern(p, cwd)) for p in self.read or []}
        return {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "network": {"allowedDomains": hosts},
            "filesystem": {
                "denyRead": [d for d in PRIVATE_DIRS if os.path.isdir(d)],
                "allowRead": sorted(readable),
            },
        }

    async def hook(self, input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        name = input_data.get("tool_name", "")
        args = input_data.get("tool_input") or {}
        cwd = os.path.realpath(input_data.get("cwd") or os.getcwd())
        if name == "WebSearch" and isinstance(self.search, list) and self.search:
            return _allow_with(dict(args, allowed_domains=self.search))
        reason = self._check(name, args, cwd)
        if reason is None:
            return {}
        self.denied.append(f"{name}: {reason}")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked by session policy: {reason}",
            }
        }

    def _check(self, name: str, args: dict, cwd: str) -> str | None:
        if name in READ_TOOLS and self.read is not None:
            path = args.get(READ_TOOLS[name]) or cwd
            if not _path_allowed(path, self.read, cwd):
                return f"reading {path} is not allowed (read: {self.read})"
        if name in WRITE_TOOLS and self.write is not None:
            path = args.get(WRITE_TOOLS[name]) or ""
            if not _path_allowed(path, self.write, cwd):
                return f"writing {path} is not allowed (write: {self.write})"
        if name == "WebFetch" and self.fetch is not None:
            url = args.get("url", "")
            if not any(fnmatch.fnmatchcase(url, p) for p in self.fetch):
                return f"fetching {url} is not allowed (fetch: {self.fetch})"
        if name == "WebSearch" and self.search in (False, []):
            return "web search is not allowed"
        if name == "Bash" and self.bash is not None:
            return _bash_reason(args.get("command", ""), self.bash)
        if name.startswith("mcp__") and self.mcp_tools is not None:
            if not any(fnmatch.fnmatchcase(name, p) for p in self.mcp_tools):
                return f"MCP tool {name} is not allowed (mcp_tools: {self.mcp_tools})"
        return None


def _allow_with(updated: dict) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated,
        }
    }


def _path_allowed(path: str, patterns: list[str], cwd: str) -> bool:
    # Resolve symlinks and `..` so a path can't talk its way out of a pattern.
    target = Path(os.path.realpath(os.path.join(cwd, os.path.expanduser(path))))
    for pattern in (_abs_pattern(p, cwd) for p in patterns):
        # "dir/**" also covers dir itself, so Glob/Grep can search from it.
        if target.full_match(pattern) or (pattern.endswith("/**") and target.full_match(pattern[:-3])):
            return True
    return False


def _abs_pattern(pattern: str, cwd: str) -> str:
    pattern = os.path.join(cwd, os.path.expanduser(pattern))
    # Resolve the literal part (e.g. /tmp -> /private/tmp) and keep the glob part as written.
    parts = Path(pattern).parts
    split = next((i for i, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts))
    base = os.path.realpath(os.path.join(*parts[:split])) if split else "/"
    return os.path.join(base, *parts[split:])


def _literal_base(pattern: str) -> str:
    parts = Path(pattern).parts
    split = next((i for i, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts))
    return os.path.join(*parts[:split]) if split else "/"


def _bash_reason(command: str, prefixes: list[str]) -> str | None:
    if "$(" in command or "`" in command:
        return "command substitution is not allowed under a bash allowlist"
    for part in _CHAIN.split(command):
        part = part.strip()
        if part and not any(part == p or part.startswith(p + " ") for p in prefixes):
            return f"`{part}` is not an allowed command (bash: {prefixes})"
    return None
