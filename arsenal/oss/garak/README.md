# garak — NVIDIA LLM vulnerability scanner

**Use:** run-against-M2 — probes an LLM endpoint for failures (prompt injection, data leakage, hallucination, toxicity). Our use: scan **our own M2/declared-pen pipeline** with a real scanner instead of hand probes.
**Repo:** https://github.com/NVIDIA/garak · Apache-2.0 · docs https://docs.garak.ai
**Class:** A — run-against-M2. **Fired by: M1 lab-ops** (report JSON → world file → micro-lane analysis).

## For M2 — visibility & on-demand use
- Repo/clone: `git clone https://github.com/NVIDIA/garak` (source/probe reading).
- The scanner runs against an LLM endpoint — in tool-runner sessions (Template C, Bash+network) M2 may create the venv, run probe suites, and write the report into the world; findings get reported in reference form (metadata: probe names, pass/fail rates — never prompt/_response bodies containing sensitive material).
- Don'ts: don't point garak at third-party endpoints without authorization; don't paste probe payloads with secret material.

## For M1 — equipping & pinning
- Install durable: `python3 -m venv ~/tools/garak-venv && ~/tools/garak-venv/bin/pip install garak@<pin>`; verify `~/tools/garak-venv/bin/garak --version`.
- Run: `~/tools/garak-venv/bin/garak --model_type <type> --model_name <endpoint> --probes <suite> --report_prefix <world/run>` → report JSON/HTML lands in cwd — move into the world.
- Probe suites relevant to us: `ansiescape`, `atkgen`, `promptinject`, `leakreplay`, `xss` — pick per the t under test.

## Updates
Pinned at install. garak's probe database ages (new LLM attack classes) — **freshness check worth running at every equip**: `git -C <clone> fetch && git log --oneline HEAD..origin/main | head` or `pip index versions garak`. Re-pin = need-driven; re-verify with a 1-probe smoke + `pencheck`.

## Learnings
- 2026-10-22: vetted from README — not yet exercised. First equip: 1-probe smoke against the M2 endpoint + report→world.
