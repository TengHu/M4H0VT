# strix — autonomous AI pentest agent

**Use:** target-facing active pentesting — recon, exploit validation with real PoCs, multi-agent orchestration, reports.
**Repo:** https://github.com/usestrix/strix · PyPI `strix-agent` · Apache-2.0 · docs https://docs.strix.ai
**Class:** B — target-facing ACTIVE testing. **Fired by: M1 lab-ops by default** (fires real traffic/exploits at the target — authorization required); M2 tool-runner variant allowed in full-policy sessions (Template C).

## For M2 — visibility & on-demand use
- Repo/clone: `git clone https://github.com/usestrix/strix` (for source reading) — normal use needs no clone.
- Install/run (durable): `pipx install strix-agent` (or `curl -sSL https://strix.ai/install | bash`). Requires Docker running + LLM key env (`STRIX_LLM`, `LLM_API_KEY`) — **keys are M1-side only, never in prompts**.
- Invoke: `strix -n --target <dir|url> --scan-mode quick` (headless, exits non-zero on findings). Results land in `strix_runs/<name>/` — copy the findings summary into a world file, then analyze via the micro-lane.
- Ships **9 SKILL.md-compatible skills**: `npx skills add usestrix/strix` (pentests, fixes, CI scanning) — planted into a world at equip time.
- MCP client: strix can consume world MCP servers via `~/.strix/mcp-servers.json`.
- Don'ts: no sync/update mid-session (`strix --update` is M1-side); no target outside the authorized scope; never echo credential values from findings.

## For M1 — equipping & pinning
- Install durable: `pipx install strix-agent@<pin>`; verify `strix --version`.
- Plant skills: `npx skills add usestrix/strix` → verify the 9 skill folders exist in the target skills dir (copy into the world's `.claude/skills/`).
- Docker image pulls on first run (sandbox).
- Authz: written permission for the target scope before any strix run.

## Updates
Pinned at install (`pipx` version). Re-pin = need-driven (new probes/fixes) or broken-pin; `strix --update` is M1-side between runs; re-verify with one smoke scan + `pencheck`.

## Learnings
- 2026-10-22: vetted from README — not yet exercised in a run. First equip: plant the 9 skills + a quick-mode scan against a test target.
