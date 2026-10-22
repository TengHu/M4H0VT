# ScopeSentry — attack-surface mapping service (DEFERRED)

**Use:** continuous attack-surface discovery — subdomain enumeration, asset mapping, fingerprinting, vulnerability scanning; distributed nodes + web UI.
**Repo:** https://github.com/Autumn-27/ScopeSentry · docs https://www.doc.sizesentry.com (verify at equip)
**Class:** C — target-facing **service** (deployed infrastructure, not a per-session tool). **Fired by: M1 deploys; M2 consumes via API/relayed facts.**

## For M2 — visibility
- M2 does **not** deploy or operate it. When a run deploys it, M2 consumes mapped-surface facts relayed into the world (or via a future MCP wrapper — same pattern as `arsenal/mcp/rea/`).
- Deployment/authz is M1-side: it actively enumerates targets — same authorization requirement as the active-testing agents.

## For M1 — equip card (on first need)
- Deploy: docker-compose stack (web UI + node(s)) per repo docs; configure the target scope; API token for programmatic access.
- Wire: results export → world files; optional `arsenal/mcp/scopesentry/` thin API wrapper (REA pattern) if M2 must query it directly.
- Verify: one mapped-surface export compared against a manual curl sweep.

## Updates
Deploy pinned (image tags); re-pull = need-driven; re-verify with a smoke export.

## Learnings
- 2026-10-22: card created deferred — no deployment yet. Trigger: a run needs continuous surface discovery beyond polite one-shot sweeps.
