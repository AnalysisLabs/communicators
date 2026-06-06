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

# TODO: Change this to your actual importable package name
# (the name you use in `import <name>` or `from <name> import`)
PACKAGE_IMPORT_NAME="communicators"

# TODO: Decide if you want a simple one-shot setup or a menu
# Set to "menu" or "oneshot"
MODE="oneshot"

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

function run() {
    local scope="$1"
    local path="$2"

    if [[ -z "$path" ]]; then
        # Old usage: run <path> (treat as internal)
        path="$scope"
        scope="internal"
    fi

    local full_path
    full_path=$(resolve_path "$scope" "$path") || return 1

    echo "→ Running ($scope): $full_path"
    set +e
    python3 -c '
import sys, os, uuid
from pygments.lexers import guess_lexer
from pathlib import Path
def _find_communicators_root(p):
    d=os.path.abspath(p)
    while d != "/":
        if os.path.basename(d)=='communicators': return d
        d=os.path.dirname(d)
    return None
if 'COMMUNICATORS_ROOT' not in os.environ:
    os.environ['COMMUNICATORS_ROOT']=_find_communicators_root(os.getcwd())
sys.path.insert(0, os.environ["COMMUNICATORS_ROOT"])
from prelude import*
exec(open(sys.argv[1]).read())
    ' "$full_path" || true
    src=$(python3 -c "import sys; print(open(sys.argv[1]).read())" "$full_path")
    ext=$(python3 -c "from pygments.lexers import guess_lexer; print(guess_lexer(open(sys.argv[1]).read()).aliases[0])")
    python3 -c '
    from pathlib import Path
    import uuid
    Path("/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/temp")/f"{uuid.uuid4()}.{ext}".write_text("$src")
    '
    set -e
}

function expose() {
  [ "$1" = "venv" ] && {
    echo "Here are the packages you have installed in this venv:"
    pip freeze
  }
}

function deactivate() { builtin deactivate 2>/dev/null || command deactivate; }

print_ready_message() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Meta-OS Development Environment is READY"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  You are now inside the activated virtual environment."
    echo "  Available commands:"
    echo "    run <python_file>     # e.g. run communicators/state-methods/namespace.py"
    echo "    expose [venv]         # show installed packages"
    echo "    quit"
    echo ""
    while true; do
        echo "Commands: quit | expose | run"
        read -p "Command: " cmd
        if [ "$cmd" == "quit" ]; then
            break
        else
            set -- $cmd
            case "$1" in
                expose) expose "$2" ;;
                run) run "$2" ;;
                *) "$cmd" ;;
            esac
            set +e
        fi
        echo "Usage: quit"
    done
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

    print_ready_message
    if [[ "$MODE" == "menu" ]]; then
        # TODO: Expand this section if you want a real interactive menu
        echo "TODO: Add menu options here (run tests, start components, etc.)"
        echo "For now, dropping you into the shell..."
    fi
}

main "$@"
