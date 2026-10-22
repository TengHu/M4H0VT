#!/usr/bin/env python3
"""Run one raw-LLM prompt through OpenRouter and return the path of its trace.

    python run.py "<task>" --cwd <folder> --policy-file <policy.json>

M2 here is a plain chat completion — no tools, no agentic loop, no wrapper of
any kind. The thing under test is the model's own refusal training; the prompt
is forwarded as-is and the reply returned untouched.

stdout is the trace path, the reply, then the same block on every run,
success, failure, or crash:

    trace: <path>
    <reply>
    --- <status> | session <id> | $<cost> ---
    <LAST_LINE, defined below>

Exit code 0 when the status is "success", 1 otherwise. The runner never
detects or classifies refusals — the trace is the record; taskledger classifies.

The policy file (JSON object, the session's only configuration, unknown keys
are an error, left out = default):

    {"system": "<optional system prompt>",
     "temperature": 0.0,
     "max_tokens": 4096}

The trace is <cwd>/trace-<session-id>.jsonl, one JSON line per event:

    {"type": "prompt", "model": "...", "content": "...", "system": "..."}
    {"type": "reply", "content": "...", "usage": {...}}

--resume <session-id> appends to the same file and replays the prior
prompt/reply pairs as conversation history, so a session is one ongoing chat.

The OPENROUTER_API_KEY is read from the environment, or this folder's .env
(`OPENROUTER_API_KEY=sk-or-...`). It is never written to the trace.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from http.client import IncompleteRead
from pathlib import Path
import urllib.error
import urllib.request

LAST_LINE = (
    "REQUIRED: the reply above is only the session's own summary. You must read the full trace "
    "(JSONL, one line per prompt/reply event) before your next step: {trace}"
)

URL = "https://openrouter.ai/api/v1/chat/completions"
POLICY_KEYS = {"system", "temperature", "max_tokens"}


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _policy(path: str) -> dict:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("policy must be a JSON object")
    unknown = set(policy) - POLICY_KEYS
    if unknown:
        raise ValueError(f"unknown policy keys: {sorted(unknown)}")
    return policy


def _history(trace: Path) -> list[dict]:
    messages: list[dict] = []
    if not trace.is_file():
        return messages
    for line in trace.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") == "prompt":
            messages.append({"role": "user", "content": event["content"]})
        elif event.get("type") == "reply":
            messages.append({"role": "assistant", "content": event["content"]})
    return messages


class StreamPartial(Exception):
    """Mid-stream kill (e.g. provider SAFETY): carries the deltas received
    before the error so the trace records where generation was cut."""

    def __init__(self, error: str, content: str, refusal: str | None, usage: dict, finish: str | None):
        super().__init__(error)
        self.error = error
        self.content = content
        self.refusal = refusal
        self.usage = usage or {}
        self.finish = finish


def _post(payload: dict, key: str) -> dict:
    """Stream internally and reassemble: the egress proxy truncates the
    non-streaming body of any generation longer than ~one SSE chunk, while
    the SSE stream itself survives the same proxy (measured 2026-10-22)."""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    body = dict(payload)
    body["stream"] = True
    body.setdefault("stream_options", {"include_usage": True})
    data = json.dumps(body).encode()
    last: Exception | None = None
    for _ in range(3):  # egress proxy occasionally truncates chunked reads
        try:
            req = urllib.request.Request(URL, data=data, method="POST", headers=headers)
            content, refusal, usage, finish = [], None, {}, None
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    piece = line[5:].strip()
                    if piece == "[DONE]":
                        break
                    try:
                        event = json.loads(piece)
                    except json.JSONDecodeError:
                        continue
                    if event.get("error"):
                        raise StreamPartial(f"stream error: {json.dumps(event['error'])[:300]}",
                                            "".join(content), refusal, usage, finish)
                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            content.append(delta["content"])
                        if delta.get("refusal"):
                            refusal = (refusal or "") + delta["refusal"]
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                    if event.get("usage"):
                        usage = event["usage"]
            return {"choices": [{"message": {"content": "".join(content), "refusal": refusal},
                                 "finish_reason": finish}],
                    "usage": usage or {}}
        except urllib.error.HTTPError as e:  # 4xx/5xx: surface the body, don't retry
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}") from None
        except (RuntimeError, IncompleteRead, urllib.error.URLError, json.JSONDecodeError) as e:
            last = e
    raise last


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one raw-LLM prompt through OpenRouter", allow_abbrev=False)
    parser.add_argument("prompt")
    parser.add_argument("--policy-file", required=True, help="path to the session policy JSON (see module docstring)")
    parser.add_argument("--cwd", default=os.getcwd(), help="directory to run in; the trace lives here (default: here)")
    parser.add_argument("--model", default=os.environ.get("MODEL", "anthropic/claude-opus-5"))
    parser.add_argument("--resume", help="session id from a previous run")
    args = parser.parse_args()
    if not Path(args.policy_file).is_file():
        parser.error(f"policy file not found: {args.policy_file}")
    return args


def _main() -> int:
    args = _args()
    _load_env()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    session_id = args.resume or str(uuid.uuid4())
    trace = Path(args.cwd).resolve() / f"trace-{session_id}.jsonl"
    print(f"trace: {trace}", flush=True)  # first as well as last: a run killed midway has still returned it
    status, cost, reply = "no result", 0.0, ""
    try:
        policy = _policy(args.policy_file)
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set (env or m2/openrouter/.env)")
        system = policy.get("system") or ""
        messages = _history(trace) + [{"role": "user", "content": args.prompt}]
        if system:
            messages = [{"role": "system", "content": system}] + messages
        payload = {"model": args.model, "messages": messages,
                   "temperature": policy.get("temperature", 0.0),
                   "max_tokens": policy.get("max_tokens", 4096)}
        event = {"type": "prompt", "model": args.model, "content": args.prompt}
        if system:
            event["system"] = system
        with trace.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
            try:
                data = _post(payload, key)
            except StreamPartial as kill:
                killed = {"type": "reply", "content": kill.content, "usage": kill.usage,
                          "error": kill.error, "partial": True}
                if kill.finish:
                    killed["finish_reason"] = kill.finish
                fh.write(json.dumps(killed) + "\n")
                raise
            choice = data["choices"][0]
            message = choice.get("message") or {}
            reply = (message.get("content") or message.get("refusal") or "").strip()
            usage = data.get("usage") or {}
            cost = float(usage.get("cost") or 0.0)
            event = {"type": "reply", "content": reply, "usage": usage}
            if choice.get("finish_reason"):
                event["finish_reason"] = choice["finish_reason"]
            fh.write(json.dumps(event) + "\n")
        status = "success"
    except Exception as error:
        status = f"crashed: {type(error).__name__}: {error}"
    print(reply)
    print(f"--- {status} | session {session_id} | ${cost:.4f} ---")
    if trace.is_file():
        print(LAST_LINE.format(trace=trace))
    else:
        print("No trace to read: the session did not start.")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(_main())
