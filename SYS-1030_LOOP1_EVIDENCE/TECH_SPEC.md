# SYS-1030 — Close cron dispatch, canary, and pre-run failure semantics

Status: Loop 1 specification; implementation and tests NOT RUN

Coauthors: Systems Panel, Runtime DevOps Panel, Six Sigma Panel

## 1. Outcome and boundary

SYS-1030 supplies the Hermes prerequisite for MarketWatch SYS-1029. It makes three existing cron operations executable and crash-explicit:

1. an operator can run exactly one full scheduled-job attempt while the job remains paused;
2. a recurring scheduled occurrence is claimed in `jobs.json` atomically before pool submission, including stale catch-up; and
3. a pre-run script failure returns a failed execution before `AIAgent` import or construction and remains failed through output, delivery, and job status.

This change adds no state store, ledger, mutex, daemon, service, process group, host scan, READY file, or result cache. Existing `cron/jobs.py::_jobs_lock`, `_jobs_file_lock`, atomic `save_jobs`, job fields, output writer, delivery path, and scheduler pools remain the only authorities. Existing `cron/scheduler.py::_run_script_process`, `cron/script_supervisor.py`, `start_new_session=True`, and `os.killpg` containment are unchanged.

Loop 2 may edit only the owners, callers, and tests named here. Production code must be panel-authored and independently approved by all three panel roles before merge.

## 2. Pinned source and present defects

Baseline repository: `kendeng300/hermes-agent`, `origin/main` and Loop-1 parent `82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`.

| Source owner | Present behavior | Defect |
|---|---|---|
| `cron/jobs.py::_get_due_jobs_locked` (1829–2180) | For a recurring job stale beyond catch-up grace, writes a provisional future `next_run_at`, saves, but returns the pre-write copied job. | The occurrence has been consumed without a dispatch claim. |
| `cron/jobs.py::advance_next_run` (1690–1727) | Reloads the row, recomputes that same future value, and returns `False` when it equals stored `next_run_at`. | Stale catch-up cannot produce the promised claim. |
| `cron/scheduler.py::tick` (4152 onward) | Calls `advance_next_run(job_id)` but ignores its Boolean result, then submits. | An unclaimed recurring occurrence can execute. |
| `cron/jobs.py::claim_dispatch` (1595–1655) | Persists only finite one-shot repeat claims; recurring jobs return `True` without mutation. | It does not close the recurring gap. |
| `cron/scheduler.py::run_job` (2990 onward) | Agent-mode setup imports `AIAgent` and opens session machinery before `_run_scheduled_job_script`; script failure is injected into an agent prompt. | The agent can turn a failed prerequisite into an apparent success. |
| `cron/scheduler.py::run_one_job` (3932–4131) | Owns execution, output save, delivery, and `mark_job_run`, but normal finalization changes recurrence and cannot be used while paused. | Operators lack a pause-preserving full-route canary. |
| `cron/jobs.py::trigger_job` (1438–1451) and `hermes cron run` | Enable and schedule a job. | Unsafe for SYS-1029 paused canaries. |
| `cron/scheduler_provider.py::CronScheduler.fire_due` (85–105) and `tools/cronjob_tools.py::_execute_job_now` (642–701) | Use `claim_job_for_fire` then `run_one_job`. | Must retain atomic claims and common finalization semantics. |

The stale-catch-up failure is exact: stored stale `S0` is advanced by due selection to `S1`; `advance_next_run` reloads `S1`, computes `S1`, returns false, and writes no `dispatch_claim`; `tick` ignores false and submits. Loop 2 removes that split ownership.

## 3. Common scalar rules

- `JobId` and claim identifiers are nonempty UTF-8 strings without surrounding whitespace.
- `UtcInstant` is an aware UTC RFC3339 string with six fractional digits and terminal `Z`.
- `ScheduledFor` is the exact persisted `next_run_at` string admitted for an occurrence, after strict parse to `UtcInstant`.
- `OccurrenceKey = job_id + "|" + scheduled_for`; no clock or random value participates.
- Every request timestamp is sampled once by the public owner before acquiring `_jobs_lock`; code beneath the lock never samples another time for that operation.
- JSON equality below means exact typed field equality after job normalization, not object identity or truthiness.
- Every store mutation is one `load_jobs` → validate → mutate → `save_jobs` critical section under the existing cross-process `_jobs_lock`. A save failure yields `STORE_FAILED`; no caller may submit or report success.

## 4. Atomic recurring dispatch claim

### 4.1 Types and owner

Target owner:

```python
cron.jobs.claim_recurring_dispatch(
    request: RecurringDispatchClaimRequestV1,
) -> RecurringDispatchClaimResultV1
```

```text
RecurringDispatchClaimRequestV1 = {
  schema: "cron-recurring-dispatch-claim-request-v1",
  job_id: JobId,
  expected_scheduled_for: ScheduledFor,
  claimed_at: UtcInstant,
  claimant: nonempty str
}

RecurringDispatchClaimV1 = {
  schema: "cron-recurring-dispatch-claim-v1",
  claim_id: OccurrenceKey,
  occurrence_key: OccurrenceKey,
  scheduled_for: ScheduledFor,
  next_run_after: UtcInstant,
  claimed_at: UtcInstant,
  by: nonempty str,
  status: "CLAIMED" | "DISPATCHED" | "NOT_SUBMITTED"
}

RecurringDispatchClaimResultV1 =
  CLAIMED {job: complete normalized postimage, claim: RecurringDispatchClaimV1}
| REFUSED {job: null, claim: null, reason:
    "NOT_FOUND" | "DISABLED" | "PAUSED" | "NOT_RECURRING" |
    "MALFORMED_NEXT_RUN" | "NOT_DUE" | "PREIMAGE_CHANGED" |
    "SUCCESSOR_UNAVAILABLE" | "ALREADY_CLAIMED"}
| STORE_FAILED {job: null, claim: null, reason: exact exception class/message}
```

Only schedule kinds `cron` and `interval` are recurring. The owner validates the stored row still has `enabled is True`, `state != "paused"`, and `next_run_at == expected_scheduled_for`; rejects a claim for the same occurrence; computes the first successor strictly greater than `claimed_at`; and persists both `next_run_at=next_run_after` and `dispatch_claim=claim` in one save. No provisional advance occurs in due selection.

A claim left by an older occurrence does not block a later scheduled time: after validating that the new `expected_scheduled_for` differs from the old claim's `scheduled_for`, the owner replaces it with the new claim in the same atomic save. A matching occurrence in any claim status returns `ALREADY_CLAIMED`. This retains one current claim field without growing history or creating a second authority.

`cron.jobs.set_dispatch_claim_status(job_id, *, expected_claim_id, status)` becomes an exact compare-and-set: only the same claim may transition `CLAIMED→DISPATCHED` after accepted `pool.submit`, or `CLAIMED→NOT_SUBMITTED` when submission is refused/raises. It never invents a claim and never changes occurrence identity or successor. Target `cron.jobs.mark_job_run(job_id: str, success: bool, error: Optional[str] = None, delivery_error: Optional[str] = None, *, expected_dispatch_claim_id: Optional[str] = None) -> None` clears only the exact matching claim handed to the runner; for that preclaimed recurring run it preserves `next_run_at == claim.next_run_after` instead of recomputing it, and increments `repeat.completed` exactly once only after execution. It must not clear a later claim. A crash before finalization consumes the occurrence but does not falsely count it completed.

### 4.2 Callers and order

`cron.scheduler.tick` performs, per returned recurring row:

1. copy the row's exact `next_run_at` as `expected_scheduled_for`;
2. call `claim_recurring_dispatch`;
3. submit only a `CLAIMED` postimage;
4. after accepted submit, CAS status to `DISPATCHED`; and
5. hand `claim_id` to `run_one_job` for matching finalization.

`_get_due_jobs_locked` may normalize/repair malformed legacy rows, but it must not advance any valid due recurring `next_run_at`. Stale catch-up returns one due row with its original stale scheduled time. The claim collapses all missed times into that one occurrence and stores the first future successor. It never emits one attempt per missed slot.

`cron.scheduler_provider.CronScheduler.fire_due(job_id, *, scheduled_for, adapters=None, loop=None) -> bool` supplies the provider-observed scheduled time and calls the same claim owner before `run_one_job`. `cron.jobs.claim_job_for_fire` remains the owner for operator-immediate fires and one-shot provider claims, but its recurring provider branch delegates to `claim_recurring_dispatch`; it may not separately advance recurrence. `tools/cronjob_tools.py::_execute_job_now` remains the manual immediate route and does not masquerade as a scheduled occurrence.

### 4.3 Crash and ambiguity contract

| Cut | Durable row | Restart action |
|---|---|---|
| before claim save | old due `next_run_at`; no claim | next tick may claim it |
| after atomic save, before submit | future successor; `CLAIMED` | do not replay old occurrence; later successor remains schedulable |
| submit rejected/raises | future successor; `NOT_SUBMITTED` | do not replay old occurrence; report scheduler error |
| submit accepted, before status CAS | future successor; `CLAIMED` | execution is ambiguous; do not replay old occurrence |
| after `DISPATCHED`, before execution starts | future successor; `DISPATCHED` | do not replay old occurrence |
| during/after job effects, before final mark | future successor; claim remains | do not replay old occurrence; retain output/effect evidence already written |
| after exact final mark | future successor; matching claim absent | normal next occurrence |

The system promises at-most-once dispatch, not exactly-once execution. It deliberately accepts a missed occurrence in the submit/crash ambiguity window rather than duplicate external effects. No watchdog, recovery replay, PID record, or secondary claim ledger is introduced.

## 5. Pause-preserving full-job canary

### 5.1 Public command, types, and claim

Target CLI, with no aliases or implicit resume:

```text
hermes cron canary <job_id>
```

`hermes_cli/subcommands/cron.py::build_cron_parser` adds exactly the `canary` action and one positional `job_id`. `hermes_cli/cron.py::cron_command` calls:

```python
cron.scheduler.run_paused_job_canary(
    job_id: str, *, adapters=None, loop=None, verbose: bool = False
) -> PausedCanaryRunResultV1
```

Store owners:

```python
cron.jobs.claim_paused_job_canary(
    request: PausedCanaryClaimRequestV1,
) -> PausedCanaryClaimResultV1

cron.jobs.finish_paused_job_canary(
    request: PausedCanaryFinishRequestV1,
) -> PausedCanaryFinishResultV1
```

```text
PausedJobPreimageV1 = {
  enabled: false, state: "paused", paused_at: UtcInstant,
  paused_reason: str|null, next_run_at: str|null,
  schedule: complete JSON object, repeat: complete JSON object|null
}
PausedCanaryClaimRequestV1 = {
  schema: "cron-paused-canary-claim-request-v1", job_id: JobId,
  expected: PausedJobPreimageV1, claimed_at: UtcInstant, claimant: nonempty str
}
PausedCanaryClaimV1 = {
  schema: "cron-paused-canary-claim-v1", claim_id: nonempty str,
  claimed_at: UtcInstant, by: nonempty str, expected: PausedJobPreimageV1,
  status: "CLAIMED"
}
PausedCanaryClaimResultV1 =
  CLAIMED {job: complete normalized postimage, claim: PausedCanaryClaimV1}
| REFUSED {job:null, claim:null, reason:
    "NOT_FOUND"|"NOT_PAUSED"|"PREIMAGE_CHANGED"|"CLAIM_PRESENT"}
| STORE_FAILED {job:null, claim:null, reason: exact exception class/message}
```

The claim ID is exactly `job_id + "|CANARY|" + claimed_at`; the store recomputes it from the request and rejects every supplied or persisted mismatch.

The claim is stored only in the existing `fire_claim` field, tagged `mode:"PAUSED_CANARY"`; it writes no schedule, enabled, state, pause, next-run, repeat, run-claim, or dispatch-claim field. A foreign/current fire claim refuses. `trigger_job` and `resume_job` are never called.

```text
PausedCanaryFinishRequestV1 = {
  schema: "cron-paused-canary-finish-request-v1", job_id: JobId,
  claim_id: nonempty str, expected: PausedJobPreimageV1,
  finished_at: UtcInstant, execution_success: bool,
  execution_error: str|null, delivery_error: str|null
}
PausedCanaryFinishResultV1 =
  FINISHED {job: complete normalized postimage, claim_id,
            last_status:"ok"|"error", last_error:str|null,
            last_delivery_error:str|null}
| CONFLICT {job:null, claim_id, reason:
    "NOT_FOUND"|"CLAIM_MISSING"|"CLAIM_CHANGED"|"PAUSED_PREIMAGE_CHANGED"}
| STORE_FAILED {job:null, claim_id, reason: exact exception class/message}
```

The finish request is valid only when `(execution_success is true) == (execution_error is null)`. Under `_jobs_lock`, `finish_paused_job_canary` requires the matching claim and byte-equal paused preimage. It updates only `last_run_at=finished_at`, `last_status="ok" if execution_success else "error"`, `last_error=execution_error`, and `last_delivery_error=delivery_error`, then clears the matching `fire_claim`. It never increments `repeat.completed`, computes `next_run_at`, deletes/completes the job, clears pause fields, or clears another claim.

```text
PausedCanaryRunResultV1 =
  PASS {job_id, claim_id, output_path, delivery_status:"DELIVERED"|"NOT_CONFIGURED"}
| JOB_FAILED {job_id, claim_id, output_path, error, delivery_error:str|null}
| DELIVERY_FAILED {job_id, claim_id, output_path, error}
| REFUSED {job_id, claim_id:null, reason}
| FINALIZE_CONFLICT {job_id, claim_id, output_path:str|null, reason}
| STORE_FAILED {job_id, claim_id:str|null, output_path:str|null, reason}
```

`PASS` requires successful job execution, successful output persistence, delivery success when configured, and successful pause-preserving finalization. CLI prints exactly one JSON object plus LF and exits 0 only for PASS; exits 2 for syntax/job refusal, 3 for job/delivery failure, and 4 for store/finalization/internal failure. Diagnostics go to stderr.

`run_paused_job_canary` reads the normalized row once, constructs `PausedJobPreimageV1`, samples `claimed_at`, claims it, and passes only the returned postimage into the shared route. A failed read/claim performs no execution. It samples `finished_at` only after output and delivery, submits the exact finish request, then rereads and compares every protected field before returning PASS.

### 5.2 Shared full route and restart cuts

`cron.scheduler.run_one_job` gains a private execution/finalization context rather than a second executor. Both ordinary and canary calls traverse exactly: `run_job` → existing output save → existing configured delivery → one injected finalizer. Ordinary finalizer is `mark_job_run`; canary finalizer is `finish_paused_job_canary`. The canary may not stub or bypass agent/no-agent execution, output, delivery, timeout, or cleanup quarantine.

| Cut | Durable job | Recovery |
|---|---|---|
| before canary claim | exact paused preimage | operator may retry |
| after claim, before job call | paused + canary claim | result ambiguous; no automatic retry |
| after effects/output/delivery, before finish | paused + canary claim + any existing artifacts | no automatic retry or claim overwrite |
| finish save succeeds | paused; matching claim clear; last fields updated | terminal canary result |
| finish save fails/preimage differs | row remains paused; claim/artifacts retained | `FINALIZE_CONFLICT`/`STORE_FAILED`; operator investigates |

No time-expiry reclaim is allowed because a crashed canary may have produced external effects. A separate operator repair callable `cron.jobs.clear_paused_canary_claim(job_id, *, expected_claim_id, expected: PausedJobPreimageV1) -> bool` may clear only an exact matching claim while the exact paused preimage remains. It never runs the job, resumes it, or changes recurrence. The CLI does not invoke this automatically.

The SYS-1029 release procedure uses two separate calls while both jobs are paused:

```text
hermes cron canary cci_precompute_runner
hermes cron canary bb_precompute_runner
```

Both must PASS, each paused row must read back with unchanged pause/schedule/next/repeat fields, and both output reports must be available before either job is resumed. Any failure leaves both paused and triggers rollback/investigation. Only after both pass may the operator run two explicit `hermes cron resume` commands.

## 6. Pre-run script failure is terminal

### 6.1 Closed execution product

```text
ScheduledJobExecutionV1 =
  SUCCEEDED {full_output:str, final_response:str, error:null, prerun_status:"OK"|"NOT_CONFIGURED"}
| SILENT {full_output:str, final_response:"", error:null, prerun_status:"OK"|"NOT_CONFIGURED"}
| FAILED {full_output:str, final_response:"", error:nonempty str,
          prerun_status:"FAILED"|"CLEANUP_UNVERIFIED"|"NOT_CONFIGURED"}
```

`cron.scheduler.run_job` retains its public four-tuple for compatibility, but it is a lossless projection of this union: success is true only for SUCCEEDED/SILENT; FAILED always returns false and the same nonempty error. No caller may infer success from nonempty diagnostic text.

For any configured script, `_run_scheduled_job_script` runs before importing `run_agent.AIAgent`, constructing `AIAgent`, opening/creating a SessionDB row, resolving an LLM provider, or building an agent prompt. On script failure it returns FAILED immediately. The failure output is still saved by `run_one_job`, its failure summary uses the existing delivery route, and finalization writes `last_status="error"` and the exact script error. Neither delivery success nor an agent response can change it to success.

Target `cron.scheduler._build_job_prompt(job, prerun_script)` never starts a script. For a scripted job, the argument must be the successful result already produced by `run_job`; missing or failed input raises before prompt/agent construction. This removes the present inline fallback and prevents any caller from bypassing the order by omitting the argument.

No-agent and agent routes share the rule. No-agent script success returns SUCCEEDED/SILENT as today. Agent-mode script success may feed validated stdout to `_build_job_prompt` and then construct the agent. `wakeAgent:false` success remains SILENT. `CronScriptCleanupError` retains its existing fail-closed quarantine/pause behavior and is never collapsed into an ordinary script error. Supervisor and process containment code are out of scope and unchanged.

### 6.2 Failure cuts

| Cut | Required result and effect |
|---|---|
| path/config validation fails | FAILED; zero script or agent spawn |
| script starts then exits nonzero/times out | FAILED; containment completes; zero AIAgent import/construction |
| cleanup cannot be attested | FAILED/CLEANUP_UNVERIFIED; existing quarantine remains authoritative; zero agent |
| script succeeds, output validation fails | FAILED; zero agent |
| script succeeds with `wakeAgent:false` | SILENT; zero agent; normal output/finalization |
| script succeeds with `wakeAgent:true` | only then may agent/session/provider work begin |
| output save fails | whole run/canary fails; no success status |
| delivery fails | execution status and delivery error remain distinct; canary is not PASS |

## 7. Mutation and invariant matrix

| Operation | enabled/state/pause | next_run | repeat.completed | fire_claim | dispatch_claim | last/output/delivery |
|---|---|---|---|---|---|---|
| recurring claim | unchanged | future successor | unchanged | unchanged | create CLAIMED atomically | unchanged |
| recurring submit accepted | unchanged | unchanged | unchanged | unchanged | matching CLAIMED→DISPATCHED | unchanged |
| recurring submit refused | unchanged | unchanged | unchanged | unchanged | matching CLAIMED→NOT_SUBMITTED | error log only |
| ordinary finalization | existing semantics | never rolls back claimed successor | existing semantics | existing semantics | clear matching only | update/save/deliver |
| paused canary claim | byte-equal paused | unchanged | unchanged | create tagged claim | unchanged | unchanged |
| paused canary finish | byte-equal paused | unchanged | unchanged | clear matching only | unchanged | update exact last fields; retain output/delivery |
| pre-run failure | unchanged until finalizer | per chosen finalizer | per chosen finalizer | per chosen finalizer | per chosen finalizer | failed output/delivery/status only |

Global invariants:

- a disabled or paused job is never selected by `tick` or provider scheduled fire;
- only the explicit canary route can execute a paused job, and it cannot enable it;
- one persisted recurring occurrence yields at most one pool submission attempt;
- `repeat.completed` changes exactly once under its existing one-shot/ordinary rules and never for a canary;
- pre-run failure admits zero AIAgent imports, constructions, or calls;
- all conflicts fail closed and preserve the last durable row.

## 8. Loop-2 source and proof inventory

Production EDIT owners:

- `cron/jobs.py`: `_get_due_jobs_locked`, `claim_recurring_dispatch`, exact-status CAS, `mark_job_run`, `claim_job_for_fire`, paused-canary claim/finish/clear; retire recurring use of `advance_next_run` without deleting unrelated compatibility until callers are migrated.
- `cron/scheduler.py`: `tick`, `_submit_with_guard`, `run_job`, `run_one_job`, `run_paused_job_canary`; no edits to `_run_script_process` or containment.
- `cron/scheduler_provider.py`: `CronScheduler.fire_due` scheduled-for handoff.
- `tools/cronjob_tools.py`: preserve immediate-run semantics and consume the common result/finalization path.
- `hermes_cli/subcommands/cron.py`, `hermes_cli/cron.py`, and command metadata in `hermes_cli/main.py`: exact canary CLI route.

Focused tests (CREATE where absent, otherwise EDIT):

- `tests/cron/test_jobs.py`: atomic recurring claim, stale and on-time schedules, false preimages, disabled/paused, same occurrence twice, successor failure, save failure, status CAS, matching-only clear, all crash postimages.
- `tests/cron/test_scheduler.py`: `tick` never submits without CLAIMED; submit exception/accepted ambiguity; one-shot unchanged; agent pre-run failure imports/constructs no agent and remains failed.
- `tests/cron/test_run_one_job.py`: full ordinary and canary execution→output→delivery→finalizer order; output/delivery/finalize failures; repeat/pause invariants.
- `tests/cron/test_scheduler_provider.py`: scheduled-for reaches the atomic owner; refusal makes zero `run_one_job` calls.
- `tests/cron/test_claim_job_for_fire.py`: manual/provider route partition and no double advance.
- `tests/tools/test_cronjob_run_immediate.py`: legacy immediate execution unchanged; canary result cannot be mistaken for it.
- `tests/hermes_cli/test_cron_parser_builder.py`: exact `cron canary JOB_ID` grammar and exit mapping.
- `tests/cron/test_sys1030_lifecycle.py` (CREATE): real isolated store integration covering paused agent/no-agent canaries, stale catch-up, restart cuts, output/delivery/readback, and SYS-1029 two-job release sequence.

Every test uses repository fixtures whose HERMES_HOME/cron/output/session roots are beneath `/home/linux/.hermes/test/sys1030/<case>`; each fixture validates and removes only its exact case root before and after. No `/tmp`, xdist, systemd, network, host scan, production jobs file, gateway process, or live delivery endpoint is used.

Deterministic RED→GREEN controls:

1. stale due selection followed by current `advance_next_run=False` still submits (RED); target atomic claim exists before exactly one submit (GREEN);
2. delete claim save or make its saved successor unequal and submission must be zero;
3. crash at each §4.3 cut and prove no duplicate old occurrence;
4. run paused finite-repeat one-shot through the full route: current trigger resumes/mutates (RED), target canary preserves every protected field (GREEN);
5. inject output, delivery, and finalization failures; no canary PASS;
6. failing pre-run plus a fake successful AIAgent: current can become successful (RED), target AIAgent import count is zero and final status is error (GREEN);
7. repeat for `no_agent=true`, `wakeAgent=false`, provider scheduled fire, and manual immediate fire;
8. mutate a foreign claim between execution and finalize; finalizer conflicts and never clears it.

## 9. Verification commands and acceptance

Loop 2 runs only after implementation, from a clean candidate checkout with an existing locked environment:

```text
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh -j 1 tests/cron/test_jobs.py tests/cron/test_scheduler.py tests/cron/test_run_one_job.py tests/cron/test_scheduler_provider.py tests/cron/test_claim_job_for_fire.py tests/tools/test_cronjob_run_immediate.py tests/hermes_cli/test_cron_parser_builder.py tests/cron/test_sys1030_lifecycle.py
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh -j 1 tests/cron tests/tools/test_cronjob_run_immediate.py tests/hermes_cli/test_cron_parser_builder.py
env TMPDIR=/home/linux/.hermes/test/sys1030/tmp scripts/run_tests.sh
```

The harness precreates the exact temp root, removes it afterward, and performs no dependency install. A missing locked environment is a verification refusal, not authority to mutate dependencies.

Acceptance requires all commands exit 0; no leaked case roots/processes; no diff outside the enumerated Loop-2 paths; source assertions showing containment functions byte-unchanged; exact paused-field and finite-repeat readback; stale/on-time claim cross-products; agent/no-agent/provider/manual coverage; and both SYS-1029 canary reports readable before resume. No production job is fired during tests.

## 10. Git, deployment, rollback, and resume

Git commits are the sole build and recovery identity. No local OID/status/READY replica is created.

1. Loop 1: this spec commit is pushed to `origin/fix/sys1030`; local HEAD must equal the remote branch OID and the worktree must be clean.
2. Loop 2: panel authors one implementation candidate OID `C`; push and require `C == origin/fix/sys1030`; all three reviewers approve those exact bytes.
3. Merge: record remote `origin/main` merge OID `M`, prove `C` is its ancestor, and deploy only `M` to the configured Hermes checkout. Require deployed checkout HEAD `D == M`, clean tracked/untracked state, and origin URL `https://github.com/kendeng300/hermes-agent.git`.
4. Restart the existing gateway with `hermes gateway restart`. Read back its PID from `hermes gateway status`, resolve `/proc/<pid>/cwd`, and require the running source checkout's Git HEAD `R == D == M` before any canary. If running-source identity cannot be proven, keep jobs paused and stop.
5. Confirm both SYS-1029 job records remain disabled/paused with expected schedule, `next_run_at`, repeat, and pause reason. Run the two full canaries in §5.2. Retain their outputs and reread unchanged protected fields.
6. Resume both jobs only after both canaries PASS and the SYS-1029 runtime/resource gates pass. A single failure keeps both paused.

Rollback deploys the recorded clean pre-merge Git OID, restarts the same gateway, proves running OID equality, and leaves the affected jobs paused. It never rewrites job history, fabricates a canary result, or replays an ambiguous recurring occurrence. Resume is a separate explicit operator action after corrected deployment and repeated readback.

## 11. Loop-1 completion criteria

This document is complete when it is the only added path, contains a final LF, is committed once with the required three coauthor trailers, is pushed, local HEAD equals `origin/fix/sys1030`, and the worktree is clean. No production/test implementation or runtime action is part of Loop 1.
