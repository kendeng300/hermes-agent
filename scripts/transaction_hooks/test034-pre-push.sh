#!/usr/bin/env bash
# Candidate-bound pre-push integrity gate.  Git supplies one four-field update
# on stdin; validate its objects, refs, configured destination, and actual
# fast-forward ancestry.  Force intent is never inferred from a ref prefix.

set -euo pipefail
IFS=$'\n\t'
umask 077

fail() {
    printf 'TEST-034 pre-push rejected: %s\n' "$1" >&2
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

[[ $# == 2 && -n $1 && -n $2 ]] || fail "expected exact remote name and URL arguments"
REMOTE_NAME=$1
REMOTE_URL=$2
CONFIGURED_URL=$($GIT_BIN remote get-url --push "$REMOTE_NAME" 2>/dev/null) ||
    fail "configured push remote is unavailable"
[[ $CONFIGURED_URL == "$REMOTE_URL" ]] || fail "push URL differs from configured remote"

mapfile -t UPDATE_LINES
[[ ${#UPDATE_LINES[@]} == 1 ]] || fail "expected exactly one ref update"
IFS=' ' read -r LOCAL_REF LOCAL_OID REMOTE_REF REMOTE_OID EXTRA <<<"${UPDATE_LINES[0]}"
[[ -n ${LOCAL_REF:-} && -n ${LOCAL_OID:-} && -n ${REMOTE_REF:-} &&
   -n ${REMOTE_OID:-} && -z ${EXTRA:-} ]] || fail "malformed ref update"
[[ $REMOTE_REF == refs/heads/* ]] || fail "destination is not a branch ref"
[[ $LOCAL_OID =~ ^[0-9a-f]{40}$|^[0-9a-f]{64}$ ]] || fail "invalid local object ID"
[[ $REMOTE_OID =~ ^[0-9a-f]{40}$|^[0-9a-f]{64}$ ]] || fail "invalid remote object ID"
[[ ${#LOCAL_OID} == ${#REMOTE_OID} ]] || fail "object ID formats differ"

ZERO_OID=$(printf '%*s' "${#LOCAL_OID}" '' | tr ' ' 0)
[[ $LOCAL_OID != "$ZERO_OID" ]] || fail "branch deletion is forbidden"
$GIT_BIN cat-file -e "$LOCAL_OID^{commit}" 2>/dev/null || fail "local object is not a commit"
RESOLVED_LOCAL=$($GIT_BIN rev-parse --verify "$LOCAL_REF^{commit}" 2>/dev/null) ||
    fail "local ref does not resolve to a commit"
[[ $RESOLVED_LOCAL == "$LOCAL_OID" ]] || fail "local ref and object ID disagree"

if [[ $REMOTE_OID != "$ZERO_OID" ]]; then
    $GIT_BIN cat-file -e "$REMOTE_OID^{commit}" 2>/dev/null ||
        fail "remote object is not locally verifiable"
    $GIT_BIN merge-base --is-ancestor "$REMOTE_OID" "$LOCAL_OID" ||
        fail "ref update is not a fast-forward"
fi

printf 'TEST-034 pre-push integrity verified for %s -> %s\n' \
    "$LOCAL_OID" "$REMOTE_REF"
