#!/usr/bin/env python3

# ---------------------------------------------------------------------------
# Transponder Management
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Input Management (parsing)
# ---------------------------------------------------------------------------

def contents_from_file_ref(file_ref: PathReffs.FileRef) -> str:
    """Read the real-filesystem file named by file_ref. Returns a code blob."""
    path = PathReffs.resolve_path(
        file_ref.uuid,
        file_ref.file_path,
        file_ref.file_name,
    )
    return path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# metamorphosis_writer Mapping (Possibly needed to abstract interface with meta_writer)
# ---------------------------------------------------------------------------

_harness_ref = PathReffs.FileRef(
    uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
    file_path="Metamorphosis/execution",
    file_name="execution_harness.py",
)

load_module, = AtomicImporter.from_path_import(
    PathReffs.resolve_path(
        _harness_ref.uuid,
        _harness_ref.file_path,
        _harness_ref.file_name,
    ),
    "load_module",
)

prefix = (
    COMMUNICATORS_ROOT
    / "Metamorphosis"
    / "execution"
    / "prefix.py"
).read_text(encoding="utf-8")

_writer_ref = PathReffs.FileRef(
    uuid="93752a7b-6da4-49ff-b704-e2bc2c32926a",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis_writer.py",
)

_writer_src, _ = load_module(
    src=_writer_ref,
    dst="Metamorphosis/DB/metamorphosis_writer.py",
    prefix=prefix,
)

write_file, read_file = AtomicImporter.from_code_import(
    _writer_src,
    "metamorphosis_writer",
    "write_file",
    "read_file",
)

# ---------------------------------------------------------------------------
# Ouput management (parsing, routing and delivery)
# ---------------------------------------------------------------------------

def request(
    db_ref: str,
    file_ref: PathReffs.FileRef | None = None,
    blob: str | None = None,
):
    """
    db_ref  – virtual path inside metamorphosis.db (VFS).
    file_ref / blob – if either is given, save; otherwise pull.

    Save returns the writer node id.
    Pull returns the stored text.
    """
    if blob is None and file_ref is None:
        return read_file(db_ref)

    if blob is None:
        blob = contents_from_file_ref(file_ref)

    return write_file(db_ref, blob)

# ---------------------------------------------------------------------------
# Port management (Still critical when namespace is a server)
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



def main() -> None:
    """Boot sequence for the namespace server process."""

    host, port = "localhost", 8765
    if port_in_use(host, port):
        kill_port(host, port)

    print(f"→ (False) Starting namespace server on {host}:{port}")

def secondary() -> None:
    print(f"→ Namespace imported")

if __name__ == "__main__":
    main()
else:
    secondary()

