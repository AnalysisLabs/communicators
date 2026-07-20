#!/usr/bin/env bash
# =============================================================================
# Meta-OS / Communicators – pure Nix ignition
# =============================================================================
set -euo pipefail

# flake.nix and run.sh live in the same directory (env-bootloader/)
FLAKE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTLOADER="$FLAKE_ROOT/bootloader.py"

echo "=== Meta-OS Development Environment (pure Nix) ==="
echo "→ Flake root : $FLAKE_ROOT"
echo "→ Bootloader : $BOOTLOADER"
echo ""

# Force the pure environment, then hand off to the bootloader.
# All Python imports (including your runtime-injected ones) will
# now resolve against the environment defined in the flake.

# --extra-experimental-features keeps this self-contained (no system config needed).
exec nix --extra-experimental-features "nix-command flakes" \
  develop "$FLAKE_ROOT" \
  --command python3 "$BOOTLOADER"
