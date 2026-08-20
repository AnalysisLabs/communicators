#!/usr/bin/env python3
"""
metamorphosis_db.py – create (or recreate) the metamorphosis / namespace SQLite database.

Analogous to VirtualFS.py from the bootstrap stage.

Responsibilities
----------------
- Resolve the database file path
- Honor the ephemeral / persistent switch
- Create the empty database file
- Install the core structures (object_catalog + VFS tables)

It does not seed domain data and does not provide the read/write API.
Those belong to later modules (metamorphosis_layout.py, metamorphosis_writer.py).
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
_meta_structures_ref = FileRef(
    uuid="09126e37-7bd4-4b2d-a455-f44125ab9048",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis_structures.py",
)

combined, _ = load_module(
    src=_meta_structures_ref,
    dst="Metamorphosis/DB/metamorphosis_structures.py",
    prefix=prefix,
)

create_core_structures, = from_code_import(
    combined,
    "metamorphosis_structures",
    "create_core_structures",
)

# ---------------------------------------------------------------------------
# Path & lifetime configuration
# ---------------------------------------------------------------------------

# Default location: sibling of this script (same convention as bootstrap).
DEFAULT_DB_FILE = Path(__file__).resolve().parent / "metamorphosis.db"

# Development default: wipe on every init so schema experiments stay cheap.
# Flip to False when real persistent data (tokens, billing, etc.) appears.
EPHEMERAL: bool = True


def _resolve_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return DEFAULT_DB_FILE


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def init_metamorphosis_db(
    db_path: Path | str | None = None,
    *,
    ephemeral: bool | None = None,
) -> Path:
    """
    Create (or recreate) the metamorphosis database and its core tables.

    Parameters
    ----------
    db_path:
        Override the default location.  None → DEFAULT_DB_FILE.
    ephemeral:
        If True, delete any existing file first.
        If None, fall back to the module-level EPHEMERAL flag.

    Returns
    -------
    Path
        Absolute path of the database file that was created.
    """
    path = _resolve_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    do_wipe = EPHEMERAL if ephemeral is None else ephemeral
    if do_wipe and path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        create_core_structures(conn)
        conn.commit()
    finally:
        conn.close()

    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize the metamorphosis SQLite database")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override database path",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Do not wipe an existing database (overrides EPHEMERAL=True)",
    )
    args = parser.parse_args()

    db = init_metamorphosis_db(
        db_path=args.db,
        ephemeral=not args.persistent,
    )
    mode = "persistent" if args.persistent else "ephemeral"
    print(f"Initialized metamorphosis database ({mode}) at: {db}")
