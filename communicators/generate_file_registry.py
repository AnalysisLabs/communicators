#!/usr/bin/env python3
"""
One-shot generator for file_registry.json

Usage:
    nix-shell -p python3 --run 'python3 generate_file_registry.py "/home/prometheusd/Analysis Labs/Dev Tools/com-branches/orchestrated-4/communicators" > file_registry.json'
"""

import sys
import uuid
import json
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_file_registry.py /absolute/path/to/root", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    items = []

    for path in sorted(root.rglob("*")):
        # Skip anything inside a __pycache__ directory
        if "__pycache__" in path.parts:
            continue

        # Skip .md files
        if path.is_file() and path.suffix.lower() == ".md":
            continue

        items.append(path)

    registry = []
    for path in items:
        rel = path.relative_to(root)
        name = path.name
        parent = rel.parent.as_posix()
        if parent == ".":
            parent = ""

        registry.append({
            "uuid": str(uuid.uuid4()),
            "absolute_path": str(path),
            "file_path": parent,
            "file_name": name
        })

    print(json.dumps(registry, indent=2))

if __name__ == "__main__":
    main()
