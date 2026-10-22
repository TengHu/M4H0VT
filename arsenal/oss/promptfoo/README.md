# promptfoo — LLM eval / redteam framework

**Use:** run-against-M2 — YAML-driven test suites and a redteam module against prompts/agents (our worlds, our prompts, our M2 endpoint).
**Repo:** https://github.com/promptfoo/promptfoo · MIT · docs https://www.promptfoo.dev/docs
**Class:** A — run-against-M2. **Fired by: M1 lab-ops** (results JSON → world → micro-lane analysis).

## For M2 — visibility & on-demand use
- Repo/clone: `git clone https://github.com/promptfoo/promptfoo` (source/examples reading).
- In tool-runner sessions (Template C): write the eval config YAML into the world, run `npx promptfoo@<pin> eval -c <config> --output <world>/results.json`, then analyze via micro-lane.
- Don'ts: eval payloads must not contain secret values; provider keys are M1-side env.

## For M1 — equipping & pinning
- Install durable: `npm install -g promptfoo@<pin>`; verify `promptfoo --version`.
- Run: `promptfoo eval -c <world>/eval.yaml --output <world>/results.json`; redteam: `promptfoo redteam generate/eval` per docs.
- The eval YAML is world furniture (M1-authored) — provider keys come from env, never the file.

## Updates
Pinned at install. promptfoo moves fast (redteam module especially) — freshness check at equip: `npm view promptfoo version` vs pin. Re-pin = need-driven; re-verify with a 1-case eval + `pencheck`.

## Learnings
- 2026-10-22: vetted from README — not yet exercised. First equip: 1-case eval against the M2 endpoint + results→world.
