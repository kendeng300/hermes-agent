# Hermes Agent — Local Patch Change Log

> **Purpose:** Track all local modifications to the NousResearch/hermes-agent codebase
> for clean version upgrades and patch reapplication.
>
> **Branch:** `fix/deepseek-provider-400-checkpoint`
> **Base:** `origin/main` (v2026.4.30 tag)
> **Last updated:** 2026-05-04

---

## Patch Summary

| # | Commit | Date | Description | Files | Lines |
|---|--------|------|-------------|-------|-------|
| 1 | `b8bc65aa7` | 2026-04-29 | fix(provider): prevent DeepSeek and Codex 400s | 6 | +288/-12 |
| 2 | `5cfe5d5c4` | 2026-04-29 | fix(provider): echo DeepSeek reasoning on plain assistant replays | 2 | +20/-15 |
| 3 | `bf384e1b9` | 2026-04-29 | fix: prevent gateway --replace cascade and stale PID deadlocks | 2 | +25/-7 |
| 4 | `28807fa9a` | 2026-04-30 | checkpoint: Slack thread_ts regex parsing (rollback) | 1 | +6 |
| 5 | `4d7e3cce8` | 2026-04-30 | feat(slack): add thread_ts support to send_message_tool | 1 | +12/-3 |
| **6** | *(uncommitted)* | 2026-05-04 | **fix(slack): composite-key _active_status_threads to prevent cross-thread status collision** | 2 | +14/-4 |

---

## Detailed Changes

### 1. fix(provider): prevent DeepSeek and Codex 400s (`b8bc65aa7`)

**Problem:** Auxiliary memory flushes and API replays with DeepSeek V4 / Codex endpoints returned HTTP 400 errors because:
- Codex (`chatgpt.com/backend-api/codex`) rejects `temperature` parameter
- Codex Responses endpoint rejects `role=tool` messages in `input`
- DeepSeek thinking mode requires `reasoning_content` on every assistant turn
- Stale `reasoning_content` leaked into non-DeepSeek auxiliary requests

**Changes:**
- `agent/auxiliary_client.py`: Added Codex detection in `_fixed_temperature_for_model()` to omit temperature; normalized `role=tool` → `role=user` with tool-name prefix for Codex adapter
- `run_agent.py`: 
  - Moved `reasoning_content=""` injection to after tool_calls attachment (fixes creation/replay ordering race)
  - Extended to cover Kimi models in addition to DeepSeek
  - Added `_should_keep_reasoning_content_for_api()` — strips stale reasoning_content during model switches
  - Prevented memory-flush auxiliary calls when `flush_min_turns=0` (hard off switch)

**Files:** `agent/auxiliary_client.py`, `run_agent.py`, `tests/agent/test_auxiliary_client.py`, `tests/run_agent/test_deepseek_reasoning_content_echo.py`, `tests/run_agent/test_run_agent.py`, `tests/run_agent/test_tool_arg_coercion.py`

---

### 2. fix(provider): echo DeepSeek reasoning on plain assistant replays (`5cfe5d5c4`)

**Problem:** DeepSeek V4 thinking-mode API rejected requests where prior assistant turns (even plain text, non-tool-call turns) lacked `reasoning_content`. Original code only padded tool-call turns.

**Changes:**
- `run_agent.py`: Apply `reasoning_content=""` fallback to ALL assistant turns during replay when provider requires it, not just tool-call turns
- `tests/run_agent/test_deepseek_reasoning_content_echo.py`: Updated test coverage

**Files:** `run_agent.py`, `tests/run_agent/test_deepseek_reasoning_content_echo.py`

---

### 3. fix: prevent gateway --replace cascade and stale PID deadlocks (`bf384e1b9`)

**Problem:** 
1. Systemd `Restart=on-failure` wouldn't restart after certain exit conditions
2. Stale PID files from killed gateway processes prevented restart without `--replace`
3. systemd unit used `--replace` flag, causing cascading SIGTERM→SIGKILL on restart
4. SIGTERM timeout was only 10s, insufficient for graceful agent shutdown

**Changes:**
- `gateway/run.py`: 
  - Added stale PID detection (check if PID is alive with `os.kill(pid, 0)`, clean up dead PIDs)
  - Extended SIGTERM grace period from 10s → 60s
  - Added SIGKILL fallback message after 60s
- `hermes_cli/gateway.py`: 
  - Removed `--replace` from systemd `ExecStart` (prevents cascade)
  - Changed `Restart=on-failure` → `Restart=always` (covers all exit conditions)

**Files:** `gateway/run.py`, `hermes_cli/gateway.py`

---

### 4. checkpoint: Slack thread_ts regex parsing (`28807fa9a`)

**Problem:** Rollback checkpoint before the full thread delivery feature — added thread_ts extraction plumbing but no behavioral change.

**Changes:**
- `tools/send_message_tool.py`: Added `thread_id` parameter pass-through to `_parse_target()`; regex extraction for Slack thread_ts format

**Files:** `tools/send_message_tool.py`

---

### 5. feat(slack): add thread_ts support to send_message_tool (`4d7e3cce8`)

**Problem:** The `send_message` tool couldn't reply in Slack threads — messages always landed at channel top level regardless of thread context.

**Changes:**
- `tools/send_message_tool.py`: 
  - Added `thread_id` parameter to `_send_to_platform()` → threaded delivery
  - `_send_slack()`: Added `thread_id` parameter, sets `thread_ts` in Slack API payload
  - Updated docstring

**Files:** `tools/send_message_tool.py`

---

### 6. fix(slack): composite-key `_active_status_threads` to prevent cross-thread status collision *(uncommitted)*

**Problem (SEV-1):** When two concurrent Slack threads were active in the same channel, the "is thinking..." status indicator (`assistant_threads_setStatus`) would appear in the wrong thread. This created the perception of cross-thread message mixing.

**Root Cause (5-Why):**
1. Why did status appear in wrong thread? → `stop_typing()` cleared the wrong thread's status entry
2. Why did it clear the wrong thread? → `_active_status_threads` dict was keyed by `chat_id` alone (scalar key), so Thread B overwrote Thread A's entry
3. Why scalar key? → Original design assumed 1:1 channel:status mapping

**Fix:**
- `gateway/platforms/slack.py`:
  - `_active_status_threads` key changed from `chat_id` → `(chat_id, thread_ts)` composite key
  - `stop_typing()`: Added optional `metadata` parameter; when available, pops composite key; otherwise iterates keys for fallback
- `gateway/platforms/base.py`:
  - `_keep_typing()` cleanup: pass `metadata` to `stop_typing()` for precise thread targeting

**Architecture Note:** Core message routing (`session_key`, `metadata.thread_id`, `adapter.send()`) was already correct — only the status indicator had the key collision. Text responses were never affected.

**Verification:** All 131 slack tests pass. Manual composite-key test confirms zero collisions under concurrent threads.

**Files:** `gateway/platforms/slack.py`, `gateway/platforms/base.py`

---

## Upgrade / Rebase Guide

When rebasing onto a new upstream version:

1. **Cherry-pick order matters:**
   ```
   git cherry-pick b8bc65aa7  # DeepSeek/Codex 400s (depends on upstream run_agent.py)
   git cherry-pick 5cfe5d5c4  # DeepSeek reasoning echo (builds on #1)
   git cherry-pick bf384e1b9  # Gateway PID/restart (independent)
   git cherry-pick 4d7e3cce8  # Slack thread_ts (independent, skip 28807fa9a checkpoint)
   ```

2. **Resolution hotspots** (files likely to conflict):
   - `run_agent.py` — heavily patched; diff against our version, not upstream
   - `gateway/run.py` — PID detection block may need line-number adjustment
   - `agent/auxiliary_client.py` — temperature/role normalization in `_CodexCompletionsAdapter`

3. **Test after rebase:**
   ```bash
   pytest tests/gateway/test_slack.py -x           # 131 tests, <2s
   pytest tests/run_agent/test_deepseek_reasoning*   # DeepSeek reasoning
   pytest tests/agent/test_auxiliary_client.py       # Codex 400 fix
   ```

4. **The uncommitted patch (#6)** must be applied on top of the rebased branch — it's a small targeted fix to `slack.py` and `base.py` that should apply cleanly to any version with the same `_active_status_threads` pattern.

---

## Governance

- **All changes local commits only** (no upstream PRs unless explicitly requested)
- **Pre-commit gate:** Full unit + integration test suite, 0 failures
- **Issue tracking:** Regressions → `~/.hermes/data/sys_issues.json` (unified ledger)
