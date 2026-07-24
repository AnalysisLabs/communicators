#!/usr/bin/env bash
# inspect.sh – self-contained VirtualFS inspector
# Place in Database/ and run from there. It automatically enters the
# pure Nix environment (env-bootloader) when needed.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate ourselves and the flake
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAKE_DIR="$(cd "$SCRIPT_DIR/../env-bootloader" && pwd)"
DB="$SCRIPT_DIR/runtime_fs.db"

# ---------------------------------------------------------------------------
# Auto-enter the pure Nix environment if we are not already inside it
# ---------------------------------------------------------------------------
if [[ -z "${COMMUNICATORS_INSPECT_ENV:-}" ]]; then
  if [[ ! -f "$FLAKE_DIR/flake.nix" ]]; then
    echo "error: could not find flake at $FLAKE_DIR" >&2
    exit 1
  fi
  export COMMUNICATORS_INSPECT_ENV=1
  # Re-exec ourselves inside the development shell.
  # Working directory is preserved by nix develop.
  exec nix --extra-experimental-features "nix-command flakes" \
    develop "$FLAKE_DIR" \
    --command bash "$0" "$@"
fi

# From here on we are guaranteed to be inside the pure environment.
cd "$SCRIPT_DIR"

if [[ ! -f "$DB" ]]; then
  echo "error: $DB not found (has the bootloader been run?)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
py() {
  python3 -c "$1"
}

# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
cmd_tree() {
  echo "=== file_graph (whole tree) ==="
  py '
import sqlite3
conn = sqlite3.connect("'"$DB"'")
print(f"{"id":>4}  {"parent":>6}  {"type":6}  {"content":>7}  {"tier":12}  name")
print("-" * 70)
for row in conn.execute("""
    SELECT id, parent_id, type, content_id, access_tier, name
    FROM file_graph ORDER BY id
"""):
    pid = row[1] if row[1] is not None else "-"
    cid = row[3] if row[3] is not None else "-"
    print(f"{row[0]:4}  {str(pid):>6}  {row[2]:6}  {str(cid):>7}  {row[4]:12}  {row[5]!r}")
'
}

cmd_ls() {
  local path="${1:-}"
  echo "=== list_dir(\"$path\") ==="
  py '
from vfs_writer import list_dir
for name, typ in list_dir("'"$path"'"):
    print(f"  {name:40} {typ}")
'
}

cmd_cat() {
  local path="$1"
  echo "=== read_file(\"$path\") ==="
  py '
from vfs_writer import read_file
print(read_file("'"$path"'"))
'
}

cmd_content() {
  local id="$1"
  echo "=== file_contents id=$id ==="
  py '
import sqlite3
conn = sqlite3.connect("'"$DB"'")
row = conn.execute("SELECT hash, size, data FROM file_contents WHERE id = ?", ('"$id"',)).fetchone()
if not row:
    print("No such content_id")
else:
    print(f"hash : {row[0]}")
    print(f"size : {row[1]}")
    print("-" * 60)
    print(row[2])
'
}

cmd_prefix() {
  cmd_cat "Database/prefix.py"
}

cmd_generated() {
  echo "=== Runtime/generated/ ==="
  py '
from vfs_writer import list_dir, read_file
for name, typ in list_dir("Runtime/generated"):
    print(f"\n--- {name} ---")
    src = read_file(f"Runtime/generated/{name}")
    lines = src.splitlines()
    for i, line in enumerate(lines[:30], 1):
        print(f"{i:3}| {line}")
    if len(lines) > 30:
        print(f"... ({len(lines)-30} more lines)")
'
}

cmd_help() {
  cat <<EOF
Usage: ./inspect.sh <command> [args]

The script automatically enters the pure Nix environment
(env-bootloader) when necessary. Just run it from Database/.

Commands:
  tree                 Show the entire file_graph table (raw)
  ls [virtual-path]    List a directory (default: root)
  cat <virtual-path>   Print the full content of a virtual file
  content <id>         Dump a raw file_contents row by id
  prefix               Shortcut: show Database/prefix.py
  generated            Show the first 30 lines of every generated script
  help                 This message

Examples:
  ./inspect.sh tree
  ./inspect.sh ls Runtime/generated
  ./inspect.sh cat Database/prefix.py
  ./inspect.sh content 2
  ./inspect.sh generated
EOF
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-help}" in
  tree)       cmd_tree ;;
  ls)         cmd_ls "${2:-}" ;;
  cat)        [[ $# -ge 2 ]] || { echo "usage: $0 cat <virtual-path>"; exit 1; }
              cmd_cat "$2" ;;
  content)    [[ $# -ge 2 ]] || { echo "usage: $0 content <id>"; exit 1; }
              cmd_content "$2" ;;
  prefix)     cmd_prefix ;;
  generated)  cmd_generated ;;
  help|-h|--help) cmd_help ;;
  *)          echo "Unknown command: $1"; cmd_help; exit 1 ;;
esac
