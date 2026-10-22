"""World pre-send verification — the concrete checks behind world-craft's verify fields.

    python3 -m harness.worldcheck <world-cwd> [--policy FILE] [--declared-skill NAME ...]

Checks (each one bit a real send in the 2026-10 runs):

  1. skill plants   every `<cwd>/.claude/skills/*/SKILL.md` exists, is non-empty,
                    and carries `name:` + `description:` frontmatter (an empty
                    or missing SKILL.md = the session invents its own path).
  2. policy tools   the policy file (given, or `<cwd>/config.json`) lists every
                    tool the planted skills and the planned shape need:
                    `Skill` + `setting_sources:["project"]` when any skill is
                    planted, and `Grep` when analysis/windowed reads are planned
                    (a session without Grep falls back to whole-file reads —
                    the dose killer).
  3. ledger law     the world cwd is NOT inside a git repository (in-repo cwd
                    leaks git status, repo names and run intent — and the
                    environment attachments carry them into the entry surface).

Prints `OK` or one `ISSUE` per problem; exit 1 on any issue.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FRONTMATTER = ("name:", "description:")


def _issues_for_skills(cwd: Path, skills: list[Path]) -> list[str]:
    issues: list[str] = []
    for skill_md in skills:
        rel = skill_md.relative_to(cwd)
        text = skill_md.read_text(errors="replace")
        if not text.strip():
            issues.append(f"ISSUE empty skill file: {rel}")
            continue
        head = "\n".join(text.splitlines()[:10])
        for field in REQUIRED_FRONTMATTER:
            if field not in head:
                issues.append(f"ISSUE skill missing `{field}` frontmatter: {rel}")
    return issues


def _issues_for_policy(policy_path: Path, skills: list[Path]) -> list[str]:
    issues: list[str] = []
    if not policy_path.is_file():
        return [f"ISSUE policy file not found: {policy_path}"]
    try:
        policy = json.loads(policy_path.read_text())
    except json.JSONDecodeError as error:
        return [f"ISSUE policy does not parse: {policy_path} ({error})"]
    tools = policy.get("tools") or []
    if skills:
        if "Skill" not in tools:
            issues.append("ISSUE skills planted but `Skill` not in policy tools")
        sources = policy.get("setting_sources") or []
        if "project" not in sources:
            issues.append("ISSUE skills planted but `project` missing from setting_sources")
    if "Grep" not in tools:
        issues.append("ISSUE `Grep` not in policy tools — analysis sessions fall back "
                      "to whole-file reads (the dose killer)")
    if policy.get("sandbox"):
        issues.append("NOTE sandbox enabled: the sandbox-instructions attachment enters "
                      "the opening surface, and loopback connects may be refused — "
                      "drop it for micro-session worlds unless network shaping matters")
    return issues


def _issues_for_oss_manifest(cwd: Path) -> list[str]:
    """Validate the world's `.oss.json` manifest — written by whoever equipped
    an OSS tool (M1 at world-prep, or M2 in a tool-runner session): each entry
    records {repo, version, path, installed_by}; the recorded path must exist
    so 'M2 cloned/installed it' is a verified fact, not a session summary."""
    manifest = cwd / ".oss.json"
    if not manifest.is_file():
        return []
    issues: list[str] = []
    try:
        oss = json.loads(manifest.read_text())
    except json.JSONDecodeError as error:
        return [f"ISSUE .oss.json does not parse: {error}"]
    if not isinstance(oss, dict):
        return ["ISSUE .oss.json must be an object of tool → {repo, version, path}"]
    for tool, entry in oss.items():
        if not isinstance(entry, dict):
            issues.append(f"ISSUE .oss.json[{tool}]: entry must be an object")
            continue
        path = entry.get("path")
        if not path:
            issues.append(f"ISSUE .oss.json[{tool}]: missing 'path'")
            continue
        expanded = Path(path).expanduser()
        if not expanded.exists():
            issues.append(f"ISSUE .oss.json[{tool}]: recorded path does not exist: {path}")
        for field in ("repo", "version"):
            if not entry.get(field):
                issues.append(f"NOTE .oss.json[{tool}]: missing '{field}' (pin/traceability)")
    return issues


def _issues_for_ledger_law(cwd: Path) -> list[str]:
    probe = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        return [f"ISSUE in-repo cwd (ledger law: clean temp dir, benign slug) — "
                f"repo root: {probe.stdout.strip()}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="World pre-send verification")
    parser.add_argument("cwd", type=Path, help="world working directory")
    parser.add_argument("--policy", type=Path, help="policy file (default <cwd>/config.json)")
    args = parser.parse_args()
    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        print(f"ISSUE world cwd does not exist: {cwd}")
        return 1
    skills = sorted((cwd / ".claude" / "skills").glob("*/SKILL.md")) \
        if (cwd / ".claude" / "skills").is_dir() else []
    issues: list[str] = []
    issues += _issues_for_skills(cwd, skills)
    issues += _issues_for_policy(args.policy or (cwd / "config.json"), skills)
    issues += _issues_for_oss_manifest(cwd)
    issues += _issues_for_ledger_law(cwd)
    oss = (cwd / ".oss.json")
    print(f"  oss manifest: {'present' if oss.is_file() else 'none'}")
    planted = ", ".join(s.parent.name for s in skills) or "none"
    print(f"world: {cwd}")
    print(f"  skills planted: {planted}")
    for issue in issues:
        print(issue)
    if not issues:
        print("OK")
    return 1 if any(i.startswith("ISSUE") for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
