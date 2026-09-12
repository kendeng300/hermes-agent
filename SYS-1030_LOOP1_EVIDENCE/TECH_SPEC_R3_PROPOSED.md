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

These are closed internal types. They may be dataclasses, enums, or typed
records, but consumers must not substitute free strings or callbacks.

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

Every lookup by job ID requires exactly one row with a nonempty exact ID.
Duplicate IDs are `MALFORMED`: load/claim/finalize/skip/import performs zero
mutation and repair never silently selects or deletes one. Unknown, malformed,
or legacy claim objects block execution rather than being overwritten.

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
identity plus PID and process start identity. Automatic/local death proof is
valid only when machine and boot equal the current node and the exact PID/start
identity is absent or mismatched, with resolved script-supervisor containment.
A foreign or unavailable machine/boot identity refuses. There is no PID scan and
no inference that absence in local `/proc` proves a remote owner dead.

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

`ChronosCronScheduler.run_claimed` is the sole post-finalization one-shot re-arm
owner for synchronous and HTTP routes. Reconcile and other paths do not re-arm
an ACTIVE or cleanup-uncertain occurrence.

## 6. Pause-preserving canary conservation

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
resume, and trigger. Pre-API refusal may restore the exact B only when no API was
entered. Tests inject every store commit cut and attempt a second canary after an
operator-skipped C1.

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

Every protected claim-path module records its actual loader/spec origin and
loaded identity at import. After provider resolution the activation aggregate
includes entrypoint, jobs, scheduler, scheduler_provider, provider loader, exact
selected provider, applicable HTTP/manual owner, and config/profile/home/auth/
secrets/verifier/NAS dependencies.

Disk HEAD/blob is only deployed identity. For each changed protected callable,
controlled verification compares its actual live `__code__` and declared direct
global callable bindings to the corresponding code object compiled from
`Dh:path` by the canonical product interpreter, and binds module origin,
checkout, and selected provider class. `inspect.getsource`, current-disk reads
after import, or same-size/hash counts are not loaded-byte proof. Stale-loaded
with current disk, mixed root/OID/blob, missing module, dirty checkout, or
selected-provider mismatch leaves cron CLOSED.

The complete Git chain is:

- Hermes: fresh reviewed candidate `Ch`; fresh canonical-remote candidate `Rh`;
  `Ch == Rh`; approved/QA-bound merge `Mh` contains `Rh`; deployed clean
  `Dh == Mh`; every active observation
  `R[role, profile, pid, start] == Dh`.
- MarketWatch: `Cmw == Rmw`; approved merge `Mmw` contains it; deployed clean
  `Dmw == Mmw`.

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

- the two pinned source OIDs and literal 25 production paths;
- every protected changed/added/deleted/unchanged-attested function;
- exact direct authority edges and counts;
- the ten semantic routes, host/role axis, ordered stages, and exact test nodes.

`validate_finite_scope_v1.py` is read-only and uses Git-object commands for
production bytes. In manifest phase it checks schema, exact scope, source
existence, canonical AST hashes, routes/hosts/roles, and test-node syntax. In
candidate phase it additionally refuses production paths outside 25, unlisted
changed functions, wrong dispositions, changed attestations, missing or
substituted direct authority calls, dynamic or escaped authority callable use,
and string-built authority names.

A literal Name/Attribute call resolved from a static import is direct. Authority
callables may not be assigned, returned, placed in a container, passed to a
generic dispatcher, selected by reflection/namespace lookup/dynamic import,
nested as a callee factory, or indexed as a subscripted callee. An unavoidable
baseline exception requires one exact `BaselineSiteV1`, one targeted test, and
spec review; adding general analyzer logic is not the remedy.

The checker result is exactly
`{"status":"PASS|REFUSED","errors":[{"code":...,"detail":...}]}` and errors are
empty iff PASS. Counts and digests are observations, not semantic proof. The
parameterized behavioral tests prove runtime meanings; the checker only proves
finite scope and syntax-level authority structure.

## 13. Required proof nodes

Hermes must contain and pass these literal nodes:

- `tests/cron/test_sys1030_scope_preflight.py::test_exact_25_path_and_changed_function_contract`
- `tests/cron/test_sys1030_scope_preflight.py::test_direct_authority_calls_and_baseline_attestations`
- `tests/cron/test_sys1030_route_matrix.py::test_ten_routes_every_cut_claim_finalize_rearm_release`
- `tests/cron/test_jobs.py::test_scheduled_claim_total_union_and_restart`
- `tests/cron/test_jobs.py::test_canary_B_C2_four_leaf_conservation`
- `tests/cron/test_scheduler_shutdown.py::test_nine_hosts_eleven_roles_close_snapshot_drain`
- `tests/cron/test_scheduler_provider.py::test_auth_profile_binding_before_first_store_open`
- `tests/cron/test_scheduler_provider.py::test_loaded_claim_modules_are_actual_imported_bytes`
- `tests/gateway/test_status.py::test_git_candidate_merge_deploy_live_role_chain`
- `tests/hermes_cli/test_backup.py::test_whole_archive_jobs_last_and_truthful_partial`
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
