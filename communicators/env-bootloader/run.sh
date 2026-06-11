#!/usr/bin/env bash
# =============================================================================
# Meta-OS / Communicators - Development Environment Setup
# Interactive "meta-terminal" for the outer layer
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# CONFIGURATION - EDIT THESE
# -----------------------------------------------------------------------------
VENV_DIR=".venv"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PACKAGE_IMPORT_NAME="communicators"

# Discover the privileged root (communicators directory)
find_communicators_root() {
    local dir="$PROJECT_ROOT"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/communicators" ]]; then
            echo "$dir/communicators"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$PROJECT_ROOT"  # fallback
}

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------

create_venv_if_needed() {
    if [[ ! -d "$VENV_DIR" ]]; then
        echo "→ Creating virtual environment in $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
        echo "   Done."
    else
        echo "→ Virtual environment already exists."
    fi
}

activate_venv() {
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    echo "→ Virtual environment activated."
}

# Check whether the package is already installed in editable mode
is_editable_package_installed() {
    # This is the key check: "install if and only if not yet installed"
    if python -c "import $PACKAGE_IMPORT_NAME" &>/dev/null; then
        return 0   # already installed
    else
        return 1   # not installed
    fi
}

install_if_needed() {
    if is_editable_package_installed; then
        echo "→ Package '$PACKAGE_IMPORT_NAME' is already installed (editable)."
        return 0
    fi

    # Optional: also handle requirements.txt if it exists
    if [[ -f "$PROJECT_ROOT/requirements.txt" ]]; then
        echo "→ Installing dependencies from requirements.txt..."
        pip install -r "$PROJECT_ROOT/requirements.txt"
    fi

    echo "→ Installation complete."
}

find_communicators_root_resolve() {
    local dir="$PROJECT_ROOT"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/communicators" ]]; then
            echo "$dir/communicators"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$PROJECT_ROOT"
}

resolve_path() {
    local scope="$1"
    local target="$2"
    local comm_root
    comm_root="$(find_communicators_root_resolve)"

    case "$scope" in
        internal|""|comm|communicators)
            echo "$comm_root/$target"
            ;;
        host)
            echo "$target"
            ;;
        *)
            echo "Unknown scope: $scope" >&2
            return 1
            ;;
    esac
}

run() {
    local scope="$1"
    local path="$2"

    if [[ -z "$path" ]]; then
        path="$scope"
        scope="internal"
    fi

    local full_path
    full_path=$(resolve_path "$scope" "$path") || return 1

    echo "→ Running ($scope): $full_path"

    local harness
    harness=$(resolve_path "internal" "env-bootloader/bootloader.py")

    set +e
    python3 "$harness" "$full_path"
    set -e
}

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

main() {
    echo "=== Meta-OS Development Environment Setup ==="
    echo ""

    create_venv_if_needed
    activate_venv
    install_if_needed
    run "${2:-internal}" "${3:-state-methods/namespace.py}"
}

main "${1:-}"
