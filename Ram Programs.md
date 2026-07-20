# Storing and Running Python Programs in RAM

**Created:** 2026-06-22  
**Tags:** #python #linux #performance #tmpfs #memfd #metaprogramming #runtime-codegen #ram

> **Goal**: Have runtime-generated Python source (or full programs) live in RAM so they can be executed or imported from *any* other Python process on the machine, with minimal latency, dynamic memory usage (no huge pre-reserved blocks), and without traditional ramdisk overhead.

---

## Why This Matters

You often generate Python code at runtime (metaprogramming, dynamic agents, custom communicators, test harnesses, etc.). Writing it to disk works, but you lose the latency guarantee and introduce unnecessary I/O. Old-school ramdisks (`/dev/ramX`) force you to reserve a fixed block of memory upfront.

The sweet spot is **tmpfs** — the modern, kernel-native way to get RAM-backed files with normal filesystem semantics and on-demand page allocation.

---

## The Pragmatic Default: tmpfs (`/dev/shm`)

### What You Get
- Normal paths (`/dev/shm/my_program.py`) that **any** process can open, `import`, `exec`, or run with `python`.
- Memory is allocated **only as you write** (page faults). No pre-reserving megabytes or gigabytes.
- Extremely low latency — pure RAM access after the initial write.
- Automatic cleanup: `unlink()` or reboot frees everything.
- Works with shebangs, packages, `.pyc` files, etc.

On most Linux systems `/dev/shm` is already a tmpfs mount (often 50% of RAM or container-limited). `/tmp` is also frequently tmpfs.

### Generator Pattern (Create the Program in RAM)

```python
import os

generated_source = '''#!/usr/bin/env python3
"""
This entire program was generated at runtime.
It lives only in RAM until unlinked.
"""
import sys
print("Running from RAM-backed tmpfs")
print("Python:", sys.executable)
print("File:", __file__ if "__file__" in globals() else "executed via exec()")
'''

path = "/dev/shm/runtime_program.py"

with open(path, "w", encoding="utf-8") as f:
    f.write(generated_source)

os.chmod(path, 0o755)  # Make it directly executable if desired
print(f"✅ Runtime program written to {path}")
```

### Consumer Patterns (Run from Anywhere)

**Any shell / subprocess on the machine:**
```bash
python3 /dev/shm/runtime_program.py --arg1 value
```

**As an importable module (recommended for libraries):**
```python
import sys
sys.path.insert(0, "/dev/shm")
import runtime_program

# Or more cleanly:
import importlib.util
spec = importlib.util.spec_from_file_location("runtime_program", "/dev/shm/runtime_program.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
```

**Inside another running Python process:**
```python
exec(open("/dev/shm/runtime_program.py").read())
```

### Using `tempfile` for Automatic Unique Names

```python
import tempfile
import os

with tempfile.NamedTemporaryFile(
    mode="w",
    suffix=".py",
    prefix="gen_",
    dir="/dev/shm",
    delete=False,
    encoding="utf-8"
) as f:
    f.write(generated_source)
    path = f.name

os.chmod(path, 0o755)
# ... later ...
os.unlink(path)  # Explicit cleanup
```

### Pre-compiling to `.pyc` for Faster Subsequent Loads

```python
import py_compile
py_compile.compile(path, cfile=path + "c", optimize=2)
```

Then future `import` or `python` invocations use the bytecode directly.

### Private / Size-Controlled tmpfs Mount

```bash
# Create a private 256 MiB tmpfs only you can access
mkdir -p ~/ram
sudo mount -t tmpfs -o size=256M,mode=700,uid=$(id -u),gid=$(id -g) tmpfs ~/ram
```

Then use `~/ram/...` paths. Unmount with `sudo umount ~/ram` when done (or it disappears on reboot).

---

## Pure Anonymous RAM: `os.memfd_create` (No Filesystem Path)

When you need **zero visible filesystem artifacts** (strict security, sandboxing, or you already have socket-based process coordination).

### Basic Creation

```python
import os

fd = os.memfd_create("my_runtime_program", os.MFD_CLOEXEC)
os.write(fd, generated_source.encode("utf-8"))
os.lseek(fd, 0, os.SEEK_SET)

# fd is now a seekable, RAM-backed anonymous file descriptor
print(f"memfd created, fd={fd}")
```

### Making It Usable from Other Processes

You must transfer the file descriptor:

1. **Best**: Unix domain socket + `SCM_RIGHTS` (ancillary data). Zero-copy, secure, standard pattern.
2. **Hacky but simple**: Expose via `/proc/<pid>/fd/<fdnum>` (fragile — receiver must know your PID and current fd number; same UID usually required).

Once the receiver has the fd:
```python
import os

# received_fd came from socket or /proc path
with os.fdopen(received_fd, "r") as f:
    source = f.read()

exec(compile(source, "<memfd>", "exec"), {"__name__": "__main__"})
```

Or build a proper `importlib` loader around the fd for module semantics.

**Complexity warning**: This is no longer "just like a file on disk." You are building a small IPC protocol for fd passing. Only worth it when tmpfs paths are unacceptable.

---

## Comparison

| Dimension                  | tmpfs (`/dev/shm`)                  | memfd_create + fd passing             | Regular disk file + page cache |
|---------------------------|-------------------------------------|---------------------------------------|--------------------------------|
| Memory allocation         | On-demand pages                     | On-demand pages                       | On-demand (OS cache)           |
| Upfront reservation       | None (respects mount `size=`)       | None                                  | None                           |
| Visible path              | Yes (normal fs path)                | No (anonymous fd only)                | Yes                            |
| Access from *any* process | Yes (permissions)                   | Requires explicit fd transfer         | Yes                            |
| Setup complexity          | Trivial (just `open()` + `write`)   | Medium–High (socket plumbing)         | Trivial                        |
| Best for                  | 95%+ of runtime codegen use cases   | High-security / no-fs-policy envs     | When RAM guarantee not critical|
| Cleanup                   | `unlink()` or reboot                | Close last fd                         | Manual or temp file            |

---

## Gotchas & Production Tips

### Permissions & Security
- Default `/dev/shm` is usually `1777` with sticky bit (anyone can create, only owner can delete their files).
- For sensitive generated code: use a private mounted tmpfs with `mode=700`.
- Never put secrets or credentials in world-readable tmpfs files.

### Size Limits
```bash
df -h /dev/shm
```
Container runtimes often give `/dev/shm` only 64 MiB by default. Mount your own larger tmpfs when needed.

### Volatility
Everything disappears on reboot or `umount`. This is usually *desired* for ephemeral generated programs. If you need persistence across reboots, you're using the wrong tool.

### Shebangs & Direct Execution
Add `#!/usr/bin/env python3` (or full path) and `chmod +x`. Works perfectly from tmpfs.

### Large Generated Programs
Still fine. Write in chunks if memory pressure is a concern during generation. Consider generating bytecode directly in some advanced cases.

### Cross-Platform Reality
- **Linux**: tmpfs + memfd are excellent.
- **macOS**: Limited tmpfs equivalents; often fall back to disk + cache or use `shm_open`.
- **Windows**: No native equivalent. Use `tempfile` on disk and accept page cache behavior, or install a third-party RAM disk driver. Abstract the backend if you need portability.

### When the Latency Benefit Actually Matters
For normal programs the difference vs. a hot page-cached SSD file is often small (interpreter startup dominates). The RAM approach shines when you have:
- Extremely hot invocation paths (thousands of times per second)
- Very large generated source trees
- Unpredictable or throttled disk I/O (containers, network filesystems, CI)
- Strict latency SLAs or benchmarking

---

## Integration Ideas for Heavy Metaprogramming / AI Infrastructure Work

- Dynamic "communicator" modules generated at runtime and imported by worker pools.
- Ephemeral agent scaffolds or tool definitions that other processes can hot-load.
- In-memory plugin systems where the core process generates and publishes extensions.
- Fast benchmark / test harness generation without polluting disk or `/tmp`.
- Self-modifying or self-extending Python programs that stay purely in RAM.

---

## Quick Reference Commands

```bash
# Inspect
df -h /dev/shm
mount | grep tmpfs

# Manual private tmpfs
mkdir -p ~/ram && sudo mount -t tmpfs -o size=512M,mode=700 tmpfs ~/ram

# Clean specific file
rm /dev/shm/runtime_program.py

# See what's using /dev/shm
lsof +D /dev/shm
```

---

## References

- `man 2 memfd_create` and `man 5 tmpfs`
- Python docs: `os.memfd_create`, `tempfile`, `importlib.util`
- Linux kernel `Documentation/filesystems/tmpfs.rst`
- `multiprocessing.shared_memory` (great for *data*, not source code)

---

**Future extensions you might add to this note:**
- Your own benchmarks (invocation latency tmpfs vs disk vs memfd)
- Container-specific mount recipes (Docker `--shm-size`, Kubernetes emptyDir `medium: Memory`)
- A small reusable `ram_program.py` helper class you build over time
- Handling of generated packages with multiple files

This note should serve as a solid, copy-paste-ready reference for years. Update it as you discover new patterns in your Analysis Labs work.