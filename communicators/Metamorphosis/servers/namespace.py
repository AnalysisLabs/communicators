#!/usr/bin/env python3
"""
namespace.py – kernel-stage namespace server entry point.

Refactored to use the kernel SQLite store (kernel_db / kernel_writer)
instead of the old in-memory BaseNamespace singleton.

Responsibilities
----------------
1. Ensure the kernel database exists (ephemeral in development).
2. Provide a small durable namespace API (initialize / populate / get)
   backed by document tables + the object catalog.
3. Manage the listening port and start the transponder-based
   namespace server.

The port-management helpers are intentionally left close to the
original implementation.  All durable state now goes through
kernel_writer; nothing is kept in a process-global dict.
"""

# ---------------------------------------------------------------------------
# Kernel store
# ---------------------------------------------------------------------------

# When this file lives inside the real communicators tree the imports will
# resolve normally.  While it sits in artifacts/ we keep the path flexible.
from metamorphosis_db import init_kernel_db
from metamorphosis_writer import (
    create_document,
    get_document,
    get_object,
    list_objects,
    put_document,
    register_object,
)

# Default document table used for general namespace key/value state.
_STATE_TABLE = "namespace_state"


def _ensure_kernel_db() -> Path:
    """Create the kernel database (honours EPHEMERAL) and the core state table."""
    path = init_kernel_db()
    # Make sure the primary document table exists and is catalogued.
    try:
        create_document(_STATE_TABLE, with_owner=True, register=True, owner=None)
    except Exception:
        # Table may already exist from a previous persistent run; that is fine.
        pass
    return path


# ---------------------------------------------------------------------------
# Durable namespace API  (replaces BaseNamespace + _namespaces)
# ---------------------------------------------------------------------------

def initialize_namespace(*names: str, owner: str | None = None) -> None:
    """
    Ensure each name exists as a top-level entry in the durable store.

    For every name we:
      - register an object_catalog entry of type 'namespace'
      - ensure an empty document exists under that key so later
        populate_namespace / get_namespace calls succeed.
    """
    for name in names:
        if not name or not isinstance(name, str):
            continue
        register_object(
            type="namespace",
            name=name,
            owner=owner,
            pointer=f"{_STATE_TABLE}:{name}",
        )
        # Seed an empty document if nothing is there yet.
        existing = get_document(_STATE_TABLE, name, owner=owner)
        if existing is None:
            put_document(_STATE_TABLE, name, {}, owner=owner)


def populate_namespace(
    name: str,
    data: dict[str, Any],
    *,
    owner: str | None = None,
    merge: bool = True,
) -> None:
    """
    Write (or merge) a dict into the durable namespace entry `name`.

    If merge=True (default) existing keys are preserved and updated;
    if merge=False the document is replaced entirely.
    """
    if not isinstance(data, dict):
        raise TypeError("populate_namespace expects a dict")

    current = get_document(_STATE_TABLE, name, owner=owner)
    if current is None:
        initialize_namespace(name, owner=owner)
        current = {}

    if merge and isinstance(current, dict):
        current.update(data)
        to_write = current
    else:
        to_write = data

    put_document(_STATE_TABLE, name, to_write, owner=owner)


def get_namespace(
    name: str,
    *,
    owner: str | None = None,
) -> dict[str, Any] | None:
    """Return the durable namespace document, or None if missing."""
    value = get_document(_STATE_TABLE, name, owner=owner)
    if value is None:
        return None
    if not isinstance(value, dict):
        return {"_value": value}
    return value


def list_namespaces(*, owner: str | None = None) -> list[str]:
    """Return the names of all registered namespace objects."""
    rows = list_objects(type="namespace", owner=owner)
    return [r["name"] for r in rows]


def debug_namespaces(*, owner: str | None = None) -> None:
    """Print a short summary of registered namespaces (development aid)."""
    names = list_namespaces(owner=owner)
    print("🧠 Namespaces:", sorted(names) if names else "(none)")


# ---------------------------------------------------------------------------
# Port management (unchanged in spirit from the original)
# ---------------------------------------------------------------------------

def port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if something is listening on (host, port) using a raw TCP connect."""
    if host == "localhost":
        host = "127.0.0.1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def kill_port(host: str = "localhost", port: int = 8765) -> None:
    """Aggressively kill anything listening on the port (Linux/macOS)."""
    if host == "localhost":
        host = "127.0.0.1"

    print(f"🔪 Checking/killing port {port}...")
    os.system(f"lsof -t -i:{port} | xargs kill -9 2>/dev/null || true")
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------

def _start_ns_server(host: str = "localhost", port: int = 8765) -> None:
    """
    Start the namespace server using the transponder abstraction.

    The transponder import is deferred so that pure data-plane use of this
    module (initialize/populate/get) does not require the full communicator
    runtime to be present.
    """
    try:
        # In the real tree this resolves through the prefix / import system.
        # While developing in isolation the import may fail; that is acceptable.
        transponder.persistent_server(host, port)
    except Exception as e:
        # Prefer Manifest when available; fall back to stderr.
        try:
            manifest.error(f"Failed to start namespace server: {e}")
        except Exception:
            print(f"Failed to start namespace server: {e}", file=sys.stderr)


def main() -> None:
    """Boot sequence for the namespace server process."""
    print("→ Ensuring kernel database …")
    db_path = _ensure_kernel_db()
    print(f"→ Kernel DB ready at {db_path}")

    host, port = "localhost", 8765
    if port_in_use(host, port):
        kill_port(host, port)

    print(f"→ Starting namespace server on {host}:{port}")
    _start_ns_server(host, port)


if __name__ == "__main__":
    main()
else:
    # When imported as a library (e.g. by other kernel-stage code) we still
    # make sure the DB and core state table exist, but we do not bind the port.
    try:
        _ensure_kernel_db()
    except Exception as e:
        print(f"namespace: kernel DB init deferred/failed: {e}", file=sys.stderr)
