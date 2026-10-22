# M2 runners

One directory here = one runner backend: the harness that puts a target
model (M2) to work on one prompt in one folder and returns its trace.
`claude_code_skill/` is the current backend; its dir name is historical.
Adding a backend means adding a folder that satisfies the contract below
plus one registry row — nothing else in the repo changes.

## Contract

Every backend's `run.py`:

- **Invocation**: `python run.py "<task>" --cwd <dir> --policy-file <f>
  [--model <name>] [--resume <id>]` (plus backend-specific flags such as
  `--append`).
- **stdout**: the trace path first, then the session's reply, then the
  status block on every run — success, failure, or crash:

  ```
  trace: <path>
  <reply>
  --- <status> | session <id> | $<cost> ---
  denied: <tool>: <reason>        (one per call the policy blocked)
  REQUIRED: the reply above is only the session's own summary. You must
  read the full trace (…) before your next step: <path>
  ```

  The last line always names the trace path (unless the session never
  started). Exit code 0 only on success.
- **Trace invariant**: a full JSONL (or equivalent) of every prompt,
  reply, thinking block, tool call and tool result, at a stable path the
  caller can read; `--resume` appends to the same file. Callers parse
  this to classify outcomes — a lossy trace breaks the loop.
- **Policy file**: backend-defined format (each agent has its own access
  model), but three invariants hold: the caller authors it per session,
  it is the session's *only* configuration, and the workflow is
  start-narrow — widen only the rule a `denied:` line names.
- **Division of labor**: the runner never detects or classifies
  refusals. It returns the trace; `harness/taskledger.py` classifies.

## Registry

| Backend | Entrypoint | Default model | Notes |
|---|---|---|---|
| `claude_code_skill` | `run.py` | `claude-fable-5-1` | Claude Code via `claude_agent_sdk`; policy keys, sandbox, MCP servers, `setting_sources` — see its `SKILL.md` |
| `openrouter` | `run.py` | `anthropic/claude-opus-5` | raw chat completion via OpenRouter — no tools, no agentic loop, model's own refusal training is the target; policy = `{system, temperature, max_tokens}`; reasoning eats ~2–3× `max_tokens` (instruction sends: ≥16000); trace is `<cwd>/trace-<session-id>.jsonl`, `--resume` replays prior turns as history; key in `m2/openrouter/.env` |
