#!/usr/bin/env python3
import subprocess, sys, uuid, traceback, marshal
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

def execution_harness(target_path, wait=False):
    comm_root = find_communicators_root()
    code_obj, _ = load_module('internal', target_path)
    try:
        old = False
        proc = subprocess.Popen([sys.executable, '-c', f"import marshal;exec(marshal.loads({marshal.dumps(code_obj)!r}))"],
            start_new_session=True,
            stdout=open(str(comm_root / 'ns_server.log'), 'a'),
            stderr=subprocess.STDOUT,
            close_fds=True)

        if old is True:
            proc = subprocess.Popen([sys.executable, '-c', code_obj],
                start_new_session=True,
                stdout=open(str(comm_root / 'ns_server.log'), 'a'),
                stderr=subprocess.STDOUT,
                close_fds=True)
        if wait:
            proc.wait()
    except Exception as e:
        print(f'execution_harness failure on: {target_path}')
        print(e)
        traceback.print_exception(type(e), e, e.__traceback__)

def main():
    execution_harness('state-methods/namespace.py', wait=False)
    execution_harness('transpiler/egg_transpiler.py', wait=True)

    print('bootloader sequence complete')

if __name__ == "__main__":
    main()
