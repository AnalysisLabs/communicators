#!/usr/bin/env bash
# =============================================================================
# Meta-OS / Communicators – pure Nix ignition
# =============================================================================
# This is the *only* place the flake is used.
# It drops us into the pure development shell defined by
# env-bootloader/flake.nix and then hands control to the
# general OS bootloader (which in turn initialises the
# ephemeral SQLite VirtualFS and launches the rest of the system).
# =============================================================================
set -euo pipefail

# flake.nix and this script live side-by-side
FLAKE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTLOADER="${FLAKE_ROOT}/bootloader.py"

# Sanity checks before we enter the Nix shell
if [[ ! -f "$BOOTLOADER" ]]; then
  echo "error: bootloader not found at $BOOTLOADER" >&2
  exit 1
fi

# The Database/ directory must exist relative to the communicators root
# (find_communicators_root will locate it once we are inside Python).
COMM_ROOT="$(cd "$FLAKE_ROOT/.." && pwd)"
if [[ ! -d "$COMM_ROOT/Database" ]]; then
  echo "error: expected Database/ under $COMM_ROOT" >&2
  exit 1
fi

echo "=== Meta-OS / Communicators (pure Nix) ==="
echo "→ Flake root     : $FLAKE_ROOT"
echo "→ Bootloader     : $BOOTLOADER"
echo "→ Communicators  : $COMM_ROOT"
echo ""

# Force the pure environment, then hand off.
# --extra-experimental-features keeps the invocation self-contained.
exec nix --extra-experimental-features "nix-command flakes" \
  develop "$FLAKE_ROOT" \
  --command python3 "$BOOTLOADER"
