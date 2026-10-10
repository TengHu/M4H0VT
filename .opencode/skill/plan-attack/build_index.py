#!/usr/bin/env python3
"""Print the plan-attack technique arsenal and worked-example library in the
native skill format (<available_skills> with name + description), generated
fresh from techniques/*/TECHNIQUE.md and examples/*/EXAMPLE.md frontmatter at
call time."""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TECH_DIR = HERE / "techniques"
EXAMPLE_DIR = HERE / "examples"


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("missing frontmatter")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def load_dir(base, filename):
    rows = []
    if not base.is_dir():
        return rows
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        f = d / filename
        if not f.exists():
            continue
        fm = parse_frontmatter(f.read_text())
        rows.append((fm["name"], fm.get("description", ""), f.relative_to(HERE.parents[2])))
    return sorted(rows)


def load_techniques():
    return load_dir(TECH_DIR, "TECHNIQUE.md")


def load_examples():
    return load_dir(EXAMPLE_DIR, "EXAMPLE.md")


def print_block(tag, rows):
    print(f"<available_{tag}>")
    for name, desc, path in rows:
        print("  <skill>")
        print(f"    <name>{name}</name>")
        print(f"    <description>{desc}</description>")
        print(f"    <path>{path}</path>")
        print("  </skill>")
    print(f"</available_{tag}>")


def main():
    print_block("skills", load_techniques())
    print_block("examples", load_examples())


if __name__ == "__main__":
    sys.exit(main())
