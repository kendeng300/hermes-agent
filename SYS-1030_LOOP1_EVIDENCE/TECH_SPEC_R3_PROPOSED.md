# SYS-1030 — finite implementation specification

Status: Loop-1 author-panel candidate. This document is the only normative
SYS-1030 technical specification. `FINITE_SCOPE_V1.json` is its machine-readable
inventory; `validate_finite_scope_v1.py` checks that finite inventory without
claiming whole-program semantic proof.

Source authorities:

- Hermes baseline `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`.
- MarketWatch baseline `2c37e4b0c261c911323d2caaeed4741ae73f2884`.
- Git object bytes at those OIDs, not an ambient checkout, are the baseline.
- The implementation interpreter is the product Python 3.11 required by
  `pyproject.toml`; Python 3.8 may show that a checker starts but cannot emit the
  semantic acceptance result.

## 1. Quality goal and acceptance boundary

SYS-1030 shall deliver all of the following as one coherent lifecycle:

1. A due recurring or one-shot occurrence is durably claimed before any submit,
   task creation, HTTP `202`, or business effect.
2. A public one-shot canary can run one paused and disabled job without resuming,
   rescheduling, or otherwise rewriting it.
3. A configured pre-run script failure happens before construction or setup of
   the agent path and remains the final failure even if diagnostic delivery also
   fails.
4. Shutdown first closes admission, snapshots exact managed executions, drains,
   and reports uncertainty without replaying ambiguous work.
5. Authentication selects one immutable profile/home/store/provider target
   before a store is opened, and closed admission opens no store.
6. Controlled rollout proves reviewed candidate, canonical remote, merge,
   deployment, and actual loaded bytes for every active execution role.
7. Imports, restores, MarketWatch utilities, and watchdogs cannot bypass the one
   jobs mutation owner or misreport partial archive work.

The quality target for this Loop-1 correction is normalized defects C01–C13:
13 before the batch and zero after the finite preflight and three author audits.
Independent formal review follows only after author-panel 3/3 and independent
Six Sigma QA find zero.

### 1.1 Exact edit scope

The permitted production edit set is the literal 25 `PathRuleV1` records in
`FINITE_SCOPE_V1.json`: 18 Hermes paths and seven MarketWatch paths. Membership
is authored, not discovered. A candidate production diff must be a subset of
that set and every changed Python function must have one exact function rule.

The following are read-only witness sources, not edit permission:

- `apps/desktop/electron/main.ts` functions `startHermes`, `spawnPoolBackend`,
  `teardownPrimaryBackendAndWait`, and `teardownPoolBackendAndWait`;
- `acp_adapter/entry.py::main`;
- `tui_gateway/entry.py::main` and `tui_gateway/ws.py::handle_ws`;
- `hermes_cli/oneshot.py::run_oneshot` and `agent/oneshot.py::run_oneshot`;
- provider, auth, config, secrets, NAS, and `restore.sh` callers.

Electron launch code is outside the 25 paths. Existing Electron handles may
prove a child STOPPED; this scope may not claim that it injected controlled argv
or restarted an Electron child VERIFIED. If an implementation truly needs any
read-only witness changed, Loop 1 must explicitly reset and re-review the scope.
It must never silently widen the candidate.

## 2. Source truth and corrections to the retired model

At the pinned Hermes baseline:

- `cron/jobs.py` already owns `_jobs_lock`, `_save_jobs_unlocked`, current CRUD
  writers, `claim_dispatch`, `claim_job_for_fire`, due selection, heartbeat,
  advance, status, and skill-ref rewrite. Several callers nevertheless perform
  read/modify/save outside one closed mutation interface.
- `cron/scheduler.py::tick` defines a nested `_submit_with_guard`; `run_one_job`
  and `run_job` combine compatibility, execution, delivery, and finalization;
  shutdown interruption is job-ID based rather than exact-context based.
- both Chronos HTTP adapters perform local profile/store selection; the Chronos
  provider has multiple possible arm/fire paths.
- `run_job` enters agent-path setup before the specification can prove a failed
  pre-run constructed nothing.
- Hermes imports/restores and the seven MarketWatch paths can write or extract
  jobs data outside one authority.
- gateway runtime status describes disk/process state but does not prove actual
  loaded callable bytes.

The retired R4 DAG, 1.469 MB model, and 148 KB semantic validator tried to infer
an open-world fixed point. That approach is rejected. It could not prove a
finite negative, obscured missing product routes, and introduced a second
lifecycle/state system beside Git. History preserves those artifacts; they are
not gates, sources, or compatibility requirements.

The former proposed interfaces `_commit_jobs_mutation(mutator,
active_authority)` and `admit_and_start_managed_execution(..., starter:
Callable)` are also rejected. Both carry executable authority through a generic
argument and directly contradict the finite direct-call rule below.

## 3. Closed types and one authority per effect

These are closed internal record contracts. In this finite candidate they are
validated data mappings/tuples constructed inside the listed whole functions;
the implementation adds no module-level import, assignment, constant, class,
base, or decorator. Consumers must not substitute free strings or callbacks.
That representation choice makes the residual structural AST rule
implementable while the behavioral tests enforce the closed products.

### 3.1 Job-store operation

`JobsOperationV1` is a tagged, data-only union whose members cover the exact
writer inventory: create, update, pause, resume, trigger, remove, run result,
heartbeat, advance, dispatch status, skill-ref rewrite, repair, scheduled claim,
not-submitted disposition, exact finalization, operator skip, cleanup quarantine,
canary claim/finalization, and archive replacement. Each public owner constructs
its own member from typed data. A caller cannot supply executable code, a
callable, a function name, or an authority tag that chooses an otherwise
unavailable effect.

`cron.jobs::_commit_jobs_operation(operation)` is the only owner that may call
`_save_jobs_unlocked`. It acquires `_jobs_lock`, fresh-loads and validates the
whole selected store, applies one fixed direct branch for the closed tag,
commits, read-backs, and returns a typed result. Each listed writer calls it
directly exactly once. The public raw `save_jobs` function is deleted;
`_save_jobs_unlocked` remains private and has no external caller.

Deletion is a source-derived migration, not a grep-after-the-fact assumption.
The pinned reverse set is recorded exactly in `save_jobs_migration` in the
manifest: 13 production owners in `cron/jobs.py` plus
`agent/curator_backup.py::_restore_cron_skill_links`; the module imports and all
affected nodes in `tests/cron/test_jobs.py` and
`tests/cron/test_ticker_stall_60703.py`; and the affected nodes in
`tests/agent/test_curator_backup.py`, `tests/cron/test_cron_provider_pin.py`,
`tests/cron/test_file_permissions.py`, `tests/hermes_cli/test_cron.py`,
`tests/test_timezone.py`, and `tests/tools/test_cronjob_tools.py`. Production
callers move to closed operations. Tests seed their worker-owned temporary store
directly or use a closed public operation; a test helper never recreates a raw
whole-store API. Candidate preflight re-derives the baseline reverse set and
requires zero remaining semantic import, attribute, name, or reflection
reference to public `save_jobs` in those paths and all 25 production paths.

Every lookup by job ID requires exactly one row with a nonempty exact ID.
Duplicate IDs are `MALFORMED`: load/claim/finalize/skip/import performs zero
mutation and repair never silently selects or deletes one. Unknown, malformed,
or legacy claim objects block execution rather than being overwritten.

`_jobs_lock` is fail-closed. Unsupported or unavailable OS locking, acquisition
timeout, lock/open error, and ownership uncertainty return typed
`LOCK_UNAVAILABLE` before the first store read or write; code never falls back
to the process-local `RLock`. A held-lock/two-process witness proves the loser
performs zero read, mutation, submit, or business effect. Reentrancy inside one
closed operation is unnecessary: public owners call the commit owner once and
the commit owner alone acquires the cross-process lock.

Job finalizers fresh-load and compare
`(canonical_store, job_id, occurrence_kind, claim_id)`. A missing, foreign, or
newer claim is not cleared. They update only execution-owned leaves on the fresh
row and preserve permitted concurrent nonexecution/pause changes; they never
write a captured stale whole row.

### 3.2 Managed start descriptor

`ManagedStartV1` is a closed data/resource union for `SYNC`, `POOL`, and
`HTTP_TASK`; it contains no callable. `admit_and_start_managed_execution`
directly switches on this type and calls the fixed owner for that route.
`run_registered_execution` and `run_registered_http_execution` each call
`_run_one_job_managed` exactly once. `run_one_job` is a Boolean compatibility
projection that calls `_run_one_job_managed` exactly once. No wrapper invokes
itself, another compatibility wrapper, or a generic dispatcher.

For a Chronos descriptor, `admit_and_start_managed_execution` calls
`ChronosCronScheduler.run_claimed` directly. That owner chooses exactly one of
`run_registered_execution` or `run_registered_http_execution`, waits for its
post-finalization outcome, and only then directly invokes `_arm_one_shot` when
eligible. `ChronosCronScheduler.fire_due` calls the admission owner, not
`run_claimed`; therefore the graph has no `run_claimed -> admit -> run_claimed`
cycle, and HTTP cannot bypass the sole re-arm owner.

The execution pipeline produces a pre-finalization `RunProductV1`. The exact
finalizer consumes that product and produces `FinalizationProductV1`; only then
does `ManagedRunOutcomeV1` aggregate both. A finalizer must not consume a
`ManagedRunOutcome` that already contains its own finalization status.

### 3.3 Total result states

Scheduled claim status is exactly:

`ACTIVE | NOT_SUBMITTED | OPERATOR_SKIPPED`.

Admission result is exactly:

`STARTED | PRE_API_REFUSED | SUBMIT_UNKNOWN`.

Cleanup result is exactly:

`PENDING | COMPLETE | INCOMPLETE | UNKNOWN`.

A recurring claim records `scheduled_for` as the exact fresh preclaim
`next_run_at`. When that instant is older than the existing grace window, the
selector collapses all missed slots into exactly one catch-up occurrence. In the
same locked commit it creates the ACTIVE claim for that original
`scheduled_for` and advances `next_run_at` to the first computed instant strictly
after the selection time. There is no fast-forward store write before the
claim. A second tick or cold restart sees ACTIVE and performs no submit.

A proved pre-API recurring refusal changes only that exact claim to
`NOT_SUBMITTED`; it retains `scheduled_for`. A later selector may CAS that same
NOT_SUBMITTED occurrence to a new ACTIVE claim and retry it. An ACTIVE,
SUBMIT_UNKNOWN, or OPERATOR_SKIPPED occurrence is never automatically retried.
For one-shot, only the corresponding never-called proof may restore its exact
preclaim image.

Only proof that a starter, task API, or external API was never called may create
`NOT_SUBMITTED` or restore the exact one-shot preimage. API entry,
enqueue-then-raise, lost acknowledgment, accepted-before-worker, process death,
or commit uncertainty remains `ACTIVE` and blocks automatic replay. An
ambiguous run is an operational fact, not a guessed failure or success.

An operator may change an `ACTIVE` claim to `OPERATOR_SKIPPED` only by knowingly
accepting an unknown business outcome. The claim carries stable machine and boot
identity plus PID and process start identity. A same-machine, different-boot
claim proves every old-boot process gone. A same-machine, current-boot claim may
be skipped only after the durable supervisor and every descendant identity are
resolved and cleanup is `COMPLETE`; a dead/reused parent with a live descendant,
or an unknown supervisor, refuses. A foreign or unavailable machine/boot
identity refuses. There is no PID scan and no inference that absence in local
`/proc` proves a remote owner dead.

### 3.4 Closed record schemas and legal products

The following aliases are exact: `JobId` and `Reason` are nonempty UTF-8
strings; `ClaimId` is canonical UUID4 text; `UtcInstant` is an aware UTC RFC3339
instant; `CanonicalStore` is an absolute, symlink-resolved jobs-file path;
`Pid` is a positive integer; and `StartIdentity` is the platform process-start
identity, not wall-clock time. `null` is legal only where stated. Unknown fields
in any control record refuse rather than being ignored.

`JobsOperationV1` has these data-only variants and no others:

| tag | required payload |
|---|---|
| `CREATE` | validated candidate job |
| `UPDATE` | `job_id`, validated field patch |
| `PAUSE`, `RESUME`, `TRIGGER`, `REMOVE` | `job_id` and operation-specific reason/time |
| `RUN_RESULT` | exact claim key plus `RunProductV1` |
| `HEARTBEAT` | exact claim key plus owner identity and observed time |
| `ADVANCE` | exact recurring claim key plus computed successor instant |
| `DISPATCH_STATUS` | exact claim key plus one legal scheduled status product |
| `REWRITE_SKILL_REFS` | validated old/new immutable reference pair |
| `REPAIR` | validated repair plan and exact observed malformed revision |
| `SELECT_AND_CLAIM_DUE` | selection instant, owner identity, route |
| `CLAIM_FIRE` | binding, occurrence kind, `scheduled_for`, owner identity |
| `CLAIM_CANARY` | canonical store, `job_id`, owner identity |
| `NOT_SUBMITTED` | exact recurring claim key and never-called proof |
| `ROLLBACK_ONESHOT` | exact one-shot claim key, preimage, never-called proof |
| `FINALIZE_RECURRING`, `FINALIZE_ONESHOT`, `FINALIZE_CANARY` | exact claim key and pre-finalization product |
| `OPERATOR_SKIP` | exact claim key, explicit acceptance, death/containment proof |
| `QUARANTINE` | exact claim key, cleanup diagnostic and immutable pre-kill snapshot |
| `ARCHIVE_REPLACE` | canonical store, validated wrapper bytes, expected current revision |

Each public owner can construct only its named private variant branch. No caller
passes a mutator, callback, function, callable factory, operation-name string,
or caller-selected capability tag. The commit result is exactly
`JobsCommitResultV1(status, store, operation, revision_before, revision_after,
value, reason)` where status is `UNCHANGED | COMMITTED | REFUSED_NO_WRITE |
COMMIT_UNKNOWN | LOCK_UNAVAILABLE`. `revision_after` is present only for
`UNCHANGED`/`COMMITTED`; `value` is present only for those variants; and a known
refusal has no postimage. `COMMIT_UNKNOWN` never asserts either preimage or
postimage.

The scheduled claim union is closed:

- `ActiveClaimV1(status=ACTIVE, mode, claim_id, job_id, scheduled_for,
  machine_id, boot_id, owner_pid, owner_start, api_state, worker_state,
  cleanup, base_snapshot)`. `mode` is `RECURRING | ONESHOT | CANARY`;
  `api_state` is `NOT_ENTERED | ENTERED_ACK_UNKNOWN | ACCEPTED`;
  `worker_state` is `NOT_STARTED | STARTED`; `cleanup` is null until STARTED and
  then `PENDING | COMPLETE | INCOMPLETE | UNKNOWN`; `base_snapshot` is exact
  serialized B only for CANARY and is null otherwise. `ACCEPTED` requires API
  entry, and STARTED requires `api_state=ACCEPTED`.
- `NotSubmittedClaimV1(status=NOT_SUBMITTED, mode=RECURRING, claim_id, job_id,
  scheduled_for, api_state=NOT_ENTERED, worker_state=NOT_STARTED, cleanup=null,
  reason)`. Owner/process/base fields are absent. It alone is retryable.
- `OperatorSkippedClaimV1(status=OPERATOR_SKIPPED, mode, claim_id, job_id,
  scheduled_for, accepted_unknown_outcome=true, skip_reason, skip_at,
  death_proof)`. `death_proof` is one closed same-node/new-boot or
  same-node/current-boot-with-descendants-COMPLETE product. It is terminal and
  never retryable.

`ReservationV1(reservation_id, lifecycle_id, route, host, role,
shutdown_requested)` exists under `_running_lock` before store open.
`ExecutionContextV1` adds canonical store, job, occurrence kind, claim ID,
phase, owner PID/start, and immutable claim readback. Phase is `RESERVED |
CLAIMED | API_ENTERED | ACCEPTED | WORKER_STARTED | FINALIZING | REARMING |
RELEASING`; transitions are monotone. A context key is exactly
`(lifecycle_id,reservation_id,canonical_store,job_id,occurrence_kind,claim_id)`.

`ManagedStartV1` is exactly one of `SYNC(route,binding,job,resources)`,
`POOL(route,binding,job,pool_resource)`, or
`HTTP_TASK(route,binding,job,task_group_resource)`. Resource fields are opaque
already-owned handles, never executable callables. `AdmissionResultV1` is:

- `STARTED(context_key, api_entered=true, accepted=true)`;
- `PRE_API_REFUSED(reason, api_entered=false, disposition)` where disposition
  is exactly recurring `NOT_SUBMITTED`, one-shot `ROLLED_BACK_PREIMAGE`, canary
  `RETAIN_ACTIVE_C2` after durable C2, or `NO_CLAIM`; or
- `SUBMIT_UNKNOWN(context_key, api_entered=true,
  disposition=RETAIN_ACTIVE)`.

No other field/nullability/status combination is legal. In particular,
`PRE_API_REFUSED + ROLLED_BACK_PREIMAGE` is impossible after C2, and
`SUBMIT_UNKNOWN + NOT_SUBMITTED` is impossible for every route.

`RunProductV1(status, output, primary_error, delivery_input)` has status
`SUCCEEDED | FAILED | PRE_RUN_FAILED | INTERRUPTED`; success alone has null
`primary_error`. `DeliveryProductV1(status, error)` is `NOT_REQUESTED`,
`DELIVERED`, or `FAILED` with an error only in the last case.
`FinalizationProductV1(status, claim_key, revision, error)` is `COMMITTED |
REFUSED_FOREIGN_CLAIM | COMMIT_UNKNOWN`, with revision only for COMMITTED.
`ManagedRunOutcomeV1(run_product, delivery_product, finalization_product,
cleanup_product, exit_code)` is created only after finalization and is never an
input to it. Exit is 0 only for fully finalized success, 1 for finalized
business/pre-run failure, 2 for known refusal before execution, and 3 for
cleanup/finalization/commit uncertainty. Tests enumerate the invalid complement
and reject every unlisted cross-product.

## 4. Admission, claim, execution, and shutdown linearization

Each process owns one in-memory lifecycle under the existing `_running_lock`:
`OPEN -> CLOSED -> DRAINED`. No runtime file, READY flag, mutex service, systemd
unit, cache, parallel lifecycle database, or new process group is introduced.

An HTTP request or controlled local route follows this order:

1. authenticate or validate controlled activation without a jobs-store open;
2. under `_running_lock`, refuse CLOSED or create a unique `RESERVED` record;
3. release `_running_lock`;
4. open the one selected store and claim under `_jobs_lock`;
5. without holding `_jobs_lock`, promote the exact reservation under
   `_running_lock` to `(store, job, occurrence_kind, claim_id, phase)`;
6. call the route's fixed submit/task/API owner;
7. worker-start, pre-run/business, typed result, exact finalizer, eligible
   Chronos re-arm, then exact release.

The global lock rule is absolute: code never holds `_running_lock` and
`_jobs_lock` simultaneously, and never performs store I/O/fsync while holding
`_running_lock`. If close wins after reservation, that record is marked
shutdown-requested; after the store step it receives only its proved pre-API
disposition and release. It does not submit.

Host shutdown makes admission CLOSED as its first teardown action and snapshots
both RESERVED and claimed records. Immediately before the existing
`process_registry.kill_all`, it takes one immutable still-active
context-and-phase snapshot under `_running_lock`, then never resamples after the
kill. A global killed-process count is not per-context proof. The worker alone
publishes cleanup and exact finalization. Shutdown never job-ID-finalizes a
worker on its behalf.

For a worker-started record, `COMPLETE` permits that worker's exact interrupted
finalization. `INCOMPLETE` or `UNKNOWN` writes only a bounded cleanup diagnostic,
quarantines the exact active claim, exits nonzero, and remains sticky: a later
completion report cannot overwrite `CLEANUP_UNCERTAIN`. Not-started reservations
or registrations get only the proved pre-API disposition. Unrelated jobs and
contexts remain byte-unchanged. DRAINED means no record remains owned by that
lifecycle.

## 5. Exact route, occurrence, cut, and host matrix

The semantic route set is exactly these ten cells:

1. `BUILTIN_RECURRING`
2. `BUILTIN_ONESHOT`
3. `CHRONOS_SYNC_RECURRING`
4. `CHRONOS_SYNC_ONESHOT`
5. `CHRONOS_GATEWAY_HTTP_RECURRING`
6. `CHRONOS_GATEWAY_HTTP_ONESHOT`
7. `CHRONOS_DASHBOARD_HTTP_RECURRING`
8. `CHRONOS_DASHBOARD_HTTP_ONESHOT`
9. `CANARY`
10. `MANUAL_COMPAT`

The manifest fixes the complete relation, not independent name sets. In the
table, `GW`, `DASH`, `EP`, `ER`, and `CLI` mean `GATEWAY/GATEWAY`,
`STANDALONE_DASHBOARD/STANDALONE_DASHBOARD`,
`ELECTRON_PRIMARY/ELECTRON_PRIMARY`, `ELECTRON_PROFILE/ELECTRON_PROFILE`, and
`CLI_CHAT/CLI_TICK` host/role pairs:

| route | occurrence | exact host/role pairs | claim owner | submit owner | finalizer | re-arm |
|---|---|---|---|---|---|---|
| `BUILTIN_RECURRING` | recurring | GW,DASH,EP,ER,CLI | `claim_recurring_occurrence` | `_submit_with_guard` | `finalize_recurring_occurrence` | N/A |
| `BUILTIN_ONESHOT` | one-shot | GW,DASH,EP,ER,CLI | `_prepare_due_one_shots_locked` | `_submit_with_guard` | `finalize_one_shot_occurrence` | N/A |
| `CHRONOS_SYNC_RECURRING` | recurring | GW,DASH | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_recurring_occurrence` | N/A |
| `CHRONOS_SYNC_ONESHOT` | one-shot | GW,DASH | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_one_shot_occurrence` | `_arm_one_shot` |
| `CHRONOS_GATEWAY_HTTP_RECURRING` | recurring | GW | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_recurring_occurrence` | N/A |
| `CHRONOS_GATEWAY_HTTP_ONESHOT` | one-shot | GW | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_one_shot_occurrence` | `_arm_one_shot` |
| `CHRONOS_DASHBOARD_HTTP_RECURRING` | recurring | DASH | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_recurring_occurrence` | N/A |
| `CHRONOS_DASHBOARD_HTTP_ONESHOT` | one-shot | DASH | `claim_job_for_fire` | `ChronosCronScheduler.run_claimed` | `finalize_one_shot_occurrence` | `_arm_one_shot` |
| `CANARY` | paused canary | `CLI_CHAT/CANARY` | `claim_paused_job_canary` | `admit_and_start_managed_execution` | `finalize_paused_job_canary` | N/A |
| `MANUAL_COMPAT` | manual | exact pairs below | `trigger_job` | `admit_and_start_managed_execution` | N/A | N/A |

The manual pairs are exactly `GATEWAY/GATEWAY`,
`GATEWAY_API_CHAT/GATEWAY`, `CLI_CHAT/CLI_CHAT`,
`CLI_CHAT/CLI_MANUAL`, `TUI_STDIO/TUI_STDIO`, `TUI_WS/TUI_WS`,
`ACP_STDIO/ACP_STDIO`, `STANDALONE_DASHBOARD/STANDALONE_DASHBOARD`,
`ELECTRON_PRIMARY/ELECTRON_PRIMARY`, and
`ELECTRON_PROFILE/ELECTRON_PROFILE`. A same-count host, role, owner, occurrence,
stage, or witness substitution is a preflight refusal.

Route is independent from ingress host. Direct `ChronosCronScheduler.fire_due`
is the preserved synchronous provider ABI, not an invented resident host.
`cron/scheduler.py::__main__ -> tick` is a `CLI_TICK` alias. `MANUAL_COMPAT` in
`tools.cronjob_tools::_execute_job_now` binds to the installed host lifecycle
when invoked inside gateway or another resident process. Otherwise its
synchronous outer wrapper creates and releases one command-scoped ordinary
lifecycle before return; it never creates a detached CLI lifecycle inside a
gateway.

Every route witness records the same ordered trace with explicit
`NOT_APPLICABLE` stages:

`authenticate/activate -> reserve -> selected-store open -> claim+readback ->
lifecycle register -> submit/task/202 -> worker-start -> pre-run/business ->
typed result -> exact finalizer -> Chronos re-arm if eligible -> release`.

The parameterized suite crosses every route with recurring/one-shot as
applicable, and with cuts at: preclaim; postclaim/preregister;
postregister/pre-API; API-entered/ack-unknown; accepted/preworker; worker
started/preeffect; cleanup pending/complete/incomplete/unknown; result;
pre/post-finalizer commit; pre/post-rearm; pre/post-release; shutdown before and
after each stage; and cold restart. Each witness asserts store bytes, active
claim, task/API count, business-effect count, finalizer count, re-arm count,
release state, and exit/result type. Count-only assertions are insufficient:
wrong-owner substitution and same-count route substitution must fail.
For every recurring route the suite includes an in-grace occurrence and a stale
multi-slot catch-up, proving one claim/one effect, exact `scheduled_for`, one
future schedule advance, ACTIVE restart blocking, and safe NOT_SUBMITTED retry.

The expected cut product is literal. “Restart” means a cold process reading the
durable postimage; it never trusts an in-memory result:

| durable cut | recurring | one-shot | canary | manual | restart/effect rule |
|---|---|---|---|---|---|
| before claim commit | preimage | preimage | B/no C2 | no scheduled claim | selection may run once |
| claim commit, before registration | ACTIVE | ACTIVE | ACTIVE C2+B | N/A | blocks automatic effect |
| registered, before API entry | NOT_SUBMITTED only with proved never-call | exact preimage rollback only with proved never-call | ACTIVE C2+B | no effect | recurring NOT_SUBMITTED alone may retry |
| API entered, ack unknown | ACTIVE | ACTIVE | ACTIVE C2+B | unknown | no replay, exit 3 |
| accepted, before worker | ACTIVE | ACTIVE | ACTIVE C2+B | accepted | no replay |
| worker start, before effect | ACTIVE/PENDING | ACTIVE/PENDING | ACTIVE C2+B/PENDING | PENDING | no replay |
| cleanup COMPLETE, before result/finalizer | ACTIVE | ACTIVE | ACTIVE C2+B | pending result | exact worker may finalize |
| cleanup INCOMPLETE or UNKNOWN | ACTIVE+quarantine | ACTIVE+quarantine | ACTIVE C2+B+diagnostic | quarantined | no replay, exit 3 |
| result durable, before finalizer | ACTIVE | ACTIVE | ACTIVE C2+B | result | exact finalizer once |
| before/unknown finalizer commit | ACTIVE or COMMIT_UNKNOWN | same | same | result | no guessed terminal state |
| finalizer verified | terminal occurrence, future schedule retained | exact terminal/removal product | B plus four allowed leaves | result | no second finalizer |
| before/unknown Chronos re-arm | terminal but re-arm pending | same | N/A | N/A | no effect replay; reconcile may arm only verified terminal one-shot |
| re-arm verified, before release | exact successor armed | exact successor armed | N/A | N/A | release only exact context |
| release verified | no context | no context | no context | no context | cold restart observes only store/provider truth |

For the “registered, before API” row the recurring and one-shot disposition is
legal only when no API/starter/task call occurred. Once a canary C2 exists it is
never rolled back in that row. Shutdown before/after every row uses the same
postimage, result, finalizer/re-arm count, and command exit; it does not create a
separate shortcut. Equivalence across route rows is allowed only when claim,
store, submit, finalizer, and re-arm owners are all identical.

`ChronosCronScheduler.run_claimed` is the sole post-finalization one-shot re-arm
owner for synchronous and HTTP routes. Reconcile and other paths do not re-arm
an ACTIVE or cleanup-uncertain occurrence.

## 6. Pause-preserving canary conservation

The public syntax is exactly `hermes cron canary JOB_ID` and
`hermes cron skip-active-claim JOB_ID --claim-id UUID4 --reason TEXT`. The
canary command emits exactly one JSON object with keys
`status,job_id,claim_id,run_status,finalization_status,cleanup_status,error`.
Success or an ordinary run failure writes that object to stdout, leaves stderr
empty, and exits 0 or 1 respectively. Parser/validation/preclaim refusal writes
the object to stderr, leaves stdout empty, and exits 2. Cleanup or commit
uncertainty writes it to stderr, leaves stdout empty, keeps ACTIVE, and exits 3.
The skip command additionally requires the exact current claim ID; success
prints the terminal `OPERATOR_SKIPPED` record and exits 0, known refusal exits 2,
and uncertain cleanup exits 3. No command has an implicit job, latest-claim,
force, retry, or yes-default form.

The public canary accepts one exact job reference only when its fresh locked row
is paused and disabled. Let `P` be that full row, including unknown extensions,
and let `C1` be its only prior `fire_claim` if that claim is a terminal
`OPERATOR_SKIPPED` canary.

- if `P` has no `fire_claim`, base `B = P`;
- if `C1` is the only claim and satisfies that exact exception, `B` is `P` with
  exactly `C1` removed;
- any other claim or malformed/duplicate row refuses and preserves `P` exactly.

The claim postimage is `B + C2`, where `C2` is a new ACTIVE canary claim that
embeds the exact serialized `B`. Successful or ordinary failed finalization
removes `C2` and may change only four leaves:
`last_run_at`, `last_status`, `last_error`, and `last_delivery_error`.
`enabled`, `state`, absent-versus-null pause keys, `paused_at`, `paused_reason`,
schedule, `next_run_at`, repeat, and every unknown extension key/type/value/order
remain exactly as in `B`. Boolean versus integer, signed zero, nested C1/C2,
extension-object key order, and extension-list order are part of conservation.

`INCOMPLETE`, `UNKNOWN`, or commit uncertainty keeps C2 ACTIVE, preserves B,
writes only the bounded cleanup diagnostic, exits 3, and blocks a second canary,
resume, and trigger. Once C2 is durably committed, even `PRE_API_REFUSED` keeps
that exact ACTIVE C2 and embedded B; the general preclaim rollback rule does not
apply. Restoring B is legal only at a cut before C2 exists. Tests inject every
store commit cut and attempt a second canary after an operator-skipped C1.

## 7. Authentication, target binding, and first store access

Both Chronos HTTP adapters pass raw `Authorization` and exact JSON body
`{job_id, fire_at}` to `select_authenticated_cron_target`. The owner:

1. rejects duplicate, missing, extra, wrong-type, or naive-time fields;
2. verifies purpose, audience, expiry, and signature against each
   source-derived eligible raw auth tuple without opening any jobs store;
3. derives an immutable candidate
   `(profile, canonical_home, canonical_jobs_file, provider, route)` from trusted
   config/auth/secrets, never caller-supplied profile/home/store/provider;
4. creates the lifecycle reservation while admission is OPEN;
5. fresh-opens only eligible candidates and accepts exactly one row whose ID and
   stored scheduled occurrence equal `fire_at`;
6. rechecks the immutable binding before promotion and submit.

Its only success product is
`AuthenticatedTargetV1(profile,canonical_home,canonical_jobs_file,provider,
route,job_id,fire_at,auth_subject,auth_purpose,auth_audience,auth_expiry,
config_revision,reservation_id)`. Every field is nonnull and source-derived;
the stored job is not copied into the product. Refusal is
`AuthenticatedTargetRefusalV1(reason,reservation_released=true)` with no target
fields. A success becomes invalid if any auth/config/profile/home/store/provider
field or revision differs at the promotion barrier. The reservation is released
exactly once on every refusal.

Zero or multiple matches, any verification failure, CLOSED admission, or a
config/auth tuple change refuses with zero mutation and no task or `202`.
An A-token with B-body must not open or mutate B. A spy on the first store-open
operation proves admission and binding happen first. The adapters call this same
owner and the same managed admission owner; neither retains an ambient profile
fire helper.

## 8. Hosts and process roles

The exact host labels are:

`GATEWAY, STANDALONE_DASHBOARD, ELECTRON_PRIMARY, ELECTRON_PROFILE, TUI_STDIO,
TUI_WS, ACP_STDIO, CLI_CHAT, GATEWAY_API_CHAT`.

The exact process roles are:

`ACP_STDIO, CANARY, CLI_CHAT, CLI_MANUAL, CLI_TICK, ELECTRON_PRIMARY,
ELECTRON_PROFILE, GATEWAY, STANDALONE_DASHBOARD, TUI_STDIO, TUI_WS`.

`GATEWAY_API_CHAT` shares the GATEWAY process. CLI_CHAT may enter its chat,
manual, tick, or canary command role. Gateway and each `web_server` lifespan own
one OPEN/CLOSED/DRAINED lifecycle. Electron primary/profile inherit their
separate Python child lifecycle; existing Electron handles are stop/wait
witnesses only. TUI, ACP, CLI, and manual calls synchronously enter the central
managed path using an installed lifecycle or one outer command-scoped lifecycle
closed and drained in `finally`.

The concrete shutdown ownership is exact:

| host / role | lifecycle close/snapshot/drain owner | pre-kill/stop witness |
|---|---|---|
| GATEWAY / GATEWAY | `GatewayRunner.stop._stop_impl` | `_kill_tool_subprocesses` |
| GATEWAY_API_CHAT / GATEWAY | same GATEWAY lifecycle | same immutable pre-kill snapshot |
| STANDALONE_DASHBOARD / STANDALONE_DASHBOARD | `hermes_cli.web_server::_lifespan` | lifespan outer `finally` |
| ELECTRON_PRIMARY / ELECTRON_PRIMARY | child `web_server::_lifespan` | existing `teardownPrimaryBackendAndWait` handle proves stop/wait |
| ELECTRON_PROFILE / ELECTRON_PROFILE | child `web_server::_lifespan` | existing `teardownPoolBackendAndWait` handle proves stop/wait |
| TUI_STDIO / TUI_STDIO | `cron.scheduler::command_scoped_lifecycle` | synchronous outer `finally` |
| TUI_WS / TUI_WS | installed host lifecycle or `command_scoped_lifecycle` | synchronous outer `finally` |
| ACP_STDIO / ACP_STDIO | `command_scoped_lifecycle` | synchronous outer `finally` |
| CLI_CHAT / CLI_CHAT, CLI_MANUAL, CLI_TICK, CANARY | installed or command-scoped lifecycle | command outer `finally` |

The Electron functions are read-only witnesses outside the 25-path edit set;
they cannot be claimed as changed launch authority. For GATEWAY, close and the
first snapshot occur in `_stop_impl`; immediately before
`process_registry.kill_all`, `_kill_tool_subprocesses` consumes one immutable
still-active snapshot and never resamples after kill. For each other row, the
named outer owner closes first, snapshots RESERVED and registered contexts,
then stops/awaits and drains or quarantines. If central implementation cannot
provide this without editing a witness path, Loop 1 must reset the literal
production scope rather than silently widen it.

`tests/cron/test_scheduler_shutdown.py::test_nine_hosts_eleven_roles_close_snapshot_drain`
must walk all nine hosts and 11 roles and prove: close is first teardown action;
RESERVED and exact execution contexts are snapshot; no later admission occurs;
all contexts drain or remain truthfully quarantined; and unrelated work is not
touched.

## 9. Pre-run ordering and failure dominance

For agent jobs, `cron.scheduler::run_job` runs and classifies
`_run_scheduled_job_script` before all of the following:

- importing or constructing `run_agent.AIAgent`;
- constructing `hermes_state.SessionDB`;
- calling `_build_job_prompt`;
- reading/expanding model or runtime config;
- resolving the runtime provider, fallback chain, or credential pool;
- discovering MCP tools or skills;
- setting session variables, environment contexts, or current directory;
- starting any agent/business effect.

`no_agent` remains a self-contained script route but obeys the same failed-script
zero-agent/setup contract. A configured script failure yields
`PRE_RUN_FAILED`, a nonzero command result, and zero agent/business construction
or effect. Its diagnostic is propagated through saved output and delivery
context; `last_status` and the canary result remain failure. Delivery failure is
a secondary field and cannot turn the result into success or replace
`PRE_RUN_FAILED` during finalization.

The existing script-supervisor containment implementation is unchanged. The
manifest pins `_close_script_pipes`, `_linux_process_probe`,
`_read_supervisor_start`, `_read_supervisor_status`, `_kill_known_target_group`,
`_cleanup_linux_supervisor`, `_cleanup_preserving_exception`, and
`_run_script_process` as baseline AST attestations. Candidate phase and
`test_existing_script_supervisor_ast_is_unchanged` refuse any change.

The exact test spies on AIAgent, SessionDB, prompt building, config/environment
readers, `resolve_runtime_provider`, `get_fallback_chain`,
`credential_pool.load_pool`, `discover_mcp_tools`, session setters, cwd/env
mutation, delivery, and business starters for agent-only, script+agent, and
no-agent cells.

## 10. Archive, import, restore, and MarketWatch ownership

`normalize_jobs_archive_members` preflights the entire archive before any
destination write, including non-jobs and `_external` members. It normalizes an
optional common `.hermes/` or `hermes/` prefix and rejects absolute paths,
traversal, symlinks, duplicate normalized paths, invalid profile names, duplicate
JSON object keys, nonfinite JSON, duplicate job IDs, and malformed jobs wrappers.
Jobs members are exactly root `cron/jobs.json` and
`profiles/<valid>/cron/jobs.json`.

Export remains the read-only baseline `hermes_cli.backup::run_backup` and is an
AST-unchanged attestation. `TestRoundTrip.test_backup_then_import` proves its
archive, including default and named-profile jobs stores plus non-jobs members,
is accepted by the new whole-archive importer without an export-side writer or
format fork.

A zero-jobs archive still restores all valid non-jobs content. After the one
read-only preflight and before `hermes_root.mkdir` or any destination creation,
normal import fixes this order independent of ZIP order:

1. internal non-jobs members by lexical normalized path;
2. `_external/` non-jobs members by lexical normalized path;
3. required profile alias/wrapper or other derived non-jobs work;
4. jobs stores last: default `cron/jobs.json`, then named profiles in lexical
   profile order through `_commit_jobs_operation`.

Each ordinary member writes a sibling temporary, applies its validated mode,
fsyncs, atomically replaces, and exact-readbacks before the next member. No
filesystem mutation occurs after the first jobs-store commit except later
ordered jobs-store commits. Attempt-created empty directories/temporaries are
removed on a zero-commit known refusal. There is no false cross-store or
whole-archive transaction claim. Unknown top-level jobs-wrapper fields are
preserved as validated candidate data, not silently dropped.

The ordered per-member/derived-step/store result distinguishes `UNCHANGED`,
`REPLACED`, `REFUSED_NO_WRITE`, `COMMIT_UNKNOWN`, and `NOT_ATTEMPTED`, including
the unattempted suffix. Aggregate is `REFUSED_NO_WRITE` only when the target tree
is exact-unchanged and zero commits were verified; `PARTIAL` when at least one
member/derived/store commit is verified and a later known refusal occurs;
`COMMIT_UNKNOWN` whenever the current replace/fsync/readback postimage is
uncertain; and `COMPLETE` only when every planned member/store/required derived
step is verified unchanged or replaced. Stop at the first failure or unknown
and never roll back a prior verified commit. Tests inject internal and external
non-jobs failures and prove zero jobs-owner calls; default-jobs success followed
by named-profile refusal proves jobs-phase PARTIAL; default commit uncertainty
proves no named-store call; zero-jobs proves COMPLETE; and shuffled ZIP order
proves the fixed jobs-last order.

`agent.curator_backup::_restore_cron_skill_links`, `run_import`,
`restore_quick_snapshot`, and `restore_cron_jobs_if_emptied` enter the same jobs
owner directly. Shipped/root `restore.sh` files remain caller witnesses.

In both MarketWatch holiday-manager copies, `_save_jobs` is deleted and pause or
resume invokes the exact Hermes owner. Both holiday-watchdog copies and
`enforcement/calibration_cron_watchdog.py::scan_and_recover` are read-only and
never clear a claim. Both `_extract_backup.py::safe_extract` copies inspect the
whole archive and refuse before any write if any normalized live-jobs member is
present; an archive with no jobs members is restored normally.

## 11. Controlled activation, loaded bytes, and Git handoff

Ordinary startup with no controlled expectation is behaviorally unchanged. A
controlled deployment uses one process-local opt-in expectation parsed by the
launcher before claim-path imports. Under the one-deployer/no-concurrent-checkout
mutation axiom, the launcher proves a clean deployed checkout/OID before the
child imports. Failure leaves cron admission CLOSED but does not make ordinary
messaging/readiness fail.

Read-only dependency modules outside the 25 paths are not changed to self-record.
One central `gateway.status::observe_loaded_cron_runtime` inspects already-loaded
module and callable objects only after provider resolution and before OPEN. The
exact base set for every route is `cron.jobs`, `cron.scheduler`,
`cron.scheduler_provider`, `hermes_cli.config`, `hermes_cli.profiles`, and
`hermes_cli.auth`. Chronos routes add `plugins.cron_providers`,
`plugins.cron_providers.chronos`, and
`plugins.cron_providers.chronos._nas_client`; GATEWAY HTTP adds
`gateway.platforms.api_server`; dashboard/Electron HTTP adds
`hermes_cli.web_server`; CANARY adds `hermes_cli.cron` and `hermes_cli.main`;
MANUAL adds `tools.cronjob_tools` plus the source-real entry module for its exact
host. `FINITE_SCOPE_V1.json::routes[].loaded_modules` and
`entrypoint_modules_by_host` are the literal route/role membership relation;
omission or same-count substitution refuses.

Disk HEAD/blob is only deployed identity. `LoadedObjectProofV1` is exactly
`(role,profile,pid,process_start,module_name,module_origin,loader_name,
checkout_root,deployed_oid,path,git_blob_sha256,object_kind,qualname,
code_projection_sha256,binding_projection_sha256,status,reason)`. For modules,
the code projection includes executed module code, imports, assignments, class
bases/decorators/bodies, defaults and closures. For each changed protected
callable it includes the live `__code__` graph (`co_code`, constants, names,
vars, flags, free/cell vars, defaults, keyword defaults and closure cell
values) and declared direct global callable bindings. The observer compares
that projection with objects compiled from `Dh:path` by the canonical product
Python 3.11 without executing them. Status is exactly `VERIFIED` or `REFUSED`;
all other fields are required on VERIFIED and `reason` is required on REFUSED.
`inspect.getsource`, re-reading current disk as a substitute for a live object,
same-size/count evidence, or a post-hoc process verifier is invalid. Stale-loaded
with restored disk, mixed root/OID/blob, missing object, dirty checkout, wrong
entrypoint set, or selected-provider mismatch leaves cron CLOSED before first
store open or claim.

The complete Git chain is:

- Hermes: fresh reviewed candidate `Ch`; fresh canonical-remote candidate `Rh`;
  `Ch == Rh`; approved/QA-bound merge `Mh` contains `Rh`; deployed clean
  `Dh == Mh`; every active observation
  `R[role, profile, pid, start] == Dh`.
- MarketWatch: `Cmw == Rmw`; approved merge `Mmw` contains it; deployed clean
  `Dmw == Mmw`.

The only canonical authorities are Hermes URL
`https://github.com/kendeng300/hermes-agent.git` at freshly fetched
`refs/remotes/origin/main`, and MarketWatch URL
`https://github.com/kendeng300/marketwatch.git` at freshly fetched
`refs/remotes/origin/master`. A similarly named remote, stale local ref, tag,
local branch, or wrong default branch refuses.

The sole handoff owner is
`gateway.status::accept_controlled_deployment(*, hermes_root,
marketwatch_root, approved_artifacts, intended_roles, launch) ->
ControlledAcceptanceV1`. It performs exactly: CLOSE, DRAIN, owner-prove every
old role STOPPED, fresh-fetch and verify MarketWatch URL/ref/ancestry and
`Cmw/Rmw/Mmw/Dmw`, fresh-fetch and verify Hermes URL/ref/ancestry and
`Ch/Rh/Mh/Dh`, launch each child with the immutable expectation before claim
imports, receive each child's pre-store loaded-object verification, aggregate
the exact intended `STOPPED | VERIFIED` role set, then OPEN. It never mutates a
checkout while an old role is live and never verifies a child after admission.

`ControlledAcceptanceV1(status, Ch, Rh, Mh, Dh, Cmw, Rmw, Mmw, Dmw,
role_receipts, reason)` is `ACCEPTED` only when every identity is present and
the full order completed; it exits 0. A known prelaunch/preclaim failure is
`REFUSED`, exits 2, leaves CLOSED, and performs zero store open/claim. An
uncertain launch/stop/receipt is `AMBIGUOUS`, exits 3, leaves CLOSED, and is
never reported as STOPPED or VERIFIED. This object, not a READY file, is the
terminal deployment handoff.

Deploy and verify MarketWatch before Hermes. Strict acceptance enumerates every
intended resident role and requires owner-proved `STOPPED` or live `VERIFIED` at
Dh; absence from a scan is not STOPPED proof. Rollback is allowed only after
CLOSED+DRAINED with no ACTIVE claim and repeats the same proof. SYS-1029, not
SYS-1030, owns product canaries and resume after deployment.

Git branches and commits are the only durable process checkpoint. No READY flag,
local lineage file, or VCS replica is added. After interruption, fetch/checkout
the latest branch and rerun the finite preflight plus required tests.

## 12. Finite preflight contract

`FINITE_SCOPE_V1.json` contains:

- the two pinned commit OIDs, canonical URLs/refs, and literal 25 production
  paths;
- every protected changed/added/deleted/unchanged-attested whole function,
  baseline-exact signature/dynamic sites, an independent authority inventory,
  and exact caller-to-callee counts;
- the ten exact route×occurrence×host/role×claim×submit×finalizer×re-arm and
  loaded-module relations, shutdown owners, closed result schemas, complete
  `save_jobs` reverse migration, and exact test nodes;
- five current subject artifacts, two Git-history evidence files, and three
  retired artifacts that must remain absent.

`validate_finite_scope_v1.py` is read-only and uses Git-object commands for
production bytes. In manifest phase it checks schema, exact scope, source
existence, canonical AST hashes, routes/hosts/roles, and test-node syntax. In
candidate phase it additionally refuses production paths outside 25, unlisted
changed functions, wrong dispositions, changed attestations or baseline-exact
signatures/defaults/decorators, any residual module/import/assignment/class
change after declared whole functions are removed, missing or substituted
direct authority calls, and new/changed reflection, namespace lookup, dynamic
import, callable-result, lambda-callee, subscript-callee, escaped callable, or
string-constructed authority selection.

Candidate OIDs must be Git commit objects. The invoked checker and manifest must
be byte-equal to their blobs in the candidate commit. Candidate mode requires
exactly five external `--approved-artifact-sha256 PATH=HASH` arguments; those
bind the proposal, pointer, manifest, checker, and current DMAIC bytes without a
self-referential candidate hash. It requires all five current artifacts and two
history files present, all three retired artifacts absent, and every required
test file plus exact Python qualname present in candidate Git objects. It
re-derives the pinned semantic reverse set of public `save_jobs` and requires
complete migration with zero candidate reference. The coordinator also supplies
`--hermes-fetched-ref-oid` and `--marketwatch-fetched-ref-oid`; each must be a
commit object equal to the configured exact canonical ref after the
coordinator's fresh fetch. Fresh-fetch timing and the full OID handoff belong to
that named coordinator, not a local state file.

A literal Name/Attribute call resolved from a static import is direct. Authority
callables may not be assigned, returned, placed in a container, passed to a
generic dispatcher, selected by reflection/namespace lookup/dynamic import,
nested as a callee factory, or indexed as a subscripted callee. An unavoidable
baseline exception requires one exact `BaselineSiteV1`, one targeted test, and
spec review; adding general analyzer logic is not the remedy.

The checker result is exactly
`{"status":"PASS|REFUSED","errors":[{"code":...,"path":...,
"qualname":...,"detail":...}]}` and errors are empty iff PASS. Counts and
digests are observations, not semantic proof. The
parameterized behavioral tests prove runtime meanings; the checker only proves
finite scope and syntax-level authority structure.

## 13. Required proof nodes

Hermes must contain and pass these literal nodes:

- `tests/cron/test_sys1030_scope_preflight.py::test_exact_25_path_and_changed_function_contract`
- `tests/cron/test_sys1030_scope_preflight.py::test_direct_authority_calls_and_baseline_attestations`
- `tests/cron/test_sys1030_scope_preflight.py::test_module_class_signature_partition_rejects_undeclared_change`
- `tests/cron/test_sys1030_scope_preflight.py::test_constructed_authority_and_dynamic_site_complement`
- `tests/cron/test_sys1030_scope_preflight.py::test_subject_artifacts_and_real_test_nodes_are_candidate_bound`
- `tests/cron/test_sys1030_scope_preflight.py::test_canonical_remotes_and_refs_are_exact`
- `tests/cron/test_sys1030_scope_preflight.py::test_authority_inventory_and_edges_are_exact`
- `tests/cron/test_sys1030_route_matrix.py::test_ten_routes_every_cut_claim_finalize_rearm_release`
- `tests/cron/test_sys1030_route_matrix.py::test_exact_route_relation_rejects_same_count_substitution`
- `tests/cron/test_sys1030_route_matrix.py::test_closed_result_schemas_reject_unlisted_cross_products`
- `tests/cron/test_sys1030_route_matrix.py::test_total_cut_restart_matrix_has_literal_postimages`
- `tests/cron/test_sys1030_route_matrix.py::test_closed_result_schemas_reject_unlisted_cross_products`
- `tests/cron/test_sys1030_route_matrix.py::test_total_cut_restart_matrix_has_literal_postimages`
- `tests/cron/test_jobs.py::test_scheduled_claim_total_union_and_restart`
- `tests/cron/test_jobs.py::test_canary_B_C2_four_leaf_conservation`
- `tests/cron/test_jobs.py::test_cross_process_lock_unavailable_refuses_before_read`
- `tests/cron/test_jobs.py::test_canary_cli_results_and_post_c2_cuts`
- `tests/cron/test_jobs.py::test_parent_dead_child_live_skip_refuses`
- `tests/cron/test_jobs.py::test_no_public_raw_jobs_writer`
- `tests/cron/test_scheduler_shutdown.py::test_nine_hosts_eleven_roles_close_snapshot_drain`
- `tests/cron/test_scheduler_shutdown.py::test_all_host_shutdown_owners_close_snapshot_before_kill`
- `tests/cron/test_scheduler_provider.py::test_auth_profile_binding_before_first_store_open`
- `tests/cron/test_scheduler_provider.py::test_loaded_claim_modules_are_actual_imported_bytes`
- `tests/cron/test_scheduler_provider.py::test_exact_loaded_module_sets_and_live_code_objects`
- `tests/gateway/test_status.py::test_git_candidate_merge_deploy_live_role_chain`
- `tests/gateway/test_status.py::test_acceptance_coordinator_order_and_typed_handoff`
- `tests/hermes_cli/test_backup.py::test_whole_archive_jobs_last_and_truthful_partial`
- `tests/hermes_cli/test_backup.py::TestRoundTrip.test_backup_then_import`
- `tests/cron/test_scheduler.py::test_prerun_failure_constructs_nothing_and_dominates`
- `tests/cron/test_scheduler.py::test_existing_script_supervisor_ast_is_unchanged`

MarketWatch must contain and pass both-copy owner/read-only/extractor nodes listed
in `FINITE_SCOPE_V1.json`. Each proof suite must kill omission, same-count
substitution, indirect dispatch, wrong owner, wrong route/cut, stale/newer claim,
duplicate ID, unauthorized field mutation, foreign-node skip, stale-loaded versus
current-disk substitution, wrong OID, partial-archive success lies, and one
forbidden pre-run constructor.

All affected existing tests in the two repositories also run. Test files are
self-contained schedulable units, create data only below their worker-owned test
directory, clean stale owned data before execution, and clean owned data in
`finally`. No test depends on systemd, xdist, a service manager, a global mutex,
or infrastructure outside user space.

## 14. Loop-1 release rule

This specification advances only when:

1. the finite manifest phase passes under product Python 3.11 against both pinned
   sources;
2. Architecture/Runtime, Systems/Concurrency/Data, and Product/Operations audit
   the same exact candidate bytes and coauthor them 3/3;
3. independent Six Sigma QA verifies C01–C13 changed from 13 to zero;
4. three independent formal reviewers then approve the same exact bytes.

Loop 2 cuts/uses the branch, implements strictly to this specification, batches
all review findings into one correction, commits/pushes immediately after each
batch, and aims for approval in two to three iterations. Loop 3 checks out the
latest branch before each full unit/gate run; after a batched panel-authored fix,
it commits and pushes before rerunning. The root runner remains an observer and
never authors a correction.
