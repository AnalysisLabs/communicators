#!/usr/bin/env bash
# =============================================================================
# Meta-OS / Communicators – pure Nix ignition
# =============================================================================
# Only job: enter the pure Nix development shell, then hand control to
# Genesis/execution/bootloader.py.  Nothing else.
# =============================================================================
set -euo pipefail

# This script lives at the communicators root
COMM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FLAKE_ROOT="${COMM_ROOT}/Genesis/execution"
BOOTLOADER="${FLAKE_ROOT}/bootloader.py"

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if [[ ! -f "${FLAKE_ROOT}/flake.nix" ]]; then
  echo "error: flake.nix not found at ${FLAKE_ROOT}/flake.nix" >&2
  exit 1
fi

if [[ ! -f "$BOOTLOADER" ]]; then
  echo "error: bootloader not found at $BOOTLOADER" >&2
  exit 1
fi

echo "=== Meta-OS / Communicators (pure Nix) ==="
echo "→ Communicators  : $COMM_ROOT"
echo "→ Flake root     : $FLAKE_ROOT"
echo "→ Bootloader     : $BOOTLOADER"
echo ""

# ---------------------------------------------------------------------------
# Enter the pure environment and hand off
# ---------------------------------------------------------------------------
exec nix --extra-experimental-features "nix-command flakes" \
  develop "$FLAKE_ROOT" \
  --command python3 "$BOOTLOADER"
