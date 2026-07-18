#!/usr/bin/env python3
"""Regenerate DocStar golden JSON after a maintainer-approved schema change."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DOCSTAR = ROOT / "docstar.py"
CORPUS = ROOT / "fixtures" / "corpus"
GOLDEN = ROOT / "golden"
COMMANDS = {
    "dump": ["dump"],
    "harvest": ["harvest"],
    "check": ["check"],
    "brief": ["brief", "TA2.3"],
    "verify": ["verify", "--baseline", "HEAD"],
    "classify": ["classify", "--pending"],
}


def top_keys(value):
    return sorted(value) if isinstance(value, dict) else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Expected schema version, for example eg-3")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "internal"))
    import entity_model

    if args.schema != entity_model.SCHEMA_VERSION:
        parser.error(
            f"--schema={args.schema} does not match engine schema {entity_model.SCHEMA_VERSION}"
        )

    generated = {}
    summaries = []
    for name, command in COMMANDS.items():
        result = subprocess.run(
            [sys.executable, str(DOCSTAR), *command, "--json", "--corpus", str(CORPUS)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"{name}: command failed ({result.returncode}): {result.stderr}", file=sys.stderr)
            return 1
        try:
            new_value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            print(f"{name}: invalid JSON: {exc}", file=sys.stderr)
            return 1
        if new_value.get("schema_version") != args.schema:
            print(f"{name}: missing schema_version={args.schema}", file=sys.stderr)
            return 1
        path = GOLDEN / f"{name}.json"
        try:
            old_value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old_value = {}
        summaries.append(
            (name, old_value.get("schema_version"), new_value.get("schema_version"),
             sorted(set(top_keys(new_value)) - set(top_keys(old_value))),
             sorted(set(top_keys(old_value)) - set(top_keys(new_value))))
        )
        generated[path] = result.stdout

    for path, content in generated.items():
        path.write_text(content, encoding="utf-8")
    for name, old_schema, new_schema, added, removed in summaries:
        print(
            f"{name}: {old_schema or 'unversioned'} -> {new_schema}; "
            f"top-level added={added}; removed={removed}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
