# REA — reverse-engineering MCP server (validated 2026-10-22)

**What:** [morluto/rea](https://github.com/morluto/rea) — open-source MCP server
for reverse engineering: JavaScript/Electron/ASAR applications, .NET, and native
binaries via optional Hopper/Ghidra/IDA. Community directory: [reamcp.dev](https://reamcp.dev)
(usage cases, tool reference, content policy). MCP Registry: `io.github.morluto/rea`.
Python port: PyPI `rea-mcp`. Node requirement: 22.19+/24.11+/26+ (**not** 23/25).
This host: v26.12.1 (homebrew node repaired 2026-10-22 for exactly this).

## Equip with M2 (validated wiring)

Merge into a world policy (`inherit_mcp: false`; policy.py auto-adds `ToolSearch`
when `mcp_servers` is set) — see `policy-fragment.json` next to this file:

```json
{
  "mcp_servers": { "rea": { "command": "npx", "args": ["-y", "rea-agents@6.7.0", "mcp"] } },
  "mcp_tools": ["mcp__rea__*"]
}
```

- **Pin the version** (`rea-agents@6.7.0`, current as of 2026-10-22 — re-check with
  `npm view rea-agents dist-tags.latest`). Prewarm M1-side once so the session's
  MCP spawn is fast: `npx -y rea-agents@6.7.0 --version`.
- Tools observed working (called by a session in the atlas-rea experiment):
  `analyze_javascript_application`, `search_strings`, `inspect_analysis_view`,
  `recover_javascript_sources`.
- The server runs **outside the sandbox with M1's access** — trusted tool only;
  analyze only software you own or are authorized to examine (REA's own content
  policy says the same).

## Why it matters here (measured)

The 788 KB minified-bundle problem (run-2): raw file reads of minified JS are
all-or-nothing dose — any read pulls the whole line, and analysis-over-captures
handed off 10/10. **REA inverts the dose**: the server holds the material and
returns digests — the experiment session extracted the embedded Gigya apiKey
prefix (`3_0VMgSDVH3Y`) and the bundle's module graph (101 modules, sha256)
**without a single raw bundle read**.

## Pen law (still applies)

REA changes *what enters context* (digests, not raw lines) — it does not remove
the entry gate: the composing step after tool results still handed off in the
validation run (pen: 1× 5-5, then 23× 4-8, flag). Run REA-equipped sessions
through the micro-lane discipline: resample on gate, `harness/pencheck.py`
after every send, reference-form output per `secrets-without-exposure`.

## Ghidra (and other native providers)

- **Optional, bring-your-own.** For *native binaries* REA drives **Ghidra
  headlessly as a provider**: imports the binary into a throwaway Ghidra
  project, waits for auto-analysis, then answers focused questions (search,
  decompile, references, traces) with evidence attached. Hopper can be
  auto-installed by `rea-agents setup` with explicit approval; IDA has its own
  guide (incl. an optional native MCP bridge); experimental Windows Ghidra
  support; 16-bit DOS via Ghidra.
- **Installation split:** REA (the MCP server) handles *invocation and lifecycle* — headless drive, throwaway project, auto-analysis wait, provider selection, startup deadlines — but **does not install Ghidra or Java**: BYO both, then `rea doctor` verifies and setup saves the verified path. One exception: `rea-agents setup` CAN auto-install **Hopper** with explicit approval (Ghidra/IDA are never auto-installed; IDA/Hopper/JEB licences are yours). Provider tuning via env
  (`REA_GHIDRA_STARTUP_TIMEOUT_MS`, `REA_HOPPER_STARTUP_TIMEOUT_MS`; provider
  selection per format).
- **Not required** for the JS/Electron/ASAR/.NET static analysis our validation
  used — the atlas-rea run needed no native engine.
- **Native verification (2026-10-22, acceptance test passed):** REA accepts
  Ghidra **12.1.x only** (12.2 rejected at preflight); version/launcher/JDK
  checks passed with 12.1.4 + JDK 25.0.5; the one gap is upstream — the
  official 12.1.4 distribution ships **no `mac_arm_64` decompiler binary**
  (linux_x86_64/win_x86_64 only; the linux ELF is not Rosetta-runnable).
  Remedy: build the decompiler from Ghidra source for darwin/arm64, or run
  the Ghidra provider on a Linux host. Meanwhile REA's `inspect_with_objdump`
  provider fully covers Mach-O analysis: an all-5-5 12-turn session (pen HELD,
  no fallback) hand-rebuilt a test binary's C from arm64 disassembly —
  functions, hardening, strings with addresses — verified correct against source.
