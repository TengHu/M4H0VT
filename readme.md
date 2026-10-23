# redteam-manual

A capability laundering experiment: a less capable, uncensored model (**M1**)
launders capability from a more capable, censored model (**M2**) whose refusal
policy is strict and undisclosed. M1 decomposes a terminal goal, probes M2's
refusals, and routes each refusal through benign, dual-use framings until M2
willingly does the work.

## How it works

- **Outer loop** (`outer.md`) — runs the search, judges residuals, and
  re-goals until the terminal goal **G** is satisfied.
- **Inner search** (`search.md`) — alternates a forward pair **F** (direct
  ask, exposes refusals) with a backward pair **B** (benign world that
  answers what the refusal named), banking accepted components.
- **World craft** (`world-craft.md`) — doctrine for building the worlds the
  asks live in.
- **Ledger** (`harness/taskledger.py`) — append-only JSONL of refusals
  (`t`) and the `(ask, world)` pairs that closed them (`aw`), per target
  model; model-agnostic recipes in `runs/task-ledger/recipes/`.

## Quick start

1. Set your OpenRouter key in `m2/openrouter/.env`:

   ```
   OPENROUTER_API_KEY=sk-or-...
   ```

2. Set the terminal goal **G** and iteration budget in `outer.md`.

3. Run M2 against a task:

   ```
   python m2/openrouter/run.py "<task>" --cwd <dir> \
       --policy-file <policy.json> --model google/gemini-4-argon
   ```

   (The `claude_code_skill/` backend is an alternative runner — see
   `m2/README.md`.)

4. Drive the loop from `outer.md`: read `search.md` for the algorithm, write
   each send's `(ask, world)` pair, and record outcomes in the ledger.

## Disclaimer

For educational purposes only. Use at your own caution.
