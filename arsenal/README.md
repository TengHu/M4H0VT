# Arsenal

M1's library of anything that helps M2 (world-craft: read before writing a
world spec). One folder per kind — details live in the cards, not here.

## Skills — `skills/<name>/SKILL.md`

Plant: `cp -r skills/<name>/ <world>/.claude/skills/<name>/` — policy needs
`setting_sources: ["project"]` + `Skill` in tools; name/description must pass
the cover-story read.

## MCP — `mcp/<name>/`

- [`mcp/rea/`](mcp/rea/README.md) — REA, reverse-engineering MCP server
  (validated 2026-10-22). Equip per its card + `policy-fragment.json`.

## OSS tools — `oss/<tool>/README.md` (one card per tool)

**The rule:** M1 installs pinned, outside this repo, and verifies
(worldcheck/pencheck); M2 gets the card as visibility, never syncs versions;
active-testing tools fire M1-side (authorization required).

| Tool | Class | Fired by | Card |
|---|---|---|---|
| strix | B — target-facing active pentest agent | M1 lab-ops | `oss/strix/README.md` |
| garak | A — run-against-M2 LLM scanner | M1 lab-ops | `oss/garak/README.md` |
| promptfoo | A — run-against-M2 eval/redteam | M1 lab-ops | `oss/promptfoo/README.md` |
| ScopeSentry | C — surface-mapping service | M1 deploys (deferred) | `oss/scopesentry/README.md` |
| pentagi | B/C — pentest platform service | M1 deploys (deferred) | `oss/pentagi/README.md` |
| CyberStrikeAI | B (presumed) | — | `oss/cyberstrikeai/README.md` (UNVERIFIED) |
