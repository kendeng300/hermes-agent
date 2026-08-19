#!/usr/bin/env bash
# Shell consumer for TempAuthority v1. Source this file, then call
# hermes_temp_file/dir with an output variable and a lowercase purpose.

hermes_temp_authority_init() {
    : "${HOME:?HOME is required for Hermes temporary authority}"
    HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
    case "$HERMES_HOME" in
        /*) ;;
        *) echo "Hermes temporary authority requires an absolute HERMES_HOME" >&2; return 125 ;;
    esac
    case "$HERMES_HOME/" in
        /tmp/*|/var/tmp/*|/dev/shm/*|/private/tmp/*|/private/var/tmp/*)
            echo "Hermes temporary authority rejects system temporary roots" >&2
            return 125
            ;;
    esac
    case "$HERMES_HOME" in
        *'/../'*|*'/./'*|*'//'*) echo "unsafe HERMES_HOME syntax" >&2; return 125 ;;
    esac
    local cursor="$HERMES_HOME" permissions
    while [ "$cursor" != / ]; do
        if [ -e "$cursor" ] || [ -L "$cursor" ]; then
            [ ! -L "$cursor" ] || { echo "symlinked HERMES_HOME ancestor" >&2; return 125; }
        fi
        cursor="${cursor%/*}"
        [ -n "$cursor" ] || cursor=/
    done
    if [ -z "${HERMES_TEMP_ROOT:-}" ] &&
       [ -n "${HERMES_TEMP_ROOT_IDENTITY:-}${HERMES_TEMP_SCOPE:-}${HERMES_TEMP_RUN_NONCE:-}${HERMES_TEMP_MANIFEST_SHA256:-}${HERMES_TEMP_AUTHORITY_VERSION:-}" ]; then
        return 125
    fi
    if [ -n "${HERMES_TEMP_ROOT:-}" ] && [ "$HERMES_TEMP_ROOT" != "$HERMES_HOME/tmp" ]; then
        return 125
    fi
    if [ -n "${HERMES_TEMP_ROOT:-}" ]; then
        [[ "${HERMES_TEMP_ROOT_IDENTITY:-}" =~ ^v1:[0-9]+:[0-9]+$ ]] || return 125
        [ "${HERMES_TEMP_AUTHORITY_VERSION:-}" = 1 ] || return 125
        case "${HERMES_TEMP_SCOPE:-}" in production|test|ci|remote) ;; *) return 125 ;; esac
        [[ "${HERMES_TEMP_RUN_NONCE:-}" =~ ^[0-9a-f]{32}$ ]] || return 125
        [ "${TMPDIR:-}" = "$HERMES_TEMP_ROOT" ] && [ "${TEMP:-}" = "$HERMES_TEMP_ROOT" ] && [ "${TMP:-}" = "$HERMES_TEMP_ROOT" ] || return 125
        if [ "$HERMES_TEMP_SCOPE" = ci ] || [ "$HERMES_TEMP_SCOPE" = remote ]; then
            [[ "${HERMES_TEMP_MANIFEST_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || return 125
        else
            [ -z "${HERMES_TEMP_MANIFEST_SHA256:-}" ] || return 125
        fi
    fi
    if [ -e "$HERMES_HOME" ]; then
        [ -d "$HERMES_HOME" ] && [ -O "$HERMES_HOME" ] || return 125
        permissions="$(stat -Lc '%a' "$HERMES_HOME")" || return 125
        (( (8#$permissions & 8#022) == 0 )) || return 125
    else
        install -d -m 700 "$HERMES_HOME" || return 125
    fi
    if [ -e "$HERMES_HOME/tmp" ]; then
        [ -d "$HERMES_HOME/tmp" ] && [ -O "$HERMES_HOME/tmp" ] || return 125
        [ "$(stat -Lc '%a' "$HERMES_HOME/tmp")" = 700 ] || return 125
    else
        install -d -m 700 "$HERMES_HOME/tmp" || return 125
    fi
    [ ! -L "$HERMES_HOME" ] && [ ! -L "$HERMES_HOME/tmp" ] || return 125
    local root="$HERMES_HOME/tmp" identity
    identity="$(stat -Lc '%d:%i' "$root")" || return 125
    case "${HERMES_TEMP_ROOT:-}" in
        "")
            HERMES_TEMP_SCOPE=production
            HERMES_TEMP_RUN_NONCE="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')" || return 125
            HERMES_TEMP_ROOT="$root"
            HERMES_TEMP_ROOT_IDENTITY="v1:$identity"
            HERMES_TEMP_AUTHORITY_VERSION=1
            unset HERMES_TEMP_MANIFEST_SHA256
            ;;
        "$root")
            [ "${HERMES_TEMP_ROOT_IDENTITY:-}" = "v1:$identity" ] || return 125
            [ "${HERMES_TEMP_AUTHORITY_VERSION:-}" = 1 ] || return 125
            case "${HERMES_TEMP_SCOPE:-}" in production|test|ci|remote) ;; *) return 125 ;; esac
            [[ "${HERMES_TEMP_RUN_NONCE:-}" =~ ^[0-9a-f]{32}$ ]] || return 125
            [ "${TMPDIR:-}" = "$root" ] && [ "${TEMP:-}" = "$root" ] && [ "${TMP:-}" = "$root" ] || return 125
            if [ "$HERMES_TEMP_SCOPE" = ci ] || [ "$HERMES_TEMP_SCOPE" = remote ]; then
                [[ "${HERMES_TEMP_MANIFEST_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || return 125
            else
                [ -z "${HERMES_TEMP_MANIFEST_SHA256:-}" ] || return 125
            fi
            ;;
        *) return 125 ;;
    esac
    export HERMES_HOME HERMES_TEMP_ROOT HERMES_TEMP_ROOT_IDENTITY
    export HERMES_TEMP_SCOPE HERMES_TEMP_RUN_NONCE HERMES_TEMP_AUTHORITY_VERSION
    export TMPDIR="$root" TEMP="$root" TMP="$root"
}

_hermes_temp_token() {
    od -An -N12 -tx1 /dev/urandom | tr -d ' \n'
}

hermes_temp_file() {
    local output_name="$1" purpose="$2" suffix="${3:-}" token path
    [[ "$output_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 125
    [[ "$purpose" =~ ^[a-z][a-z0-9-]{0,31}$ ]] || return 125
    [[ "$suffix" != *'/'* && "$suffix" != *'..'* && ${#suffix} -le 32 ]] || return 125
    hermes_temp_authority_init || return
    token="$(_hermes_temp_token)" || return 125
    path="$HERMES_TEMP_ROOT/$purpose-$token$suffix"
    ( set -o noclobber; umask 077; : > "$path" ) 2>/dev/null || return 125
    chmod 600 "$path" || { rm -f -- "$path"; return 125; }
    printf -v "$output_name" '%s' "$path"
}

hermes_temp_dir() {
    local output_name="$1" purpose="$2" token path
    [[ "$output_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 125
    [[ "$purpose" =~ ^[a-z][a-z0-9-]{0,31}$ ]] || return 125
    hermes_temp_authority_init || return
    token="$(_hermes_temp_token)" || return 125
    path="$HERMES_TEMP_ROOT/$purpose-$token"
    mkdir -m 700 -- "$path" || return 125
    printf -v "$output_name" '%s' "$path"
}
