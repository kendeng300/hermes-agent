#!/usr/bin/env bash
# Canonical test runner for hermes-agent. Run this instead of calling
# `pytest` directly to guarantee your local run matches CI behavior.
#
# What this script enforces:
#   * Per-file isolation via scripts/run_tests_parallel.py — each test
#     file runs in its own freshly-spawned `python -m pytest <file>`
#     subprocess. No xdist, no shared workers, no module-level leakage
#     between files.
#   * TZ=UTC, LANG=C.UTF-8, PYTHONHASHSEED=0 (deterministic)
#   * Env vars blanked (conftest.py also does this, but this
#     is belt-and-suspenders for anyone running pytest outside our
#     conftest path — e.g. on a single file)
#   * Proper venv activation (probes .venv, venv, then ~/.hermes/...)
#
# Usage:
#   scripts/run_tests.sh                            # full suite
#   scripts/run_tests.sh -j 4                       # cap parallelism
#   scripts/run_tests.sh tests/agent/               # discover only here
#   scripts/run_tests.sh tests/agent/ tests/acp/    # multiple roots
#   scripts/run_tests.sh tests/foo.py               # single file
#   scripts/run_tests.sh tests/foo.py -q            # path + bare pytest flag
#   scripts/run_tests.sh tests/foo.py -v --tb=long  # bare flags "just work"
#   scripts/run_tests.sh -k 'pattern'               # value flags pass through too
#   scripts/run_tests.sh tests/foo.py -- --tb=long  # explicit '--' still works
#
# Bare pytest flags (anything starting with '-' that isn't one of this
# runner's own options: -j/--jobs, --paths, --slice, --file-timeout, etc.)
# are forwarded to each per-file pytest invocation automatically — no '--'
# separator required. The explicit '--' form still works and stacks with
# bare flags. Positional path arguments override the default discovery
# root (tests/).

set -euo pipefail

# ── Locate repo root ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Activate venv ───────────────────────────────────────────────────────────
VENV=""
PYTHON=""
for candidate in "$REPO_ROOT/.venv" "$REPO_ROOT/venv" "$HOME/.hermes/hermes-agent/venv"; do
  if [ ! -f "$candidate/bin/activate" ] || [ ! -x "$candidate/bin/python" ]; then
    continue
  fi
  # A stale/partially-created virtualenv can have an activation script and a
  # Python binary while lacking pytest.  Selecting it makes every per-file
  # worker fail before collection and prevents the canonical runner from
  # reaching a healthy fallback environment.  Probe the one dependency this
  # wrapper must have before committing to the candidate.
  if "$candidate/bin/python" -c "import pytest" >/dev/null 2>&1; then
    VENV="$candidate"
    PYTHON="$candidate/bin/python"
    break
  fi
  echo "warning: skipping unusable test virtualenv $candidate (pytest unavailable)" >&2
done

if [ -z "$VENV" ]; then
  echo "error: no usable pytest virtualenv found in $REPO_ROOT/.venv, $REPO_ROOT/venv, or $HOME/.hermes/hermes-agent/venv" >&2
  exit 1
fi

# ── Establish a run-owned temporary authority ──────────────────────────────
# Never let pytest or a transitive dependency fall back to the host's system
# temporary directory.  An already-bound authority (CI/remote execution) is
# preserved exactly.  Local runs receive a fresh profile beneath the user's
# private state directory rather than the live Hermes profile.
if [ -n "${HERMES_TEMP_ROOT:-}" ]; then
  TEST_HERMES_HOME="${HERMES_HOME:?bound HERMES_TEMP_ROOT requires HERMES_HOME}"
  TEST_RUN_NONCE="${HERMES_TEMP_RUN_NONCE:?bound HERMES_TEMP_ROOT requires HERMES_TEMP_RUN_NONCE}"
  TEST_TEMP_SCOPE="${HERMES_TEMP_SCOPE:?bound HERMES_TEMP_ROOT requires HERMES_TEMP_SCOPE}"
  TEST_MANIFEST_SHA256="${HERMES_TEMP_MANIFEST_SHA256:-}"
  case "$TEST_TEMP_SCOPE" in
    test|ci|remote) ;;
    *) echo "error: tests require a test, ci, or remote temporary authority" >&2; exit 1 ;;
  esac
else
  TEST_RUN_NONCE="${HERMES_TEMP_RUN_NONCE:-$($PYTHON -c 'import secrets; print(secrets.token_hex(16))')}"
  TEST_STATE_BASE="${XDG_STATE_HOME:-$HOME/.local/state}/hermes/test-runs"
  TEST_HERMES_HOME="$TEST_STATE_BASE/$TEST_RUN_NONCE"
  TEST_TEMP_SCOPE=test
  TEST_MANIFEST_SHA256=""
fi

# ── Live-gateway plugin (computed before we drop env) ───────────────────────
EXTRA_PYTHONPATH=""
EXTRA_PYTEST_PLUGINS=""
if [ -f "$HOME/.hermes/pytest_live_guard.py" ]; then
  EXTRA_PYTHONPATH="$HOME/.hermes"
  EXTRA_PYTEST_PLUGINS="pytest_live_guard"
fi


# ── Run in hermetic env ──────────────────────────────────────────────────────
# env -i: start with empty environment, opt-in only what we need.
# No credential var can leak — you'd have to explicitly add it here.
echo "▶ running per-file parallel test suite via run_tests_parallel.py"
echo "  (TZ=UTC LANG=C.UTF-8 PYTHONHASHSEED=0; clean env)"

cd "$REPO_ROOT"

exec env -i \
  PATH="$PATH" \
  HOME="$HOME" \
  TZ=UTC \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PYTHONHASHSEED=0 \
  PYTHONDONTWRITEBYTECODE=1 \
  HERMES_TEST_ACTIVE=1 \
  HERMES_OFFLINE=1 \
  OFFLINE=1 \
  NO_NETWORK=1 \
  BOOT_HERMES_HOME="$TEST_HERMES_HOME" \
  BOOT_TEMP_SCOPE="$TEST_TEMP_SCOPE" \
  BOOT_RUN_NONCE="$TEST_RUN_NONCE" \
  BOOT_MANIFEST_SHA256="$TEST_MANIFEST_SHA256" \
  BOOT_TEMP_ROOT="${HERMES_TEMP_ROOT:-}" \
  BOOT_TEMP_ROOT_IDENTITY="${HERMES_TEMP_ROOT_IDENTITY:-}" \
  BOOT_AUTHORITY_VERSION="${HERMES_TEMP_AUTHORITY_VERSION:-}" \
  BOOT_TMPDIR="${TMPDIR:-}" \
  BOOT_TEMP="${TEMP:-}" \
  BOOT_TMP="${TMP:-}" \
  ${TEST034_CONFIG_ROOT:+TEST034_CONFIG_ROOT="$TEST034_CONFIG_ROOT"} \
  ${HERMES_RUN_SLOW_PET_TESTS:+HERMES_RUN_SLOW_PET_TESTS="$HERMES_RUN_SLOW_PET_TESTS"} \
  ${EXTRA_PYTHONPATH:+PYTHONPATH="$EXTRA_PYTHONPATH"} \
  ${EXTRA_PYTEST_PLUGINS:+PYTEST_PLUGINS="$EXTRA_PYTEST_PLUGINS"} \
  "$PYTHON" -c '
import os
import sys
from hermes_temp import TempAuthorityError, resolve_temp_authority

runner, *pytest_args = sys.argv[1:]
scope = os.environ["BOOT_TEMP_SCOPE"]
nonce = os.environ["BOOT_RUN_NONCE"]
manifest = os.environ["BOOT_MANIFEST_SHA256"] or None
source = {"HERMES_HOME": os.environ["BOOT_HERMES_HOME"]}
root = os.environ["BOOT_TEMP_ROOT"]
if root:
    source.update({
        "HERMES_TEMP_ROOT": root,
        "HERMES_TEMP_ROOT_IDENTITY": os.environ["BOOT_TEMP_ROOT_IDENTITY"],
        "HERMES_TEMP_SCOPE": scope,
        "HERMES_TEMP_RUN_NONCE": nonce,
        "HERMES_TEMP_AUTHORITY_VERSION": os.environ["BOOT_AUTHORITY_VERSION"],
        "TMPDIR": os.environ["BOOT_TMPDIR"],
        "TEMP": os.environ["BOOT_TEMP"],
        "TMP": os.environ["BOOT_TMP"],
    })
    if manifest:
        source["HERMES_TEMP_MANIFEST_SHA256"] = manifest
try:
    authority = resolve_temp_authority(
        scope=scope,
        run_nonce=nonce,
        manifest_sha256=manifest,
        env=source,
    )
except TempAuthorityError as exc:
    print(f"error: could not establish the Hermes test temporary authority: {exc}", file=sys.stderr)
    raise SystemExit(1)
try:
    child_env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("BOOT_")
    }
    child_env.update(authority.child_environment())
finally:
    authority.close()
os.execve(sys.executable, [sys.executable, runner, *pytest_args], child_env)
' "$SCRIPT_DIR/run_tests_parallel.py" "$@"
