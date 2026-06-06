#!/usr/bin/env bash
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
import sys, os
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
    set -e
}

run "$@"
