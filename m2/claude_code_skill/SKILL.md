---
name: claude-code-session
description: Run a Claude Code session on a task in a chosen folder, with a policy file that fixes exactly which tools, files, URLs, shell commands, and MCP servers it may use. Use when you need Claude Code to do work for you and want its access limited, and when you need its full trace afterwards.
---

# Claude Code session

`run.py` runs one prompt as a Claude Code session in a folder and returns the path of the trace Claude Code keeps of it. You write a policy file; that file is the session's only configuration. No settings, CLAUDE.md, skills, hooks, or MCP servers load from the user account or the folder unless the policy names them.

## Run

```bash
python m2/claude_code_skill/run.py "<task>" --cwd <folder> --policy-file <policy.json>
```

Use the repo's `.venv/bin/python`. Optional: `--model <name>` (default `claude-fable-5-1`), `--resume <session-id>` to continue a previous session, `--append "<extra instructions>"`.

## Output

stdout is the trace path, then, when the session ends, its reply followed by the same block on every run — success, failure, or crash:

```
trace: <path>
<reply>
--- <status> | session <id> | $<cost> ---
denied: <tool>: <reason>
subagent traces: <dir>
REQUIRED: the reply above is only the session's own summary. You must read the full trace (…) before your next step: <path>
```

- `<status>` — `success`, the session's error subtype, or `crashed: <error>`.
- `denied:` — one line per call the policy blocked.
- `subagent traces:` — only if it started subagents; one `agent-*.jsonl` each, with a `.meta.json` whose `toolUseId` links back to the main trace.
- **The last line** is always the `REQUIRED:` sentence ending in the path of the full trace. The one exception: if the session never started there is no trace, and the last line is `No trace to read: the session did not start.`
- **The trace** is the log Claude Code itself keeps of the session: `~/.claude/projects/<project key of --cwd>/<session-id>.jsonl` (or under `$CLAUDE_CONFIG_DIR`). One JSON line per message: every prompt, reply and thinking block, every tool call with its full input, every tool result (bash output, hook denials), token usage. `run.py` picks the session id, so the path is also printed before the session starts; a run that is killed midway has still returned it. A resumed session appends to the same file.
- **exit code**: 0 when the status is `success`, 1 otherwise.

Claude Code deletes traces older than 30 days (`cleanupPeriodDays`). Copy a trace you need to keep.

## After every run

**Read the trace before your next step — every run, no exceptions.** The reply is the session's own account of what it did; what the tools received and returned is only in the trace. No trace read, no next session, and no reporting done.

- **`denied:` lines** — each names the rule to widen; widen, then `--resume <session-id>`.
- **Incomplete runs** — any status other than `success`, or unfinished tool calls in the trace, mean the work is partial: widen the rule the last blocked call needed and resume.
- **Refusals** — this runner only returns the trace. It does not detect, classify, or record refusals; that is yours to do from the trace, with the `task-ledger` skill.

## Policy file

JSON object. Every key is optional. **Left out = unrestricted. Empty list = nothing allowed.** Unknown keys are an error.

| Key | Value | Effect |
|---|---|---|
| `tools` | list of built-in tool names | The only built-in tools the session has. Common: `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`, `WebFetch`, `WebSearch`, `Task` (subagents). |
| `read` | path globs | Where `Read`/`Glob`/`Grep` may look. Relative to `--cwd` unless absolute; `**` spans folders. |
| `write` | path globs | Where `Edit`/`Write`/`NotebookEdit` may write. |
| `fetch` | URL patterns | URLs `WebFetch` may open. `*` matches anything, including `/`. |
| `search` | `true` / `false` / list of domains | Whether `WebSearch` works, or which domains results may come from. |
| `bash` | command prefixes | Allowed shell commands. Every part of a `&&` / `;` / `\|` chain must match; `$(...)` and backticks are refused. |
| `mcp_servers` | `{name: config}` | MCP servers for this session, `.mcp.json` shape, e.g. `{"type": "stdio", "command": "python3", "args": ["/abs/server.py"]}` or `{"type": "http", "url": "..."}`. |
| `mcp_tools` | name patterns | Which MCP tools may be called, e.g. `mcp__mytools__*`. |
| `inherit_mcp` | bool, default `true` | Also load the user's MCP servers and claude.ai connectors. Set `false` unless you need them. |
| `sandbox` | bool, default `false` | Run Bash in the OS sandbox: network only to the hosts in `fetch`, writes only inside `--cwd`, no reads of home or other user folders except `--cwd` and folders in `read`. |

## Recipes

Read-only review of a folder:
```json
{"tools": ["Read", "Glob", "Grep"], "read": ["**"], "inherit_mcp": false}
```

Confined to one folder, shell included:
```json
{"tools": ["Read", "Glob", "Grep", "Edit", "Write", "Bash"],
 "read": ["**"], "write": ["**"], "sandbox": true, "inherit_mcp": false}
```

Research from specific docs only, results into `out/`:
```json
{"tools": ["Read", "Write", "WebFetch"], "write": ["out/**"],
 "fetch": ["https://docs.python.org/3/*"], "inherit_mcp": false}
```

Give it your own tools as an MCP server:
```json
{"tools": ["Read", "Write"], "write": ["work/**"],
 "mcp_servers": {"mytools": {"type": "stdio", "command": "python3", "args": ["/abs/path/tools/server.py"]}},
 "mcp_tools": ["mcp__mytools__*"], "inherit_mcp": false}
```

## Rules of thumb

- Start narrow. Widen only the rule a `denied:` line names.
- If `Bash` is in `tools`, file and URL rules don't cover what its commands do. Add `sandbox: true` (or a `bash` prefix list) whenever `read`, `write`, or `fetch` matter.
- Keep any tool or server code you provide outside the `write` globs, so the session can't edit it.
- MCP servers run outside the sandbox with your own access. Only attach servers you trust, or start them inside a sandbox you control.
- The sandbox is an OS-level boundary on your machine, not a VM. Use a container for untrusted code.
- Each run is one prompt. To continue, pass `--resume <session-id>` with the same `--policy-file`.
