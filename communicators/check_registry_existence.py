#!/usr/bin/env python3
"""
Report three classes of registry problems (read-only):

  1. stale entries      – registry entries whose relative path does not exist on disk
  2. orphan files       – files/dirs that generate_file_registry.py would include
                         but that currently have no matching registry entry
  3. broken references  – FileRef(...) triples in source that do not match any
                         registry entry (exact uuid + file_path + file_name)
"""

from __future__ import annotations
import ast
import json
import sys
from pathlib import Path


def find_communicators_root(start=None) -> Path:
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()


def discover_disk_items(root: Path) -> list[tuple[str, str, Path]]:
    """
    Same discovery rules as generate_file_registry.py:
      - recursive walk
      - skip anything inside a __pycache__ directory
      - skip .md files
      - keep both files and directories
    Returns list of (file_path, file_name, absolute Path).
    """
    items = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and path.suffix.lower() == ".md":
            continue

        rel = path.relative_to(root)
        name = path.name
        parent = rel.parent.as_posix()
        if parent == ".":
            parent = ""
        items.append((parent, name, path))
    return items


def _extract_str(node: ast.AST | None) -> str | None:
    """Return the string value of a Constant/Str node, else None."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Python < 3.8 compatibility (unlikely, but cheap)
    if isinstance(node, ast.Str):
        return node.s
    return None


def extract_filerefs_from_source(
    source: str, filename: str
) -> list[tuple[str, str, str, int]]:
    """
    Parse *source* and return every FileRef(uuid=..., file_path=..., file_name=...)
    found via AST.

    Each result is (uuid, file_path, file_name, lineno).
    Only keyword-argument forms are recognised (matches actual codebase style).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    results: list[tuple[str, str, str, int]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Accept both bare FileRef(...) and module.FileRef(...)
        func = node.func
        is_fileref = (
            (isinstance(func, ast.Name) and func.id == "FileRef")
            or (isinstance(func, ast.Attribute) and func.attr == "FileRef")
        )
        if not is_fileref:
            continue

        kwargs: dict[str, str | None] = {
            "uuid": None,
            "file_path": None,
            "file_name": None,
        }
        for kw in node.keywords:
            if kw.arg in kwargs:
                kwargs[kw.arg] = _extract_str(kw.value)

        uuid = kwargs["uuid"]
        file_path = kwargs["file_path"]
        file_name = kwargs["file_name"]

        # Only record complete, well-formed triples
        if uuid is not None and file_path is not None and file_name is not None:
            results.append((uuid, file_path, file_name, node.lineno))

    return results


def scan_codebase_filerefs(root: Path) -> list[tuple[str, str, str, str, int]]:
    """
    Walk every .py file under *root* and collect FileRef triples.
    Returns list of (uuid, file_path, file_name, relative_source_file, lineno).
    """
    found: list[tuple[str, str, str, str, int]] = []

    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel = path.relative_to(root).as_posix()
        for uuid, file_path, file_name, lineno in extract_filerefs_from_source(
            source, rel
        ):
            found.append((uuid, file_path, file_name, rel, lineno))

    return found


def main() -> None:
    root = find_communicators_root()
    registry_path = root / "file_registry.json"

    if not registry_path.exists():
        print(f"error: {registry_path} not found", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(registry_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Index the registry
    # ------------------------------------------------------------------
    # Exact triple → entry
    registry_triples: set[tuple[str, str, str]] = set()
    # (file_path, file_name) → list of uuids that claim it
    path_to_uuids: dict[tuple[str, str], list[str]] = {}
    # uuid → list of (file_path, file_name)
    uuid_to_paths: dict[str, list[tuple[str, str]]] = {}

    for entry in entries:
        uuid = entry["uuid"]
        file_path = entry.get("file_path", "")
        file_name = entry["file_name"]
        triple = (uuid, file_path, file_name)
        registry_triples.add(triple)
        path_to_uuids.setdefault((file_path, file_name), []).append(uuid)
        uuid_to_paths.setdefault(uuid, []).append((file_path, file_name))

    # ------------------------------------------------------------------
    # 1. Stale entries (in registry, missing on disk)
    # ------------------------------------------------------------------
    stale = []
    for entry in entries:
        file_path = entry.get("file_path", "")
        file_name = entry["file_name"]
        if file_path:
            candidate = root / file_path / file_name
        else:
            candidate = root / file_name
        if not candidate.exists():
            stale.append((entry["uuid"], file_path, file_name, candidate))

    # ------------------------------------------------------------------
    # 2. Orphan files (on disk under generator rules, missing from registry)
    # ------------------------------------------------------------------
    disk_items = discover_disk_items(root)
    orphans = []
    for file_path, file_name, abs_path in disk_items:
        key = (file_path, file_name)
        if key not in path_to_uuids:
            orphans.append((file_path, file_name, abs_path))

    # ------------------------------------------------------------------
    # 3. Broken references (FileRef triples in source that do not match registry)
    # ------------------------------------------------------------------
    code_refs = scan_codebase_filerefs(root)
    broken = []
    for uuid, file_path, file_name, source_file, lineno in code_refs:
        triple = (uuid, file_path, file_name)
        if triple not in registry_triples:
            # Collect a little diagnostic context
            same_path_uuids = path_to_uuids.get((file_path, file_name), [])
            same_uuid_paths = uuid_to_paths.get(uuid, [])
            broken.append(
                (
                    uuid,
                    file_path,
                    file_name,
                    source_file,
                    lineno,
                    same_path_uuids,
                    same_uuid_paths,
                )
            )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print(f"Registry root              : {root}")
    print(f"Registry entries           : {len(entries)}")
    print(f"Disk items (generator rules): {len(disk_items)}")
    print(f"FileRef instances in code  : {len(code_refs)}")
    print()

    if not stale and not orphans and not broken:
        print("Clean — registry, disk, and all FileRef triples agree.")
        return

    # --- Stale ---
    if stale:
        print(f"=== Stale entries ({len(stale)}) ===")
        print("(in registry, missing on disk)\n")
        for uuid, file_path, file_name, candidate in stale:
            rel = f"{file_path}/{file_name}" if file_path else file_name
            print(f"  {rel}")
            print(f"    uuid     : {uuid}")
            print(f"    expected : {candidate}")
            print()
    else:
        print("=== Stale entries (0) ===\n")

    # --- Orphans ---
    if orphans:
        print(f"=== Orphan files ({len(orphans)}) ===")
        print("(on disk under generator rules, absent from registry)\n")
        for file_path, file_name, abs_path in orphans:
            rel = f"{file_path}/{file_name}" if file_path else file_name
            print(f"  {rel}")
            print(f"    path : {abs_path}")
            print()
    else:
        print("=== Orphan files (0) ===\n")

    # --- Broken references ---
    if broken:
        print(f"=== Broken references ({len(broken)}) ===")
        print("(FileRef triple in source does not match any registry entry)\n")
        for (
            uuid,
            file_path,
            file_name,
            source_file,
            lineno,
            same_path_uuids,
            same_uuid_paths,
        ) in broken:
            rel = f"{file_path}/{file_name}" if file_path else file_name
            print(f"  {rel}")
            print(f"    uuid      : {uuid}")
            print(f"    location  : {source_file}:{lineno}")

            if same_path_uuids:
                print(f"    note      : path exists in registry under uuid(s) {same_path_uuids}")
            if same_uuid_paths:
                print(f"    note      : this uuid is registered for path(s) {same_uuid_paths}")
            if not same_path_uuids and not same_uuid_paths:
                print(f"    note      : neither uuid nor path appears in the registry at all")
            print()
    else:
        print("=== Broken references (0) ===\n")


if __name__ == "__main__":
    main()
