# SYS-1030 — Atomic cron dispatch and pause-preserving full-job canaries

Status: Loop 1 corrected specification; implementation and tests NOT RUN

Coauthors: Systems Panel, Runtime DevOps Panel, Six Sigma Panel

## 1. Required outcome and fixed boundary

SYS-1030 is the Hermes prerequisite for MarketWatch SYS-1029. Loop 2 shall make these three outcomes true:

1. every built-in or Chronos recurring occurrence is durably claimed with its exact scheduled instant before executor submission, including one collapsed stale catch-up;
2. an operator can execute one complete `run_one_job` attempt while its job remains paused, using the normal script/agent, output, delivery, status, cleanup, and interruption route; and
3. a pre-run script failure stops before `AIAgent` import/construction and remains a failure through output, delivery, and final job status.

No new store, ledger, mutex, daemon, service, process group, host scan, READY file, or cache is authorized. The only durable authority remains the profile's existing `cron/jobs.json`, mutated through `cron/jobs.py::_jobs_lock` and `save_jobs`. The existing in-process locks remain implementation guards, not recovery authority. `cron/script_supervisor.py`, `cron/scheduler.py::_run_script_process`, `start_new_session=True`, and current `killpg` behavior are byte-unchanged.

Finite one-shot dispatch/repeat behavior is not redesigned. Loop 2 changes its plumbing only enough to carry an explicit execution context and to let paused canaries bypass `claim_dispatch`; §7 freezes its behavior.

Baseline: Hermes `origin/main` at `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`. Loop-2 code must be panel-authored and approved by all three named roles before merge.

## 2. Source-backed current-state diagnosis

| Source locator | Current fact | Required correction |
|---|---|---|
| `cron/jobs.py::_jobs_lock` (222 onward) | lock-open/flock timeout or error logs and proceeds under `_jobs_file_lock` only | claims/finalizers request strict cross-process mode; failure is typed and causes zero mutation/execution (D01) |
| `cron/jobs.py::_get_due_jobs_locked` (1829–2180) | stale recurring catch-up saves a provisional future `next_run_at` but returns the old copied row | due selection must not mutate a valid recurring row |
| `cron/jobs.py::advance_next_run` (1690–1727), `cron/scheduler.py::tick` (4152 onward) | reload sees that future value, returns false without a claim; tick ignores false and submits | one claim owner atomically validates old scheduled time, advances, and creates the claim before submit |
| `docs/chronos-managed-cron-contract.md`, `plugins/cron_providers/chronos/_nas_client.py::NasCronClient.provision` | NAS provision already carries exact `fire_at` | preserve its bytes through relay JWT/body and every reader (D02) |
| `gateway/platforms/api_server.py::APIServerAdapter._handle_cron_fire`; `hermes_cli/web_server.py::cron_fire_webhook` | both verify JWT but read only `job_id`; `fire_at` is discarded | require authenticated scheduled time, exact body/claim equality, zero execution on mismatch |
| `cron/scheduler_provider.py::CronScheduler.fire_due`; `plugins/cron_providers/chronos/__init__.py::ChronosCronScheduler.fire_due` | neither accepts the scheduled time | version both signatures and pass it to the claim |
| `cron/jobs.py::advance_next_run`, `set_dispatch_claim_status`; MarketWatch `enforcement/calibration_cron_watchdog.py` | legacy claims are untagged `{at,by,status}` with lowercase statuses; watchdog directly rewrites stale claims | use tagged lowercase V2; classify every legacy/current shape; no ambiguous replay (D03) |
| `cron/scheduler.py::run_one_job` | internally calls `claim_dispatch`; callers provide only a job dict | carry mode and exact claim identity end to end; canary bypasses one-shot claim (D04–D05) |
| `cron/scheduler.py::run_job` (2990 onward), `_build_job_prompt` | agent path imports `AIAgent`/opens `SessionDB` before script; a failed script becomes prompt context | script failure is terminal before agent/session/provider work (D08) |
| `cron/scheduler.py::_running_job_ids`, `_interrupted_job_ids`, `mark_running_jobs_interrupted`; `gateway/run.py` shutdown call | identity is only `job_id` | use `(job_id,mode,nonempty claim_id)` so occurrence N cannot mark N+1/canary (D10) |
| `cron/jobs.py::trigger_job`; current `hermes cron run` | enables/schedules the job | add distinct pause-preserving canary; never use trigger/resume (D11/D13) |
| gateway health/status | PID is visible but no live loaded-module Git identity is bound; cwd is not proof | compute build identity inside the running process and bind it to configured PID/start/executable (D12) |

Exact stale defect: due selection loads stale `S0`, saves future `S1`, returns the copy carrying `S0`; `advance_next_run` reloads `S1`, recomputes `S1`, returns false, and writes no claim; `tick` ignores false and submits. No reviewer may treat current watchdog replay as closure because submit may already have occurred.

## 3. Scalar, time, canonical-byte, and identity rules

### 3.1 Scalars

- `JobId`: nonempty UTF-8 string, exact persisted bytes, no surrounding whitespace.
- `ModeV2`: `builtin_recurring | chronos_recurring | manual_recurring | builtin_one_shot | chronos_one_shot | manual_one_shot | paused_canary`. These seven tags are exhaustive; trigger origin and schedule class are never inferred later.
- `ClaimStatusV2`: lowercase `claimed | dispatched | not_submitted | finished | interrupted`.
- `JsonValue = null | bool | Int | finite decimal | UTF-8 str | List[JsonValue] | Map[UTF8String,JsonValue]`; maps cannot contain duplicate keys.
- JSON canonical bytes: UTF-8, NFC strings, object keys sorted by Unicode code point, separators `,` and `:`, no insignificant whitespace, no NaN/Infinity, integers written base 10, booleans/null lowercase.
- `sha256:<64 lowercase hex>` is SHA-256 over canonical bytes. A digest lives only in the existing current claim; it creates no separate record or authority.

### 3.2 Stored and generated instants (D07)

```text
StoredAwareInstantV1 = {raw:str, epoch_microseconds:Int}
GeneratedUtcInstantV1 = {raw:str, epoch_microseconds:Int}
```

`StoredAwareInstantV1.raw` accepts exactly RFC3339 calendar/time fields with `T`, optional 1–6 fractional digits, and either literal `Z` or numeric `+HH:MM`/`-HH:MM`. It rejects naive values, leap-second `:60`, offset beyond 23:59, whitespace, and more than six fractional digits. Parsing preserves `raw` byte-for-byte; comparison/order uses the uniquely normalized signed UTC `epoch_microseconds`. Thus a real persisted `2026-09-11T09:05:00-04:00` is valid and not rewritten to `Z`.

New owner-generated times are separate `GeneratedUtcInstantV1`, exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`. The owner samples once before its lock call; beneath the lock no wall clock is sampled. Equality of `scheduled_for` is raw-byte equality after both values independently pass `StoredAwareInstantV1`; due/future ordering uses `epoch_microseconds`.

### 3.3 Protected job preimage and collision-safe IDs (D06)

`NormalizedJobV1` is the complete normalized persisted object, including unknown extension keys. `JobProtectedBodyV1` is derived by removing only these volatile paths:

```text
last_run_at, last_status, last_error, last_delivery_error,
fire_claim, run_claim, dispatch_claim, next_run_at, repeat.completed
```

It therefore includes every execution/effect field, including `id,name,prompt,skills,skill,model,provider,provider_snapshot,model_snapshot,base_url,script,no_agent,context_from,schedule,schedule_display,repeat.times,enabled,state,paused_at,paused_reason,created_at,deliver,origin,enabled_toolsets,workdir,attach_to_session` and any future persisted key not explicitly classified volatile. `protected_digest=sha256(canonical(JobProtectedBodyV1))`.

`ClaimSlotProjectionV1` is a nonrecursive projection of one complete stored
claim field:

```text
ABSENT {present:false,schema_tag:null,claim_id:null,status:null,raw_digest:null}
| PRESENT {present:true,
    schema_tag:legacy_run|legacy_fire|legacy_dispatch|fire_v2|canary_v2|dispatch_v2,
    claim_id:str|null,status:str|null,
    raw_digest:sha256(canonical(the complete stored claim object))}
```

Legacy run/fire claims have null `claim_id` and `status`; legacy dispatch has
null `claim_id` and its exact lowercase status. Current claims have their
recomputed ID and exact lowercase status. An unknown or malformed object has
no projection: row validation returns MALFORMED_ROW. This digest binds every
claim leaf without embedding an earlier claim body in a later one.

`JobLifecyclePreimageV1` is:

```text
LegacyRunClaimV1={at:str,by:str}
LegacyFireClaimV1={at:str,by:str}
{protected_digest, next_run_at:str|null, repeat_completed:Int>=0,
 last_run_at:str|null, last_status:str|null, last_error:str|null,
 last_delivery_error:str|null,
 fire_claim:ClaimSlotProjectionV1,
 run_claim:ClaimSlotProjectionV1,
 dispatch_claim:ClaimSlotProjectionV1}
```

`JobFinishGuardV1={protected_digest,next_run_at,repeat_completed,last_run_at,last_status,last_error,last_delivery_error,fire_claim_id:str|null,run_claim:LegacyRunClaimV1|null,dispatch_claim_id:str|null,dispatch_claim_status:str|null}`. It projects claim identities/statuses rather than nesting a claim body, so it cannot hash/reference itself.

Claims compare the entire preimage before writing and store that preimage plus the exact postclaim `JobFinishGuardV1`. Finalizers compare the current row to the stored guard before changing authorized leaves. A changed prompt, script, model/provider, delivery target, context, toolset, workdir, pause field, schedule, repeat limit, unknown persisted extension, successor, repeat count, last-result field, or claim identity refuses before effect/final mutation.

Claim IDs never concatenate unescaped fields:

```text
dispatch claim_id = sha256(canonical({schema:"cron-dispatch-id-v2",job_id,mode,scheduled_for_raw,protected_digest}))
fire claim_id     = sha256(canonical({schema:"cron-fire-id-v2",job_id,mode,issued_at_raw,protected_digest}))
canary claim_id   = sha256(canonical({schema:"cron-canary-id-v2",job_id,mode:"paused_canary",issued_at_raw,protected_digest}))
legacy one-shot execution claim_id = sha256(canonical({
  schema:"cron-one-shot-execution-id-v2",job_id,mode:"builtin_one_shot",
  run_claim,repeat_completed_before,protected_digest}))
```

The store recomputes every ID and rejects mismatch. Tests include delimiter-containing IDs/instants and one-leaf mutations.

## 4. Strict store lock and closed claim product (D01/D09)

Target existing owner:

```python
cron.jobs._jobs_lock(*, require_cross_process: bool = False)
```

Legacy non-claim readers/writers may retain `False`. Every dispatch/fire/canary claim, status transition, interruption write, and finalizer passes `True`. On POSIX, lock-file open, `flock` acquisition within existing `_JOBS_LOCK_TIMEOUT_SECONDS=30.0`, or unavailable `fcntl` raises `CronJobsLockUnavailable` before yielding the critical section. On Windows the existing native lock must be acquired within the same bound or fail the same way. `_jobs_file_lock` remains nested protection but is never sufficient for strict mode. No new lock file or mutex is introduced.

The reentrant lock state records whether the outermost acquisition actually
owns the cross-process lock. A nested `require_cross_process=True` call is
admitted only when that bit is already true; attempting to upgrade an outer
non-strict acquisition raises `CronJobsLockUnavailable` before the inner
body. Strict owners therefore run at the outermost boundary, or every caller
propagates strict mode. A nested-call test proves no RLock-only bypass.

All claim owners return this closed product:

```text
ClaimAttemptResultV2 =
  CLAIMED {claim:ClaimEvidenceV2, job_postimage:NormalizedJobV1,
           reason:null, error:null}
| REFUSED {claim:null, job_postimage:null,
           reason:NOT_FOUND|DISABLED|PAUSED|NOT_DUE|PREIMAGE_CHANGED|
                  ALREADY_CLAIMED|MODE_MISMATCH,
           error:null}
| INVALID_REQUEST {claim:null, job_postimage:null,
           reason:INVALID_JOB_ID|INVALID_MODE|INVALID_TIME|INVALID_STATUS|
                  INVALID_NULLABILITY|CLAIM_ID_MISMATCH,
           error:null}
| MALFORMED_ROW {claim:null, job_postimage:null,
           reason:NOT_OBJECT|MISSING_FIELD|INVALID_FIELD|UNKNOWN_CLAIM_SCHEMA|
                  UNKNOWN_CLAIM_STATUS|INVALID_LEGACY_CLAIM,
           error:null}
| LOCK_FAILED {claim:null, job_postimage:null, reason:LOCK_UNAVAILABLE,
           error:nonempty exact class/message}
| STORE_FAILED {claim:null, job_postimage:null, reason:SAVE_FAILED,
           error:nonempty exact class/message}
```

Only CLAIMED has claim/postimage. Only LOCK_FAILED/STORE_FAILED has error. Every other combination is invalid. All non-CLAIMED variants cause zero execution, output, delivery, status mutation, or pool submission.

Two-process RED: process A holds `.jobs.lock` beyond the bound while process B calls each strict owner. Baseline mutates under its RLock-only fallback; target returns LOCK_FAILED and the jobs file is byte-identical.

## 5. Recurring scheduled occurrence and Chronos ingress (D02/D03)

### 5.1 Current dispatch schema

```text
LegacyDispatchClaimV1={at:str,by:str,status:claimed|dispatched|recovered,
 recovered_at:str|null}

DispatchClaimV2 = {
 schema:"cron-dispatch-claim-v2", mode:builtin_recurring|chronos_recurring,
 claim_id, occurrence_key, job_id, scheduled_for_raw,
 next_run_after_raw, claimed_at_raw, by, protected_digest,
 preimage:JobLifecyclePreimageV1, finish_guard:JobFinishGuardV1,
 status:claimed|dispatched|not_submitted|finished|interrupted
}
```

`occurrence_key=claim_id`; it is not separately constructed. All timestamps validate under §3.2. Status is deliberately lowercase for current source/readers.

Target owner:

```python
cron.jobs.claim_recurring_dispatch(
    *, job_id: str, mode: Literal["builtin_recurring","chronos_recurring"],
    scheduled_for: str, claimed_at: str, claimant: str
) -> ClaimAttemptResultV2
```

Under strict lock it loads once; constructs/validates the full preimage; requires enabled true, state not paused, recurring kind, exact stored `next_run_at.raw == scheduled_for`, and `scheduled_for <= claimed_at`; computes the first schedule successor strictly later than `claimed_at`; and saves `next_run_at=next_run_after_raw` plus DispatchClaimV2 in the same atomic replace. `repeat.completed` is unchanged at claim.

`_get_due_jobs_locked` returns a valid due recurring row without changing it. A stale schedule yields exactly one claim at the original stored `scheduled_for`; the successor is future, so all missed slots collapse without burst. Same `(job,scheduled_for)` in any status returns ALREADY_CLAIMED. A later exact scheduled value may atomically replace an older claim; matching-ID finalization prevents the old runner from touching it.

`cron.jobs.transition_dispatch_claim(job_id: str, *, expected_claim_id: str, from_status: str, to_status: str) -> FinalizationResultV2` admits only `claimed→dispatched`, `claimed→not_submitted`, and `claimed|dispatched→interrupted`. It uses strict lock and exact ID/status CAS and atomically changes both `claim.status` and its nonrecursive `finish_guard.dispatch_claim_status` to the same target. Target `cron.jobs.mark_job_run(job_id: str, success: bool, error: Optional[str] = None, delivery_error: Optional[str] = None, *, execution_context: ClaimContextV2) -> FinalizationResultV2` changes `dispatched→finished` and then removes only that exact claim in the same final save; it preserves the claim's exact `next_run_after_raw`.

### 5.2 Exact Chronos wire

NAS provision remains:

```text
POST /api/agent-cron/provision
{job_id, fire_at:<exact stored next_run_at raw>, agent_callback_url,
 dedup_key:job_id+":"+fire_at}
```

The NAS relay maps `fire_at` to `scheduled_for` without parsing/reformatting. Its signed JWT must contain exact `purpose="cron_fire"`, `aud`, `iss`, `exp`, `job_id`, and `scheduled_for`. Its request body is exactly:

```text
ChronosFireRequestV2={schema:"cron-fire-request-v2",job_id,scheduled_for}
```

The existing verifier `plugins/cron_providers/chronos/verify.py::verify_nas_fire_token` retains signature/algorithm/audience/issuer/expiry/not-before/purpose checks and additionally validates typed JWT `job_id` and `scheduled_for`. Body and JWT values must be byte-equal, with no missing/extra body keys. Missing/invalid auth, signature, issuer, audience, purpose, expiry, or not-before returns `401 {"error":"invalid fire token"}`. Invalid JSON/object/schema/job/time/nullability or JWT/body mismatch returns `400 {"error":"invalid fire request","detail_code":<MALFORMED_JSON|INVALID_SCHEMA|INVALID_JOB_ID|INVALID_SCHEDULED_FOR|JWT_BODY_MISMATCH>}`. Valid ingress returns `202 {"status":"accepted","job_id":job_id,"scheduled_for":scheduled_for}` after background-task creation. Every 400/401 path performs zero profile lookup, claim, task creation, execution, output, or delivery; a background claim refusal after 202 still performs zero job execution.

Both ingress surfaces implement the same parser and result mapping:

- `gateway/platforms/api_server.py::APIServerAdapter._handle_cron_fire`;
- `hermes_cli/web_server.py::cron_fire_webhook`, then `_fire_cron_job_for_profile`.

The NAS relay/JWT/body V2 deployment and an authenticated probe are a hard
prerequisite to enabling either Hermes V2 ingress. A legacy job-ID-only body,
even with an otherwise valid old token, is INVALID_SCHEDULED_FOR and creates
no background task. Hermes never provides a compatibility fallback that
substitutes store-current or wall-clock time.

Exact target signatures:

```python
cron.scheduler_provider.CronScheduler.fire_due(
    self, job_id: str, *, scheduled_for: str,
    adapters: Any = None, loop: Any = None
) -> JobRouteResultV2

plugins.cron_providers.chronos.ChronosCronScheduler.fire_due(
    self, job_id: str, *, scheduled_for: str,
    adapters: Any = None, loop: Any = None
) -> JobRouteResultV2
```

After locked row classification, the provider calls `claim_recurring_dispatch(mode="chronos_recurring", scheduled_for=exact body raw)` for a recurring row, or strict `claim_job_for_fire(mode="chronos_one_shot", scheduled_for=exact body raw)` followed by unchanged one-shot `claim_dispatch` for a one-shot row. Both validate the authenticated raw time against stored `next_run_at` before submission. Its override rearms NAS only from a recurring CLAIMED postimage successor and only after the route terminal; it never recomputes the consumed scheduled time. A completed one-shot is not rearmed. No body timestamp may be replaced by store-current or wall-clock time.

### 5.3 Legacy dispatch compatibility

An untagged claim is legacy only if it is an object whose keys are a subset of `{at,by,status,recovered_at}`, `at/by` are nonempty strings, status is exactly lowercase `claimed|dispatched|recovered`, `recovered_at` is present and valid only for `recovered`, and is absent for the other statuses. Total reader behavior:

| Stored `dispatch_claim` | Classification | Execution/recovery |
|---|---|---|
| absent/null | NONE | normal eligibility |
| valid DispatchClaimV2 for exact current scheduled occurrence | CURRENT | use exact V2 transition table |
| V2 `claimed`/`dispatched` from an older occurrence | CURRENT_AMBIGUOUS | never replay old occurrence; later exact scheduled claim may replace |
| V2 `not_submitted`/`finished`/`interrupted` | CURRENT_TERMINAL | never replay; later exact scheduled claim may replace |
| valid legacy `claimed` | LEGACY_AMBIGUOUS | never reset `next_run_at`, never replay, alert only |
| valid legacy `dispatched` | LEGACY_AMBIGUOUS | never replay, alert only |
| valid legacy `recovered` | LEGACY_TERMINAL | preserve recorded row; no new recovery |
| unknown schema/status, partial, wrong type, future/malformed time | MALFORMED_ROW | fail closed for that row; zero execution/mutation |

MarketWatch root `enforcement/calibration_cron_watchdog.py` and shipped mirror `scripts/enforcement/calibration_cron_watchdog.py` consume this exact table. They become read-only compatibility/alerting clients and never rewrite `jobs.json`, `next_run_at`, or claim status. Their tests prove all legacy/current/unknown rows. Existing untagged ambiguous claims are not converted or replayed.

## 6. Closed execution context across every route (D04/D10)

```text
FireClaimV2={schema:"cron-fire-claim-v2",
 mode:chronos_one_shot|manual_recurring|manual_one_shot,
 claim_id,job_id,issued_at_raw,scheduled_for_raw:str|null,
 next_run_after_raw:str|null,protected_digest,
 preimage:JobLifecyclePreimageV1,finish_guard:JobFinishGuardV1,
 status:"claimed"}

OneShotClaimContextV1={run_claim:{at:str,by:str}|null,
 repeat_completed_before:Int>=0,finite_dispatch_claimed:bool}

ClaimEvidenceV2=DispatchClaimV2|FireClaimV2|PausedCanaryClaimV2|OneShotClaimContextV1

ClaimContextV2 =
  RECURRING {mode:builtin_recurring|chronos_recurring,
             claim:DispatchClaimV2, fire_claim:null, one_shot_claim:null}
| MANUAL_RECURRING {mode:manual_recurring, claim:null,
          fire_claim:FireClaimV2, one_shot_claim:null}
| BUILTIN_ONE_SHOT {mode:builtin_one_shot, claim:null, fire_claim:null,
            one_shot_claim:OneShotClaimContextV1}
| EXTERNAL_ONE_SHOT {mode:chronos_one_shot|manual_one_shot, claim:null,
            fire_claim:FireClaimV2,one_shot_claim:OneShotClaimContextV1}
| CANARY {mode:paused_canary, claim:null,
          fire_claim:PausedCanaryClaimV2, one_shot_claim:null}
```

For Chronos one-shot, `scheduled_for_raw` is mandatory and byte-equal to the authenticated ingress and stored `next_run_at`; for manual modes it is null. `next_run_after_raw` is mandatory only for `manual_recurring`; it is null for both one-shot modes. `claim_job_for_fire` creates FireClaimV2 under strict lock and, only for manual recurring, advances recurrence in that same save. `OneShotClaimContextV1` is a typed transport of existing one-shot behavior, not a new stored object.

```python
cron.jobs.claim_job_for_fire(
    job_id: str, *,
    mode: Literal["chronos_one_shot","manual_recurring","manual_one_shot"],
    issued_at: str, scheduled_for: Optional[str] = None
) -> ClaimAttemptResultV2
```

No default mode is permitted. `scheduled_for` is required only for Chronos and forbidden for manual modes; every invalid combination is INVALID_REQUEST before read/write.

Exactly one variant is present; all cross-variant fields are forbidden.
`RunIdentityV2={job_id,mode,claim_id:nonempty str}`. Current claims contribute
their recomputed ID. A built-in one-shot contributes the deterministic
`cron-one-shot-execution-id-v2` hash from §3.3 over its admitted legacy
`run_claim`, repeat preimage, and protected digest; this is an in-memory
execution identity and does not change the stored one-shot schema.
`JobRunEnvelopeV2={job:NormalizedJobV1,job_preimage:JobLifecyclePreimageV1,context:ClaimContextV2,identity:RunIdentityV2}`.

Target shared route:

```python
cron.scheduler.run_one_job(
    envelope: JobRunEnvelopeV2, *, adapters=None, loop=None,
    verbose: bool = False
) -> JobRouteResultV2
```

Callers and contexts are total:

| Caller | Mode/claim before route | Finalizer |
|---|---|---|
| built-in `tick` | recurring DispatchClaimV2 | matching recurring `mark_job_run` |
| base/Chronos `fire_due`, recurring row | chronos_recurring DispatchClaimV2 | same |
| base/Chronos `fire_due`, one-shot row | chronos_one_shot FireClaimV2 + existing one-shot claim | existing one-shot mark/remove with matching fire ID |
| `tools/cronjob_tools.py::_execute_job_now`, recurring row | manual_recurring FireClaimV2 with atomic successor | ordinary mark with matching fire ID |
| `_execute_job_now`, one-shot row | manual_one_shot FireClaimV2 + existing one-shot claim | existing one-shot mark/remove with matching fire ID |
| built-in finite/infinite one-shot due route | existing `run_claim`/`claim_dispatch`, builtin_one_shot | existing one-shot mark/remove behavior |
| `run_paused_job_canary` | PausedCanaryClaimV2 | canary finish CAS |

Authorized row deltas are exhaustive:

| Mode | Claim delta | Successful or failed finish delta |
|---|---|---|
| builtin/Chronos recurring | `next_run_at→next_run_after`; create DispatchClaimV2; repeat unchanged | preserve successor; `repeat.completed→before+1`; set four last-result fields; remove matching dispatch claim; if finite count reaches limit, retain existing removal behavior |
| manual recurring | same successor equation; create FireClaimV2; repeat unchanged | preserve successor; completed +1; set last fields; remove matching fire claim |
| built-in one-shot | existing due `run_claim`, then existing finite `claim_dispatch` | exact §7 behavior |
| Chronos/manual one-shot | create FireClaimV2, then existing finite `claim_dispatch` | exact §7 behavior plus remove matching fire claim |
| paused canary | create PausedCanaryClaimV2 only | repeat/next/pause/schedule unchanged; set last fields; remove matching canary claim |

`run_one_job` must not infer mode from fields. Paused canary never calls `claim_dispatch`; one-shot always retains its current call/order. Cleanup quarantine, BaseException cleanup, `_consume_interrupted_flag`, and every finalizer receive the same context/identity. A missing/mismatched context is INVALID_REQUEST before execution.

In-memory `_running_job_ids` and `_interrupted_job_ids` become sets/maps keyed by `RunIdentityV2`, not job ID. Target `cron.scheduler.get_running_job_identities() -> frozenset[RunIdentityV2]` returns a locked copy; `get_running_job_ids()` may remain only as a non-authoritative job-ID projection for legacy counts. Target `mark_running_jobs_interrupted(reason: str, *, identities: frozenset[RunIdentityV2]) -> list[RunIdentityV2]` validates the exact snapshot and writes interruption only through matching-claim finalization. `_submit_with_guard`, built-in tick, provider, manual, one-shot, canary, worker finally, and `gateway/run.py::GatewayRunner._stop_impl` use the exact identity. `_stop_impl` snapshots identities immediately before its existing `process_registry.kill_all()` call and passes that same snapshot to interruption marking; a run admitted after the snapshot is not falsely classified as killed. Interruption of occurrence N cannot clear, fail, deliver for, or suppress completion of N+1 or a canary of the same job. No identity is persisted outside existing claims.

## 7. One-shot preservation (D05)

`cron.jobs.claim_dispatch` retains finite one-shot pre-effect `repeat.completed += 1`; `run_claim` due selection/heartbeat/stale rules remain unchanged; `mark_job_run` does not double-increment preclaimed finite one-shots and retains existing completion/removal rules. Infinite/no-repeat one-shots retain current behavior. No scheduled-for retrofit, replay policy, TTL change, or schema migration is applied to one-shots. Only the explicit `builtin_one_shot|chronos_one_shot|manual_one_shot` contexts and matching shutdown identity are added. Regression tests compare exact pre/post rows at the baseline and target for success, failure, interruption, finite exhaustion, and restart.

## 8. Pause-preserving full-job canary (D06/D11/D13)

### 8.1 Public contract

```text
hermes cron canary <job_id>
```

`hermes_cli/subcommands/cron.py::build_cron_parser` adds exactly one action/positional. `hermes_cli/cron.py::cron_command` calls:

```python
cron.scheduler.run_paused_job_canary(
    job_id: str, *, adapters=None, loop=None, verbose: bool = False
) -> JobRouteResultV2
```

Store owners:

```python
cron.jobs.claim_paused_job_canary(
    *, job_id:str, issued_at:str, claimant:str
) -> ClaimAttemptResultV2

cron.jobs.finish_paused_job_canary(
    *, expected_claim_id:str, route:JobRouteLeafSetV2,
    finished_at:str
) -> FinalizationResultV2

cron.jobs.clear_paused_canary_claim(
    *, job_id:str, expected_claim_id:str,
    expected_preimage:JobLifecyclePreimageV1
) -> FinalizationResultV2
```

`PausedCanaryClaimV2={schema:"cron-paused-canary-claim-v2",mode:"paused_canary",claim_id,job_id,issued_at_raw,protected_digest,preimage:JobLifecyclePreimageV1,finish_guard:JobFinishGuardV1,status:"claimed"}` is stored only in existing `fire_claim`. Claim requires strict lock; enabled false; state exactly paused; valid nonnull paused_at; no current fire/run/dispatch claim; and a valid full row. It changes only `fire_claim`. It never calls `trigger_job`, `resume_job`, `advance_next_run`, or `claim_dispatch`.

Finish requires strict lock, matching ID/status, byte-equal protected digest, and byte-equal pause/schedule/next/repeat preimage. It may update only `last_run_at`, `last_status`, `last_error`, `last_delivery_error`, and remove the exact canary `fire_claim`. It never changes enabled/state/paused_at/paused_reason/schedule/next_run_at/repeat, deletes/completes the job, or clears another claim. A changed protected field or foreign claim returns FINALIZE_CONFLICT and preserves the current row.

The canary uses the complete shared route: script containment, agent/no-agent choice, prompt/session/provider when applicable, output save, normal delivery, cleanup/quarantine, interruption, and final status. Script-only invocation is forbidden.

### 8.2 Exact five canaries and coupling

| Job ID | Exact script/mode/schedule preimage | Coupling |
|---|---|---|
| `9e059716170c` | `orchestrators/consolidated_calibration.py`; agent; `10 18 * * 1-5` | coupled with `20c3fd791e82`; both PASS before either resumes |
| `20c3fd791e82` | `orchestrators/daily_calibrate.py`; agent; `5 20 * * 1-5` | coupled with `9e059716170c` |
| `cci_precompute_runner` | `skyline/cci_runner.py`; no-agent; `35 16 * * 1-5` | independent; only its PASS permits its resume |
| `bb_precompute_runner` | `skyline/bollinger_band/bb_runner.py`; no-agent; `40 16 * * 1-5` | independent; only its PASS permits its resume |
| `c7033e9248d1` | `orchestrators/macd_precompute.py`; no-agent; `30 20 * * 1-5` | independent; only its PASS permits its resume |

Before each canary, `get_job` must match the literal ID/script/mode/schedule and the operator-approved full paused preimage. The deployment procedure pauses CCI, BB, and MACD separately before their canaries; AMC and Daily must already be separately paused and are never implicitly re-paused. A mismatch refuses before claim. Every canary returns an independently readable output path and exact final job postimage. AMC/Daily form one all-or-none resume unit; CCI, BB, and MACD have no cross-family resume dependency. Failure never resumes any job.

A canary crash after claim is effect-ambiguous: it remains paused with the claim and is not automatically reclaimed/retried. Existing-row operator repair may clear the exact claim only after remediation and exact paused-preimage comparison; it cannot execute or resume. No TTL or new recovery record is added.

## 9. Pre-run failure and closed route result (D08/D09)

### 9.1 Leaf products

Exact leaf owners are `cron.scheduler.run_job(job: dict, *, defer_agent_teardown: Optional[list] = None) -> RunLeafV2`, existing `cron.jobs.save_job_output(job_id: str, output: str) -> pathlib.Path`, target `cron.scheduler._deliver_job_result(job: dict, content: str, *, run: RunLeafV2, adapters=None, loop=None) -> DeliveryLeafV2`, and the matching finalizer selected by ClaimContextV2. `_deliver_job_result` resolves whether delivery is configured, calls existing `_deliver_result` only when required, and removes the present `None` ambiguity between delivered and not configured. No caller may synthesize an aggregate without invoking these owners in order.

```text
RunLeafV2 =
  SUCCESS {output_document:str,final_response:str,error:null,pre_run:ok|not_configured}
| SILENT {output_document:str,final_response:"",error:null,pre_run:ok|not_configured}
| FAILURE {output_document:str,final_response:"",error:nonempty str,
           pre_run:failed|cleanup_unverified|not_configured}

OutputLeafV2 =
  SAVED {output_path:absolute str,error:null}
| FAILED {output_path:null,error:nonempty str}
| SKIPPED {output_path:null,error:null,reason:run_not_started}

DeliveryLeafV2 =
  DELIVERED {error:null}|NOT_CONFIGURED {error:null}|SILENT {error:null}
| FAILED {error:nonempty str}|SKIPPED {error:null,reason:output_failed|run_not_started}

JobRouteLeafSetV2={run:RunLeafV2,output:OutputLeafV2,
 delivery:DeliveryLeafV2,output_path:str|null}

FinalizationResultV2 =
  FINISHED {job_postimage:NormalizedJobV1,error:null}
| CONFLICT {job_postimage:null,error:null,reason:CLAIM_CHANGED|PREIMAGE_CHANGED|JOB_MISSING}
| LOCK_FAILED {job_postimage:null,error:nonempty str,reason:LOCK_UNAVAILABLE}
| STORE_FAILED {job_postimage:null,error:nonempty str,reason:SAVE_FAILED}
| SKIPPED {job_postimage:null,error:null,reason:claim_not_acquired}
```

### 9.2 Aggregate and dominance

```text
JobRouteResultV2={schema:"cron-job-route-result-v2",mode,job_id,
 claim_result:ClaimAttemptResultV2,
 claim_postimage:NormalizedJobV1|null,
 run:RunLeafV2|null, output:OutputLeafV2, delivery:DeliveryLeafV2,
 finalization:FinalizationResultV2, output_path:str|null,
 status:REFUSED|RUN_FAILED|OUTPUT_FAILED|DELIVERY_FAILED|FINALIZE_FAILED|PASS}
```

Nullability: a non-CLAIMED claim has null run/claim_postimage, SKIPPED output/delivery/finalization, null output_path, and status REFUSED. A CLAIMED route always has nonnull run. Output SAVED iff output_path is the same nonnull path; all other output variants require null. Finalization FINISHED alone has job_postimage. No leaf may be omitted.

Status is selected by this sole precedence, top first:

1. non-CLAIMED claim → REFUSED;
2. finalization CONFLICT/LOCK_FAILED/STORE_FAILED → FINALIZE_FAILED;
3. output FAILED → OUTPUT_FAILED;
4. run FAILURE → RUN_FAILED, regardless of delivery success/failure;
5. delivery FAILED → DELIVERY_FAILED;
6. otherwise PASS.

Thus a failed pre-run can never become PASS. Output/delivery still retain their exact diagnostic leaves.

For a configured script, `cron.scheduler.run_job` calls `_run_scheduled_job_script` before importing `run_agent.AIAgent`, constructing it, opening SessionDB, resolving provider/model, or building the prompt. Failed script returns RunLeaf FAILURE immediately. `_build_job_prompt(job, successful_prerun)` never runs a script; missing/failed pre-run input for a scripted job is invalid. `wakeAgent:false` remains SILENT. No-agent follows the same failure rule. Cleanup-unverified retains the existing quarantine/pause authority.

The failed output document is saved, the existing failure summary is delivered if configured, and matching finalization writes `last_status="error"`, exact `last_error`, and separate delivery error. Delivery success cannot clear it; delivery failure cannot replace it. Output-save failure is also never success.

## 10. Complete mutation/restart matrix

| Cut/operation | Durable state | Required next behavior |
|---|---|---|
| strict lock fails | byte-identical store | return LOCK_FAILED; zero submit/effect |
| due read before recurring claim | old due instant, no V2 claim | same occurrence may be claimed |
| after atomic recurring save, before submit | future next; V2 claimed | old occurrence never replayed |
| submit refuses/raises | same, then matching not_submitted if CAS succeeds | no old replay; next occurrence eligible at its time |
| submit accepted before status CAS | V2 claimed | ambiguous; no old replay |
| after dispatched, before worker starts | V2 dispatched | ambiguous; no old replay |
| run/effect/output/delivery before finish | current exact claim plus artifacts | matching finish only; restart does not rerun old occurrence |
| recurring finish | claim successor preserved; completed +1; matching claim removed | next occurrence normal |
| recurring failed attempt | same successor; completed +1; last_status error | no retry of same scheduled instant |
| finite recurring reaches `repeat.times` | completed becomes times; existing terminal removal behavior | no successor execution |
| canary before claim | exact paused row | retry allowed |
| canary after claim at any effect cut | paused row + exact claim + artifacts | no auto retry/reclaim/resume |
| canary FINISHED | pause/schedule/next/repeat byte-equal; last fields updated; claim removed | operator evaluates PASS/resume policy |
| canary finish conflict/failure | current paused row/claim retained | fail closed; investigate |
| pre-run fails | claimed occurrence/canary, failed output/delivery/status | no agent work; normal matching terminal rules |
| shutdown snapshots occurrence N | in-memory exact RunIdentityV2 | interrupt/finalize N only; N+1/canary unaffected |

Manual immediate remains a distinct occurrence under its V2 fire claim. Chronos/built-in scheduled claims share the recurring state machine. One-shot remains §7. No crash cut creates a retry worker, state sweeper, or exactly-once claim.

## 11. Running-build identity and deployment (D12)

Target `cron.scheduler.running_build_identity() -> RunningBuildIdentityV1` runs inside the gateway process:

```text
RunningBuildIdentityV1={schema:"hermes-running-build-v1",pid:Int,
 proc_start_ticks:Int,executable_realpath:absolute str,
 scheduler_module_realpath:absolute str,checkout_root:absolute str,
 git_oid:40 lowercase hex}
```

It derives `scheduler_module_realpath` from the already-loaded `cron.scheduler.__file__`, requires exactly one ancestor Git root, and runs `git -C <checkout_root> rev-parse --verify HEAD` with stdin closed, replacement environment, two-second timeout, stdout exactly 41 bytes (`OID40+LF`), empty stderr, and exit 0. It reads its own `/proc/self/stat` start ticks and `/proc/self/exe`; missing/ambiguous Git root, deleted/replaced executable, non-40-hex OID, or unsupported `/proc` returns a typed refusal. It never uses process cwd or network.

The existing `gateway/platforms/api_server.py::APIServerAdapter._handle_health` response includes this live object. Deployment verification obtains exactly one configured PID through `gateway.status.get_running_pid()` for the selected profile—never a process-table scan—records `/proc/<pid>/stat` start ticks and `/proc/<pid>/exe`, calls that gateway's health endpoint, and requires PID/start/executable equality plus `R=running.git_oid=D=deployed checkout HEAD=M=reviewed merge`. A PID change during either read restarts verification. Missing/multiple authority, missing endpoint, replacement, stale PID, module from another checkout, or any OID mismatch refuses all canaries/resumes. No identity file/hash line is persisted.

Git lifecycle:

1. Loop-2 candidate `C` is pushed to `origin/fix/sys1030` and approved 3/3 at exact OID.
2. Merge `M` is read from `origin/main`; `C` must be its ancestor.
3. Deployed checkout is clean at `D=M`; origin is exactly `https://github.com/kendeng300/hermes-agent.git`.
4. Restart with existing `hermes gateway restart`; verify RunningBuildIdentityV1 and `R=D=M`.
5. Verify each required paused preimage, execute full-route canaries, read output/job postimages, and apply §8 coupling.
6. On failure, keep affected jobs paused, restore reviewed prior Git OID, restart, and repeat identity proof. Never copy files or fabricate an OID marker.

## 12. One nonduplicated Loop-2 inventory

| Repository/path | Exact owner/edge | Disposition |
|---|---|---|
| Hermes `cron/jobs.py` | `_jobs_lock`, due reader, recurring/fire/canary claims, claim transition, `claim_dispatch`, `mark_job_run`, canary finish | EDIT; one store authority |
| Hermes `cron/scheduler.py` | `tick`, `_submit_with_guard`, `run_job`, `_build_job_prompt`, `run_one_job`, canary owner, running/interrupted identities, live build identity | EDIT; supervisor functions excluded |
| Hermes `cron/scheduler_provider.py` | base `fire_due` exact scheduled-time ingress | EDIT |
| Hermes `plugins/cron_providers/chronos/__init__.py` | override fire/rearm | EDIT |
| Hermes `plugins/cron_providers/__init__.py` | provider discovery/load edge to the versioned base/Chronos interface | PRESERVE_WITH_TEST |
| Hermes `plugins/cron_providers/chronos/_nas_client.py` | provision exact `fire_at` | PRESERVE_WITH_TEST |
| Hermes `plugins/cron_providers/chronos/verify.py` | JWT job/time binding | EDIT |
| Hermes `gateway/platforms/api_server.py` | `_handle_cron_fire` first webhook parser/background caller; `_handle_health` live build identity | EDIT |
| Hermes `hermes_cli/web_server.py` | second webhook/profile caller | EDIT |
| Hermes `hermes_cli/dashboard_auth/public_paths.py` | authenticated public-path admission for `/api/cron/fire` | PRESERVE_WITH_TEST; JWT remains the gate |
| Hermes `hermes_cli/config.py` | Chronos callback/issuer/audience configuration read by provision and ingress | PRESERVE_WITH_TEST; no time authority |
| Hermes `hermes_cli/subcommands/cron.py`, `hermes_cli/cron.py`, `hermes_cli/main.py` | exact canary grammar/dispatch/command admission | EDIT |
| Hermes `tools/cronjob_tools.py` | manual immediate context/result consumer | EDIT |
| Hermes `gateway/run.py` | `GatewayRunner._stop_impl` exact shutdown identity snapshot/interruption caller | EDIT |
| Hermes `docs/chronos-managed-cron-contract.md` | provision→JWT/body→claim wire | EDIT |
| MarketWatch `enforcement/calibration_cron_watchdog.py` | root legacy/V2 claim reader | EDIT read-only compatibility |
| MarketWatch `scripts/enforcement/calibration_cron_watchdog.py` | shipped mirror | CREATE/EDIT to byte-semantic parity; read-only compatibility |

No other production owner is implied. The two MarketWatch copies are consumers only and do not make Hermes state decisions.

Exact proof files:

- `tests/cron/test_jobs.py`: strict two-process lock; stored offset times; preimage mutation per protected field; current/legacy/unknown claim Cartesian; recurring and one-shot matrices.
- `tests/cron/test_scheduler.py`: all modes; claim-before-submit; pre-run zero-agent; leaf/aggregate Cartesian; output/delivery/finalizer failures.
- `tests/cron/test_run_one_job.py`: context propagation, claim-ID matching, canary full route, one-shot parity.
- `tests/cron/test_parallel_pool.py` and `tests/cron/test_shutdown_interrupt.py`: occurrence N shutdown then N+1/canary, every cleanup path.
- `tests/gateway/test_cron_active_work_drain.py`: gateway caller uses full identities.
- `tests/cron/test_scheduler_provider.py` and `tests/plugins/test_chronos_cron.py`: scheduled time through base/override/rearm.
- `tests/cron/test_cron_script.py`: direct base-provider callers receive exact one-shot/recurring contexts.
- `tests/gateway/test_cron_fire_webhook.py` and `tests/hermes_cli/test_cron_fire_dashboard.py`: both authenticated timestamp ingress surfaces, mismatch/missing/extra/invalid token zero execution.
- `tests/hermes_cli/test_web_server_cron_profiles.py` and `tests/hermes_cli/test_cron_dashboard_off_loop.py`: profile selection and off-loop execution transport the exact scheduled time.
- `tests/hermes_cli/test_cron.py`: configured-provider discovery and existing cron command compatibility.
- `tests/plugins/test_chronos_verify.py`: JWT job/time claims.
- `tests/tools/test_cronjob_run_immediate.py`: manual context, failure/status compatibility.
- `tests/hermes_cli/test_cron_parser_builder.py`: canary CLI and exits.
- `tests/cron/test_sys1030_full_route.py` (CREATE): five isolated full-route canaries, coupling/readback, stored `-04:00`, every crash cut, PID/OID replacement.
- MarketWatch `tests/test_sys770_cron_silent_skip.py` and shipped `scripts/tests/test_sys770_cron_silent_skip.py`: root/shipped watchdog parity and no write/replay.

## 13. Deterministic RED/GREEN acceptance

1. Hold `.jobs.lock` in process A; every strict process-B owner returns LOCK_FAILED, file bytes unchanged. Baseline process-local fallback is RED.
2. For each webhook, use a valid JWT/body with matching timestamp (one claim), then missing/mismatched/reformatted/JWT-only/body-only times (zero claim/run). Invalid auth always zero profile lookup/task.
3. Feed null, each valid legacy status, each V2 status, unknown schema/status, partial/wrong-type/future timestamp into Hermes plus both watchdog copies; exact §5.3 result and zero ambiguous replay.
4. Cross every ModeV2 with submit, run, cleanup, interruption, and finalizer success/failure. Any missing context or wrong ID is RED and cannot mutate a successor.
5. Preserve baseline one-shot pre/post rows exactly for success/failure/restart/exhaustion; canary must record zero calls to `claim_dispatch`.
6. Mutate each protected field between read/claim and claim/finish; exactly PREIMAGE_CHANGED/CONFLICT, zero effect or foreign clear. Mutating only the explicitly authorized final fields yields the stated postimage.
7. Use equivalent instants with `Z`, `+00:00`, and `-04:00`: raw equality governs occurrence identity; normalized ordering governs due/future; no accepted raw bytes are rewritten.
8. Enumerate the valid leaf product Cartesian and one invalid nullability mutation per row; aggregate status follows §9.2 only. A failed pre-run with a fake successful agent remains RUN_FAILED and agent import count is zero.
9. Shutdown occurrence N after successor N+1 is claimed, and while a canary for the same job ID exists in isolation; only exact N is interrupted/finalized.
10. Execute the five §8 jobs through mocked external providers but real shared job route/store/output/delivery adapters under isolated homes. AMC/Daily resume only together; CCI/BB/MACD independently. Script-only calls are RED.
11. Change configured PID, PID start ticks, executable path, loaded module checkout, deployed OID, and health OID one at a time; every mismatch refuses before canary/resume.

All test roots are exact descendants of `/home/linux/.hermes/test/sys1030/<case>` and are validated/cleaned before and after. No `/tmp`, xdist, systemd invocation, network, host scan, live gateway mutation, production jobs file, or live delivery occurs.

Future verification commands, only after implementation:

```text
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh -j 1 tests/cron/test_jobs.py tests/cron/test_scheduler.py tests/cron/test_run_one_job.py tests/cron/test_parallel_pool.py tests/cron/test_shutdown_interrupt.py tests/cron/test_scheduler_provider.py tests/plugins/test_chronos_cron.py tests/plugins/test_chronos_verify.py tests/gateway/test_cron_fire_webhook.py tests/hermes_cli/test_cron_fire_dashboard.py tests/gateway/test_cron_active_work_drain.py tests/tools/test_cronjob_run_immediate.py tests/hermes_cli/test_cron_parser_builder.py tests/cron/test_sys1030_full_route.py
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh -j 1 tests/cron tests/plugins/test_chronos_cron.py tests/plugins/test_chronos_verify.py tests/gateway/test_cron_fire_webhook.py tests/hermes_cli/test_cron_fire_dashboard.py tests/gateway/test_cron_active_work_drain.py tests/tools/test_cronjob_run_immediate.py tests/hermes_cli/test_cron_parser_builder.py
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh
```

The repository's existing environment must already be complete; commands do not install dependencies. Missing dependencies fail closed. CPU scheduling remains the repository wrapper's policy.

## 14. Round-1 rejection closure and release condition

| IDs | Closed here | Discriminating proof |
|---|---|---|
| D01 | strict existing cross-process lock | two-process lock-loss RED |
| D02 | scheduled time through NAS/JWT/body/both ingress/provider/claim | auth+time mismatch zero-execution matrix |
| D03 | lowercase V2 plus total legacy table and watchdog twins | current/legacy/unknown Cartesian |
| D04,D10 | closed mode/context and exact in-memory shutdown identity | all-mode cleanup plus N/N+1 mutation |
| D05 | explicit one-shot non-redesign | baseline/target row parity |
| D06,D07 | complete job digest, collision-safe IDs, real stored offsets | per-field mutations, collision and offset vectors |
| D08,D09 | total leaf/aggregate products and failure precedence | result Cartesian and fake-success agent RED |
| D11,D13 | five literal complete-route canaries and coupling | five isolated routes; no script-only authority |
| D12 | PID/start/executable/loaded-module OID | one-field replacement/refusal matrix |

Baseline is 11 valid blockers grouped into six causal families. Release CTQ is no more than two localized residuals after this batch (at least 81.8% reduction), with no P0 lifecycle recurrence. Loop 1 remains specification-only. Loop 2 releases only after one exact candidate OID receives 3/3 review, all focused/adjacent/full tests pass, live `R=D=M`, five canary policies pass, and job/output readbacks match. Otherwise roll back by Git OID and leave affected jobs paused.
