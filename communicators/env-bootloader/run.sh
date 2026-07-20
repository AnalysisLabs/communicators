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

    # Locate pyproject.toml: it lives in the same directory as the communicators root
    local comm_root
    comm_root="$(find_communicators_root_resolve)"
    local project_dir
    project_dir="$(dirname "$comm_root")"
    local pyproject="${project_dir}/pyproject.toml"

    if [[ -f "$pyproject" ]]; then
        echo "→ Syncing package and dependencies from pyproject.toml (editable)..."
        # relative path is mandatory — cd into the project dir and use "."
        (
            cd "$project_dir"
            pip install -e .
        )
    else
        echo "→ Warning: pyproject.toml not found next to communicators root." >&2
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
    local harness
    harness=$(resolve_path "internal" "env-bootloader/bootloader.py")
    set +e
    python3 "$harness"
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
    run
}

main "${1:-}"
