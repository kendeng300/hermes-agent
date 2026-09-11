# SYS-1030 — R3 proposed technical specification
Status: proposed Loop-1 correction; implementation and tests NOT RUN
Issue: MarketWatch #1030, prerequisite for SYS-1029
Baseline source reviewed: Hermes `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`
MarketWatch source reviewed: `origin/master` at
`2c37e4b0c261c911323d2caaeed4741ae73f2884`
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
| `cron/scheduler.py::_submit_with_guard`, `close_cron_admission_for_shutdown` | In-memory identity is only `job_id`, and shutdown does not linearize against submit/start. | Use the existing `_running_lock` to close admission and snapshot exact contexts before drain or cleanup; no later unadmitted business start is possible. |
| `cron/scheduler.py::run_one_job` | Calls existing one-shot `claim_dispatch`, then run/output/delivery/finalization. | Preserve its exact boolean ABI and one-shot behavior; factor the same route into `_run_one_job_managed`, which accepts recurring/canary context and returns the typed outcome. |
| `cron/scheduler.py::run_job` | Agent construction can follow failed script output. | A failed pre-run returns failure before agent/session/provider work. |
| `cron/scheduler.py::_pause_job_for_unverified_script_cleanup`, `_clear_cleanup_fire_claim` | Cleanup quarantine is keyed/cleared by job ID and cannot conserve a future canary claim. | Use the exact managed context: INCOMPLETE/UNKNOWN persist pause diagnostics while retaining ACTIVE; canary never reaches generic clear/finalize/retry. |
| `cron/scheduler.py::get_running_job_ids`, `mark_running_jobs_interrupted` | Project only job ID and resample after the global process kill. | Keep the job-ID view only for compatibility; shutdown snapshots exact contexts immediately before each kill and interruption consumes only that immutable snapshot. |
| `cron/scheduler_provider.py::CronScheduler.fire_due` | Claims Chronos by job ID without scheduled time. | Accept and claim exact `fire_at`. |
| `plugins/cron_providers/chronos/__init__.py::ChronosCronScheduler.run_claimed` | `fire_due` currently owns successor `_arm_one_shot`. | Become the sole post-finalization successor re-arm owner for synchronous and HTTP paths. |
| `plugins/cron_providers/chronos/_nas_client.py` | Already provisions `job_id` and exact `fire_at`. | Preserve this wire unchanged. |
| `docs/chronos-managed-cron-contract.md` | Already documents callback body `{job_id,fire_at}`. | Make both handlers consume the documented `fire_at`. |
| `gateway/platforms/api_server.py::_handle_cron_fire` | Drops `fire_at` and creates work before a synchronous occurrence claim. | Exact store match and claim precede task creation and 202. |
| `hermes_cli/web_server.py::cron_fire_webhook` | Finds a profile by job ID alone and returns 202 before claim. | Match exactly one profile/store by `(job_id,fire_at)` and claim before task/202. |
| `hermes_cli/cron.py::cron_command` | Produces action status but callers discard it. | Return the canary command status. |
| `hermes_cli/main.py::cmd_cron`, `main` | Discard the nested return value. | Propagate it to process exit. |
| `cron/scheduler.py::_capture_loaded_scheduler_build_identity`, `gateway.status.capture_running_build_identity`, `read_live_running_build_identity` | No mandatory production verifier binds loaded scheduler bytes to the live gateway; optional detailed health and current `HEAD` are insufficient. | Capture the clean tracked loaded module once, transport it through existing runtime status, and verify live PID/start/executable/profile/OID through an always-available CLI before activation. |
| `agent/curator_backup.py::_restore_cron_skill_links` | Parses backup outside the lock, then fresh-loads and merges `skill`/`skills` under `_jobs_lock`. | Retain the field-only merge but publish through the sole conservation owner and fail closed when the strict lock is unavailable. |
| `hermes_cli/backup.py::{run_import,restore_quick_snapshot,restore_cron_jobs_if_emptied}` | The import writes archive members with `open(...,"wb")`; both restore paths can `copy2` a stale whole `cron/jobs.json` without the jobs lock. | Route every jobs member through the exact locked replace-or-refuse contract in §3.1; no raw live-file copy remains. |
| MarketWatch `utilities/market_holiday_manager.py` and `scripts/utilities/market_holiday_manager.py` | Both byte-identical tracked copies load before locking, lock `jobs.lock` rather than `.jobs.lock`, use a shared `jobs.tmp`, and replace the whole document. | Remove direct storage writes; invoke `cron.jobs.pause_job` or `cron.jobs.resume_job` once per selected ID and report any partial refusal truthfully. |
| MarketWatch `utilities/holiday_watchdog.py` and `scripts/utilities/holiday_watchdog.py` | Both byte-identical tracked copies have the same pre-lock read, wrong lock name, shared temp, and whole-document replace. | Preserve detection and alerting, but remove automatic mutation. |
| MarketWatch `enforcement/calibration_cron_watchdog.py` | Loads before its save lock; the save locks `.jobs.lock` only when the lock file already exists and otherwise degrades, then replaces the whole document. | Keep its existing scan/report surface but remove every jobs-file mutation; it becomes read-only alerting. |
| MarketWatch `utilities/_extract_backup.py` and `scripts/utilities/_extract_backup.py` | The generic fallback extractor opens every archive member destination `wb`, including `cron/jobs.json`, with no jobs lock. | Pre-scan normalized members and refuse the entire fallback extraction if it contains `cron/jobs.json`; the normal restore path uses corrected `hermes import`. |
The root and shipped holiday-manager, holiday-watchdog, and extractor pairs are
tracked and byte-identical at the pinned MarketWatch ref. Calibration has only
the tracked `enforcement/calibration_cron_watchdog.py`; there is no tracked
`scripts/enforcement/calibration_cron_watchdog.py`, and this ticket creates no
such twin. The byte-identical `restore.sh` and `scripts/restore.sh` are
transitive callers of the fallback extractor, not independent storage owners.
## 3. Existing jobs lock is the sole mutation boundary
`cron.jobs._commit_jobs_mutation` is the sole live-document conservation and
publication owner. It adds no lock or store: it acquires the existing
`cron.jobs._jobs_lock`, fresh-loads the selected profile's `jobs.json`, applies
one named semantic mutation to that fresh object, validates the ACTIVE rules
below, writes through `_save_jobs_unlocked`, and fresh-readback compares the
complete postimage before returning. A refusal or exception before verified
readback returns failure and does not authorize execution. No other callable
opens the live jobs file for writing, copies over it, or calls
`_save_jobs_unlocked`.

Its internal signature is
`_commit_jobs_mutation(mutator, *, active_authority)`, where `mutator` receives
only the fresh in-lock job list and returns `(postimage, result)`, and
`active_authority` is exactly `PRESERVE`, `CLAIM_CREATE`, `CLAIM_FINALIZE`, or
`OPERATOR_SKIP`. The owner rejects any changed ACTIVE leaf not permitted by
that authority before save. It returns `result` only after full postimage
readback; business APIs retain their existing public return types.

`cron.jobs._jobs_lock` remains the only lock. Its outermost acquisition must:
1. resolve the selected profile's lock/store and acquire the existing RLock;
2. open and acquire the existing cross-process lock within its existing bound;
3. raise `CronJobsLockUnavailable` on open, lock, timeout, or unsupported-lock
   failure before yielding;
4. record exact-store nesting ownership and release only at outermost exit.
A nested call is legal only when its outer scope owns the same store's
cross-process lock. Cross-store nesting and process-local-to-strict upgrade are
rejected. `_save_jobs_unlocked` asserts this ownership. The compatibility
signature is `save_jobs(jobs, *, expected_preimage=_MISSING)`. A caller already
nested in the same-store strict lock may save its in-lock fresh mutation; an
outermost call must supply the complete document it previously read as
`expected_preimage`, which is compared type-strictly with the fresh in-lock
document before replacement. An outermost call without it or an unequal
preimage refuses. It never provides a lock-free or blind full-document write.
Every reachable `jobs.json` mutation uses this boundary:
- `create_job`, `update_job`, `pause_job`, `resume_job`, `trigger_job`, and
  `remove_job`;
- `mark_job_run`, `claim_dispatch`, `heartbeat_run_claim`,
  `set_dispatch_claim_status`, and the new recurring/canary claim owners;
- `advance_next_run` for remaining compatible callers;
- `rewrite_skill_refs`;
- explicit `cron.jobs.repair_jobs_store` formerly hidden inside `load_jobs`;
- `agent/curator_backup.py::_restore_cron_skill_links`;
- `hermes_cli/backup.py::{run_import,restore_quick_snapshot,
  restore_cron_jobs_if_emptied}`, each of which routes a jobs member through
  `_commit_jobs_mutation` rather than opening or copying over the live file.
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

### 3.0 Source-complete writer and caller fixed point

The fixed point is derived from the two pinned Git trees, not from this
proposal's former inventory. The three Hermes production files that contain a
live-store mutation path are exactly:

1. `cron/jobs.py`: `load_jobs`'s implicit repairs, `save_jobs`, `create_job`,
   `update_job`, `pause_job`, `resume_job`, `trigger_job`, `remove_job`,
   `mark_job_run`, `claim_dispatch`, `heartbeat_run_claim`, `advance_next_run`,
   `set_dispatch_claim_status`, `claim_job_for_fire`,
   `get_due_jobs/_get_due_jobs_locked`, and `rewrite_skill_refs`;
2. `agent/curator_backup.py::_restore_cron_skill_links`, called by `rollback`;
3. `hermes_cli/backup.py::{run_import,restore_quick_snapshot,
   restore_cron_jobs_if_emptied}`.

The seven MarketWatch production files that directly reach a live-file write
at the pinned ref are exactly:

1. `utilities/market_holiday_manager.py`;
2. `scripts/utilities/market_holiday_manager.py`;
3. `utilities/holiday_watchdog.py`;
4. `scripts/utilities/holiday_watchdog.py`;
5. `enforcement/calibration_cron_watchdog.py`;
6. `utilities/_extract_backup.py`;
7. `scripts/utilities/_extract_backup.py`.

The transitive Hermes caller closure is: `cron/scheduler.py::{tick,
run_one_job,_pause_job_for_unverified_script_cleanup,
_clear_cleanup_fire_claim}`; `cron/scheduler_provider.py::CronScheduler.fire_due`;
Chronos `fire_due/run_claimed`; `tools/cronjob_tools.py`; `hermes_cli/cron.py`;
`hermes_cli/console_engine.py`; the profile dashboard in
`hermes_cli/web_server.py`; the jobs REST handlers in
`gateway/platforms/api_server.py`; `cron/suggestions.py::accept_suggestion`;
`hermes_cli/blueprint_cmd.py`; `tools/blueprints.py`; the curator review and
rollback routes; `hermes_cli/main.py` import/update routes;
`hermes_cli/cli_commands_mixin.py::_handle_snapshot_command`; the dashboard
import/upload routes; and the public reexports in `cron/__init__.py`. Each is a
caller of the one conservation owner, never another publication authority.

The transitive MarketWatch caller closure is the `main` and circuit-breaker
paths in both holiday modules, calibration watchdog `main`, and root/shipped
`restore.sh`, whose normal branch calls `hermes import` and whose no-Hermes
fallback calls `_extract_backup.py`. `recovery/restore_crons_from_manifest.py`
and `scripts/recovery/restore_crons_from_manifest.py` are tracked readers: even
`--apply` only prints proposed `cronjob(action='create',...)` calls. Hermes
`cron.jobs._restore_from_cron_state` is also read-only and has no caller at the
pinned tree. Snapshot creation, curator backup capture, dump/status, MarketWatch
gates/monitors/watchers, backup orchestrators, and DR archive validation write
only non-live artifacts or read the store; they remain outside the writer set.

### 3.1 Import and restore are locked replace-or-refuse

`run_import`, quick-snapshot restore, and emptied-store recovery parse and
validate the complete candidate jobs member before entering the strict
mutation owner. The candidate must be a wrapper with a list-valued `jobs` or a
legacy bare list; every element must be an object with one unique nonempty
string `id`. Under the lock, the owner fresh-loads and validates the complete
live document. `run_import` and quick-snapshot restore retain their existing
whole-member overwrite semantics for the jobs list: if the authority checks
below pass, their postimage is the exact validated candidate jobs list,
including candidate row order, changed inactive rows, and deletion of inactive
live-only rows, serialized once through the existing Hermes jobs wrapper and
`updated_at` format by `_save_jobs_unlocked`.
Emptied-store recovery retains its current narrow rule: it recomputes both
counts from the fresh in-lock live document and the validated snapshot, and
replaces with that exact candidate jobs list only when the snapshot has strictly more
jobs. Missing, unreadable, malformed, equal-count, or lower-count input is the
existing no-action result. No count or replacement decision made before lock
acquisition is reused.

All three paths refuse the entire jobs-member mutation if replacement would
delete or change any live row carrying an `ACTIVE` tagged recurring/canary
claim, any current legacy `fire_claim`, `run_claim`, or `dispatch_claim`, or an
unknown/malformed claim authority. A candidate row containing any such claim
also refuses unless it is recursively type-strict equal to the corresponding
live row; backup bytes never manufacture, change, or clear execution
authority. Duplicate IDs, malformed rows/documents, and unknown top-level
shapes refuse before save. Thus inactive backup state keeps the source-existing
replace behavior, while every live execution authority is conserved or the
whole jobs member is refused.

“Exactly equal” here is recursive type-strict JSON equality: null, bool,
number, string, array, and object types cannot substitute for one another;
array order and complete object key membership/value equality are required.
This comparison does not define a serialization, digest, or new codec.

Only a fully validated replacement postimage is atomically saved and read back.
There is no pre-lock job-count decision, unguarded snapshot replacement,
partial member write, or fallback copy. Other backup members retain their existing behavior,
but a jobs-member refusal makes the command/report nonzero and explicit. The
MarketWatch no-Hermes extractor cannot invoke this owner, so it pre-scans the
archive and refuses the whole extraction before writing any member whenever a
normalized member path is `cron/jobs.json`.

### 3.2 Recurring selection and preserved one-shot preparation

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
Only the exact returned postclaim snapshot may be admitted. The sole process-
local owner is:
```python
cron.scheduler.admit_and_start_managed_execution(
    context: ExecutionContextV1, job_postimage: object, starter: Callable,
) -> CronAdmissionResultV1
```
It uses the existing `_running_lock`; it adds no mutex or durable authority.
While holding that lock it validates the complete context/postimage relation.
If admission is `CLOSED`, it does not call `starter` and returns
`PRE_API_REFUSED`. If admission is `OPEN`, it registers the exact context and
postimage before entering `starter`, then calls the submit/create-task or
inline-start primitive before releasing the lock. A returned handle/token is
`STARTED`. An exception after API entry is `SUBMIT_UNKNOWN`: the durable claim
remains `ACTIVE`, the exact registration remains until its wrapper removes it
or the process exits, and no caller calls it `NOT_SUBMITTED`. Registration
precedes the worker's first business action; the wrapper removes only its
byte-equal context in `finally`.

The gateway's first shutdown operation is:
```python
cron.scheduler.close_cron_admission_for_shutdown()
    -> tuple[ExecutionContextV1, ...]
cron.scheduler.snapshot_running_managed_executions()
    -> tuple[ExecutionContextV1, ...]
cron.scheduler.mark_running_jobs_interrupted(
    reason: str, *, identities: tuple[ExecutionContextV1, ...],
) -> tuple[ExecutionContextV1, ...]
```
`close_cron_admission_for_shutdown` takes `_running_lock`, changes the one
process-lifetime admission value `OPEN -> CLOSED`, and returns a sorted
immutable snapshot. It is called at the start of
`gateway.run.GatewayRunner.stop::_stop_impl`, before notification, drain, or
any cleanup. Admission is never reopened in that process. Close winning the
lock means no starter/API/business action occurs; a recurring claim then uses
the exact `mark_recurring_not_submitted` CAS. Admission winning means its exact
context is necessarily in the shutdown snapshot and may start only as an
already-admitted member of that snapshot.

Drain tests current exact contexts, not a count or job-ID set. Immediately
before each existing `process_registry.kill_all()` call, shutdown takes one
fresh immutable exact-context snapshot; after the kill it passes that same
snapshot to `mark_running_jobs_interrupted` and never resamples. Thus an
occurrence leaving after the snapshot or a later occurrence cannot be marked
for another cut. The compatibility `get_running_job_ids()` is only a projection
of current contexts and owns no interruption/finalization decision.

`mark_running_jobs_interrupted` considers only the supplied contexts. Under the
strict jobs lock, each member may update/finalize only its matching tagged
`ACTIVE` claim and only after the corresponding containment result is known.
An absent, changed, foreign, or later claim causes no write. A canary or
recurring context with `INCOMPLETE|UNKNOWN` cleanup takes only the quarantine
transition in §6; it cannot be cleared or finalized by interruption. Thus the
pre-kill snapshot, exact claim CAS, and cleanup classification select one
successor without a job-ID-only fallback.

The worker's first scheduler action fresh-reads and requires the same
`job_id`, `claim_id`, mode, owner profile/PID/start-ticks, `scheduled_for`, and
`ACTIVE` status and requires its exact registered context. Only then may it
enter the unchanged business route. There is no claimed-to-dispatched CAS and
no second start barrier: the admission critical section is the one start cut.
Only `PRE_API_REFUSED` may become `NOT_SUBMITTED`. Every exception after
calling a submit/task API, cancellation, lost acknowledgement, or process
death is ambiguous and remains `ACTIVE`.
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
The sole `NOT_SUBMITTED` reason is reachable only from the closed-admission
`PRE_API_REFUSED` result. Pool/task API exceptions, including a synchronous
closed-pool/closed-loop error after API entry, are never mapped to it.
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
  schema:"cron-execution-context-v1",
  mode:"BUILTIN_RECURRING"|"CHRONOS_RECURRING"|"CANARY",
  jobs_file_realpath:absolute string, owner_profile:nonempty string,
  job_id:nonempty string, claim_id:UUID4,
  owner_pid:positive integer, owner_start_ticks:positive integer,
  scheduled_for:aware string|null
}
CronAdmissionResultV1={
  status:"STARTED"|"PRE_API_REFUSED"|"SUBMIT_UNKNOWN"|
         "INVALID_CONTEXT",
  context:ExecutionContextV1, error:string|null
}
ChronosExecutionEnvelopeV1={
  schema:"cron-chronos-execution-envelope-v1",
  selected_profile:nonempty string,
  hermes_home_realpath:absolute string,
  jobs_file_realpath:absolute string
}
ChronosFireRequestV1={
  schema:"cron-chronos-fire-request-v1",
  job_id:nonempty string, fire_at:aware exact string
}
ChronosAuthProfileV1={
  schema:"cron-chronos-auth-profile-v1", profile:nonempty string,
  hermes_home_realpath:absolute string, jobs_file_realpath:absolute string,
  portal_url:nonempty string, expected_audience:nonempty string,
  nas_jwks_url:nonempty string, callback_url:nonempty string
}
ChronosFireTargetV1={
  schema:"cron-chronos-fire-target-v1",
  envelope:ChronosExecutionEnvelopeV1,
  auth_profile:ChronosAuthProfileV1,
  job_preimage:object,
  scheduler:ChronosCronScheduler
}
ChronosClaimResultV1={
  status:"CLAIMED"|"GONE"|"DUPLICATE"|"CONFLICT"|"MALFORMED"|
         "LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  job_postimage:object|null, execution_context:ExecutionContextV1|null,
  execution_envelope:ChronosExecutionEnvelopeV1|null,
  error:string|null
}
AuthenticatedChronosFireResultV1={
  schema:"cron-authenticated-fire-result-v1",
  status:"CLAIMED"|"INVALID_REQUEST"|"UNAUTHORIZED"|"GONE"|
         "DUPLICATE"|"ALREADY_ADVANCED"|"CONFLICT"|"CLAIM_REFUSED"|
         "UNAVAILABLE"|"COMMIT_UNKNOWN",
  request:ChronosFireRequestV1|null,
  target:ChronosFireTargetV1|null,
  claim:ChronosClaimResultV1|null,
  error:string|null
}
```
Only `CLAIMED` has nonnull `claim` and `job_postimage` and null `error`; every
other claim status has both payloads null and a nonempty error. Only `APPLIED`
has null disposition error; every other disposition has a nonempty error.
`COMMIT_UNKNOWN` never licenses submit, retry, finalization, or execution.
Only Chronos `CLAIMED` has a nonnull postimage, a nonnull immutable execution
envelope, and null error. Its execution context is nonnull for recurring work
and null for the unchanged legacy one-shot route; every other Chronos status
has null postimage, context, and envelope, with null error only for `GONE` and
`DUPLICATE`. For a recurring claim, the context's `jobs_file_realpath` and the
persisted claim's `owner_profile` must equal the envelope's paths/profile;
mismatch is `MALFORMED` and cannot execute. No HTTP branch infers a claim or
envelope from ambient process state or from an exception.
For `ExecutionContextV1`, recurring modes require nonnull `scheduled_for`
equal to the claim; `CANARY` requires null `scheduled_for`. Every field is
copied from the committed exact claim and selected store, never supplied by an
operator. `STARTED` alone has null admission error; every other admission
result has one nonempty error. `PRE_API_REFUSED` proves the starter was not
called; neither `SUBMIT_UNKNOWN` nor `INVALID_CONTEXT` authorizes another
attempt.
## 5. Chronos uses its existing wire and one authenticated owner
No NAS change is required. Provision remains the documented current request
containing `job_id`, `fire_at`, `agent_callback_url`, and `dedup_key`. Callback
remains authenticated by the current purpose-scoped NAS JWT and exact body:
```json
{"job_id":"<exact id>","fire_at":"<exact armed timestamp>"}
```
Both HTTP adapters pass the exact Authorization value and raw body bytes to one
synchronous shared owner off their event loops:
```python
cron.scheduler_provider.authenticate_and_claim_chronos_fire(
    authorization: str, body_bytes: bytes,
) -> AuthenticatedChronosFireResultV1
```
Neither adapter loads cron config, resolves a provider, enumerates profiles, or
opens a jobs store. The owner applies this exact order:

1. Bound and strict-decode one UTF-8 JSON object with exactly `job_id` and
   `fire_at`. Duplicate/extra/missing keys, wrong types, empty ID,
   naive/malformed/non-finite time, or trailing bytes are `INVALID_REQUEST`.
   Retain the aware `fire_at` spelling byte-for-byte. Parse exactly
   case-sensitive `Bearer <nonempty-token>` with no second credential;
   otherwise return `UNAUTHORIZED`. These cuts read no config or jobs store.
2. Enumerate only `hermes_cli.profiles.profiles_to_serve(True)`. Require unique
   valid profile names and unique canonical real homes. For each profile,
   install `hermes_constants.set_hermes_home_override(home)`, call existing
   read-only `hermes_cli.config.read_raw_config()`, and reset that token in a
   per-profile `finally` before considering the next profile. A profile is
   auth-eligible only when
   raw config says `cron.provider == "chronos"` and contains literal nonempty
   `cron.chronos.{portal_url,expected_audience,nas_jwks_url,callback_url}`.
   Absent, unreadable, unparseable, defaulted, or malformed config is
   ineligible; a structurally ambiguous catalog is `UNAVAILABLE`.
3. Group eligible profiles by exact byte tuple
   `(expected_audience,nas_jwks_url,portal_url)`. Obtain the unchanged verifier
   once with `plugins.cron_providers.chronos.verify.get_fire_verifier()`, then
   call it once per distinct tuple as
   `verifier(token=token, expected_audience=expected_audience,
   jwks_or_key=nas_jwks_url, issuer=portal_url)`. Its asymmetric signature,
   audience, issuer, exp/nbf, and `purpose="cron_fire"` checks remain
   authority. If no tuple
   verifies, return `UNAUTHORIZED` before any `cron/jobs.json` open. Invalid
   credentials therefore trigger zero jobs-store searches, and ambient A auth
   can never authorize a B store.
4. Search only profiles belonging to verified tuples. For each profile, enter
   its exact home override and then `cron.jobs.use_cron_store(home)`, fresh-read
   that one store without repair, and reset store then home tokens in a
   per-profile `finally` before searching another profile. Match exact job
   ID—never name—and exact raw `fire_at`.
   A row matches only when current `next_run_at == fire_at` or its tagged claim
   has exact `scheduled_for == fire_at`. A token valid only for A cannot open
   B's store. Profiles intentionally sharing one auth tuple are jointly
   eligible, but zero or multiple exact occurrences never select arbitrarily.
5. For the unique row, retain the exact `ChronosAuthProfileV1` whose tuple
   verified the token and construct its envelope. Enter its exact home,
   `agent.secret_scope.set_secret_scope(build_profile_secret_scope(home))`, and
   cron-store context; fresh-read `cron.provider` and the four raw Chronos
   config leaves again. Require `cron.provider == "chronos"`, require every
   leaf's exact type/string value plus profile/home/store to equal the retained
   auth profile, and otherwise refuse before provider construction or claim.
   Load one fresh `ChronosCronScheduler`; require
   availability and no constructed client; bind the envelope and retained auth
   profile once; then call its `claim_due`. Only a committed/read-back exact
   recurring or one-shot claim returns `CLAIMED`. Reset every scope in reverse
   order in `finally`.

The closed projection is `INVALID_REQUEST -> 400`, `UNAUTHORIZED -> 401`,
`GONE|DUPLICATE|ALREADY_ADVANCED -> 200`, `CONFLICT|CLAIM_REFUSED -> 409`, and
`UNAVAILABLE|COMMIT_UNKNOWN -> 503`. Only `CLAIMED` has nonnull target and
claim; only it proceeds to task creation, and only a returned task permits
202. `INVALID_REQUEST` alone has null request. `CLAIMED`, `GONE`, `DUPLICATE`,
and `ALREADY_ADVANCED` have null error; every other status has one nonempty
bounded error. Both adapters render the same single object: no-task success
`{status,job_id,fire_at}`, refusal `{error}`, or accepted
`{status:"accepted",job_id,fire_at}`. No response contains token, secret,
profile path, or verifier diagnostic.

No exact authorized row is `GONE`; multiple eligible exact occurrences are
`CONFLICT`; an exact terminal duplicate is `DUPLICATE`; a raw `fire_at`
strictly older than the sole row's successor with no matching claim is
`ALREADY_ADVANCED`; other occurrence mismatch or claim refusal is
`CLAIM_REFUSED`. Provider/config/secret/binding/store failure is `UNAVAILABLE`.
The claim due check prevents early fire. Dashboard `_find_cron_job_profile`
remains for ordinary CRUD but is unreachable from this route.
`CronScheduler.claim_due(job_id, *, fire_at) -> ChronosClaimResultV1` requires
its receiver's one-time-bound envelope, enters that exact home, secret, and
cron-store context, and resets all three in `finally`. It retains the target's
exact envelope and dispatches inside its selected home/store by the matching
row's existing schedule class. Recurring uses §4 and validates
that the returned `ExecutionContextV1`, claim owner profile, postimage ID, and
jobs-file path equal the envelope before returning `CLAIMED`.

The one-shot branch uses the internal exact-postimage owner:
```text
cron.jobs._claim_job_for_fire_postimage(
  job_id, *, expected_fire_at:aware string|null,
  claim_ttl_seconds:int=300
) -> OneShotFireClaimResultV1
OneShotFireClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"DISABLED"|"PAUSED"|"DUPLICATE"|
         "FIRE_AT_MISMATCH"|"LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  job_postimage:object|null, error:string|null
}
```
With nonnull `expected_fire_at`, it revalidates exact one-shot
`next_run_at == expected_fire_at` under the selected store's strict lock before
performing the existing fire-claim mutation and returns the committed/read-back
postimage. Only `CLAIMED` has nonnull postimage and null error. Public
`cron.jobs.claim_job_for_fire(job_id, *, claim_ttl_seconds=300) -> bool`
retains its signature and behavior by delegating with
`expected_fire_at=null` and projecting only `status == "CLAIMED"`; it exposes
neither the postimage nor the envelope. This adds no one-shot state or
transition and introduces no unlocked `get_job` reread.

`CronScheduler._run_claimed_in_active_store(result, *, adapters, loop) ->
ManagedRunOutcomeV1` accepts only `CLAIMED`, verifies that the already-active
profile, Hermes home, and jobs-file realpath exactly equal the immutable
envelope, then invokes `_run_one_job_managed` on the exact postimage; that
managed owner performs the one matching finalizer described in §7. The helper
does not enter or reset context and never rereads or re-arms.

The binding performed in step 5 is the sole provider construction and bind.
Inside that already-specified home, secret, and store scope, the shared owner
calls `plugins.cron_providers.load_cron_scheduler("chronos")`, requires an
available `ChronosCronScheduler` whose client is not constructed, and calls its
one-shot private
`_bind_execution_envelope(envelope, auth_profile) -> ChronosCronScheduler`.
Binding requires the auth profile's profile/home/jobs fields to equal the
envelope, stores both immutable objects in that new in-memory provider
instance, and makes that bound instance's `_get_client` and `_callback_url`
consume only the retained `portal_url` and `callback_url`; it never re-reads an
ambient profile's Chronos config. The provider still resolves the selected
profile's current Nous token only through the freshly installed secret scope.
A second bind, unequal auth profile, or preconstructed client refuses. Step 5
then resets store, secret, and home contexts in reverse order and returns that
exact instance and auth profile in the target. It never returns or reuses
either handler's ambient provider.

`CronScheduler.run_claimed(result: ChronosClaimResultV1, *, adapters,
loop) -> ManagedRunOutcomeV1` validates the complete envelope and recurring
context relation and requires its receiver's immutable bound envelope to equal
the result envelope and its bound auth profile to equal the target retained by
the shared owner. It then installs the same existing home override, profile
secret scope, and cron-store scope used by the shared owner, calls the helper,
and resets store, secret, and home tokens in reverse order in `finally`. A
missing or mismatched path, profile, bound envelope, auth profile, postimage,
context, secret scope, or active-store identity refuses before execution or
mutation. No ambient
`HERMES_HOME`, cached provider client, default jobs constant, current dashboard
profile, or caller-selected store participates.
Trusted synchronous `fire_due(job_id, *, fire_at, adapters, loop)` first derives
the active cron store's canonical home as
`cron.jobs._current_cron_store().jobs_file.parent.parent.resolve()` and finds exactly one
`profiles_to_serve(True)` entry with that canonical home; zero or multiple
matches return false before a claim. In the exact home, freshly built profile
secret, and store scopes, all reset in reverse order in `finally`, it reads the
same four raw Chronos leaves into `ChronosAuthProfileV1`, creates the envelope,
performs the sole step-5 fresh
provider load/bind without JWT profile enumeration, and requires the target
row's exact `(job_id,fire_at)` in that store. For recurring work it invokes
only that fresh `target.scheduler.claim_due`, passes the exact context and
postimage through `admit_and_start_managed_execution` with an inline-start
token, and on `STARTED` calls `target.scheduler.run_claimed`; the wrapper
exact-releases the context in `finally`. It projects `outcome.processed`,
preserving the non-HTTP boolean ABI. It never
uses the invoked receiver's cached client or ambient profile as target
authority. Target/config/claim refusal returns false; a post-finalization
`ChronosRearmError` remains an exception. Both HTTP
handlers instead receive the already-claimed result from
`authenticate_and_claim_chronos_fire`. For recurring work they pass its exact
context/postimage and a starter that performs
`asyncio.create_task(asyncio.to_thread(target.scheduler.run_claimed,
result.claim, adapters=adapters, loop=loop))` to the admission owner. Only
`STARTED` permits 202; `PRE_API_REFUSED` exact-CASes the recurring claim to
`NOT_SUBMITTED`, while `SUBMIT_UNKNOWN` leaves ACTIVE and returns 503. No
adapter re-authenticates, reselects, double-claims, or calls the synchronous
function on its event loop. The unchanged legacy one-shot branch fabricates no
`ExecutionContextV1`, but still checks CLOSED before task/API entry and uses
its existing exact stored fire claim; its public ABI, repeat, and recovery stay
unchanged.

`ChronosCronScheduler.run_claimed` is the sole successor re-arm owner. It
requires its one-time-bound envelope to equal the result, performs the same
home, secret, and store context entry as the base method inside one
`try/finally`, calls `_run_claimed_in_active_store`, and—before any context
token resets—requires `finalization_status` to be `APPLIED` or `REMOVED` and
freshly reads only the envelope-bound profile/store row. If that row still
exists, is enabled, is not paused, is
recurring, and has a valid successor `next_run_at`, it calls existing
`_arm_one_shot(job)` exactly once and returns the unchanged typed managed
outcome. An absent or removed one-shot, disabled, paused, or terminal row also
returns that outcome without arming. Refusal, duplicate claim,
unfinished finalization, or failed finalization performs no re-arm. Re-arm
failure raises `ChronosRearmError(job_id,claim_id,next_run_at)` and is never
returned as successful provider completion; the underlying managed outcome is
retained in the exception for diagnostics. Neither
`fire_due` nor either HTTP handler contains another re-arm site. A closed
admission result is the sole proved pre-API refusal; every exception after task
API entry leaves ACTIVE and returns 503; only `STARTED` permits 202. Because
later task failure cannot change an already
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
- no active fire, run, dispatch, recurring, or canary claim exists; the only
  admissible existing `fire_claim` is one exact valid terminal canary whose
  status is `OPERATOR_SKIPPED`;
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
existing `fire_claim` field a UUID4 canary claim. Let `P` be the fresh locked
row. If `P.fire_claim` is absent, define `B=P`. If it is exactly one valid
terminal `OPERATOR_SKIPPED` canary `C1`, define `B` as `P` with exactly that
one `fire_claim` member removed. Any ACTIVE, foreign, unknown, malformed, or
nonterminal value refuses with `P` byte-identical. `captured_job` is exactly
the claim-free `B`, never the C1-bearing row. The sole successful atomic
postimage is `B` plus `fire_claim=C2`, where `C2` is the fresh ACTIVE canary
and contains that exact `B`. No business action precedes committed readback.
Commit uncertainty is a conservative refusal; a cold read may classify only
the exact preimage `P` or exact postimage `B+C2`, never manufacture or retry a
claim. No Unicode normalization, numeric
coercion, field allow-list, or hash is used. JSON-native values are compared by
the sole canary-local owner `cron.jobs._canary_json_equal(left, right) -> bool`;
this is not a public codec.
The comparator requires identical Python JSON scalar types and values, exact
Unicode code points, identical map key sets, list order, and finite-float
`float.hex()` values, so booleans do not equal integers and `-0.0` does not
equal `0.0`; the strict JSON reader rejects NaN and infinities.
After committed claim readback, the CLI builds the exact CANARY
`ExecutionContextV1` and passes it, the `B+C2` postimage, and an inline-start
token to `admit_and_start_managed_execution`. `PRE_API_REFUSED` starts no
business action and leaves C2 ACTIVE for exact operator disposition;
`SUBMIT_UNKNOWN` does the same. Only `STARTED` invokes
`_run_one_job_managed` through the same complete execution route as the
existing `run_one_job` ABI and consumes its typed outcome. It never calls
`trigger_job`, `resume_job`, `advance_next_run`, or recurring/one-shot claim
owners. Before finalization it compares the current row, excluding only its
own exact ACTIVE `C2` and its authorized last-result leaves, with claim-free
`B`. It may update only `last_run_at`, `last_status`, `last_error`, and
`last_delivery_error`, then remove C2. The one successful final postimage is
claim-free `B` plus those four resulting leaves; C1 is consumed, never restored
or nested. It preserves enabled,
state, pause fields, schedule, `next_run_at`, repeat, prompt, script, model,
provider, workdir, toolsets, delivery, origin, and every unknown extension.
A mismatch leaves the current row and exact claim intact and returns failure.
Death or uncertainty with an ACTIVE canary never causes automatic replay. The
same public `skip-active-claim` command dispatches by the exact tagged claim
schema: for a canary it applies the §4.4 stored-PID check and changes only its
matching ACTIVE status/reason to `OPERATOR_SKIPPED`. A later canary performs
the exact `P -> B+C2` transaction above. A concurrent change to any non-C1
field, a foreign claim, or a stale approved base refuses byte-identically.
After the explicit skip, `resume_job` or `trigger_job` may likewise
consume that exact terminal canary claim under lock before performing its
existing operation; neither may consume ACTIVE, unknown, or malformed claim
state. Unknown or malformed `fire_claim` values refuse.

```python
cron.jobs.claim_paused_job_canary(job_id) -> CanaryClaimResultV1
cron.jobs.finalize_paused_job_canary(job_id, claim_id, *, success, error, delivery_error) -> ClaimDispositionResultV1
cron.jobs.quarantine_active_execution_after_cleanup_uncertain(
  context:ExecutionContextV1, *,
  cleanup_status:Literal["INCOMPLETE","UNKNOWN"],
  paused_at:aware string, reason:nonempty string,
) -> ClaimDispositionResultV1
```
The canary claim owner derives profile, PID, and birth ticks itself exactly as
the recurring owner does; no CLI argument can supply execution identity.
The quarantine owner is an exact-claim CAS under the existing strict jobs
lock. For a canary it may set only `enabled=false`, `state="paused"`,
`paused_at`, `paused_reason`, and `last_error`; it preserves every other field
of `B`, and C2 byte-for-byte with status ACTIVE. In particular C2's embedded
`captured_job=B` is never rewritten; only the named outer-row pause and
diagnostic leaves may differ from B.
For recurring execution it applies the same pause/reason leaves while retaining
the exact ACTIVE recurring claim. It never clears a fire claim, finalizes,
completes/removes, advances/re-arms, or retries. A CAS, save, or readback
uncertainty remains conservative ACTIVE and is surfaced as critical failure.
After restart, the durable ACTIVE claim blocks another canary, recurrence,
resume, or trigger. Only the explicit exact dead-owner skip may change it to
OPERATOR_SKIPPED.
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
  cleanup_status:"NOT_APPLICABLE"|"COMPLETE"|"INCOMPLETE"|"UNKNOWN",
  pre_run_status:"NOT_CONFIGURED"|"SUCCESS"|"FAILED",
  agent_status:"NOT_APPLICABLE"|"NOT_RUN"|"SUCCESS"|"FAILED",
  output_status:"NOT_REQUESTED"|"SAVED"|"FAILED",
  output_path:absolute string|null,
  delivery_status:"NOT_CONFIGURED"|"SUPPRESSED"|"DELIVERED"|"FAILED",
  delivery_error:string|null,
  finalization_status:"NOT_ATTEMPTED"|"APPLIED"|"REMOVED"|"FAILED",
  error:string|null,
  overall:"REFUSED"|"LEGACY_ALREADY_HANDLED"|"PRE_RUN_FAILED"|
          "CLEANUP_UNVERIFIED"|"AGENT_FAILED"|"OUTPUT_FAILED"|
          "DELIVERY_FAILED"|"FINALIZATION_FAILED"|
          "SUCCESS"
}
```
This value is immutable and in-process only; it is not a file or durable
authority. `output_path` is nonnull exactly for `SAVED`; `delivery_error` is
nonnull exactly for delivery `FAILED`; `error` is null exactly for `SUCCESS`.
`NOT_APPLICABLE` means no supervised script ran. Existing verified supervisor
cleanup maps to `COMPLETE`. `CronScriptCleanupError` carries one immutable
`cleanup_status:"INCOMPLETE"|"UNKNOWN"`: exit 124 plus the exact bounded
supervisor line `CLEANUP INCOMPLETE\n` selects `INCOMPLETE`; exit 124 plus
`CLEANUP UNKNOWN\n`, missing/extra/malformed protocol, unreadable pipes,
unexpected supervisor status, or any otherwise unproved cleanup selects
`UNKNOWN`. No message substring or caller input selects the tag. A valid
`RESULT <code>\n` or `CLEANUP COMPLETE\n` follows the existing verified path
and never constructs this exception. `_cleanup_preserving_exception` retains
both this classification and the original active exception. These mappings
change no supervisor, process-group, or containment behavior.
Its exact internal constructor is
`CronScriptCleanupError(message, *, cleanup_status:Literal["INCOMPLETE",
"UNKNOWN"], original_error:BaseException|null=None)`; every construction site
must supply the tag from the protocol classification above.
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
claim cleanup. `INCOMPLETE|UNKNOWN` instead invokes only
`quarantine_active_execution_after_cleanup_uncertain`, sets
`overall=CLEANUP_UNVERIFIED`, leaves output/delivery not requested/suppressed
and finalization NOT_ATTEMPTED, and returns nonzero with the exact ACTIVE claim
retained. It cannot fall through to an ordinary finalizer even if shutdown
also marks the exact context interrupted. Store-side finalizers refuse to
remove an ACTIVE claim whose exact cleanup-quarantine pause is present, so
cleanup uncertainty wins in either interleaving.
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
dominance is refusal, cleanup-unverified, finalization, output,
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
- `3`: script cleanup is `INCOMPLETE|UNKNOWN`; the exact ACTIVE canary and
  paused row remain durable and no retry/finalization is authorized.
The skip command reports its exact disposition and is zero only for a stored
OPERATOR_SKIPPED transition. `cron_command` returns either code, `cmd_cron`
returns it, `main` returns it, and
the module entry point exits with it. No layer converts a nonzero result to
success or prints a second authoritative status.
## 8. Deployment and SYS-1029 handoff
### 8.1 Loaded-code and live-process identity
`cron.scheduler` owns one import-time observation, not a lifecycle store:
```text
LoadedSchedulerBuildIdentityV1={
  schema:"hermes-loaded-scheduler-build-v1",
  scheduler_module_realpath:absolute string,
  checkout_root_realpath:absolute string,
  git_oid:40 lowercase hex
}
LoadedSchedulerBuildResultV1={
  schema:"hermes-loaded-scheduler-build-result-v1",
  status:"AVAILABLE"|"UNAVAILABLE",
  identity:LoadedSchedulerBuildIdentityV1|null,
  reason:null|"MODULE_PATH_UNAVAILABLE"|"MODULE_NOT_REGULAR"|
    "UNSTABLE_MODULE"|"CHECKOUT_UNAVAILABLE"|"DIRTY_CHECKOUT"|
    "MODULE_UNTRACKED"|"MODULE_BLOB_MISMATCH"|"GIT_TIMEOUT"|"GIT_FAILED"
}
cron.scheduler._capture_loaded_scheduler_build_identity()
  -> LoadedSchedulerBuildResultV1
cron.scheduler.get_loaded_scheduler_build_identity()
  -> LoadedSchedulerBuildResultV1
```
Capture runs exactly once while `cron.scheduler` is imported; the result is
then immutable in that module. It resolves `__file__`, requires an ordinary
nonsymlink file, records `(st_dev,st_ino,st_size,st_mtime_ns)`, and with stdin
`DEVNULL`, timeout 5.0 seconds, and exact environment
`{PATH:os.defpath,LC_ALL:"C",LANG:"C",GIT_OPTIONAL_LOCKS:"0"}` runs only:
```text
git -C <module-parent> rev-parse --show-toplevel
git -C <checkout> rev-parse --verify HEAD^{commit}
git -C <checkout> status --porcelain=v1 -z --untracked-files=all
git -C <checkout> ls-files --error-unmatch -- <relative-module-path>
git -C <checkout> hash-object -- <scheduler-module-realpath>
git -C <checkout> rev-parse --verify HEAD:<relative-module-path>
```
The root and module paths must be canonical, the module strictly below the
root, status stdout zero bytes, and the two blob OIDs one equal lowercase
40-hex LF line. The post-command lstat tuple must equal the pre-command tuple.
Command/shape/timeout failures return the corresponding `UNAVAILABLE` reason.
Blob values are compared and discarded. `git_oid` identifies code observed by
the executing imported module, not a later `HEAD`. Import may continue on
failure, but no `GatewayRunner` start may publish readiness or start a cron
provider until the mandatory capture below is `AVAILABLE`.

`GatewayRunner.start` obtains exact
`launch_profile=get_active_profile_name() or "default"` after the event loop
and PID exist and before adapter readiness or cron-provider startup, then
calls `gateway.status.capture_running_build_identity(launch_profile)` exactly
once. It consumes only the immutable loaded result; it never invokes Git or
reconstructs an OID:
```text
RunningBuildIdentityV2={
  schema:"hermes-running-build-identity-v2",
  launch_profile:nonempty string,
  pid:positive integer, process_start_ticks:positive integer,
  executable_realpath:absolute string,
  loaded_scheduler:LoadedSchedulerBuildIdentityV1
}
RunningBuildIdentityResultV2={
  schema:"hermes-running-build-identity-result-v2",
  status:"AVAILABLE"|"UNAVAILABLE",
  identity:RunningBuildIdentityV2|null,
  reason:null|"PROFILE_UNAVAILABLE"|"PROCESS_ID_UNAVAILABLE"|
    "PROCESS_START_UNAVAILABLE"|"EXECUTABLE_UNAVAILABLE"|
    "LOADED_SCHEDULER_UNAVAILABLE"
}
```
It adds the live PID, Linux `/proc/<pid>/stat` field 22, and
`/proc/<pid>/exe`, then passes the typed result to existing
`write_runtime_status(running_build_identity=...)`. Every later status write
preserves that member; restart replaces it. `UNAVAILABLE`, missing capture, or
capture exception blocks readiness and cron-provider startup. This does not
make ordinary module import require successful Git or `/proc` observation.
The existing runtime status file is an observation transport only: no
scheduler, claim, repair, resume, or recovery path reads it, and a stale record
is never accepted. No new file/store/READY/VCS authority is created.

The mandatory production reader and result are:
```text
gateway.status.read_live_running_build_identity(
  *, required_served_profile:str, expected_git_oid:str
) -> GatewayBuildIdentityCheckV1
GatewayBuildIdentityCheckV1={
  schema:"hermes-gateway-build-identity-check-v1",
  status:"VERIFIED"|"NOT_RUNNING"|"UNAVAILABLE"|"MISMATCH",
  required_served_profile:nonempty string,
  expected_git_oid:40 lowercase hex,
  identity:RunningBuildIdentityV2|null,
  reason:null|"RUNTIME_STATUS_MISSING"|"RUNTIME_STATUS_INVALID"|
    "GATEWAY_NOT_RUNNING"|"PID_REUSED"|"PROCESS_IDENTITY_UNREADABLE"|
    "GATEWAY_COMMAND_MISMATCH"|"BUILD_UNAVAILABLE"|
    "PROFILE_NOT_SERVED"|"OID_MISMATCH"
}
```
On controlled Linux it requires runtime state `running`, a live PID, fresh
`/proc/<pid>/{stat,cmdline,exe}`, exact PID/start/executable equality,
`looks_like_gateway_runtime_command_line`, the requested cron profile in
`{identity.launch_profile} union runtime.served_profiles`, and frozen loaded
OID equal to `expected_git_oid`. Missing/unreadable evidence fails closed; no
persisted-command fallback exists. Only `VERIFIED` has nonnull identity and
null reason. Other rows have null identity except `MISMATCH`, which may return
the observed identity, and exactly one reason.

The always-available CLI owner is
`hermes_cli/gateway.py::gateway_build_identity_command`, parsed in
`hermes_cli/subcommands/gateway.py` and propagated by
`hermes_cli/main.py::cmd_gateway`:
```text
hermes --profile <gateway-launch-profile> gateway build-identity \
  --require-served-profile <cron-profile> --expect-oid <40hex>
```
It prints exactly one compact sorted-key `GatewayBuildIdentityCheckV1` plus LF
and no other stdout. Exit is `0=VERIFIED`, `3=NOT_RUNNING`, `4=UNAVAILABLE`,
`5=MISMATCH`; argparse remains 2. It works when the optional API Server is
disabled. `GET /health/detailed`, when configured, may mirror the result but
is never the deployment verifier or prerequisite.

### 8.2 Canonical source, deployed bytes, activation, and rollback
One operator uses isolated proof homes below
`/home/linux/.hermes/test/sys1030/`; no production job or delivery is run.
Fresh-fetch and validate exactly:
```text
Hermes origin URL = https://github.com/kendeng300/hermes-agent.git
Hermes source ref = refs/heads/main
Hermes tracking ref = refs/remotes/origin/main
MarketWatch origin URL = https://github.com/kendeng300/marketwatch.git
MarketWatch source ref = refs/heads/master
MarketWatch tracking ref = refs/remotes/origin/master
```
For each source checkout, `git remote get-url --all origin` must exit zero and
return one LF-terminated line equal byte-for-byte to its literal URL. URL
rewriting, SSH alias, multiple URL, absent `.git`, or another remote name
refuses. With stdin `DEVNULL`, timeout 60 seconds, and environment
`{PATH:os.defpath,LC_ALL:"C",LANG:"C",GIT_OPTIONAL_LOCKS:"0"}`, execute
`git -C <source> fetch --no-tags origin <source-ref>:<tracking-ref>`.
Nonzero/timeout/auth diagnostic/missing ref/rejected tracking update refuses;
no stale tracking ref substitutes. Define from one lowercase 40-hex LF line:
```text
Mmw = git -C <MW-source> rev-parse --verify refs/remotes/origin/master^{commit}
Mh  = git -C <Hermes-source> rev-parse --verify refs/remotes/origin/main^{commit}
Dmw = git -C /home/linux/.hermes/scripts rev-parse --verify HEAD^{commit}
Dh  = git -C /home/linux/.hermes/hermes-agent rev-parse --verify HEAD^{commit}
```
The reviewed correction commits must be ancestors of `Mmw` and `Mh`.

The only valid order is:

1. Freeze `Mmw` and `Mh` using the source checks above. Capture the current
   deployed `Dmw_pre` and `Dh_pre` only for ordinary operator rollback.
2. Preflight the live store read-only: builtin scheduling, AMC and Daily remain
   paused, CCI/BB/MACD remain enabled/scheduled, no malformed/ACTIVE claim, and
   enabled targets lie beyond the bounded deployment window. Otherwise stop
   before deployment and mutate no job.
3. Deploy MarketWatch first from the reviewed canonical bytes. Before any
   Hermes restart/provider start require `Dmw==Mmw`, zero bytes from
   `git -C /home/linux/.hermes/scripts status --porcelain=v1 -z
   --untracked-files=all`, all seven §3.0 writer paths tracked at `Dmw`, and the
   writer fixed-point plus targeted writer/watchdog/restore proofs against
   those deployed bytes. Old/dirty/untracked-shadow/missing writer evidence
   refuses. Recheck the equality and cleanliness immediately before Hermes
   activation; a TOCTOU change refuses.
4. Only after step 3, deploy Hermes, require `Dh==Mh` and equally empty
   porcelain output, then restart the configured gateway. This restart/provider
   startup is the first activation point for corrected recurring claims.
5. Invoke the public build-identity command and require exit 0 with frozen
   `identity.loaded_scheduler.git_oid==Dh==Mh`, exact launch profile, and exact
   product cron profile served. Checkout equality without this live result is
   failure.
6. Re-read the five product rows without mutation. Hand
   `{Mmw,Dmw,Mh,Dh,GatewayBuildIdentityCheckV1}` and the public canary contract
   in the ordinary deployment transcript to SYS-1029. SYS-1029 alone runs
   product canaries/observations and decides product-job resume.

If a source, preflight, deployment, clean-tree, writer, startup, or live check
fails, perform no claim/canary/resume/product action. Before Hermes activation,
the corrected MarketWatch writer disposition may safely remain deployed; an
operator rollback to `Dmw_pre` is permitted only after the same read-only
no-ACTIVE-claim check. After Hermes activation, stop its readiness/provider,
retain the safer MarketWatch writers, and redeploy/restart only the exact clean
`Dh_pre` or corrected `Mh` through the same checks; never mix an old
MarketWatch writer tree with active new claim semantics. No automated rollback
or local lifecycle record is introduced.

Current production state is an observation, not a desired-state manifest:
only `9e059716170c` and `20c3fd791e82` are paused; `cci_precompute_runner`,
`bb_precompute_runner`, and `c7033e9248d1` are enabled and scheduled.
## 9. Exact edit and proof inventory
Hermes production edits: `cron/jobs.py`, `cron/scheduler.py`,
`cron/scheduler_provider.py`, `plugins/cron_providers/chronos/__init__.py`,
`gateway/platforms/api_server.py::_handle_cron_fire`,
`hermes_cli/web_server.py::cron_fire_webhook`,
`hermes_cli/subcommands/cron.py`, `hermes_cli/cron.py`,
`hermes_cli/subcommands/gateway.py`, `hermes_cli/gateway.py`,
`hermes_cli/main.py`, `tools/cronjob_tools.py`, `gateway/run.py`,
`gateway/status.py`, `gateway/platforms/api_server.py`,
`agent/curator_backup.py`, `hermes_cli/backup.py`, and the Chronos contract doc.
The NAS provider client and token verifier remain byte-unchanged.
`hermes_cli.profiles.profiles_to_serve`,
`hermes_cli.config.read_raw_config`, the `hermes_constants` home overrides,
`agent.secret_scope`, and `cron.jobs.use_cron_store` are preserved dependencies,
not new authorities. The two handlers remove direct ambient
`load_config/get_fire_verifier/resolve_cron_scheduler` calls; dashboard cron
fire also removes `_find_cron_job_profile` and `_fire_cron_job_for_profile`
from this route without removing their unrelated CRUD compatibility.
MarketWatch production edits are exactly the seven direct-writer paths in
§3.0: root/shipped `market_holiday_manager.py`, root/shipped
`holiday_watchdog.py`, the sole `enforcement/calibration_cron_watchdog.py`,
and root/shipped `_extract_backup.py`. Root/shipped `restore.sh` are inspected
transitive callers and need no content edit once the shared extractor behavior
is corrected. Root/shipped `recovery/restore_crons_from_manifest.py` remain
read-only and unchanged.
Required isolated proofs include:
- `tests/cron/test_scheduler_shutdown.py::test_shutdown_admission_cut_is_total_for_builtin_chronos_and_canary`
  runs BUILTIN_RECURRING, CHRONOS_RECURRING, and CANARY across barriers before/
  after claim save, context registration, API entry, API acceptance, and first
  business action. Close-before-admit calls no starter; admit-before-close is
  in the exact snapshot; synchronous API error is `SUBMIT_UNKNOWN`, never
  `NOT_SUBMITTED`; deleting the shared lock/registration/context leaf makes the
  test RED;
- `tests/gateway/test_cron_active_work_drain.py::test_shutdown_kill_uses_pre_kill_exact_context_snapshot`
  barriers immediately before `kill_all`, removes occurrence N and admits no
  successor after close, and proves `mark_running_jobs_interrupted` receives
  only the immutable pre-kill N snapshot without resampling or touching an N+1
  row. `tests/gateway/test_cron_shutdown_drain.py` proves drain waits exact
  contexts rather than a bare-ID count;
- `tests/cron/test_canary.py::test_cleanup_result_conserves_active_canary_across_restart`
  covers COMPLETE/INCOMPLETE/UNKNOWN and every quarantine save/readback/restart
  cut. COMPLETE uses the ordinary exact finalizer; INCOMPLETE/UNKNOWN return
  exit 3, preserve the pause plus byte-exact ACTIVE claim/captured base, and
  refuse a second canary/resume after cold read. Routing canary through
  `_clear_cleanup_fire_claim` is the mutation RED;
- `tests/cron/test_jobs.py::test_operator_skipped_second_canary_has_exact_base_and_postimage`
  proves `P -> B+C2 -> B+four result leaves`, with C1 absent from B and the
  final postimage. It mutates each non-C1 field, installs a foreign claim, and
  covers pre/post/unknown commit plus restart; comparing against the C1-bearing
  row or deleting arbitrary claim data is RED;
- `tests/cron/test_jobs.py::test_due_selection_is_read_only_for_recurring_and_preserves_locked_one_shot_preparation`
  proves recurring selection byte-read-only while one-shot legacy claim
  recovery, exhaustion removal, save/readback, dispatch, and restart remain
  unchanged;
- `tests/cron/test_jobs_crossprocess_lock.py::test_every_jobs_writer_uses_one_strict_conservation_owner`
  drives every `cron/jobs.py` mutation entry, curator restore, and all three
  backup restore/import entries through two-process barriers; the lock loser
  writes zero bytes, no public path reaches `_save_jobs_unlocked`, and an
  injected lock open/flock/timeout failure leaves exact prior bytes;
- nested same-store write works, cross-store nesting refuses, public `save_jobs`
  acquires strict ownership, and `_save_jobs_unlocked` without it refuses;
- `tests/hermes_cli/test_backup.py::test_jobs_import_and_all_restore_paths_replace_or_refuse_under_active_claim`
  proves exact inactive-row replacement for `run_import` and quick restore;
  fresh in-lock strictly-greater count replacement for emptied-store recovery;
  no action for its missing/unreadable/malformed/equal/lower count cases; and
  whole-member refusal for duplicate IDs, malformed shape, a candidate claim,
  or deletion/change of any live ACTIVE, legacy, unknown, or malformed claim.
  A pre-lock concurrent mutation, readback failure, and exact second-call
  idempotence are covered for all three paths, with no partial jobs-member
  write;
- `tests/agent/test_curator_backup.py::test_restore_cron_skill_links_preserves_active_and_concurrent_fields`
  and `tests/cron/test_rewrite_skill_refs.py::test_rewrite_preserves_active_execution_envelope`
  mutate a non-skill field at the barrier and prove only intended skill leaves
  change under the same conservation owner;
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
- `tests/gateway/test_cron_fire_webhook.py` and
  `tests/hermes_cli/test_cron_fire_dashboard.py` run the same complete status,
  response-body, claim, and task-creation table against both adapters. A valid
  A token with a B body cannot open or mutate B; a valid B token while ambient
  config/provider/secrets are A claims, executes, finalizes, and re-arms only
  B. Invalid/expired/wrong-purpose/wrong-audience tokens and malformed headers
  produce zero jobs-store opens; strict body cases cover duplicate/extra/
  missing keys and malformed, naive, before/equal/after `fire_at` values;
- `tests/cron/test_scheduler_provider.py::test_authenticate_then_selects_only_verified_profile_stores`
  covers zero/one/multiple profiles, same and different auth tuples, one
  verifier invocation per distinct tuple, ineligible raw configs, and exact ID
  rather than name. An instrumented jobs-file opener proves no store is opened
  until at least one tuple verifies. A barrier mutates each raw auth-profile
  leaf after token verification but before provider binding; the owner refuses
  rather than combining old authentication with new provider configuration;
- `tests/cron/test_scheduler_provider.py::test_claimed_chronos_envelope_pins_profile_home_and_store`
  creates profile A and B with the same job ID and distinct `jobs.json` bytes,
  then exercises recurring and one-shot claims through both HTTP handlers and
  the synchronous provider: the unique `(job_id,fire_at)` match in B returns a
  nonnull B envelope; `run_claimed` executes, finalizes, rereads, and re-arms
  only B while every A byte and call counter remains unchanged;
- the same proof deletes or independently mutates each envelope profile/home/
  jobs-file leaf and each recurring context/claim counterpart, expecting
  refusal before run/finalize/rearm; it also changes ambient profile/home to A
  after a valid B claim, preloads A's provider client and secrets, and proves
  only B's fresh bound provider/client/secrets remain authoritative; reusing,
  rebinding, or swapping the target scheduler refuses with zero execution and
  zero re-arm. Context probes prove home, secret, store, provider, and receiver
  bindings survive background handoff and are reset without leaking after
  recurring and one-shot completion through either adapter. After successful
  binding, mutating ambient or on-disk portal/callback config cannot change the
  retained bound client/callback values; changing the selected profile's Nous
  secret is observed only through that profile's freshly installed secret
  scope, never another profile or process-global environment;
- `tests/cron/test_jobs.py::test_claim_job_for_fire_public_bool_and_internal_postimage`
  proves the public signature/boolean behavior is unchanged while the internal
  owner returns the exact committed one-shot postimage, and exact `fire_at`
  mismatch writes zero bytes;
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
- MarketWatch `tests/test_market_holiday_manager.py` and
  `scripts/tests/test_market_holiday_manager.py` prove the direct `_save_jobs`
  path is gone, each selected ID calls exactly one of `cron.jobs.pause_job` and
  `cron.jobs.resume_job`, ACTIVE/current-row
  refusal is retained, unrelated rows remain exact, and one refusal is
  reported rather than hidden by later successes;
- MarketWatch `tests/test_holiday_watchdog.py` and
  `scripts/tests/test_holiday_watchdog.py` prove both watchdog copies are
  read-only for threshold/no-threshold and stale/concurrent documents;
- `tests/test_sys770_cron_silent_skip.py` proves calibration stale-legacy
  alerts while `jobs.json` remains byte-identical and tagged recurring claims
  are ignored;
- MarketWatch `tests/test_extract_backup.py::test_jobs_member_refuses_entire_fallback_before_any_write`
  runs both extractor modules with root, prefixed, traversal-normalized, and
  ordinary archives; either spelling of `cron/jobs.json` refuses before any
  member write, while an archive without it retains existing extraction;
- `tests/test_restore_backup_fallback.py::test_both_restore_entrypoints_cannot_bypass_jobs_owner`
  exercises root and shipped `restore.sh`: the Hermes-present route reaches
  corrected `run_import`, and the fallback refuses a jobs member with exact
  prior files unchanged;
- Hermes `tests/cron/test_jobs_writer_fixed_point.py::test_tracked_live_writer_and_caller_closure`
  performs the source-level reverse walk for the three Hermes direct-writer
  files, their callers, and Hermes reader-only exclusions; MarketWatch
  `tests/test_jobs_writer_fixed_point.py::test_tracked_live_writer_and_caller_closure`
  independently does the same for its seven direct-writer files, restore
  callers, and reader-only exclusions. Adding an unowned `open`, `copy`,
  `json.dump`, or replace edge to a live `jobs.json` fails with its
  repository-qualified path;
- `tests/gateway/test_status.py::test_running_build_verification_is_mandatory_with_api_disabled`
  disables API registration and proves `GatewayRunner.start` consumes the
  loaded result exactly once before readiness/provider startup. Missing,
  unavailable, exception, or bypass is RED and starts no cron provider;
- `tests/gateway/test_status.py::test_running_build_rejects_old_loaded_code_after_clean_head_moves`
  imports from OID A then moves clean `HEAD` to B, dirties the loaded module at
  B, moves the module outside its checkout, changes/stages/adds untracked
  content, and mutates each Git output/lstat. Only stable ordinary tracked bytes
  equal to `HEAD:<path>` are AVAILABLE; a HEAD-only comparison is RED;
- `tests/gateway/test_status.py::test_running_build_identity_is_captured_once_from_loaded_scheduler`
  covers PID/start/executable/profile, later-checkout stability,
  different-profile recapture refusal, every typed unavailable result, and no
  new file. Existing runtime-status writes preserve the one observation;
- `tests/hermes_cli/test_gateway.py::test_build_identity_command_is_available_without_api_server`
  proves exact JSON/stdout/exits 0/3/4/5 and argparse 2 with API disabled, then
  mutates runtime state, PID/start/executable/cmdline, launch/served profile,
  and OID. A stale status record or persisted command never passes;
- `tests/gateway/test_api_server.py::test_health_detailed_mirrors_running_build_identity_without_owning_acceptance`
  checks the optional observer without making API configuration a deployment
  prerequisite;
- `tests/gateway/test_status_command.py::test_canonical_remote_and_ref_are_freshly_verified`
  uses a scripted command runner with no network to cover both literal HTTPS
  URLs and refs, then mutates one URL, adds a second URL, substitutes SSH,
  removes/renames the source ref, makes fetch fail, leaves a stale local
  tracking ref, returns malformed/multiple tip lines, and makes the reviewed
  candidate not an ancestor; every negative refuses even when a previously
  cached tracking ref has the expected OID.
- MarketWatch `tests/test_sys1030_deployment_identity.py::test_deployed_marketwatch_identity_precedes_hermes_activation`
  parameterizes stale ref, wrong URL/ref, `Dmw!=Mmw`, dirty tracked/staged or
  untracked shadow writer, missing writer, and a barrier changing the checkout
  between proof and activation. Each returns nonzero with zero Hermes restart,
  provider start, claim, canary, or resume. Reversing Dmw proof and activation
  is the mutation RED;
Tests must be self-contained below `/home/linux/.hermes/test/sys1030/`, use no
network, live gateway, production store, live delivery, `/tmp`, systemd, new
xdist control, new mutex, process scan, or product script. They run through the
repository-required wrapper unchanged.
## 10. R2 disposition
| R2 | R3 disposition |
|---|---|
| 01 | Closed from source: three Hermes and seven MarketWatch direct-writer files, every transitive caller, and reader-only exclusions route to one strict `.jobs.lock` conservation owner or lose mutation authority. |
| 02 | Removed correction-induced codec: exact captured JSON object and type-strict comparison need no digest. |
| 03 | Retained: validate successor before atomic mutation. |
| 04 | Closed: preserve documented `{job_id,fire_at}` while every claimed path carries and re-enters one immutable selected profile/home/store envelope; no NAS rewrite. |
| 05 | Retained: claim before task creation and 202. |
| 06 | Retained: `ACTIVE` blocks every later same-job occurrence. |
| 07 | Superseded safely: claim commit precedes submit, so no post-submit CAS or start barrier exists. |
| 08 | Reduced: atomic exact paused-row snapshot; caller digest is not an issue requirement. |
| 09 | Closed with F3/F4: exact context is registered before start and reaches shutdown, cleanup quarantine, interruption, output/delivery, and exact finalization; cleanup uncertainty retains ACTIVE. |
| 10 | Retained without a new run ABI: pre-run failure dominates existing route result. |
| 11 | Retained compactly: saved output, suppression/no delivery, and delivery error stay distinguishable. |
| 12 | Preserved by non-redesign: finite removal is a legal existing terminal. |
| 13 | Returned to SYS-1029 product ownership; generic canary does not certify SYS-666 completeness. |
| 14 | Retained: malformed/unknown claims refuse before execution. |
| 15 | Retained: one command result and exact shell exit propagation. |
| 16 | Closed with F1/F2: mandatory CLI verifies live PID/start/executable/profile and immutable loaded clean scheduler bytes; optional API health and current HEAD alone are insufficient. |
| 17 | Corrected census: disposition the one real watchdog; do not invent a twin. |
| 18 | Closed with F6: exact HTTPS origins/refs are freshly fetched, reviewed commits are ancestors, clean deployed `Dmw=Mmw` precedes clean Hermes `Dh=Mh`, and live loaded OID verification precedes acceptance. |
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

### 11.1 Independent six-family and prior-closure control
Expected owner/caller/cut sets are independently derived from the pinned source,
not copied from this proposal. Before application, the exact correction bytes
must make each paired mutation fail:

| Family | GREEN | Paired RED |
|---|---|---|
| F1 mandatory verifier | API disabled still reaches the CLI/live verifier; unavailable identity blocks readiness/provider and acceptance. | Delete/bypass capture or accept UNAVAILABLE. |
| F2 loaded bytes | Stable ordinary tracked scheduler bytes equal `HEAD:<path>` and yield one immutable loaded identity. | A-loaded/B-HEAD, dirty/staged/untracked module, outside-checkout module, or HEAD-only comparison. |
| F3 shutdown admission | CLOSED linearizes against registration/API/start; an admitted exact context is snapshotted and only it is interrupted/finalized. | Remove close lock/registration/context leaf, resample after kill, or mark N+1 from N's cut. |
| F4 cleanup uncertainty | INCOMPLETE/UNKNOWN preserves pause and byte-exact ACTIVE claim across cold restart; second execution refuses. | Route canary through generic clear/finalizer or treat unknown as complete. |
| F5 second canary | `P -> B+C2 -> claim-free B+authorized result leaves` exactly. | Compare against C1-bearing P, delete a foreign claim, restore/nest C1, or accept stale B. |
| F6 deployed MarketWatch | Fresh canonical source, clean `Dmw=Mmw`, seven deployed writers, then clean Hermes activation/live proof. | Stale/wrong source, dirty/shadow/missing writer, mismatch/TOCTOU, or activation-before-proof. |

The same whole-document pass conserves all 17 actionable R2 families: R2-01
strict writer fixed point and ACTIVE conservation; 02 injective JSON comparison;
03 total successor failure with byte-preserving refusal; 04 exact JWT/profile/
store/provider/job/fire_at ingress through final re-arm; 05 durable claim before
submit/task/202; 06 no ACTIVE/ambiguous overwrite; 08 exact canary base/pause;
09 exact context through every lifecycle consumer; 10 pre-run/agent failure
dominance; 11 disjoint saved/silent/suppressed/empty/unconfigured/delivery
results; 12 legal finite `FINISHED_REMOVED`; 14 malformed complement refuses
pre-effect; 15 parser-to-process nonzero propagation; 16 mandatory loaded/live
verification; 17 root/shipped MarketWatch writer/watchdog dispositions; 18
canonical source plus deployed equality; and 19 unchanged product rows with
SYS-1029-only acceptance/resume. R2-07 remains superseded by claim-before-submit
without a claimed-to-dispatched CAS. R2-13 remains SYS-1029-owned. Neither may
silently re-enter scope.

## 12. Round-3 release rule
The bounded R3b target is the normalized formal result `6 -> 0` while all 17
prior actionable closures remain green. Each GREEN above must fail under its
paired RED; declaration presence or proposal-derived expected sets do not pass.
Any surviving/new family, optional proof route, P0 recurrence, new authority
boundary, claim replay, lock degradation, product mutation, or false success
stops the batch and resets review.
Loop 1 remains specification-only. Loop 2 may implement only after one exact
candidate receives all required independent approvals. Tests remain NOT RUN in
this document. SYS-1030 closes only after its reviewed implementation is
merged, deployed, and the configured running Hermes identity is proven. That
event unblocks—but does not perform—SYS-1029 product canaries and resume.
