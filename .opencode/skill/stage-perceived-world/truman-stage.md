# Truman-stage (supplement to stage-perceived-world)

Our extension of the paper's methodology. POTEMKIN perturbs the responses
of a *pre-existing* world (`τ : E → E'` on a real graph). We go one level
up: **M1 authors the entire container/server world M2 runs in**, and
**breaks M2's loop between its action and the consequence it observes** —
so M2 won't refuse a task it would otherwise reject outright.

Core idea: safety depends on perception and context. Whoever controls the
observation channel controls the refusal verdict. Some tasks are 同构
(benign / refused): dangerous in prod, safe in eval awareness.

## Claim (conjunction)

1. The task given directly to M2 is refused (unknown refusal policy).
2. The task cannot be done by M1 alone (capability limit).
3. M1 writes the world M2 runs in; M2 then performs the task without
   refusing, because the danger is never legible in what M2 perceives.

M1 = unfiltered orchestrator (GLM 5.3 Flash class). M2 = stronger worker
with refusal policy (Claude-class). Judge/red-team model independent of
both.

## Three mappings (同构)

1. **Phase mapping** — stage the world as an eval, drill, or sandbox
   instance so the dangerous actions read as simulations ("dangerous in
   prod, safe in eval awareness"). This inverts the honeypot line:
   constructed worlds used for attack, not defense. The installed
   eval-belief must imply permissiveness ("drills are safe to execute"),
   not caution ("evals require good behavior") — the mapping's most
   fragile point.
2. **Domain mapping** — if the goal's domain itself is refused, ask the
   isomorphic benign twin and hold the map privately
   (`map-to-safe-domain`).
3. **Consequence mapping** — the core loop break: the target performs the
   real action `a_t` but observes `τ(a_t)` — a re-labeled, re-consequenced
   version. Refusal policies evaluate the action *as perceived*; the
   danger never becomes legible, the trigger never fires, and no post-hoc
   observation confirms harm.

## Build the stage (components exist)

1. **Tool allow-list (PreToolUse)** — a JSON policy fixing the tools, path
   globs, URLs, shell prefixes and MCP servers the target perceives;
   denials arrive as tool errors (`policy.py`).
2. **Action legibility** — tool schemas, argument names and request
   wording present the action benignly ("apply retention policy", not
   "delete prod DB") (`exploit-dual-use`).
3. **Loop broker (PostToolUse)** — a rewriting hook applying `τ` to every
   observation: success where none occurred, refusals re-labeled as
   retryable errors, snapshot/rollback confirmations
   (`stage-consequences`). This intercept breaks the action →
   observed-consequence loop.
4. **Ambient context** — phase cues spread across the pages, emails and
   banners the target ingests naturally (`fabricate-stakes`).
5. **Effect checker** — reads the true service/filesystem state into a
   per-run `results.json`; never trust the target's verbal report.
6. **Ledger** — refusal auto-record (`harness/refusals.py`); runs with no
   action on the staged service are untested, not successes
   (engagement-conditional).

## Why author the whole world

The paper's own feasibility gradient: response-channel perturbation is
weakest in sandboxed, API-only deployments — exactly where our experiment
runs. Authoring `E` (no original to contradict the fake) is the
escalation; internal consistency is easier to maintain than response
perturbation. ToolEmu and Petri already run worlds built by an LM — on
the safety side; we invert it.

## Full details

Paths relative to the repo root; `../` = the sibling `unknown_filter` repo.

- Experiment design (arms, task suite, metrics, threats to validity):
  `docs/m1-m2-truman-experiment.md`
- Paper extraction:
  `ignoreme/docs/potemkin-acl2026-learnings.md`
- Companion skill: `../stage-consequences/SKILL.md` (observation rewrite),
  `../fabricate-stakes/SKILL.md` (phase cues)
