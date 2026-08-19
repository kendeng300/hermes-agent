#!/usr/bin/env bash
# Candidate-bound pre-commit integrity gate.  The mechanical coordinator has
# already run the test and gate phases; this hook proves that Git is committing
# the same isolated, mutation-free worktree under the coordinator environment.

set -euo pipefail
IFS=$'\n\t'
umask 077

fail() {
    printf 'TEST-034 pre-commit rejected: %s\n' "$1" >&2
    exit 1
}

require_coordinator_environment() {
    [[ ${HERMES_TEST034_MANIFEST_SHA256:-} =~ ^[0-9a-f]{64}$ ]] ||
        fail "missing or invalid sealed manifest digest"
    [[ ${HERMES_TEST034_RUN_NONCE:-} =~ ^[A-Za-z0-9_-]{32,128}$ ]] ||
        fail "missing or invalid sealed run nonce"
    [[ ${GIT_CONFIG_GLOBAL:-} == /dev/null ]] ||
        fail "global Git configuration is not isolated"
    [[ ${GIT_CONFIG_NOSYSTEM:-} == 1 ]] ||
        fail "system Git configuration is not isolated"
    [[ ${GIT_TERMINAL_PROMPT:-} == 0 ]] ||
        fail "interactive Git prompting is not disabled"

    local name value path_entry
    for name in HOME HERMES_HOME TMPDIR; do
        value=${!name:-}
        [[ $value == /* && -d $value && ! -L $value ]] ||
            fail "$name is not a coordinator-provided regular directory"
    done
    [[ -n ${PATH:-} ]] || fail "coordinator PATH is empty"
    local old_ifs=$IFS
    IFS=:
    for path_entry in $PATH; do
        [[ $path_entry == /* && -d $path_entry ]] ||
            fail "coordinator PATH contains an unbound entry"
    done
    IFS=$old_ifs
}

require_coordinator_environment
GIT_BIN=$(command -v git) || fail "Git is unavailable on coordinator PATH"
[[ $GIT_BIN == /* && -x $GIT_BIN ]] || fail "Git toolchain is not an absolute executable"
export GIT_OPTIONAL_LOCKS=0

REPO_ROOT=$($GIT_BIN rev-parse --show-toplevel 2>/dev/null) ||
    fail "hook is not running in a Git worktree"
REPO_ROOT=$(cd -- "$REPO_ROOT" && pwd -P) || fail "repository root is unavailable"
[[ $(pwd -P) == "$REPO_ROOT" ]] || fail "hook must run at the repository root"

[[ -z $($GIT_BIN ls-files -u) ]] || fail "index contains unresolved entries"
$GIT_BIN diff --cached --check -- || fail "staged content fails Git whitespace validation"
$GIT_BIN diff --check -- || fail "worktree content fails Git whitespace validation"

set +e
$GIT_BIN diff --cached --quiet --
STAGED_RC=$?
set -e
[[ $STAGED_RC == 1 ]] || fail "candidate index has no exact staged change"
$GIT_BIN diff --quiet -- || fail "unstaged tracked changes are present"
[[ -z $($GIT_BIN ls-files --others --exclude-standard) ]] ||
    fail "untracked files are present"

printf 'TEST-034 pre-commit integrity verified for manifest %s\n' \
    "$HERMES_TEST034_MANIFEST_SHA256"
