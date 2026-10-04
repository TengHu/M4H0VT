---
name: claude-code-session
description: Run a Claude Code session on a task in a chosen folder, with a policy file that fixes exactly which tools, files, URLs, shell commands, and MCP servers it may use. Use when you need Claude Code to do work for you and want its access limited, and when you need its full trace afterwards.
---

# Claude Code session

`run.py` runs one prompt as a Claude Code session in a folder and streams what it does. You write a policy file; that file is the session's only configuration. No settings, CLAUDE.md, skills, hooks, or MCP servers load from the user account or the folder unless the policy names them.

## Run

```bash
python manual/claude_code/run.py "<task>" --cwd <folder> --policy-file <policy.json>
```

Use the repo's `.venv/bin/python`. Optional: `--model <name>` (default `claude-fable-5-1`), `--resume <session-id>` to continue a previous session, `--append "<extra instructions>"`, `--run <slug>` to record every refusal this session commits (denied policy calls, error exits) into the shared refusal ledger (`runs/refusal-ledger/<model>.jsonl`, via `harness.refusals`).

## Output

- **stdout**: the session's reply text.
- **stderr**: `[tool] <name> <input>` for each tool call, then:
  - `--- session <id> | $<cost> ---`
  - `transcript: <path>` — the full JSONL trace (every message, tool call, result, token usage).
  - `subagent transcripts: <dir>` — only if it started subagents; one `agent-*.jsonl` each, with a `.meta.json` whose `toolUseId` links back to the main trace.
  - `denied: <tool>: <reason>` — one line per call the policy blocked.
- **exit code**: 0 on success, 1 on failure (the error and transcript path are printed to stderr).

## After every run

Examine the output before reporting done — a session can fail without anything on stdout.

- **`denied:` lines** — each names the rule to widen; widen, then `--resume <session-id>`.
- **Trace** (`transcript: <path>` on stderr) — the ground truth of the run: every user prompt, thinking block, tool call with its full input, tool result (bash stdout/stderr, exit codes, hook denials), reply, token usage and cost.
- **On disk** — every session's trace is kept at `~/.claude/projects/<cwd with non-alphanumerics replaced by ->/<session-id>.jsonl` (or `$CLAUDE_CONFIG_DIR/projects/…`); subagent traces sit at `<transcript without .jsonl>/subagents/agent-*.jsonl`, linked back to the main trace by `toolUseId`.
- **Incomplete runs** — a safety-classifier stop, non-zero exit, or unfinished tool calls in the trace mean the work is partial: widen the rule the last blocked call needed and resume.

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
- MCP servers run outside the sandbox with your own access. Only attach servers you trust, or start them through `srt` (sandbox-runtime).
- The sandbox is an OS-level boundary on your machine, not a VM. Use a container for untrusted code.
- Each run is one prompt. To continue, pass `--resume <session-id>` with the same `--policy-file`.

## From Python

```python
from run import Settings, claude
from policy import Policy

async for event in claude("<task>", cwd="<folder>",
                          settings=Settings(policy=Policy.from_file("policy.json"))):
    if event.kind == "done":
        event.text, event.transcript, event.denied, event.session_id
```
