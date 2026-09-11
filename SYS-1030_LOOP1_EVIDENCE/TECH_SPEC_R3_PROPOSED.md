# SYS-1030 — R3 proposed technical specification
Status: proposed Loop-1 correction; implementation and tests NOT RUN
Issue: MarketWatch #1030, prerequisite for SYS-1029
Baseline source reviewed: Hermes `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`
This replaces rejected R2 and authorizes no product-job execution or live mutation.
## 1. Quality goals and boundary
### CTQ-1 — claim before submit
Every recurring builtin or Chronos occurrence and its successor are durably
stored before executor submission or background-task creation.
### CTQ-2 — pause-preserving canary
A public command runs one paused job through complete `run_one_job` while
preserving enabled, pause, schedule, successor, repeat, execution, and extensions.
### CTQ-3 — pre-run failure truth
A pre-run script failure precedes agent/session/model/provider construction and
remains failure through output, delivery, finalization, command, and exit.
### Non-goals
- No redesign of finite one-shot claims, repeat accounting, or recovery.
- No SYS-666 or other MarketWatch product-acceptance redesign.
- No production product canary, pause, resume, trigger, or schedule change.
- No five-job release cohort. SYS-1029 owns its product canaries and resume.
- No NAS protocol change, NAS repository assumption, or invented NAS version.
- No general canonical codec, caller-approved digest, or hash authority.
- No new store, ledger, mutex, service, process group, PID scan, cache, READY file, or lifecycle state file.
- `cron/script_supervisor.py`, `_run_script_process`, `start_new_session`, and
  existing process-group containment remain unchanged.
## 2. Current source truth
| Source owner | Current behavior | Required change |
|---|---|---|
| `cron/jobs.py::_jobs_lock` | File-lock timeout/error/unavailability degrades to process-local locking. | All jobs-file writers fail closed unless the existing cross-process lock is held. |
| `cron/jobs.py::load_jobs` | A read can auto-repair and write malformed input. | Reading is side-effect free; repair is an explicit locked mutation. |
| `cron/jobs.py::_get_due_jobs_locked` | Due selection mixes recurring selection with existing one-shot `run_claim` and exhaustion preparation. | Split the paths: recurring selection is read-only, while locked one-shot preparation and its current recovery/exhaustion contract are preserved. |
| `cron/jobs.py::advance_next_run` | Advance and legacy claim are separate from the returned due snapshot and submit. | Recurring scheduled callers use the new atomic claim owner. |
| `cron/scheduler.py::tick` | Calls due, advances separately, then submits; submit status is best effort. | Claim first, then submit the exact claimed snapshot. |
| `cron/scheduler.py::_submit_with_guard` | In-memory identity is only `job_id`. | Carry exact occurrence identity and never run without matching `ACTIVE`. |
| `cron/scheduler.py::run_one_job` | Calls existing one-shot `claim_dispatch`, then run/output/delivery/finalization. | Preserve its exact boolean ABI and one-shot behavior; factor the same route into `_run_one_job_managed`, which accepts recurring/canary context and returns the typed outcome. |
| `cron/scheduler.py::run_job` | Agent construction can follow failed script output. | A failed pre-run returns failure before agent/session/provider work. |
| `cron/scheduler.py::get_running_job_ids`, `mark_running_jobs_interrupted` | Project only job ID. | Internally key scheduled work by exact claim identity; retain job-ID projection only for compatibility. |
| `cron/scheduler_provider.py::CronScheduler.fire_due` | Claims Chronos by job ID without scheduled time. | Accept and claim exact `fire_at`. |
| `plugins/cron_providers/chronos/__init__.py::ChronosCronScheduler.run_claimed` | `fire_due` currently owns successor `_arm_one_shot`. | Become the sole post-finalization successor re-arm owner for synchronous and HTTP paths. |
| `plugins/cron_providers/chronos/_nas_client.py` | Already provisions `job_id` and exact `fire_at`. | Preserve this wire unchanged. |
| `docs/chronos-managed-cron-contract.md` | Already documents callback body `{job_id,fire_at}`. | Make both handlers consume the documented `fire_at`. |
| `gateway/platforms/api_server.py::_handle_cron_fire` | Drops `fire_at` and creates work before a synchronous occurrence claim. | Exact store match and claim precede task creation and 202. |
| `hermes_cli/web_server.py::cron_fire_webhook` | Finds a profile by job ID alone and returns 202 before claim. | Match exactly one profile/store by `(job_id,fire_at)` and claim before task/202. |
| `hermes_cli/cron.py::cron_command` | Produces action status but callers discard it. | Return the canary command status. |
| `hermes_cli/main.py::cmd_cron`, `main` | Discard the nested return value. | Propagate it to process exit. |
| `gateway/status.py::capture_running_build_identity`, `get_running_build_identity` | No callable currently exposes the identity of the loaded scheduler build. | Capture once in memory at gateway start and expose through existing detailed health; write no state file. |
| MarketWatch `enforcement/calibration_cron_watchdog.py` | Directly rewrites stale claim status and successor. | Keep its existing scan/report surface but remove every jobs-file mutation; it becomes read-only alerting. |
Only one tracked MarketWatch watchdog copy exists. There is no tracked
`scripts/enforcement/calibration_cron_watchdog.py`; this ticket shall not create
one or claim a parity obligation that source does not contain.
## 3. Existing jobs lock is the sole mutation boundary
`cron.jobs._jobs_lock` remains the only lock. Its outermost acquisition must:
1. resolve the selected profile's lock/store and acquire the existing RLock;
2. open and acquire the existing cross-process lock within its existing bound;
3. raise `CronJobsLockUnavailable` on open, lock, timeout, or unsupported-lock
   failure before yielding;
4. record exact-store nesting ownership and release only at outermost exit.
A nested call is legal only when its outer scope owns the same store's
cross-process lock. Cross-store nesting and process-local-to-strict upgrade are
rejected. `_save_jobs_unlocked` asserts this ownership. `save_jobs` uses the
same scope and is safely reentrant; it never provides a lock-free public write.
Every reachable `jobs.json` writer uses this boundary:
- `create_job`, `update_job`, `pause_job`, `resume_job`, `trigger_job`, and
  `remove_job`;
- `mark_job_run`, `claim_dispatch`, `heartbeat_run_claim`,
  `set_dispatch_claim_status`, and the new recurring/canary claim owners;
- `advance_next_run` for remaining compatible callers;
- `rewrite_skill_refs`;
- explicit `cron.jobs.repair_jobs_store` formerly hidden inside `load_jobs`;
- `agent/curator_backup.py::_restore_cron_skill_links`;
- `hermes_cli/backup.py::restore_cron_jobs_if_emptied`, which must route
  through a jobs owner rather than `shutil.copy2` over the live file.
Strict serialization does not authorize claim loss. While a tagged recurring
or canary claim is `ACTIVE`, only its exact-claim CAS owner may write result,
repeat, schedule-successor, or claim fields. `remove_job`, `trigger_job`,
`resume_job`, repair, restore, and any context-free `mark_job_run` targeting
that row refuse before writing. `pause_job` may only add the exact pause leaves;
`update_job` and `rewrite_skill_refs` may only merge nonexecution fields into a
fresh row while preserving `id`, schedule, `next_run_at`, repeat, both claim
fields, and every last-result field byte-for-byte. Canary ACTIVE is stricter:
every generic mutation of that row refuses. Every allowed merge must recheck
the same claim immediately before save and must not replace the row with a
caller-supplied or stale whole-row image. Unknown job extensions and unknown
tagged claims are preserved; malformed claim authority blocks mutation.
Lock failure means zero write and zero execution. There is no process-local
write fallback. Read-only functions may read without acquiring an exclusive
lock when they make no correctness decision; claim and canary decisions use a
locked fresh read.

### 3.1 Recurring selection and preserved one-shot preparation

`cron.jobs._get_due_jobs_locked(raw_jobs, now)` remains the coordinator under
the existing strict jobs lock and delegates to two disjoint internal owners:

```text
cron.jobs._select_due_recurring_locked(raw_jobs, now) -> list[dict]
cron.jobs._prepare_due_one_shots_locked(raw_jobs, now) -> tuple[list[dict], bool]
```

`_select_due_recurring_locked` validates and selects recurring rows without
changing the jobs document. It does not repair recurrence, advance
`next_run_at`, create a claim, or save. `_prepare_due_one_shots_locked`
preserves the current one-shot contract under the same lock: it retains
`_recoverable_oneshot_run_at`, `_oneshot_run_claim_ttl_seconds`,
`_job_running_in_this_process`, legacy `run_claim={"at":...,"by":...}`
creation/recovery, finite-run exhaustion removal, and the single final
save/readback when `changed=true`. The coordinator returns the union only
after any one-shot mutation is durably saved and read back. A malformed
recurring row refuses recurring selection and remains for explicit repair; it
cannot suppress or partially save one-shot preparation. Existing one-shot
dispatch, heartbeat, `mark_job_run`, exhaustion, and restart semantics are
unchanged. No jobs schema or one-shot state is added.

The public due path samples `now` once, acquires that same strict lock, calls
the explicit `cron.jobs.repair_jobs_store` owner, then fresh-loads the stored
postimage before calling the coordinator. That repair owner preserves the
current record normalizations plus missing-`next_run_at` and
timezone-migration repairs and performs at most one save/readback; `load_jobs`
and recurring selection never do so implicitly. A stale but otherwise valid
recurring `next_run_at` is not fast-forwarded by selection: it is selected
with its exact stored
`scheduled_for`, and §4.2 atomically persists the successor with the claim.
Thus the split neither drops the current repair cases nor advances a stale
recurrence before its occurrence has durable authority. Tests cover
missing-successor repair, timezone migration, and stale catch-up in addition
to one-shot recovery.
## 4. Recurring occurrence claim
### 4.1 Timestamp and identity
`scheduled_for` and `next_run_after` are exact persisted aware ISO-8601 strings.
Parsing must reject naive, malformed, and non-finite values. Due ordering uses
their UTC instants; identity equality uses the exact stored string. Accepted
offset strings are never rewritten merely to normalize them.
```text
RecurringClaimV1={
  schema:"cron-recurring-claim-v1", claim_id:UUID4, job_id:nonempty string,
  mode:"BUILTIN_RECURRING"|"CHRONOS_RECURRING",
  scheduled_for:aware string, claimed_at:aware string,
  next_run_after:aware string,
  owner_profile:nonempty string, owner_pid:positive integer,
  owner_start_ticks:positive integer,
  status:"ACTIVE"|"NOT_SUBMITTED"|"OPERATOR_SKIPPED",
  terminal_error:string|null
}
```
`ACTIVE` requires null `terminal_error`. `NOT_SUBMITTED` and
`OPERATOR_SKIPPED` require a nonempty
error/reason supplied by their owning transition. That diagnostic is not an
occurrence selector; the existing last-result fields remain the detailed
failure authority. Unknown schema,
status, missing field, wrong type, invalid timestamp, ID mismatch, or
contradictory nullability is malformed authority and blocks automatic
execution or replacement. The object is stored only in the existing job row's
`recurring_claim` field; it creates no new file or table.
### 4.2 Atomic owner
```python
cron.jobs.claim_recurring_occurrence(
    job_id: str, scheduled_for: str,
    *,
    mode: Literal["BUILTIN_RECURRING", "CHRONOS_RECURRING"],
) -> RecurringClaimResultV1
```
Under one strict lock the owner fresh-loads the exact row, samples one UTC
`claimed_at`, derives `owner_profile` from the selected store context, samples
its own PID and birth ticks, and validates:
- the row exists, is enabled, not paused, and has a cron/interval schedule;
- `next_run_at` exactly equals `scheduled_for` and is due;
- no ACTIVE `fire_claim`, `run_claim`, `dispatch_claim`, canary claim, or
  recurring claim exists, and no legacy ambiguous, unknown, or malformed claim
  value exists;
- exactly one `compute_next_run(schedule, claimed_at)` call returns a valid
  successor strictly later than `claimed_at`.
Successor exception, null, malformed value, or nonfuture value returns
`SUCCESSOR_FAILED` with the row byte-identical. On success, one save writes
both `next_run_at=next_run_after` and one `ACTIVE` claim, then returns the exact
postclaim job snapshot. This is the only recurring claim owner.
A terminal `NOT_SUBMITTED` or `OPERATOR_SKIPPED` claim may be replaced only by
a later exact due occurrence.
An `ACTIVE` claim is never aged out, replayed, recovered by a watchdog, or
overwritten by a later occurrence.
### 4.3 Submit and run
Builtin `tick` and Chronos call `claim_recurring_occurrence` before any call to
`ThreadPoolExecutor.submit`, `asyncio.create_task`, or `asyncio.to_thread`.
Only the exact returned postclaim snapshot may be submitted.
The worker's first scheduler action fresh-reads and requires the same
`job_id`, `claim_id`, mode, owner profile/PID/start-ticks, `scheduled_for`, and
`ACTIVE` status. Only then may it
enter the unchanged `run_one_job` route. There is no claimed-to-dispatched CAS
and no start barrier because durable authority already precedes submission.
Only a refusal proved before entering submit/task creation may become
`NOT_SUBMITTED`. Every exception after calling either API, including a
synchronous exception, is ambiguous and remains `ACTIVE`; cancellation, lost
acknowledgement, or process death does too.
Failure to persist `NOT_SUBMITTED` also leaves `ACTIVE` and blocks recurrence.
Exact successful or failed completion applies the existing `mark_job_run`
last-result and repeat effects and removes only the matching `ACTIVE` claim in
one strict transaction. If the unchanged finite-repeat rule removes the job,
job removal and the final result are the existing single terminal cut. A
missing, changed, or foreign claim prevents every finalization write. Existing
finite one-shot
`claim_dispatch`, repeat counting, removal, and restart behavior are otherwise
unchanged.

```python
cron.jobs.mark_recurring_not_submitted(
    job_id, claim_id,
    reason: Literal["CALLER_SHUTTING_DOWN_BEFORE_SUBMIT"],
) -> ClaimDispositionResultV1
cron.jobs.finalize_recurring_occurrence(job_id, claim_id, *, success, error, delivery_error) -> ClaimDispositionResultV1
```
Both are strict exact-claim CAS owners; no generic writer performs either cut.
The sole `NOT_SUBMITTED` reason is reachable only from the existing
pre-API shutdown guard. Pool/task API exceptions, including a synchronous
closed-pool/closed-loop error, are never mapped to it.
### 4.4 Explicit skip of an ambiguous claim
```python
cron.jobs.skip_active_recurring_claim(
    job_id: str, claim_id: str, *, reason: str,
) -> ClaimDispositionResultV1
```
Skip is never automatic. It requires the exact `ACTIVE` claim and proves that
the claim's stored PID/start-ticks no longer identify a live process. It checks
only that exact stored PID and birth directly; it performs no host scan and
does not substitute a configured gateway PID. Identity is never supplied by
the operator. PID reuse, inaccessible or unknown liveness, or a matching owner
refuses and leaves `ACTIVE`. A successful skip is an explicit operator
acceptance that the business outcome is unknown; it never proves nonexecution
or successful cleanup and no product acceptance may consume it as success.
The exact transaction changes only `ACTIVE` to `OPERATOR_SKIPPED`. It does not
execute or replay the occurrence and does not move `next_run_at`, which was
already advanced in the original claim transaction.

### 4.5 Closed internal results and execution context
These are internal return values, not persisted authorities:
```text
RecurringClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"NOT_DUE"|"BLOCKED_ACTIVE"|"MALFORMED"|
         "SUCCESSOR_FAILED"|"LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  claim:RecurringClaimV1|null, job_postimage:object|null, error:string|null
}
ClaimDispositionResultV1={
  status:"APPLIED"|"NOT_FOUND"|"STALE_CLAIM"|"INVALID_TRANSITION"|
         "LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  claim_id:UUID4, error:string|null
}
ExecutionContextV1={
  mode:"RECURRING"|"CANARY", jobs_file_realpath:absolute string,
  job_id:nonempty string, claim_id:UUID4
}
ChronosClaimResultV1={
  status:"CLAIMED"|"GONE"|"DUPLICATE"|"CONFLICT"|"MALFORMED"|
         "LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  job_postimage:object|null, execution_context:ExecutionContextV1|null,
  error:string|null
}
```
Only `CLAIMED` has nonnull `claim` and `job_postimage` and null `error`; every
other claim status has both payloads null and a nonempty error. Only `APPLIED`
has null disposition error; every other disposition has a nonempty error.
`COMMIT_UNKNOWN` never licenses submit, retry, finalization, or execution.
Only Chronos `CLAIMED` has a nonnull postimage and null error. Its context is
nonnull for recurring work and null for the unchanged legacy one-shot route;
every other Chronos status has both payloads null, with null error only for
`GONE` and `DUPLICATE`. No HTTP branch infers a claim from an exception.
## 5. Chronos uses its existing wire
No NAS change is required. Provision remains the documented current request
containing `job_id`, `fire_at`, `agent_callback_url`, and `dedup_key`. Callback
remains authenticated by the current purpose-scoped NAS JWT and body:
```json
{"job_id":"<exact id>","fire_at":"<exact armed timestamp>"}
```
Both ingress handlers strict-parse exactly `job_id` and an aware `fire_at`, then
call the sole shared read-only owner
`cron.scheduler_provider.resolve_chronos_fire_target(job_id, fire_at)`, which
returns one exact `(profile, jobs_file_realpath)` or a closed
gone/conflict/malformed/store-failure classification over configured profile
stores. The resolver first finds rows by exact job ID, then classifies the occurrence. A row
matches the occurrence only when either current
`next_run_at == fire_at` or its tagged recurring claim has exact
`scheduled_for == fire_at`.
- No row with that job ID returns 200 `gone` and executes nothing, preserving
  the existing no-retry behavior for a removed finite job.
- More than one profile/store row matching the exact `(job_id,fire_at)`
  occurrence returns 409 and executes nothing. If no occurrence matches but
  multiple stores contain the job ID, the result is also 409; no arbitrary
  profile is selected.
- One due/current match selects that store and synchronously invokes the atomic
  recurring claim owner.
- An exact ACTIVE, NOT_SUBMITTED, or OPERATOR_SKIPPED duplicate returns 200
  without task creation. When one exact job-ID row exists and no exact claim
  remains, an authenticated callback whose `fire_at` instant is strictly
  earlier than current `next_run_at` returns 200 `already_advanced`; it is
  never replayed because either the atomic claim owner or an explicit later
  schedule mutation already superseded it. Every other occurrence mismatch is
  409.
- A refused/malformed/not-due claim returns 409 without task creation.
- Lock/store failure returns 503 without task creation.
- Only a committed claim followed by successful task creation returns 202.
Invalid authentication returns 401; malformed JSON, extra/missing keys, or an
invalid field returns 400. Every 400/401 branch performs no store search or
mutation.
The claim's due check prevents a valid bearer callback from firing a future
job early. `_find_cron_job_profile(job_id)` is not used for this route.
`CronScheduler.claim_due(job_id, *, fire_at) -> ChronosClaimResultV1` dispatches
by the selected row's
existing schedule class: recurring uses §4 and one-shot uses unchanged
`claim_job_for_fire` semantics with exact `fire_at` revalidation inside that
owner's existing lock and returns that lock's exact postclaim snapshot. This
adds no one-shot state or transition and introduces no unlocked `get_job`
reread. `CronScheduler.run_claimed(result: ChronosClaimResultV1, *, adapters,
loop) -> ManagedRunOutcomeV1` accepts only `CLAIMED`, invokes
`_run_one_job_managed` on its exact postimage, and uses its optional context.
`fire_due(job_id, *, fire_at, adapters, loop)` is exactly `claim_due` followed
by `self.run_claimed` for synchronous callers. HTTP handlers call `claim_due`
synchronously and create a task for that same `run_claimed`; no task
double-claims.

`ChronosCronScheduler.run_claimed` is the sole successor re-arm owner. It
calls `super().run_claimed` and waits for exact-claim finalization. Only when
`finalization_status` is `APPLIED` or `REMOVED` does it freshly read the same
profile/store row. If that row still exists, is enabled, is not paused, is
recurring, and has a valid successor `next_run_at`, it calls existing
`_arm_one_shot(job)` exactly once and returns the unchanged typed managed
outcome. An absent or removed one-shot, disabled, paused, or terminal row also
returns that outcome without arming. Refusal, duplicate claim,
unfinished finalization, or failed finalization performs no re-arm. Re-arm
failure raises `ChronosRearmError(job_id,claim_id,next_run_at)` and is never
returned as successful provider completion; the underlying managed outcome is
retained in the exception for diagnostics. Neither
`fire_due` nor either HTTP handler contains another re-arm site. An exception
before `asyncio.create_task` returns leaves ACTIVE and returns 503; only a
returned task permits 202. Because later task failure cannot change an already
sent 202, each HTTP handler attaches the same exact done callback in
`cron.scheduler_provider.observe_chronos_task(task, *, job_id, fire_at) ->
None`, which registers one callback. That callback calls `task.result()`
exactly once and logs cancellation, `ChronosRearmError` (including its
retained managed outcome), or any other task exception; it creates no task,
claim, re-arm, retry, or state. Synchronous callers receive the exception
directly. No background exception is left unobserved or represented as a
synchronous HTTP result.
This changes no NAS wire or external authority.
## 6. Pause-preserving canary
Public grammar:
```text
hermes cron canary <job-id>
hermes cron skip-active-claim <job-id> --claim-id <UUID4> --reason <text>
```
No digest argument is required. Under the strict jobs lock,
`claim_paused_job_canary` fresh-loads the exact current row and requires:
- `enabled` is false and `state` is exactly `paused`;
- the schedule and `next_run_at` are valid;
- no active fire, run, dispatch, recurring, or canary claim exists;
- the complete row is valid.
The exact persisted shape is:
```text
CanaryClaimV1={
  schema:"cron-paused-canary-claim-v1", claim_id:UUID4,
  job_id:nonempty string, owner_profile:nonempty string,
  owner_pid:positive integer, owner_start_ticks:positive integer,
  status:"ACTIVE"|"OPERATOR_SKIPPED", operator_reason:string|null,
  captured_job:object
}
CanaryClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"NOT_PAUSED"|"BLOCKED"|"MALFORMED"|
         "LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  claim:CanaryClaimV1|null, job_postimage:object|null, error:string|null
}
```
`ACTIVE` requires null `operator_reason`; `OPERATOR_SKIPPED` requires a
nonempty reason. Only `CLAIMED` has nonnull claim/postimage and null error;
every other result has null payloads and a nonempty error. It stores in the
existing `fire_claim` field a UUID4 canary claim containing
the complete exact preclaim job object. No Unicode normalization, numeric
coercion, field allow-list, or hash is used. JSON-native values are compared by
the sole canary-local owner `cron.jobs._canary_json_equal(left, right) -> bool`;
this is not a public codec.
The comparator requires identical Python JSON scalar types and values, exact
Unicode code points, identical map key sets, list order, and finite-float
`float.hex()` values, so booleans do not equal integers and `-0.0` does not
equal `0.0`; the strict JSON reader rejects NaN and infinities.
The canary invokes `_run_one_job_managed` through the same complete execution
route as the existing `run_one_job` ABI and consumes its typed outcome. It never calls
`trigger_job`, `resume_job`, `advance_next_run`, or recurring/one-shot claim
owners. Before finalization it compares the current row, excluding only its
own canary claim and its authorized last-result leaves, with the captured row.
It may update only `last_run_at`, `last_status`, `last_error`, and
`last_delivery_error`, then remove its exact claim. It preserves enabled,
state, pause fields, schedule, `next_run_at`, repeat, prompt, script, model,
provider, workdir, toolsets, delivery, origin, and every unknown extension.
A mismatch leaves the current row and exact claim intact and returns failure.
Death or uncertainty with an ACTIVE canary never causes automatic replay. The
same public `skip-active-claim` command dispatches by the exact tagged claim
schema: for a canary it applies the §4.4 stored-PID check and changes only its
matching ACTIVE status/reason to `OPERATOR_SKIPPED`. A later canary may replace
that terminal tagged claim while atomically treating its removal as an owned
operational-field change; it captures and later preserves every other current
field. After the explicit skip, `resume_job` or `trigger_job` may likewise
consume that exact terminal canary claim under lock before performing its
existing operation; neither may consume ACTIVE, unknown, or malformed claim
state. Unknown or malformed `fire_claim` values refuse.

```python
cron.jobs.claim_paused_job_canary(job_id) -> CanaryClaimResultV1
cron.jobs.finalize_paused_job_canary(job_id, claim_id, *, success, error, delivery_error) -> ClaimDispositionResultV1
```
The canary claim owner derives profile, PID, and birth ticks itself exactly as
the recurring owner does; no CLI argument can supply execution identity.
## 7. Pre-run, managed outcome, and legacy ABI
The internal source of execution truth is:
```text
cron.scheduler._run_one_job_managed(
  job, *, adapters=None, loop=None, verbose=False,
  execution_context:ExecutionContextV1|null=None
) -> ManagedRunOutcomeV1
ManagedRunOutcomeV1={
  schema:"cron-managed-run-outcome-v1", job_id:nonempty string,
  execution_context:ExecutionContextV1|null,
  admitted:bool, processed:bool,
  pre_run_status:"NOT_CONFIGURED"|"SUCCESS"|"FAILED",
  agent_status:"NOT_APPLICABLE"|"NOT_RUN"|"SUCCESS"|"FAILED",
  output_status:"NOT_REQUESTED"|"SAVED"|"FAILED",
  output_path:absolute string|null,
  delivery_status:"NOT_CONFIGURED"|"SUPPRESSED"|"DELIVERED"|"FAILED",
  delivery_error:string|null,
  finalization_status:"NOT_ATTEMPTED"|"APPLIED"|"REMOVED"|"FAILED",
  error:string|null,
  overall:"REFUSED"|"LEGACY_ALREADY_HANDLED"|"PRE_RUN_FAILED"|
          "AGENT_FAILED"|"OUTPUT_FAILED"|
          "DELIVERY_FAILED"|"FINALIZATION_FAILED"|
          "SUCCESS"
}
```
This value is immutable and in-process only; it is not a file or durable
authority. `output_path` is nonnull exactly for `SAVED`; `delivery_error` is
nonnull exactly for delivery `FAILED`; `error` is null exactly for `SUCCESS`.
`admitted=false` requires `processed=false`, neutral/not-attempted stage
values, and `overall=REFUSED`, except for the one source-existing legacy
no-op: when `claim_dispatch` proves a `None`-context one-shot was already
handled or removed, the exact tuple is `admitted=false`, `processed=true`, all
stages neutral/not-attempted,
`error="legacy one-shot already handled or removed"`, and
`overall=LEGACY_ALREADY_HANDLED`. That variant is illegal for recurring or
canary context and performs no effect or finalization. `processed` preserves
the legacy boolean ABI exactly: true includes that historical handled no-op
and a route that processed the job even if its business result failed; false
means admission or execution machinery prevented processing in every other
case.

Managed recurring and canary owners pass exact `ExecutionContextV1` to this
callable. `None` preserves the complete legacy one-shot/manual path without a
fabricated claim ID. Running, cleanup, quarantine, interruption, output,
delivery, and finalization keys for managed calls are
`(jobs_file_realpath,job_id,mode,claim_id)`. The callable selects exactly one
finalizer: recurring invokes `finalize_recurring_occurrence`, canary invokes
`finalize_paused_job_canary`, and `None` invokes unchanged `mark_job_run`.
A managed context never invokes `claim_dispatch` or a second finalizer.
Canary bypasses `_clear_cleanup_fire_claim`; recurring cannot invoke job-ID-only
claim cleanup.
For a configured script, `run_job` calls the existing supervised script path
before importing or constructing `AIAgent`, opening `SessionDB`, resolving a
model/provider, or building an agent prompt. Script failure returns through
the existing run ABI as failure. Its diagnostic output may still be saved and
delivered, but delivery success cannot change run failure to success.
SYS-1030 does not reinterpret SYS-666 or make generic canary PASS prove a
MarketWatch report. SYS-1029 performs its own product-output acceptance.
Pre-run FAILED requires agent NOT_RUN. Agent NOT_APPLICABLE is
legal only for the existing script-only/no-agent route after pre-run success.
NOT_CONFIGURED, NOT_APPLICABLE, NOT_REQUESTED, and SUPPRESSED are neutral, not
failures. Any FAILED stage makes the command nonzero; delivery success cannot
mask an earlier failure. `LEGACY_ALREADY_HANDLED` is selected only by its
closed tuple above and does not participate in failure dominance. Failure
dominance is refusal, finalization, output,
pre-run, agent, delivery, then success. Every stage is
retained even when a higher-priority failure determines `overall`. Invalid or
contradictory tuples are rejected and never finalized as success.

The public compatibility ABI remains source-exact:
```text
cron.scheduler.run_one_job(job, *, adapters=None, loop=None, verbose=False) -> bool
```
It calls `_run_one_job_managed(..., execution_context=None)` and returns only
`outcome.processed`. Existing callers therefore retain their current meaning:
true means processing completed, not that the job business result succeeded.
Managed recurrence, the canary, and Chronos consume the typed internal result.
The canary maps only `overall=SUCCESS` to exit 0; Chronos consumes the outcome
before applying its sole successor re-arm rule in §5 and does not mutate it.
The canary command reports one compact result containing job ID, claim ID,
run success, output path or error, delivery error if any, final last status,
and preservation/finalization outcome. Exit behavior is:
- `0`: the existing route completed successfully and preservation finalized;
- `1`: attempted route, output, delivery, or finalization failed;
- `2`: parser error or canary refused before execution.
The skip command reports its exact disposition and is zero only for a stored
OPERATOR_SKIPPED transition. `cron_command` returns either code, `cmd_cron`
returns it, `main` returns it, and
the module entry point exits with it. No layer converts a nonzero result to
success or prints a second authoritative status.
## 8. Deployment and SYS-1029 handoff
1. Use isolated homes below `/home/linux/.hermes/test/sys1030/`, never production jobs or delivery.
2. Deploy the single watchdog's read-only-alerting change before claim
   activation: it may report stale legacy claims but performs no jobs-file
   mutation. There is no retirement alternative left for the implementer to
   choose.
3. Fresh-fetch both remotes; each reviewed candidate must be merge-commit ancestor.
4. Preflight the live store read-only. Require builtin scheduling, AMC and
   Daily still paused, CCI/BB/MACD still enabled and scheduled, no malformed or
   active claim, and every enabled target safely beyond the bounded deployment
   verification window. Otherwise defer deployment; do not pause a job.
5. Deploy the clean reviewed merge normally and restart the configured gateway.
6. `gateway.run.GatewayRunner.start` calls
   `gateway.status.capture_running_build_identity(profile)` once after profile
   selection and before readiness or cron-provider startup. It returns and
   retains in process memory only:
   ```text
   RunningBuildIdentityV1={
     schema:"hermes-running-build-identity-v1", profile:nonempty string,
     pid:positive integer, process_start_ticks:positive integer,
     executable_realpath:absolute string,
     scheduler_module_realpath:absolute string,
     checkout_root_realpath:absolute string,
     git_oid:40 lowercase hexadecimal characters
   }
   RunningBuildIdentityResultV1={
     schema:"hermes-running-build-identity-result-v1",
     status:"AVAILABLE"|"UNAVAILABLE",
     identity:RunningBuildIdentityV1|null,
     reason:null|"PROCESS_ID_UNAVAILABLE"|"EXECUTABLE_UNAVAILABLE"|
       "SCHEDULER_MODULE_UNAVAILABLE"|"CHECKOUT_UNAVAILABLE"|
       "AMBIGUOUS_CHECKOUT"|"GIT_TIMEOUT"|"GIT_FAILED"|"INVALID_GIT_OID"
   }
   ```
   `AVAILABLE` requires a nonnull identity and null reason; `UNAVAILABLE`
   requires null identity and exactly one listed reason.
   Capture reads `/proc/self/stat`, `/proc/self/exe`, and the loaded
   `cron.scheduler.__file__`. It resolves the checkout only by
   `git -C <scheduler-module-parent> rev-parse --show-toplevel`, requires one
   absolute real path containing the scheduler module, then runs
   `git -C <checkout> rev-parse --verify HEAD^{commit}`. Both commands use
   exact environment
   `{PATH:os.defpath,LC_ALL:"C",LANG:"C",GIT_OPTIONAL_LOCKS:"0"}`, stdin
   `DEVNULL`, and timeout 5.0 seconds. The first result is exactly one absolute
   path line; the second is exactly one 40-lowercase-hex line.
   On the controlled
   Linux deployment, an unavailable `/proc` identity, executable/module path,
   Git checkout, or OID yields `UNAVAILABLE`. It does not make Hermes generally
   require a Git checkout or Linux `/proc` merely to start; instead it blocks
   this ticket's deployment acceptance. Capture is write-once: a later call
   for the same profile returns the retained result without reading process,
   filesystem, or Git state, while a different-profile call raises
   `RuntimeError("running build identity already captured for a different profile")`
   without replacing it. A first
   `UNAVAILABLE` result remains unavailable until process restart.
7. `gateway.status.get_running_build_identity() -> RunningBuildIdentityResultV1`
   returns the captured result. Existing authenticated `GET /health/detailed`
   exposes it as `running_build_identity` without changing the endpoint's
   existing availability status. Read-only deployment verification treats
   `UNAVAILABLE` as failure rather than omitting or reconstructing it and
   requires candidate ancestor of merge and captured running OID = deployed
   HEAD = freshly fetched merge, with exact profile/PID/start/executable/module
   and checkout path. Later checkout movement does not change the captured
   value. No OID, READY, digest, or identity state file is written.
8. Re-read five product rows unchanged; invoke no canary, trigger, pause, resume, or product script.
9. Hand the exact merge/running evidence and public canary contract to
   SYS-1029. SYS-1029 independently verifies it, runs product canaries and
   observations, and alone decides product-job resume.
Current production state is an observation, not a desired-state manifest:
only `9e059716170c` and `20c3fd791e82` are paused; `cci_precompute_runner`,
`bb_precompute_runner`, and `c7033e9248d1` are enabled and scheduled.
## 9. Exact edit and proof inventory
Hermes production edits: `cron/jobs.py`, `cron/scheduler.py`,
`cron/scheduler_provider.py`, `plugins/cron_providers/chronos/__init__.py`,
both cron-fire handlers, `hermes_cli/subcommands/cron.py`, `hermes_cli/cron.py`,
`hermes_cli/main.py`, `tools/cronjob_tools.py`, `gateway/run.py`,
`gateway/status.py`, `gateway/platforms/api_server.py`,
`agent/curator_backup.py`, `hermes_cli/backup.py`, and the Chronos contract doc.
The NAS provider client and token verifier remain byte-unchanged.
MarketWatch production edit: only
`enforcement/calibration_cron_watchdog.py`; no shipped twin is created.
Required isolated proofs include:
- `tests/cron/test_jobs.py::test_due_selection_is_read_only_for_recurring_and_preserves_locked_one_shot_preparation`
  proves recurring selection byte-read-only while one-shot legacy claim
  recovery, exhaustion removal, save/readback, dispatch, and restart remain
  unchanged;
- two processes contend against every jobs writer; loser writes zero bytes;
- nested same-store write works, cross-store nesting refuses, public `save_jobs`
  acquires strict ownership, and `_save_jobs_unlocked` without it refuses;
- successor null, exception, malformed, and nonfuture leave the row unchanged;
- claim save occurs before submit and before Chronos task creation/202;
- a proved pre-API refusal becomes `NOT_SUBMITTED`; enqueue-then-raise and every
  task/submit API exception remain `ACTIVE` and block the next occurrence;
- exact completion cannot clear a foreign or later claim;
- operator skip refuses for live/equal, reused, inaccessible, or unknown stored
  PID identity; dead/replaced applies only as an explicit ambiguous-outcome
  operator acceptance and never as proof of nonexecution or cleanup;
- ACTIVE claim protection rejects remove/trigger/resume/context-free completion,
  permits only the specified pause/nonexecution merges, and catches a claim
  change at the immediate pre-save recheck;
- Chronos exact `(job_id,fire_at)` has zero/one/multiple profile fixtures;
- duplicate callback produces no second task;
- `tests/cron/test_scheduler_provider.py::test_chronos_run_claimed_rearms_exactly_once_after_finalization`
  uses a mocked NAS/`_arm_one_shot` boundary to prove synchronous and HTTP
  paths use the same owner, re-arm the exact successor once after exact
  finalization, and re-arm zero times for refusal, duplicate, or failed
  finalization; re-arm failure raises `ChronosRearmError` with the retained
  managed outcome, and the HTTP done callback consumes/logs the exception
  exactly once without retrying or changing the already returned 202;
- completed, failed, skipped, not-submitted, removed finite, and older-retained
  Chronos callbacks each take their exact no-task acknowledgement branch;
- canary preserves every field and unknown extension and constructs no agent
  after pre-run failure;
- command exit survives parser through process boundary;
- `tests/cron/test_scheduler.py::test_managed_run_outcome_failure_dominance_and_legacy_bool_wrapper`
  exercises every legal stage/null combination and failure dominance,
  including the source-existing `LEGACY_ALREADY_HANDLED` true no-op; legacy
  `run_one_job` returns `processed` while canary and Chronos consume `overall`;
- legacy one-shot success, failure, exhaustion, and restart remain unchanged;
- MarketWatch watchdog fixtures prove stale-legacy alerts while the input
  `jobs.json` remains byte-identical and tagged recurring claims are ignored;
- `tests/gateway/test_status.py::test_running_build_identity_is_captured_once_from_loaded_scheduler`
  checks PID/start/executable/module/checkout/OID, moving-checkout stability,
  different-profile recapture refusal without replacement, typed unavailable
  results for each missing Linux/Git witness, ordinary startup without a Git
  checkout, and zero file writes;
- `tests/gateway/test_api_server.py::test_health_detailed_returns_in_memory_running_build_identity`
  checks the exact authenticated available/unavailable schema without changing
  the endpoint's existing health status;
- `tests/gateway/test_status_command.py::test_deployment_identity_rejects_each_mismatch`
  rejects each profile/PID/start/executable/path/OID mismatch.
Tests must be self-contained below `/home/linux/.hermes/test/sys1030/`, use no
network, live gateway, production store, live delivery, `/tmp`, systemd, new
xdist control, new mutex, process scan, or product script. They run through the
repository-required wrapper unchanged.
## 10. R2 disposition
| R2 | R3 disposition |
|---|---|
| 01 | Retained: strict existing-lock fixed point over every writer. |
| 02 | Removed correction-induced codec: exact captured JSON object and type-strict comparison need no digest. |
| 03 | Retained: validate successor before atomic mutation. |
| 04 | Reduced: use documented existing `{job_id,fire_at}` wire; no NAS repository/version invention. |
| 05 | Retained: claim before task creation and 202. |
| 06 | Retained: `ACTIVE` blocks every later same-job occurrence. |
| 07 | Superseded safely: claim commit precedes submit, so no post-submit CAS or start barrier exists. |
| 08 | Reduced: atomic exact paused-row snapshot; caller digest is not an issue requirement. |
| 09 | Retained: exact claim context reaches cleanup, interruption, and finalization. |
| 10 | Retained without a new run ABI: pre-run failure dominates existing route result. |
| 11 | Retained compactly: saved output, suppression/no delivery, and delivery error stay distinguishable. |
| 12 | Preserved by non-redesign: finite removal is a legal existing terminal. |
| 13 | Returned to SYS-1029 product ownership; generic canary does not certify SYS-666 completeness. |
| 14 | Retained: malformed/unknown claims refuse before execution. |
| 15 | Retained: one command result and exact shell exit propagation. |
| 16 | Retained: configured running-process identity, not checkout-only evidence. |
| 17 | Corrected census: disposition the one real watchdog; do not invent a twin. |
| 18 | Retained: fresh canonical-remote ancestry immediately before deployment proof. |
| 19 | Removed: five-job mutation/resume contradicts live state and belongs to SYS-1029. |
## 11. Five-question authority gate
Every normative operation must answer all five questions before authorship:
1. **Owner:** Is there exactly one named source callable that decides it?
2. **Atomicity:** Is every jobs mutation inside the existing strict lock and
   does failure preserve exact prior bytes?
3. **Cut:** For every pre-save, post-save, pre-submit, accepted/uncertain submit,
   worker-start, effect, and finalization cut, is the next behavior unique?
4. **Caller/consumer:** Are builtin, Chronos, CLI, dashboard, API, shutdown,
   backup, curator, and MarketWatch writer/reader edges explicitly handled?
5. **Proof/deploy:** Is there a mutation-sensitive isolated test and a
   read-only deployment check that does not execute or resume product work?
Any `no`, undefined noun, silent fallback, ambiguous overwrite, product-state
mutation, or invented external authority blocks the candidate.
## 12. Round-3 release rule
The frozen comparison remains `19 -> Z<=2`, a reduction of at least 17 defects
and at least 89.5 percent. No P0 recurrence, new authority boundary, claim
replay, lock degradation, product mutation, or false success is allowed.
Loop 1 remains specification-only. Loop 2 may implement only after one exact
candidate receives all required independent approvals. Tests remain NOT RUN in
this document. SYS-1030 closes only after its reviewed implementation is
merged, deployed, and the configured running Hermes identity is proven. That
event unblocks—but does not perform—SYS-1029 product canaries and resume.
