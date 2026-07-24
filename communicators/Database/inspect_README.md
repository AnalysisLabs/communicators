# `inspect.sh` – Self-contained VirtualFS Inspector

Place this script (and this README) in the `Database/` directory.

```
communicators/
├── Database/
│   ├── runtime_fs.db
│   ├── vfs_writer.py
│   ├── inspect.sh          ← the script
│   └── inspect_README.md   ← this file
└── env-bootloader/
    └── flake.nix
```

---

## Design goal

The script removes all environment boilerplate.  
Once it is in place you only ever type the specific thing you want to inspect.

You do **not** need to:

- manually `cd` into `env-bootloader`
- remember the long `nix --extra-experimental-features … develop` invocation
- worry about whether you are already inside the pure shell or not

The script detects the situation and, if necessary, re-executes itself inside the pure Nix environment automatically.

---

## One-time setup

```bash
cd Database
chmod +x inspect.sh
```

---

## Everyday usage

From the `Database/` directory (or any directory, as long as you invoke the script by path):

```bash
./inspect.sh tree
./inspect.sh ls
./inspect.sh ls Runtime/generated
./inspect.sh prefix
./inspect.sh cat Runtime/generated/<uuid>.py
./inspect.sh content 2
./inspect.sh generated
./inspect.sh help
```

That is all. The first time (or any time you are outside the Nix shell) it will transparently enter the environment, run the requested command, and exit.

---

## Commands

| Command | What it does |
|---------|--------------|
| `tree` | Raw dump of the entire `file_graph` table |
| `ls [path]` | List a virtual directory (default = root) |
| `cat <path>` | Print the full content of a virtual file |
| `content <id>` | Dump a raw `file_contents` row by numeric id |
| `prefix` | Shortcut for the assembled prefix |
| `generated` | First 30 lines of every script under `Runtime/generated/` |
| `help` | Show usage |

All paths are **virtual paths** inside the SQLite VirtualFS (e.g. `Database/prefix.py`), not real filesystem paths.

---

## How the automatic environment entry works

1. The script locates its own directory and the sibling `env-bootloader/` flake.
2. If the environment variable `COMMUNICATORS_INSPECT_ENV` is not set, it re-executes itself with:

   ```bash
   nix --extra-experimental-features "nix-command flakes" \
     develop <flake-dir> --command bash <this-script> "$@"
   ```

3. Once inside the pure shell the variable is set, so the re-execution stops and the real inspection logic runs.
4. Working directory is forced back to `Database/` so relative imports (`vfs_writer`) and the database path are correct.

You never have to think about any of that.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `could not find flake at …` | The expected directory layout is missing (`Database/` and `env-bootloader/` must be siblings). |
| `runtime_fs.db not found` | The bootloader has not been run yet, or you are in the wrong tree. |
| Still asks for experimental features | Extremely old Nix; the script already passes the required flags. |

---

## Philosophy

This script exists so that the only thing you ever have to decide is *what* you want to look at.  
Everything else (environment, paths, Python availability) is abstracted away.
