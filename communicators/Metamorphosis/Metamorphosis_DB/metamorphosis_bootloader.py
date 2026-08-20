#!/usr/bin/env python3
"""
metamorphosis_bootloader.py – thin orchestrator for metamorphosis DB initialization.

Analogous to DB_bootloader.py from the bootstrap stage.

Current sequence:

  1. metamorphosis_db.init_metamorphosis_db   → create file + core structures
                                   (object_catalog + VFS tables)
  2. (future) metamorphosis_layout     → optional seed rows / catalog entries

Keeps the boot path dumb and ordered.  Domain data access lives in
metamorphosis_writer.py; structure definitions live in metamorphosis_structures.py.
"""

# ---------------------------------------------------------------------------
# Bring in the execution harness so we can assemble a true prefixed source
# ---------------------------------------------------------------------------
_harness_ref = FileRef(
    uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
    file_path="Metamorphosis/execution",
    file_name="execution_harness.py",
)

load_module, = from_path_import(
    resolve_path(
        _harness_ref.uuid,
        _harness_ref.file_path,
        _harness_ref.file_name,
    ),
    "load_module",
)

# The Meta execution bootloader already wrote the prefix here
prefix = (
    find_communicators_root()
    / "Metamorphosis"
    / "execution"
    / "prefix.py"
).read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Assemble the real (prefix + metamorphosis_db) source, then extract the symbol
# ---------------------------------------------------------------------------
_meta_db_ref = FileRef(
    uuid="f306ba10-b72d-4cc9-9281-c75818f5b376",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis_db.py",
)

combined, _ = load_module(
    src=_meta_db_ref,
    dst="Metamorphosis/DB/metamorphosis_db.py",
    prefix=prefix,
)

init_metamorphosis_db, = from_code_import(
    combined,
    "metamorphosis_db",
    "init_metamorphosis_db",
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Initialize the metamorphosis / namespace SQLite database"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override database path (default: metamorphosis.db next to the modules)",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Do not wipe an existing database (overrides EPHEMERAL=True)",
    )
    args = parser.parse_args(argv)

    print("→ Initializing metamorphosis database …")
    path = init_metamorphosis_db(
        db_path=args.db,
        ephemeral=not args.persistent,
    )
    mode = "persistent" if args.persistent else "ephemeral"
    print(f"→ metamorphosis database ready ({mode}) at {path}")

    # Future extension point:
    # from metamorphosis_layout import seed_metamorphosis_layout
    # seed_metamorphosis_layout(path)

    print("metamorphosis boot sequence complete")


if __name__ == "__main__":
    main()
