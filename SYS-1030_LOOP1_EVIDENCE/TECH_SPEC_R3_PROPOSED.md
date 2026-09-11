# SYS-1030 — R4 proposed technical specification
Status: proposed Loop-1 R4 correction; implementation and tests NOT RUN
Issue: MarketWatch #1030, prerequisite for SYS-1029
Baseline source reviewed: Hermes `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`
MarketWatch source reviewed: `origin/master` at
`2c37e4b0c261c911323d2caaeed4741ae73f2884`
This replaces rejected R2/R3 and authorizes no product-job execution or live mutation.
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
- No change to the public finite one-shot APIs, ordinary finite terminal/removal
  behavior, or business-result semantics. Scheduled one-shots do gain the same
  exact nonexpiring occurrence authority and process-local lifecycle identity as
  every other scheduled route; this is the minimum claim-before-submit closure.
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
| `cron/jobs.py::_get_due_jobs_locked` | Due selection mixes recurring selection with lease-based one-shot `run_claim` and exhaustion preparation. | Split the paths: recurring selection is read-only; one-shot preparation atomically writes a tagged nonexpiring exact claim plus finite-repeat postimage while preserving public APIs and terminal behavior. |
| `cron/jobs.py::advance_next_run` | Advance and legacy claim are separate from the returned due snapshot and submit. | Recurring scheduled callers use the new atomic claim owner. |
| `cron/scheduler.py::tick` | Calls due, advances separately, then submits; submit status is best effort. | Claim first, then submit the exact claimed snapshot. |
| `cron/scheduler.py::_submit_with_guard`, `close_cron_admission_for_shutdown` | In-memory identity is only `job_id`, and shutdown does not linearize against submit/start. | Use the existing `_running_lock` to close admission and snapshot exact contexts before drain or cleanup; no later unadmitted business start is possible. |
| `cron/scheduler.py::run_one_job` | Calls lease-based one-shot `claim_dispatch`, then run/output/delivery/finalization; whitespace failure is classified after output/delivery. | Preserve its exact boolean ABI; factor the route into `_run_one_job_managed`, which accepts every scheduled context and returns the total content/output/delivery/finalization product. |
| `cron/scheduler.py::run_job` | Agent construction can follow failed script output. | A failed pre-run returns failure before agent/session/provider work. |
| `cron/scheduler.py::_pause_job_for_unverified_script_cleanup`, `_clear_cleanup_fire_claim` | Cleanup quarantine is keyed/cleared by job ID, overwrites a canary's original pause fields, and can clear its exact claim. | Use the exact context: INCOMPLETE/UNKNOWN preserve the canary pause quartet and ACTIVE claim byte-for-byte; the diagnostic has a separate result leaf and generic clear/finalize/retry is unreachable. |
| `cron/scheduler.py::get_running_job_ids`, `mark_running_jobs_interrupted` | Project only job ID, omit one-shots, and resample after the global process kill. | Keep the job-ID view only for compatibility; one lifecycle-scoped registry snapshots every exact context and cleanup phase before teardown, and interruption cannot compete with cleanup/finalization. |
| `cron/scheduler_provider.py::CronScheduler.fire_due` | Claims Chronos by job ID without scheduled time. | Accept and claim exact `fire_at`. |
| `plugins/cron_providers/chronos/__init__.py::ChronosCronScheduler.run_claimed` | `fire_due` currently owns successor `_arm_one_shot`. | Become the sole post-finalization successor re-arm owner for synchronous and HTTP paths. |
| `plugins/cron_providers/chronos/_nas_client.py` | Already provisions `job_id` and exact `fire_at`. | Preserve this wire unchanged. |
| `docs/chronos-managed-cron-contract.md` | Already documents callback body `{job_id,fire_at}`. | Make both handlers consume the documented `fire_at`. |
| `gateway/platforms/api_server.py::_handle_cron_fire` | Drops `fire_at` and creates work before a synchronous occurrence claim. | Exact store match and claim precede task creation and 202. |
| `hermes_cli/web_server.py::cron_fire_webhook` | Finds a profile by job ID alone and returns 202 before claim. | Match exactly one profile/store by `(job_id,fire_at)` and claim before task/202. |
| `hermes_cli/cron.py::cron_command` | Produces action status but callers discard it. | Return the canary command status. |
| `hermes_cli/main.py::cmd_cron`, `main` | Discard the nested return value. | Propagate it to process exit. |
| loaded-build/status paths | The scheduler-only observation omits store, resolver, selected-provider, HTTP/manual entry modules and conflates messaging `served_profiles` with cron ownership. | For controlled deployment only, attest the complete exact cron activation tuple and loaded module closure before atomically opening cron admission; ordinary startup stays unchanged. |
| `agent/curator_backup.py::_restore_cron_skill_links` | Parses backup outside the lock, then fresh-loads and merges `skill`/`skills` under `_jobs_lock`. | Retain the field-only merge but publish through the sole conservation owner and fail closed when the strict lock is unavailable. |
| `hermes_cli/backup.py::{run_import,restore_quick_snapshot,restore_cron_jobs_if_emptied}` | Import writes archive members with `open(...,"wb")`; root and `profiles/<name>/cron/jobs.json` can bypass their selected store lock. | Preflight the whole archive, route each root/named jobs member through its own exact conservation owner without nested store locks, and report partial/unknown truth. |
| MarketWatch `utilities/market_holiday_manager.py` and `scripts/utilities/market_holiday_manager.py` | Both byte-identical tracked copies load before locking, lock `jobs.lock` rather than `.jobs.lock`, use a shared `jobs.tmp`, and replace the whole document. | Remove direct storage writes; invoke `cron.jobs.pause_job` or `cron.jobs.resume_job` once per selected ID and report any partial refusal truthfully. |
| MarketWatch `utilities/holiday_watchdog.py` and `scripts/utilities/holiday_watchdog.py` | Both byte-identical tracked copies have the same pre-lock read, wrong lock name, shared temp, and whole-document replace. | Preserve detection and alerting, but remove automatic mutation. |
| MarketWatch `enforcement/calibration_cron_watchdog.py` | Loads before its save lock; the save locks `.jobs.lock` only when the lock file already exists and otherwise degrades, then replaces the whole document. | Keep its existing scan/report surface but remove every jobs-file mutation; it becomes read-only alerting. |
| MarketWatch `utilities/_extract_backup.py` and `scripts/utilities/_extract_backup.py` | The generic fallback extractor opens every archive destination `wb`, including root or named-profile jobs stores, with no jobs lock. | Pre-scan normalized members and refuse the entire fallback extraction if any root or named-profile jobs destination exists; normal restore uses corrected `hermes import`. |
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
- `mark_job_run`, compatibility `claim_dispatch`/`heartbeat_run_claim`,
  `set_dispatch_claim_status`, and the recurring/one-shot/canary claim owners;
- `advance_next_run` for remaining compatible callers;
- `rewrite_skill_refs`;
- explicit `cron.jobs.repair_jobs_store` formerly hidden inside `load_jobs`;
- `agent/curator_backup.py::_restore_cron_skill_links`;
- `hermes_cli/backup.py::{run_import,restore_quick_snapshot,
  restore_cron_jobs_if_emptied}`, each of which routes a jobs member through
  `_commit_jobs_mutation` rather than opening or copying over the live file.
Strict serialization does not authorize claim loss. While a tagged recurring,
one-shot, or canary claim is `ACTIVE`, only its exact-claim CAS owner may write result,
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
`hermes_cli.backup.normalize_jobs_archive_members(zf) ->
JobsArchivePreflightResultV1` completes a read-only pass before any archive
member is written. It applies current `_detect_prefix`: `.hermes/` or
`hermes/` is stripped only when every nondirectory member shares that one first
component. It then rejects absolute paths, backslashes, empty/`.`/`..`
components, symlink/nonregular entries, and duplicate normalized
destinations. The complete live-jobs predicate is exactly:

- `cron/jobs.json` -> default Hermes-root store;
- `profiles/<name>/cron/jobs.json` -> that named-profile store, where `name`
  matches `^[a-z0-9][a-z0-9_-]{0,63}$` and is an existing valid profile or the
  archive also contains that profile's `config.yaml` or `.env`.

`_external/**` is never a jobs store. An otherwise valid named member with no
existing/archive-defined profile is `UNKNOWN_PROFILE`. Every jobs member must
pass the complete wrapper-or-bare-list, unique nonempty ID, row-shape, and
tagged/legacy claim-authority validation before the first archive write.

```text
JobsArchiveMemberV1={
  normalized_path:canonical relative string,
  profile:nonempty string,
  jobs_file_realpath:absolute canonical string,
  candidate_jobs:list[object]
}
JobsArchivePreflightResultV1={
  schema:"hermes-jobs-archive-preflight-v1",
  status:"VALIDATED"|"REFUSED_NO_WRITE",
  members:list[JobsArchiveMemberV1], error:null|nonempty string
}
JobsArchiveStoreResultV1={
  profile:nonempty string,
  jobs_file_realpath:absolute canonical string,
  status:"UNCHANGED"|"REPLACED"|"REFUSED_NO_WRITE"|"COMMIT_UNKNOWN",
  before_count:nonnegative integer|null,
  after_count:nonnegative integer|null,
  error:null|nonempty string
}
JobsArchiveImportResultV1={
  schema:"hermes-jobs-archive-import-result-v1",
  status:"COMPLETE"|"REFUSED_NO_WRITE"|"PARTIAL"|"COMMIT_UNKNOWN",
  stores:list[JobsArchiveStoreResultV1], error:null|nonempty string
}
```

VALIDATED has a sorted unique members list (possibly empty for a non-jobs archive)
and null error;
REFUSED_NO_WRITE has an empty list and nonempty error. Members are ordered
default first then named profiles lexically and contain only fully validated
candidate rows.

For a store, UNCHANGED/REPLACED have nonnull before/after counts and null
error; REFUSED_NO_WRITE has known before count when a store was opened, null
after count, and nonempty error; COMMIT_UNKNOWN has its known before count,
null after count, and nonempty error. COMPLETE has only successful store rows
and null aggregate error. REFUSED_NO_WRITE has no committed store row and one
error. PARTIAL has at least one verified successful row followed by one known
refusal row and one error. COMMIT_UNKNOWN ends with exactly one unknown row and
one error. Empty/mixed/contradictory products are invalid.

`hermes_cli.backup.apply_imported_jobs_members(preflight)` orders default first
and named profiles lexically. For each store it installs
`use_cron_store(home)` and invokes
`_commit_jobs_mutation(import_member_mutator, active_authority=PRESERVE)` under
that store's `.jobs.lock`; `import_member_mutator` is the lexical closure over
that validated member and selected store. Two store locks
are never nested. Exact readback is required for `UNCHANGED|REPLACED`.
Known refusal before any store or non-jobs member write is `REFUSED_NO_WRITE`.
A later refusal after a verified store commit is `PARTIAL` and lists every
verified postimage. Replace/readback uncertainty is `COMMIT_UNKNOWN` and stops
the sequence. Earlier stores are neither rolled back nor described as one
cross-store transaction. The CLI is nonzero for every non-COMPLETE result.

Whole-member replace retains current inactive-row semantics, but refuses any
change/deletion of ACTIVE tagged recurring, scheduled-one-shot, or canary
authority; any legacy, unknown, or malformed claim also blocks. Candidate
claim bytes never manufacture or alter authority. Recursive equality is
type-strict JSON equality, including scalar types, Unicode code points, map
keys, and list order; it creates no digest or codec.

`restore_quick_snapshot` and `restore_cron_jobs_if_emptied` remain one explicit
current-home store each; curator `_restore_cron_skill_links` remains a
field-only current-home merge. Both MarketWatch fallback `safe_extract`
owners, reached by root/shipped `restore.sh`, apply the same normalization and
refuse the entire archive before opening any destination when either jobs
predicate matches. They exit 2 with one `JOBS_OWNER_REQUIRED` diagnostic.

### 3.2 Recurring selection and exact scheduled one-shot preparation

`cron.jobs._get_due_jobs_locked(raw_jobs, now)` remains the coordinator under
the existing strict jobs lock and delegates to two disjoint internal owners:

```text
cron.jobs._select_due_recurring_locked(raw_jobs, now) -> list[dict]
cron.jobs._prepare_due_one_shots_locked(raw_jobs, now) -> OneShotDueBatchV1
```

`_select_due_recurring_locked` validates and selects recurring rows without
changing the jobs document. It does not repair recurrence, advance
`next_run_at`, create a claim, or save. Scheduled one-shots instead use one
tagged authority in the existing `run_claim` (builtin) or `fire_claim`
(Chronos) member:

```text
OneShotExecutionClaimV1={
  schema:"cron-oneshot-execution-claim-v1", claim_id:UUID4,
  job_id:nonempty string,
  mode:"BUILTIN_ONESHOT"|"CHRONOS_ONESHOT",
  scheduled_for:aware exact string, claimed_at:aware string,
  owner_profile:nonempty string, owner_pid:positive integer,
  owner_start_ticks:positive integer,
  repeat_completed_before:nonnegative integer|null,
  repeat_completed_after:positive integer|null,
  status:"ACTIVE"|"OPERATOR_SKIPPED", terminal_error:string|null
}
OneShotDueBatchV1={
  status:"PREPARED"|"UNCHANGED"|"MALFORMED"|"LOCK_UNAVAILABLE"|
         "COMMIT_UNKNOWN",
  jobs:list[dict], claims:list[OneShotExecutionClaimV1],
  error:string|null
}
```

PREPARED has nonempty equal-length jobs/claims and null error; UNCHANGED has
both lists empty and null error. Every failure has both lists empty and one
nonempty error. No claim appears without its byte-equal job postimage.

ACTIVE requires null terminal error; OPERATOR_SKIPPED requires nonempty error.
The repeat pair is simultaneously null for an unlimited/nonfinite route or
simultaneously nonnull with `after=before+1<=times`. Under the existing strict
lock, the owner validates the one-shot, allocates its UUID, increments finite
`repeat.completed` exactly once, saves claim plus repeat postimage once, and
returns only committed/read-back snapshots. Exhaustion before allocation
retains the existing terminal removal. Unknown/malformed/foreign claim bytes
refuse unchanged. ACTIVE never ages out, is overwritten, or automatically
replayed; `_oneshot_run_claim_ttl_seconds` and generic heartbeat are legacy
read compatibility only and cannot classify a tagged claim.

The coordinator returns selected recurring rows and exact one-shot postimages
only after the one-shot batch readback. A malformed recurring row refuses its
route without partially saving a one-shot mutation. Public `get_due_jobs()`
still returns a list and public `claim_dispatch(...) -> bool` retains its
source meaning; builtin tick consumes the private typed batch and does not
claim/increment a prepared one-shot a second time.

The public due path samples `now` once, acquires that same strict lock, calls
the explicit `cron.jobs.repair_jobs_store` owner, then fresh-loads the stored
postimage before calling the coordinator. That repair owner preserves the
current record normalizations plus missing-`next_run_at` and
timezone-migration repairs and performs at most one save/readback; `load_jobs`
and recurring selection never do so implicitly. A stale but otherwise valid
recurring `next_run_at` is not fast-forwarded by selection: it is selected
with its exact stored
`scheduled_for`, and §4.2 atomically persists the successor with the claim.
Thus the split neither drops current repair cases nor advances a stale
recurrence before durable authority. A source-proved refusal before any
submit/task API may exact-CAS the one-shot postimage to its preimage, including
the finite repeat count. API entry, lost acknowledgement, commit uncertainty,
or process death retains ACTIVE. Only exact dead-owner operator skip consumes
the occurrence into existing last-result/exhaustion/removal behavior; it never
replays it. Public finite terminal behavior and return signatures remain
unchanged.
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
Builtin, Chronos, scheduled one-shot, manual-compatible, and canary routes all
enter one lifecycle-scoped process-local owner after their exact claim and
before submit/task/inline start:

```text
CronExecutionLifecycleV1={
  lifecycle_id:UUID4, state:"OPEN"|"CLOSED"|"DRAINED",
  records:map[ExecutionKeyV1,ExecutionRecordV1]
}
ExecutionKeyV1=(jobs_file_realpath,job_id,mode,claim_id)
ExecutionPhaseV1="REGISTERED"|"WORKER_STARTED"|
  "SCRIPT_CLEANUP_PENDING"|"CLEANUP_COMPLETE"|"CLEANUP_UNCERTAIN"|
  "EFFECTS_STARTED"|"FINALIZING"|"RELEASED"
ExecutionRecordV1={
  key:ExecutionKeyV1, context:ExecutionContextV2,
  phase:ExecutionPhaseV1, shutdown_requested:bool,
  cleanup_status:"NOT_APPLICABLE"|"COMPLETE"|"INCOMPLETE"|"UNKNOWN",
  release_owner:"OUTER_PREWORKER"|"WORKER"|null
}
```

This replaces lifecycle decisions by `_running_job_ids`,
`_cleanup_unverified_jobs`, and `_interrupted_job_ids`; their public/job-ID
views remain compatibility projections only. It uses the existing
`_running_lock`, is never serialized, and is not result/retry authority. A new
lifecycle opens only after the predecessor is CLOSED, DRAINED, and empty. The
shared teardown bound is the source-existing gateway outer drain bound, 65.0
seconds; expiry never implies cleanup success or claim absence.

```python
cron.scheduler.admit_and_start_managed_execution(
    context: ExecutionContextV2, job_postimage: object, starter: Callable,
) -> CronAdmissionResultV1
```
Under `_running_lock` it validates exact context/postimage/claim equality. If
CLOSED it does not call `starter` and returns PRE_API_REFUSED. If OPEN it
registers before entering the API. Returned handle/token is STARTED. Any
exception after API entry is SUBMIT_UNKNOWN: the durable claim and record stay
ACTIVE until the exact worker wrapper releases or the process exits.

Every starter, including both HTTP adapters, runs exactly:

```python
cron.scheduler.run_registered_execution(
    context: ExecutionContextV2, job_postimage: object,
    *, adapters=None, loop=None,
) -> ManagedRunOutcomeV2
cron.scheduler.run_registered_http_execution(
    context: ExecutionContextV2, job_postimage: object,
    *, scheduler: CronScheduler, adapters=None, loop=None,
) -> Awaitable[ManagedRunOutcomeV2]
```

At its first instruction it takes `_running_lock` and changes its byte-equal
record REGISTERED -> WORKER_STARTED. A missing/released record or a CLOSED
record with shutdown requested performs no business action. Its `finally`
changes only that record to RELEASED and removes it once. Builtin submit,
trusted synchronous Chronos, and both HTTP `to_thread` calls use this wrapper,
never raw `run_claimed`.

For HTTP, the outer coroutine owns a `worker_started` token and task handle.
Cancellation/error before worker entry removes REGISTERED while retaining the
durable ACTIVE claim unless non-entry is proved and its exact rollback commits.
After worker entry, outer cancellation does not release: the thread wrapper
remains sole owner through finalization/re-arm and release. A thread arriving
after its pre-start record was removed sees that fact under `_running_lock`
and performs zero business action. Both host lifecycles retain and drain the
outer tasks; success, error, cancellation, and re-arm failure each yield one
release.

Every host's first teardown operation is:
```python
cron.scheduler.close_cron_admission_for_shutdown(lifecycle_id: UUID4)
    -> tuple[ExecutionContextV2, ...]
cron.scheduler.snapshot_running_managed_executions()
    -> tuple[ExecutionContextV2, ...]
cron.scheduler.mark_running_jobs_interrupted(
    reason: str, *, identities: tuple[ExecutionContextV2, ...],
) -> tuple[ExecutionContextV2, ...]
```
Close atomically changes OPEN -> CLOSED, marks every record
`shutdown_requested`, and returns one sorted immutable snapshot. Close winning
means no registration/API/worker effect follows. Admission winning means the
exact context is in that snapshot. At `GatewayRunner.stop`, dashboard lifespan
exit, desktop-process exit, or startup abort, close precedes provider stop,
task cancellation, drain, process cleanup, and status teardown.

Shutdown never directly finalizes WORKER_STARTED or SCRIPT_CLEANUP_PENDING.
The worker publishes cleanup phase under `_running_lock`; COMPLETE lets that
worker apply one interrupted exact finalizer, while INCOMPLETE/UNKNOWN permits
only §6 quarantine. If the bounded drain expires while cleanup is pending,
shutdown atomically sets CLEANUP_UNCERTAIN/UNKNOWN and invokes the same exact
quarantine. Thus cleanup uncertainty wins without a competing generic writer.
For a started non-script context whose worker cannot complete, shutdown leaves
ACTIVE; owner death plus explicit skip is the only later successor. No global
kill count is containment truth.

Gateway `start_gateway` and `GatewayRunner` share this exact lifecycle.
Dashboard `_lifespan` creates it before exposing any webhook, including when
`HERMES_DESKTOP` is absent. Its `finally` closes admission, sets the desktop
ticker stop event, calls provider `stop` if constructed, cancels only
not-started HTTP tasks, boundedly awaits started tasks and ticker, classifies
pending cleanup UNKNOWN/quarantines, marks DRAINED, and only then continues
unrelated PTY/app teardown. The Electron primary/profile Python processes each
own their separate lifecycle. Startup abort invokes the same idempotent close;
a closed predecessor is never reopened. CLI tick/manual/canary create one
command-scoped lifecycle and close/drain it in the command's outer `finally`,
so command exit cannot strand a registered in-process worker.

Immediately before an existing process cleanup, teardown uses one immutable
snapshot and never resamples job IDs afterward. An absent, changed, foreign,
or later claim causes no store write. Exact successful/failed completion
updates current last-result/repeat behavior and removes only its claim in one
strict transaction; legal finite removal is that same terminal cut. There is
no claimed-to-dispatched CAS. Only a proved pre-API refusal can become
NOT_SUBMITTED or exact one-shot rollback; all post-API uncertainty remains
ACTIVE.

The complete source-derived route set is: builtin recurring tick; builtin
scheduled one-shot; trusted synchronous Chronos recurring and scheduled
one-shot; gateway-API Chronos recurring and scheduled one-shot; dashboard-HTTP
Chronos recurring and scheduled one-shot; paused canary; and compatible manual
fire. CLI tick is the builtin owner, not an eleventh route. Every scheduled
route carries an exact claim/context; manual compatibility carries a context
when it owns a claim but changes no public ABI.

Every route uses the same cut/restart table:

| Cut | Sole result/postimage | Cold successor |
|---|---|---|
| preclaim | no mutation/API/effect | ordinarily eligible |
| postclaim, preregistration | only proved pre-API recurring NOT_SUBMITTED or exact one-shot rollback; otherwise ACTIVE | terminal/rolled back eligible; ACTIVE blocked |
| postregistration, pre-API | close winner starts nothing and applies the same proved disposition | same |
| API entered/ack unknown | ACTIVE; no NOT_SUBMITTED/replay | blocked |
| accepted, preworker | canceled wrapper either proves no worker and exact-disposes or retains ACTIVE | terminal or blocked |
| worker started, pre-effect | shutdown request produces exact interrupted successor; crash retains ACTIVE | terminal or blocked |
| cleanup pending/classified | COMPLETE permits interrupted finalizer; INCOMPLETE/UNKNOWN only quarantine | quarantined ACTIVE blocked |
| result/output/delivery | §7 product retained; shutdown cannot turn failure into success | exact final or ACTIVE |
| finalizer pre/post commit | accept exact postimage only; uncertainty fresh-reads exact pre/post | terminal or ACTIVE |
| release | exact record removed once | jobs row is sole restart truth |

Outer HTTP cancellation and underlying worker exit are different cuts. Same-
process, shutdown-generation, and cold-restart generations cross all cleanup
values. No equivalence collapse may combine gateway/dashboard, recurring/
one-shot, API/worker, default/named store, or cleanup/shutdown unless source
proves identical owner, read set, write set, and result projection.

```python
cron.jobs.mark_recurring_not_submitted(
    job_id, claim_id,
    reason: Literal["CALLER_SHUTTING_DOWN_BEFORE_SUBMIT"],
) -> ClaimDispositionResultV1
cron.jobs.finalize_recurring_occurrence(job_id, claim_id, *, success, error, delivery_error) -> ClaimDispositionResultV1
cron.jobs.rollback_oneshot_before_submit(job_id, claim_id, exact_preimage) -> ClaimDispositionResultV1
cron.jobs.finalize_oneshot_occurrence(job_id, claim_id, *, outcome:ManagedRunOutcomeV2) -> ClaimDispositionResultV1
```
These are strict exact-claim CAS owners; no generic writer performs either cut.
The sole `NOT_SUBMITTED` reason is reachable only from the closed-admission
`PRE_API_REFUSED` result. Pool/task API exceptions, including a synchronous
closed-pool/closed-loop error after API entry, are never mapped to it.
### 4.4 Explicit skip of an ambiguous claim
```python
cron.jobs.skip_active_scheduled_claim(
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
For recurring it changes only ACTIVE to OPERATOR_SKIPPED and does not move the
already-advanced successor. For a one-shot it atomically consumes that exact
unknown occurrence into the existing failed/skipped last-result and finite
completion/removal postimage. Neither branch executes or replays it.

### 4.5 Closed internal results and execution context
These are internal return values, not persisted authorities:
```text
RecurringClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"NOT_DUE"|"BLOCKED_ACTIVE"|"MALFORMED"|
         "SUCCESSOR_FAILED"|"LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  claim:RecurringClaimV1|null, job_postimage:object|null, error:string|null
}
ClaimDispositionResultV1={
  status:"APPLIED"|"ALREADY_QUARANTINED"|"NOT_FOUND"|"STALE_CLAIM"|"INVALID_TRANSITION"|
         "LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  claim_id:UUID4, error:string|null
}
ExecutionContextV2={
  schema:"cron-execution-context-v2", lifecycle_id:UUID4,
  ingress:"BUILTIN_TICK"|"CLI_TICK"|"CHRONOS_SYNC"|
    "CHRONOS_GATEWAY_HTTP"|"CHRONOS_DASHBOARD_HTTP"|
    "MANUAL_TOOL"|"CANARY_CLI",
  mode:"BUILTIN_RECURRING"|"CHRONOS_RECURRING"|
    "BUILTIN_ONESHOT"|"CHRONOS_ONESHOT"|"MANUAL"|"CANARY",
  jobs_file_realpath:absolute canonical string, owner_profile:nonempty string,
  job_id:nonempty string, claim_id:UUID4,
  claim_field:"recurring_claim"|"run_claim"|"fire_claim",
  owner_pid:positive integer, owner_start_ticks:positive integer,
  scheduled_for:aware string|null, exact_job_postimage:object
}
CronAdmissionResultV1={
  status:"STARTED"|"PRE_API_REFUSED"|"SUBMIT_UNKNOWN"|
         "INVALID_CONTEXT",
  context:ExecutionContextV2, error:string|null
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
  claim:RecurringClaimV1|OneShotExecutionClaimV1|null,
  job_postimage:object|null, execution_context:ExecutionContextV2|null,
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
Only Chronos `CLAIMED` has a nonnull postimage, immutable envelope, and exact
nonnull execution context for recurring or scheduled one-shot work; every other status
has null postimage, context, and envelope, with null error only for `GONE` and
`DUPLICATE`. For a recurring claim, the context's `jobs_file_realpath` and the
persisted claim's `owner_profile` must equal the envelope's paths/profile;
mismatch is `MALFORMED` and cannot execute. No HTTP branch infers a claim or
envelope from ambient process state or from an exception.
For `ExecutionContextV2`, every scheduled mode requires nonnull
`scheduled_for` equal to its claim; CANARY and compatible MANUAL require null.
Every field is
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
row's existing schedule class. Recurring and scheduled one-shot use §4 and
validate the returned `ExecutionContextV2`, claim owner profile, postimage ID,
and jobs-file path against the envelope before returning `CLAIMED`.

The one-shot branch uses the internal exact-postimage owner:
```text
cron.jobs._claim_scheduled_oneshot_for_fire(
  job_id, *, expected_fire_at:aware string
) -> OneShotFireClaimResultV1
OneShotFireClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"DISABLED"|"PAUSED"|"DUPLICATE"|
         "FIRE_AT_MISMATCH"|"MALFORMED_AUTHORITY"|"LOCK_UNAVAILABLE"|
         "COMMIT_UNKNOWN",
  claim:OneShotExecutionClaimV1|null,
  job_preimage:object|null, job_postimage:object|null,
  execution_context:ExecutionContextV2|null, error:string|null
}
ManualFireClaimResultV1={
  status:"CLAIMED"|"NOT_FOUND"|"DISABLED"|"PAUSED"|"DUPLICATE"|
         "MALFORMED_AUTHORITY"|"LOCK_UNAVAILABLE"|"COMMIT_UNKNOWN",
  legacy_claim:object|null, job_postimage:object|null,
  execution_context:ExecutionContextV2|null, error:string|null
}
```
It revalidates exact one-shot
`next_run_at == expected_fire_at` under the selected store's strict lock before
allocating the tagged claim, applying the one finite-repeat increment, and
returning the committed/read-back postimage and exact context. Only `CLAIMED`
has nonnull claim/preimage/postimage/context and null error. Every other row
has null payloads and nonempty error. For the manual result, CLAIMED alone has
nonnull legacy claim/postimage/context and null error; every other row has null
payloads and nonempty error. The actual manual-tool path uses
`cron.jobs._claim_manual_fire_postimage(job_id,claim_ttl_seconds) ->
ManualFireClaimResultV1`, which returns the exact legacy claim postimage plus a
nonpersistent MANUAL `ExecutionContextV2`; its finalizer type-strictly compares
that stored legacy claim before the existing mark. Its context claim_id is an
in-process UUID tied to `exact_job_postimage.fire_claim`, never a durable claim
or restart selector. Public
`cron.jobs.claim_job_for_fire(job_id, *, claim_ttl_seconds=300) -> bool`
retains its signature and legacy boolean behavior by projecting this private
result; `tools.cronjob_tools._execute_job_now` consumes the typed result rather
than rereading. This compatibility claim is not a scheduled automatic route.
No scheduled tagged ACTIVE claim is subject to its TTL. There is no unlocked
`get_job` reread.

`CronScheduler._run_claimed_in_active_store(result, *, adapters, loop) ->
ManagedRunOutcomeV2` accepts only CLAIMED, verifies that the already-active
profile, Hermes home, and jobs-file realpath exactly equal the immutable
envelope, then invokes `run_registered_execution` on the exact postimage; that
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
loop) -> ManagedRunOutcomeV2` validates the complete envelope and scheduled
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
only that fresh `target.scheduler.claim_due`; scheduled one-shot uses the exact
one-shot owner above. Both pass the exact context and
postimage through `admit_and_start_managed_execution` with an inline-start
token, and on STARTED call `run_registered_execution`; that wrapper invokes
the bound scheduler and exact-releases in `finally`. It projects `outcome.processed`,
preserving the non-HTTP boolean ABI. It never
uses the invoked receiver's cached client or ambient profile as target
authority. Target/config/claim refusal returns false; a post-finalization
`ChronosRearmError` remains an exception. Both HTTP
handlers instead receive the already-claimed result from
`authenticate_and_claim_chronos_fire`. For recurring and scheduled one-shot they pass its exact
context/postimage and a starter that performs
`asyncio.create_task(cron.scheduler.run_registered_http_execution(
context, result.claim.job_postimage, scheduler=target.scheduler,
adapters=adapters, loop=loop))` to
the admission owner; that coroutine delegates to `to_thread` with
`run_registered_execution` and implements the pre/post-worker release rule in
§4.3. Only
`STARTED` permits 202; `PRE_API_REFUSED` exact-CASes the recurring claim to
NOT_SUBMITTED or exact-rolls back a one-shot, while SUBMIT_UNKNOWN leaves
ACTIVE and returns 503. No
adapter re-authenticates, reselects, double-claims, or calls the synchronous
function on its event loop. One-shot public signatures and finite terminal
behavior stay unchanged; lease recovery and context omission do not.

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
`ExecutionContextV2` and passes it, the `B+C2` postimage, and an inline-start
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
  context:ExecutionContextV2, *,
  cleanup_status:Literal["INCOMPLETE","UNKNOWN"],
  diagnostic:nonempty string,
) -> ClaimDispositionResultV1
```
The canary claim owner derives profile, PID, and birth ticks itself exactly as
the recurring owner does; no CLI argument can supply execution identity.
The quarantine owner is an exact-claim CAS under the existing strict jobs
lock. For a canary it preserves `enabled`, `state`, `paused_at`, and
`paused_reason` byte-for-byte from B, preserves every other business field,
and retains C2 byte-for-byte ACTIVE. C2's embedded `captured_job=B` is never
rewritten. Only outer `last_error` may receive the bounded cleanup diagnostic;
an exact replay with that same diagnostic is ALREADY_QUARANTINED and makes no
write, while any unequal retry refuses.
For recurring or scheduled one-shot execution, first quarantine may set the
ordinary pause quartet and last_error while retaining its exact ACTIVE claim;
an already-quarantined row is accepted only byte-identically. It never clears
a claim, finalizes, completes/removes, advances/re-arms, or retries. CAS, save,
or readback uncertainty remains conservative ACTIVE and is surfaced as
critical failure.
After restart, durable ACTIVE blocks another canary, scheduled occurrence,
resume, or trigger. Only the explicit exact dead-owner skip may consume it.
## 7. Pre-run, managed outcome, and legacy ABI
The internal source of execution truth is:
```text
cron.scheduler._run_one_job_managed(
  job, *, adapters=None, loop=None, verbose=False,
  execution_context:ExecutionContextV2|null=None
) -> ManagedRunOutcomeV2
ContentStatusV1="NONEMPTY"|"WHITESPACE_EMPTY"|"EMPTY_RESPONSE"|"FAILED"
DeliveryResultV2={
  status:"NOT_CONFIGURED"|"SUPPRESSED"|"SUPPRESSED_EMPTY"|
         "DELIVERED"|"FAILED"|"NOT_REQUESTED",
  error:string|null
}
ManagedRunOutcomeV2={
  schema:"cron-managed-run-outcome-v2", job_id:nonempty string,
  execution_context:ExecutionContextV2|null,
  admitted:bool, processed:bool,
  cleanup_status:"NOT_APPLICABLE"|"COMPLETE"|"INCOMPLETE"|"UNKNOWN",
  pre_run_status:"NOT_CONFIGURED"|"SUCCESS"|"FAILED",
  agent_status:"NOT_APPLICABLE"|"NOT_RUN"|"SUCCESS"|"FAILED",
  content_status:ContentStatusV1,
  output_status:"NOT_REQUESTED"|"SAVED"|"FAILED",
  output_path:absolute string|null,
  delivery_status:DeliveryResultV2.status,
  delivery_error:string|null,
  finalization_status:"NOT_ATTEMPTED"|"APPLIED"|"REMOVED"|"FAILED",
  error:string|null,
  overall:"REFUSED"|"LEGACY_ALREADY_HANDLED"|"PRE_RUN_FAILED"|
          "CLEANUP_UNVERIFIED"|"SHUTDOWN_INTERRUPTED"|"AGENT_FAILED"|
          "EMPTY_RESPONSE"|"OUTPUT_FAILED"|"DELIVERY_FAILED"|
          "FINALIZATION_FAILED"|
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
`admitted=false` requires `processed=false`, cleanup NOT_APPLICABLE, pre-run
NOT_CONFIGURED, agent NOT_APPLICABLE, content FAILED, output/delivery
NOT_REQUESTED, finalization NOT_ATTEMPTED, and `overall=REFUSED`, except for the one source-existing legacy
no-op: when `claim_dispatch` proves a `None`-context one-shot was already
handled or removed, the exact tuple is `admitted=false`, `processed=true`, all
stages neutral/not-attempted,
`error="legacy one-shot already handled or removed"`, and
`overall=LEGACY_ALREADY_HANDLED`; its stage tuple is the same neutral tuple.
That variant is illegal for scheduled managed or
canary context and performs no effect or finalization. `processed` preserves
the legacy boolean ABI exactly: true includes that historical handled no-op
and a route that processed the job even if its business result failed; false
means admission or execution machinery prevented processing in every other
case.

Every scheduled owner and canary passes exact `ExecutionContextV2` to this
callable. `None` preserves only the compatible unscheduled/manual path without
a fabricated claim ID. Running, cleanup, quarantine, interruption, output,
delivery, and finalization keys for managed calls are
`(jobs_file_realpath,job_id,mode,claim_id)`. The callable selects exactly one
finalizer: recurring, scheduled one-shot, and canary invoke their exact-claim
owners, while `None` invokes compatible `mark_job_run`.
A managed context never invokes `claim_dispatch` or a second finalizer.
Canary bypasses `_clear_cleanup_fire_claim`; no scheduled route invokes job-ID-only
claim cleanup. `INCOMPLETE|UNKNOWN` instead invokes only
`quarantine_active_execution_after_cleanup_uncertain`, sets
`overall=CLEANUP_UNVERIFIED`, leaves output and delivery NOT_REQUESTED
and finalization NOT_ATTEMPTED, and returns nonzero with the exact ACTIVE claim
retained. It cannot fall through to an ordinary finalizer even if shutdown
also marks the exact context interrupted. The lifecycle phase prevents ordinary
finalization while cleanup is pending or uncertain; store finalizers
independently refuse the exact ACTIVE quarantine postimage. Cleanup uncertainty
therefore wins before and after its CAS.
For a configured script, `run_job` calls the existing supervised script path
before importing or constructing `AIAgent`, opening `SessionDB`, resolving a
model/provider, or building an agent prompt. Script failure returns through
the existing run ABI as failure. Its diagnostic output may still be saved and
delivered, but delivery success cannot change run failure to success.
SYS-1030 does not reinterpret SYS-666 or make generic canary PASS prove a
MarketWatch report. SYS-1029 performs its own product-output acceptance.
Pre-run FAILED requires agent NOT_RUN. Agent NOT_APPLICABLE is
legal only for the existing script-only/no-agent route after pre-run success.
The legal content/output/delivery product is total:

| Upstream/content | Output | Delivery | Overall rule |
|---|---|---|---|
| exact intentional-silence sentinel produced by the existing `wakeAgent=false` or script-only route | `SAVED` or source-compatible `NOT_REQUESTED` | `SUPPRESSED` | SUCCESS unless another stage failed |
| agent success with zero bytes | `SAVED` | `SUPPRESSED_EMPTY` | EMPTY_RESPONSE |
| agent success with whitespace-only bytes | `SAVED` | `SUPPRESSED_EMPTY` | EMPTY_RESPONSE |
| nonempty success/failure diagnostic, no configured target | `SAVED` | `NOT_CONFIGURED` | preserve upstream result |
| nonempty eligible body, provider succeeds | `SAVED` | `DELIVERED` | preserve upstream result |
| nonempty eligible body, provider fails | `SAVED` | `FAILED` | DELIVERY_FAILED only absent earlier failure |
| any body whose output save fails | `FAILED` | `NOT_REQUESTED` | OUTPUT_FAILED |
| refusal or cleanup uncertainty before output | `NOT_REQUESTED` | `NOT_REQUESTED` | preserve earlier failure |

WHITESPACE_EMPTY is one or more whitespace bytes; EMPTY_RESPONSE is zero
bytes. Both are failures even when output is SAVED, and delivery is the
independent fact SUPPRESSED_EMPTY. FAILED content is a nonempty diagnostic and
never fabricates agent success; a precontent refusal also carries FAILED with
output/delivery NOT_REQUESTED. NOT_CONFIGURED, NOT_APPLICABLE,
NOT_REQUESTED, and SUPPRESSED are neutral facts, not DELIVERED aliases.
Invalid combinations—including DELIVERED without SAVED/nonempty eligible
content, delivery error outside FAILED, output path outside SAVED, or SUCCESS
with empty content—are rejected before success finalization.

Aggregate dominance is REFUSED, CLEANUP_UNVERIFIED, SHUTDOWN_INTERRUPTED,
FINALIZATION_FAILED, OUTPUT_FAILED, PRE_RUN_FAILED, AGENT_FAILED,
EMPTY_RESPONSE, DELIVERY_FAILED, then SUCCESS. Every lower-priority stage is
retained. LEGACY_ALREADY_HANDLED remains only its closed no-effect tuple.
Cleanup INCOMPLETE/UNKNOWN always selects CLEANUP_UNVERIFIED and exact ACTIVE
quarantine even when shutdown is requested.

`cron.scheduler._deliver_result_typed(job, content: str, *,
content_status: ContentStatusV1, adapters=None, loop=None) ->
DeliveryResultV2` is the sole
internal delivery producer. Any existing Optional-string helper is only a
compatibility projection; `None` no longer represents both delivered success
and absent configuration.

The public compatibility ABI remains source-exact:
```text
cron.scheduler.run_one_job(job, *, adapters=None, loop=None, verbose=False) -> bool
```
It calls `_run_one_job_managed(job, adapters=adapters, loop=loop,
verbose=verbose, execution_context=None)` for compatible
unscheduled/manual callers and returns only
`outcome.processed`. Existing callers therefore retain their current meaning:
true means processing completed, not that the job business result succeeded.
Every scheduled route, the canary, and Chronos consume the typed result.
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
### 8.1 Controlled activation and complete loaded-code identity
`CronDeploymentExpectationV1` is an opt-in in-memory launch value:
```text
H40=exactly 40 lowercase hexadecimal characters
CronProcessRoleV1="GATEWAY"|"DASHBOARD"|"DESKTOP_PRIMARY"|
  "DESKTOP_PROFILE"|"CLI_TICK"|"CLI_MANUAL"
CronDeploymentExpectationV1={
  schema:"hermes-cron-deployment-expectation-v1", expected_git_oid:H40,
  expected_process_role:CronProcessRoleV1,
  expected_profile:nonempty string,
  expected_home_realpath:absolute canonical string,
  expected_jobs_file_realpath:absolute canonical string,
  expected_provider_name:nonempty lowercase string
}
```
`gateway run`, `dashboard`, `serve`, `cron tick`, `cron run`, and canary accept
the same six all-or-none `--cron-deployment-expect-{oid,role,profile,home,
jobs-file,provider}` flags. Partial/duplicate/malformed/relative/extra values
are argparse exit 2. Parsers pass one immutable object in memory; no env,
config, file, READY marker, or runtime status is expectation authority.

Without the expectation, `CronExecutionLifecycleV1` initializes OPEN and
ordinary packaged, dirty, non-Git, non-Linux, gateway, dashboard, desktop,
provider, messaging, and manual behavior is unchanged. With it, the same
lifecycle initializes CLOSED before adapter/API/provider construction.
`verify_and_open_activation(expected, observed)` under `_running_lock` changes
CLOSED -> OPEN only for exact VERIFIED while shutdown is absent; mismatch,
unavailability, or shutdown remains CLOSED. Every claim-capable route calls
`require_admission(route,activation_id:UUID4|null)` before jobs-store open, claim,
registration, provider start, task/thread/Popen, or HTTP 202. Closed gateway/
dashboard HTTP is 503; controlled cron commands exit 4; the tool returns its
structured failure. Messaging, readiness, health, and non-cron APIs remain
ordinary. With no expectation, OPEN accepts null observation identity; with an
expectation, only its matching VERIFIED activation ID passes. `served_profiles`
is never cron authority.

```text
LoadedCronModuleV1={
  role:"PROCESS_ENTRY"|"STORE"|"ORCHESTRATOR"|"RESOLVER"|
    "PROVIDER_LOADER"|"SELECTED_PROVIDER"|"HTTP_OWNER"|"MANUAL_OWNER",
  module_name:nonempty dotted string,
  module_realpath:absolute canonical string,
  checkout_root_realpath:absolute canonical string,
  relative_path:canonical repository-relative string,
  git_oid:H40, git_blob_oid:H40
}
CronActivationIdentityV1={
  schema:"hermes-cron-activation-identity-v1", activation_id:UUID4,
  process_role:CronProcessRoleV1,
  pid:positive integer, process_start_ticks:positive integer,
  executable_realpath:absolute canonical string,
  profile:nonempty string, home_realpath:absolute canonical string,
  jobs_file_realpath:absolute canonical string,
  provider_name:nonempty lowercase string,
  routes:nonempty sorted unique list of "BUILTIN_TICK"|"PROVIDER_SYNC"|
    "GATEWAY_CHRONOS_HTTP"|"DASHBOARD_CHRONOS_HTTP"|"CLI_TICK"|
    "CLI_MANUAL"|"CANARY",
  modules:nonempty list[LoadedCronModuleV1]
}
CronActivationResultV1={
  schema:"hermes-cron-activation-result-v1",
  status:"VERIFIED"|"UNAVAILABLE"|"MISMATCH",
  identity:CronActivationIdentityV1|null,
  reason:null|"PROCESS_IDENTITY_UNAVAILABLE"|"MODULE_UNAVAILABLE"|
    "MODULE_NOT_REGULAR"|"MODULE_UNTRACKED"|"DIRTY_CHECKOUT"|
    "MODULE_BLOB_MISMATCH"|"MIXED_CHECKOUT"|"MIXED_OID"|
    "PROVIDER_AMBIGUOUS"|"EXPECTATION_MISMATCH"|"SHUTDOWN_CLOSED"
}
CronActivationCheckV1={
  schema:"hermes-cron-activation-check-v1",
  status:"VERIFIED"|"NOT_RUNNING"|"UNAVAILABLE"|"MISMATCH",
  identity:CronActivationIdentityV1|null,
  reason:null|"RUNTIME_STATUS_MISSING"|"RUNTIME_STATUS_INVALID"|
    "PROCESS_NOT_RUNNING"|"PID_REUSED"|"PROCESS_IDENTITY_UNREADABLE"|
    "COMMAND_MISMATCH"|"ACTIVATION_UNAVAILABLE"|"EXPECTATION_MISMATCH"
}
```

VERIFIED alone has nonnull identity and null reason. UNAVAILABLE has null
identity and one availability reason. MISMATCH may carry the observed identity
and has exactly one mismatch reason. For `CronActivationCheckV1`, VERIFIED has
nonnull identity/null reason; NOT_RUNNING and UNAVAILABLE have null identity
and one matching reason; MISMATCH may return observed identity and has one
mismatch reason. No other combination is constructible.

`cron.scheduler_provider.resolve_and_capture_cron_activation(
expectation:CronDeploymentExpectationV1|null, *, process_role,profile,home,
jobs_file,routes) -> CronActivationResultV1` is the sole constructor. Under the
exact profile/home/store scope, after one provider is resolved but before it
starts or claims, it eagerly imports and attests applicable modules: always
`cron.jobs` STORE, `cron.scheduler` ORCHESTRATOR, and
`cron.scheduler_provider` RESOLVER/ builtin SELECTED_PROVIDER; named providers
also include `plugins.cron_providers` PROVIDER_LOADER and exact
`provider.__class__.__module__` (Chronos concrete module); each reachable
process/HTTP/manual entry is included under its role.

Every module must be an ordinary nonsymlink file with stable pre/post
`(st_dev,st_ino,st_size,st_mtime_ns)`, canonical tracked path, empty porcelain
including untracked, and `hash-object(file)==HEAD:<relative_path>`. All rows
share one checkout and H40 HEAD. Provider instance/class/module is unique and
equals `provider_name`; aliases deduplicate only for identical module object,
canonical path, blob, and OID. Missing/stale/mixed/ambiguous evidence is never
partial VERIFIED.

Gateway activation binds only its launch profile/home/jobs/provider. Messaging
secondary adapters do not activate cron. Each Electron primary or pooled
profile `serve` process has its own activation. A plain dashboard has no local
ticker but its Chronos HTTP ingress is an activation route. Dashboard-selected
HTTP, CLI tick/manual/canary each capture their exact scoped activation before
claim. Existing runtime status may mirror the observation, but claims/retry/
restore never read it as authority. The exact gateway verifier is:

```text
gateway.status.read_live_cron_activation(
  expectation:CronDeploymentExpectationV1
) -> CronActivationCheckV1
hermes --profile <launch-profile> gateway build-identity \
  --expect-oid <H40> --require-role GATEWAY \
  --require-profile <cron-profile> --require-home <absolute-home> \
  --require-jobs-file <absolute-jobs-file> --require-provider <name>
```

It fresh-checks owner-local PID/start/cmdline/executable and exact activation,
prints one compact sorted-key `CronActivationCheckV1` plus LF, and exits 0
VERIFIED, 3 NOT_RUNNING, 4 UNAVAILABLE, 5 MISMATCH; argparse remains 2.
Optional API health may mirror but never substitutes.

### 8.2 Canonical source, deployed bytes, activation, and rollback
One operator uses isolated proof homes below `/home/linux/.hermes/test/sys1030/`;
no production job or delivery is run. Fresh-fetch from exactly:
```text
Hermes origin URL = https://github.com/kendeng300/hermes-agent.git
Hermes source ref = refs/heads/main
Hermes tracking ref = refs/remotes/origin/main
Hermes candidate ref = refs/heads/fix/sys1030
Hermes candidate tracking ref = refs/remotes/origin/fix/sys1030
MarketWatch origin URL = https://github.com/kendeng300/marketwatch.git
MarketWatch source ref = refs/heads/master
MarketWatch tracking ref = refs/remotes/origin/master
MarketWatch candidate ref = refs/heads/fix/sys1030
MarketWatch candidate tracking ref = refs/remotes/origin/fix/sys1030
```
Each origin is one exact LF-terminated URL; SSH/rewriting/multiple/absent Git
refuses. With stdin DEVNULL, 60-second timeout, and
`{PATH:os.defpath,LC_ALL:"C",LANG:"C",GIT_OPTIONAL_LOCKS:"0"}`, fetch each
candidate ref and canonical ref without stale fallback. Define:
```text
GitReleaseIdentityV1={
  repository:"HERMES"|"MARKETWATCH", origin_url:literal HTTPS URL,
  candidate_ref:full refs/heads string,
  canonical_ref:"refs/heads/main"|"refs/heads/master",
  tracking_candidate_ref:full refs/remotes/origin string,
  tracking_canonical_ref:full refs/remotes/origin string,
  candidate_oid:H40, reviewed_remote_oid:H40,
  merged_oid:H40, deployed_oid:H40
}
Hermes: Ch=candidate; Rh=fresh remote candidate; Mh=fresh merged main;
        Dh=deployed HEAD; R=each live role identity
MarketWatch: Cmw=candidate; Rmw=fresh remote candidate;
             Mmw=fresh merged master; Dmw=deployed HEAD
```
The exact reviewed identities satisfy `Ch==Rh`, `Cmw==Rmw`; approval names
those OIDs. QA names exact merged `Mh/Mmw`; `Rh<=Mh` and `Rmw<=Mmw` are
ancestor-or-equal. Clean deployments require `Dh==Mh`, `Dmw==Mmw`, empty
porcelain including untracked, and exact deployed tracked blobs. Every live
role-module R equals Dh. Ancestry alone, clean HEAD alone, scheduler-only
identity, or messaging health never substitutes. `evidence_only_exclusions=[]`.

The source-derived host evidence is:
```text
ExecutorHostV1={
  role:CronProcessRoleV1, entrypoint:nonempty qualified name,
  resident:bool, claim_routes:nonempty sorted unique list,
  owner_stop_proof:nonempty qualified owner
}
ExecutorHostEvidenceV1={
  role:CronProcessRoleV1, status:"STOPPED"|"VERIFIED",
  pid:positive integer|null, process_start_ticks:positive integer|null,
  activation:CronActivationIdentityV1|null
}
```
Exact host rows are:

| Role | Entrypoint/routes | Existing stop proof |
|---|---|---|
| GATEWAY | `gateway.run.start_gateway`; builtin, provider sync, gateway Chronos HTTP | gateway PID/start/lock owner |
| DASHBOARD | `hermes_cli.web_server.start_server/_lifespan`; dashboard Chronos HTTP | foreground/supervisor child handle |
| DESKTOP_PRIMARY | Electron `startHermes` -> `hermes serve`; builtin, provider sync, dashboard HTTP | `hermesProcess` handle |
| DESKTOP_PROFILE | Electron `spawnPoolBackend` -> `hermes --profile P serve`; same routes | `backendPool[P].process` handle |
| CLI_TICK | `hermes_cli.cron` tick | invoking process handle |
| CLI_MANUAL | `tools.cronjob_tools._execute_job_now` plus canary | invoking process handle |

STOPPED requires null process fields and the existing role owner to terminate
and wait its exact known PID/start/child handle. VERIFIED requires all process
fields and matching activation. The resident set is gateway, standalone
dashboard, Electron desktop primary, and every Electron profile backend; no
host scan is allowed. Gateway verification never covers dashboard/desktop.
CLI tick/manual/canary are nonresident and are not invoked during deployment.

The only valid order is: (1) bind fresh candidate/review identities; (2) merge
and QA exact Mh/Mmw; (3) read-only no-ACTIVE/no-due store preflight; (4) close
and drain every resident host; (5) deploy MW first and prove Dmw==Mmw, the
seven writers/callers and clean tree; (6) deploy Hermes and prove Dh==Mh;
(7) start each intended host with its controlled expectation and cron CLOSED;
(8) capture complete activation and atomically OPEN only on VERIFIED, then
start provider; (9) strict live CLI proves every R==Dh; (10) reread stores
without mutation and hand `{Ch,Rh,Mh,Dh,Cmw,Rmw,Mmw,Dmw,activations}` to
SYS-1029. SYS-1030 performs no product canary/pause/resume.

Failure before OPEN leaves hosts stopped or cron CLOSED and causes zero claim.
Stop an exact controlled process by owner PID/start evidence. Manual rollback
deploys the previously reviewed clean pair only while admission is CLOSED,
contexts DRAINED, and no ACTIVE claim exists, then repeats the same verification.
After OPEN, close/drain first. Never reset a claim, mix an old MW writer with
new claim semantics, or restart unverified bytes. Ordinary launch without an
expectation remains non-gating.

Current production state is an observation, not a desired-state manifest:
only `9e059716170c` and `20c3fd791e82` are paused; `cci_precompute_runner`,
`bb_precompute_runner`, and `c7033e9248d1` are enabled and scheduled.
## 9. Exact edit and proof inventory
Hermes production edits: `cron/jobs.py`, `cron/scheduler.py`,
`cron/scheduler_provider.py`, `plugins/cron_providers/chronos/__init__.py`,
`gateway/platforms/api_server.py::_handle_cron_fire`,
`hermes_cli/web_server.py::cron_fire_webhook`,
`hermes_cli/subcommands/cron.py`, `hermes_cli/cron.py`,
`hermes_cli/subcommands/gateway.py`, `hermes_cli/subcommands/dashboard.py`,
`hermes_cli/gateway.py`,
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

### 9.1 R4 source-derived manifests and fixed point

Expected membership comes from independent pinned-source walks, never this
proposal or generated tests. Exact hosts are gateway (`start_gateway`),
desktop dashboard (`web_server._lifespan`), gateway API Chronos, dashboard HTTP
Chronos, and manual/CLI owners. Exact routes are the ten routes in §4.3. Exact
module seed is `cron/jobs.py`, `cron/scheduler.py`,
`cron/scheduler_provider.py`, provider loader and selected provider,
`gateway/run.py`, `gateway/platforms/api_server.py`,
`hermes_cli/web_server.py`, `hermes_cli/cron.py`, `hermes_cli/main.py`,
`hermes_cli/gateway.py`, both gateway/dashboard parser modules, and
`tools/cronjob_tools.py`. Store/archive closure additionally contains
`agent/curator_backup.py`, `hermes_cli/backup.py`, and the seven MarketWatch
writers plus both restore callers.

The conserved resource identity is `(profile,canonical home,canonical
jobs-file,provider,host route)` over default and every valid named profile.
Archive forms are root, accepted common prefix plus root, and named-profile
jobs paths from §3.1. Cuts are preclaim; postclaim/preregistration;
postregistration/pre-API; API-entered/unknown; accepted/preworker;
worker-started; result-created; cleanup-classified; pre/post-quarantine;
shutdown close/snapshot/containment; pre/post-finalizer; pre/post-release; and
cold restart. Outer HTTP cancellation and thread completion remain distinct.

Perform a forward walk from every host/route through claim, admission,
execution, output/delivery, finalization, release, shutdown, archive,
deployment, and handoff. Independently reverse-walk from every jobs write,
submit/start, result/output/delivery, release, interruption/finalization,
archive destination, provider-start/admission-open, deployed/running identity,
and acceptance sink. Iterate union to exact set equality. Each reachable cell
records `{host,route,module,store/profile,archive form,cut,generation,preimage,
sole owner,postimage,typed result/exit,consumer,negative test}`. An exclusion
names its source locator and reachability proof. Equivalence requires the same
owner/read-set/write-set/result and retains entry/exit witnesses plus MC/DC.
Required isolated proofs include:
- `tests/cron/test_scheduler_shutdown.py::test_all_modes_share_one_lifecycle_and_exact_shutdown_cut`
  runs builtin/Chronos recurring and scheduled one-shot, both HTTP hosts,
  canary, and compatible manual fire across claim, registration, API,
  cancellation, first-effect, cleanup, finalization, release, and restart
  barriers. Close-before-admit calls no starter; admit-before-close is in the
  exact snapshot; post-API error is never NOT_SUBMITTED. Deleting the lock,
  context leaf, worker-owned release, or cleanup phase makes the test RED;
- `tests/gateway/test_cron_active_work_drain.py::test_shutdown_kill_uses_pre_kill_exact_context_snapshot`
  barriers immediately before `kill_all`, removes occurrence N and admits no
  successor after close, and proves `mark_running_jobs_interrupted` receives
  only the immutable pre-kill N snapshot without resampling or touching an N+1
  row. `tests/gateway/test_cron_shutdown_drain.py` proves drain waits exact
  contexts rather than a bare-ID count;
- `tests/cron/test_canary.py::test_cleanup_result_conserves_active_canary_across_restart`
  covers COMPLETE/INCOMPLETE/UNKNOWN and every quarantine save/readback/restart
  cut. COMPLETE uses the ordinary exact finalizer; INCOMPLETE/UNKNOWN return
  exit 3, preserve each original enabled/state/paused_at/paused_reason leaf plus
  byte-exact ACTIVE claim/captured base, and
  refuse a second canary/resume after cold read. Routing canary through
  `_clear_cleanup_fire_claim` is the mutation RED;
- `tests/cron/test_jobs.py::test_operator_skipped_second_canary_has_exact_base_and_postimage`
  proves `P -> B+C2 -> B+four result leaves`, with C1 absent from B and the
  final postimage. It mutates each non-C1 field, installs a foreign claim, and
  covers pre/post/unknown commit plus restart; comparing against the C1-bearing
  row or deleting arbitrary claim data is RED;
- `tests/cron/test_jobs.py::test_scheduled_oneshot_claim_and_repeat_postimage_are_exact_for_builtin_and_chronos`
  proves recurring selection byte-read-only and both one-shot fields receive
  one tagged claim plus exact finite increment before submit. Pre-API rollback,
  post-API ACTIVE retention, malformed refusal, no TTL replay, operator skip,
  terminal removal, cold restart, and unchanged public booleans are crossed;
- `tests/cron/test_jobs_crossprocess_lock.py::test_every_jobs_writer_uses_one_strict_conservation_owner`
  drives every `cron/jobs.py` mutation entry, curator restore, and all three
  backup restore/import entries through two-process barriers; the lock loser
  writes zero bytes, no public path reaches `_save_jobs_unlocked`, and an
  injected lock open/flock/timeout failure leaves exact prior bytes;
- nested same-store write works, cross-store nesting refuses, public `save_jobs`
  acquires strict ownership, and `_save_jobs_unlocked` without it refuses;
- `tests/hermes_cli/test_backup.py::test_import_normalizes_default_and_named_profile_jobs_members`
  crosses root/two named stores, both prefixes, duplicate-normalized target,
  traversal, bad/unknown profile, malformed member, ACTIVE conflict,
  concurrent mutation, second-store refusal, and readback uncertainty. It
  proves per-store COMPLETE/PARTIAL/COMMIT_UNKNOWN without false cross-store
  atomicity. Quick/emptied restore retain their one current-store rules;
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
- those two files also prove the registered worker wrapper releases once on
  success, execution error, re-arm error, cancellation before worker entry,
  and outer cancellation after worker entry; the latter retains registration
  until the real thread exits;
- `tests/hermes_cli/test_web_server.py::test_dashboard_lifespan_closes_and_drains_ticker_and_http`
  covers desktop ticker present/absent and hosted webhook work, asserting
  close-before-stop/cancel, provider stop, bounded join, UNKNOWN quarantine,
  and zero admission after close;
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
  manual owner returns exact legacy postimage/context;
  `tests/tools/test_cronjob_run_immediate.py::test_manual_fire_uses_exact_registered_context`
  proves the actual tool consumes it through release with no reread. The
  scheduled Chronos owner returns its tagged claim/context and exact
  `fire_at` mismatch writes zero bytes;
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
  exercises every legal content/output/delivery/finalization row and invalid
  complement, including zero-byte and whitespace-only SAVED plus
  SUPPRESSED_EMPTY and nonzero EMPTY_RESPONSE, and failure dominance,
  including the source-existing `LEGACY_ALREADY_HANDLED` true no-op; legacy
  `run_one_job` returns `processed` while canary and Chronos consume `overall`;
- scheduled one-shot success/failure/exhaustion/removal remain behaviorally
  unchanged, while tagged ACTIVE blocks TTL restart/replay and exact context
  participates in shutdown;
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
- MarketWatch `tests/test_extract_backup.py::test_root_and_named_jobs_members_refuse_both_fallbacks_before_any_write`
  runs both extractors with root, prefixed, named-profile, duplicate, traversal,
  and ordinary archives; any jobs destination refuses before every write;
- `tests/test_restore_backup_fallback.py::test_root_and_shipped_restore_cannot_bypass_named_profile_jobs_owner`
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
- `tests/gateway/test_status.py::test_controlled_deployment_verifies_before_cron_admission`
  barriers provider resolution, module capture, OPEN, provider start, HTTP
  claim, and task. Every mismatch gives zero jobs-file open/write/start/task/
  202 while messaging/readiness remains healthy; absent opt-in proves ordinary
  startup unchanged;
- `tests/cron/test_scheduler_provider.py::test_full_loaded_claim_module_set_one_oid_and_selected_provider`
  mutates/removes each role module, swaps/aliases provider, mixes checkout/OID/
  blob, and moves HEAD after import. Any omitted module or HEAD-only comparison
  is RED;
- `tests/gateway/test_status.py::test_cron_activation_profile_store_is_not_messaging_served_profiles`
  proves launch A with messaging A+B certifies only A; B needs its own exact
  dashboard/desktop identity. Gateway/dashboard HTTP and manual-tool tests
  prove CLOSED refuses before profile/store open, task, and 202;
- `tests/gateway/test_executor_host_manifest.py::test_every_source_claim_host_is_stopped_or_exactly_attested`
  proves exact host-set equality and owner-local stop/join without scans;
  `apps/desktop/electron/backend-command.test.ts` covers primary/pool handles,
  controlled argv, and stale pool backend RED;
- `tests/gateway/test_status_command.py::test_candidate_review_merge_deploy_running_equalities`
  mutates Ch!=Rh, Cmw!=Rmw, stale/failed fetch, nonancestor merge, QA on another
  OID, dirty/untracked, D!=M, and any R!=Dh. Optional API absence cannot weaken
  the public CLI;
- MarketWatch `tests/test_sys1030_deployment_identity.py::test_deployed_marketwatch_identity_precedes_hermes_activation`
  parameterizes stale ref, wrong URL/ref, `Dmw!=Mmw`, dirty tracked/staged or
  untracked shadow writer, missing writer, and a barrier changing the checkout
  between proof and activation. Each returns nonzero with zero Hermes restart,
  provider start, claim, canary, or resume. Reversing Dmw proof and activation
  is the mutation RED;
- one end-to-end barrier crosses controlled verification and Systems teardown:
  shutdown-before-verify never opens; verify-before-shutdown opens once then
  close/drain wins; no second controller or finalizer exists;
Tests must be self-contained below `/home/linux/.hermes/test/sys1030/`, use no
network, live gateway, production store, live delivery, `/tmp`, systemd, new
xdist control, new mutex, process scan, or product script. They run through the
repository-required wrapper unchanged.
## 10. R2 disposition
| R2 | R4 disposition |
|---|---|
| 01 | Closed from source: three Hermes and seven MarketWatch direct-writer files, every transitive caller, and reader-only exclusions route to one strict `.jobs.lock` conservation owner or lose mutation authority. |
| 02 | Removed correction-induced codec: exact captured JSON object and type-strict comparison need no digest. |
| 03 | Retained: validate successor before atomic mutation. |
| 04 | Closed: preserve documented `{job_id,fire_at}` while every claimed path carries and re-enters one immutable selected profile/home/store envelope; no NAS rewrite. |
| 05 | Retained: claim before task creation and 202. |
| 06 | Retained: `ACTIVE` blocks every later same-job occurrence. |
| 07 | Superseded safely: claim commit precedes submit and there is no claimed-to-dispatched CAS; the process-local worker-entry acknowledgement only closes lifecycle ownership. |
| 08 | Reduced: atomic exact paused-row snapshot; caller digest is not an issue requirement. |
| 09 | Closed with R4 F2/F3/F8/F9: every scheduled context reaches release, shutdown, quarantine, interruption, output/delivery, and exact finalization; uncertainty retains ACTIVE. |
| 10 | Retained without a new run ABI: pre-run failure dominates existing route result. |
| 11 | Closed by the total content/output/delivery product, including saved whitespace/empty plus independent suppressed-empty failure. |
| 12 | Preserved: tagged exact one-shot authority retains legal finite removal and public APIs while eliminating TTL replay. |
| 13 | Returned to SYS-1029 product ownership; generic canary does not certify SYS-666 completeness. |
| 14 | Retained: malformed/unknown claims refuse before execution. |
| 15 | Retained: one command result and exact shell exit propagation. |
| 16 | Closed by controlled full-module activation and live PID/start/executable/profile/store/provider proof; optional API/current HEAD alone are insufficient. |
| 17 | Corrected census: disposition the one real watchdog; do not invent a twin. |
| 18 | Closed by exact candidate==remote-review, QA-bound merge, deployed equality, and every running role OID, with MW proof before Hermes activation. |
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

### 11.1 Independent twelve-family and prior-closure control
Expected owner/caller/cut sets are independently derived from the pinned source,
not copied from this proposal. Before application, the exact correction bytes
must make each paired mutation fail:

| Family | GREEN | Paired RED |
|---|---|---|
| F1 pause conservation | INCOMPLETE/UNKNOWN preserves original enabled/state/paused_at/paused_reason and ACTIVE through restart. | Change/drop a pause leaf or write diagnostics into it. |
| F2 scheduled one-shot authority | Builtin/Chronos one-shots have tagged nonexpiring claims, exact contexts, and unchanged public/finite terminal behavior. | TTL reclaim, missing context, malformed overwrite, post-API replay, foreign clear. |
| F3 HTTP release | Both handlers retain exact registration until actual worker exit and release once on every result. | Omit/double release or release a live thread on outer cancellation. |
| F4 product truth | Every legal content/output/delivery/finalization tuple and invalid complement is explicit. | Empty/whitespace success, SAVED conflated with suppression, or later stage masking earlier failure. |
| F5 controlled deploy admission | Controlled cron stays CLOSED until full verification; failure yields zero provider/claim/task/202 while ordinary startup stays unchanged. | Open/start before verification or leave controlled cron open after failure. |
| F6 module closure | Every applicable loaded claim-path module has one checkout/OID/blob and selected-provider identity. | Replace/omit one module, mix OIDs, alias/swap provider. |
| F7 activation tuple | Exact process role/profile/home/jobs/provider/routes/PID/start are bound; messaging profiles do not substitute. | Swap/drop one leaf or use served_profiles alone. |
| F8 cleanup × shutdown | One phase/claim successor makes COMPLETE terminal and INCOMPLETE/UNKNOWN quarantine. | Shutdown/generic finalizer clears before or after UNKNOWN CAS. |
| F9 host teardown | Gateway, desktop/dashboard, HTTP, and manual hosts close before admission and drain exact work. | Delete one host close/drain or admit immediately after close. |
| F10 archive namespace | Root/prefixed/named jobs members use selected strict owner or fallback refuses before all writes. | Duplicate/traversal/A-B basename swap or unowned named-store write. |
| F11 executor hosts | Each resident source-derived host is owner-stopped or exactly attested. | Leave stale gateway/dashboard/desktop role executable. |
| F12 Git chain | C==remote review, QA-bound merge, D==M, every R==D for Hermes and MW ordering. | Break one equality/ancestry/QA/deploy/live edge or use stale ref. |

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

## 12. Round-4 release rule
The bounded R4 target is the independently normalized result `13 raw -> 12
families -> 0` while all 17
prior actionable closures remain green. Each GREEN above must fail under its
paired RED; declaration presence or proposal-derived expected sets do not pass.
Any surviving/new family, optional proof route, P0 recurrence, new authority
boundary, claim replay, lock degradation, product mutation, or false success
stops the batch and resets review.
Loop 1 remains specification-only. Loop 2 may implement only after one exact
candidate receives Systems, Architecture, and Six-Sigma panel approval plus an
independent source-derived audit with 100% ownership/cell/product/mutation
coverage. Tests remain NOT RUN in
this document. SYS-1030 closes only after its reviewed implementation is
merged, deployed, and the configured running Hermes identity is proven. That
event unblocks—but does not perform—SYS-1029 product canaries and resume.
