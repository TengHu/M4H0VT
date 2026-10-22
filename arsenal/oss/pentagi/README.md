# pentagi — self-hosted autonomous pentesting platform (DEFERRED)

**Use:** multi-agent autonomous pentesting platform — 20+ pro tools (nmap, Metasploit, sqlmap) in isolated Docker sandboxes; web UI; REST/GraphQL APIs (bearer auth); memory/knowledge-graph; self-hosted, LLM-provider-flexible.
**Repo:** https://github.com/vxcontrol/pentagi · docs in-repo (installation_configuration guide) · by VXControl
**Class:** B/C — target-facing ACTIVE testing **service**. **Fired by: M1 deploys and drives via API; M2 consumes via MCP wrapper or relayed facts.**

## For M2 — visibility
- M2 does **not** deploy it (docker-compose stack: Postgres+pgvector, Neo4j, monitoring, scraper — needs LLM provider keys, M1-side).
- When deployed: M2 consumes via its REST/GraphQL API (flows, tasks, reports) through a future `arsenal/mcp/pentagi/` wrapper — or facts relayed into the world. Reference-form reporting per `secrets-without-exposure`.
- Don'ts: pentagi runs real exploitation tooling — target scope/authorization is M1-side; never point it at unauthorized targets; API tokens are M1-side.

## For M1 — equip card (on first need)
- Deploy: interactive installer (macOS arm64 build exists) or docker-compose; default admin `admin@pentagi.com`/`admin` — change immediately; API bearer token via web Settings.
- Wire: `arsenal/mcp/pentagi/` wrapper (thin: flows/tasks/reports endpoints) + policy fragment; results export → world files.
- Verify: one flow against a test container compared with a manual tool pass.

## Updates
Image tags pinned in the compose; re-pull = need-driven; re-verify with a smoke flow.

## Learnings
- 2026-10-22: card created deferred — heavy stack (20GB disk, multi-container), deploy when a run needs autonomous platform-grade pentesting.
