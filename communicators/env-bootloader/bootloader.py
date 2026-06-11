#!/usr/bin/env python3
import sys
import uuid
from pathlib import Path

def find_communicators_root(start=None):
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback

def resolve_path(scope: str, target: str) -> str:
    comm_root = find_communicators_root()
    if scope in ("internal", "", "comm", "communicators"):
        return str(comm_root / target)
    if scope == "host":
        return target
    raise ValueError(f"Unknown scope: {scope}")

def load_module(scope, path):
    program_path = Path(resolve_path(scope, path))
    prefix_path = Path(resolve_path('internal', 'env-bootloader/prefix.py'))
    if not prefix_path.exists():
        print(f"Error: prefix not found at {prefix_path}")
        sys.exit(1)
    if not program_path.exists():
        print(f"Error: program not found at {program_path}")
        sys.exit(1)
    prefix_code = prefix_path.read_text().replace('{insert path here}', str(find_communicators_root()))
    user_code = program_path.read_text()
    combined = (
        prefix_code.rstrip()
        + '\n\n\n# ==================== USER PROGRAM ====================\n'
        + user_code
    )

    # Save to temp/{uuid}.py for inspection/tracebacks
    temp_dir = Path(resolve_path("internal", "temp"))
    temp_dir.mkdir(exist_ok=True, parents=True)
    temp_file = temp_dir / f"{uuid.uuid4().hex}.py"
    temp_file.write_text(combined)

    print(f"→ Combined script written to {temp_file}")

    return compile(combined, str(program_path), 'exec'), temp_file

def main():
    if len(sys.argv) < 2:
        print("Usage: bootloader.py <full_path>")
        sys.exit(1)

    code_obj, temp_file = load_module('internal', 'state-methods/namespace.py')

    try:
        comm_root = find_communicators_root()
        ns_path = str(comm_root / 'state-methods/namespace.py')
        subprocess.Popen(
            [sys.executable, ns_path],
            start_new_session=True,
            stdout=open(str(comm_root / 'ns_server.log'), 'a'),
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    except:
        print('subprocess.Popen failure')

    # Run original code generated in RAM (never the temp file)
    try:
        exec(code_obj, {"__file__": str(temp_file), "__name__": "__main__"})
    finally:
        # Uncomment if you want automatic cleanup
        # temp_file.unlink(missing_ok=True)
        pass


if __name__ == "__main__":
    main()
