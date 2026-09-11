# SYS-1030 Loop 1 — DMAIC R3 prescreen

Immutable subject: commit `9f96b58675704ea521b5cc67e311f1cfaabc5576`,
TECH Git blob `3081464fd071fdb33c70edcfaabe15284f1e095d`, file SHA-256
`d174318bb8d7d6945cf13577a05fad0cb0d9c183e599ecef372f14c6ed080038`.

## Measure

The prior review union contained 30 raw comments: 10 duplicates, one overbroad
claim, 19 frozen comparison items, two of those out of SYS-1030 scope, and 17
source-valid actionable items.

- Like-for-like actionable comparison: `17 -> 4 | -13 | 76.5% reduction | zero target FAILED`.
- Frozen control comparison: `19 -> 4 | -15 | 78.9% reduction | target <=2 FAILED by 2`.

## Analyze

RCA: `The fix was label-complete but not path-complete: it dispositioned all 19 review labels without proving each source path through its final consumer, leaving one-shot preparation, Chronos re-arm, managed outcome transport, and live-OID proof unowned.`

The four remaining blockers are one causal batch:

1. **B1 — One-shot preparation has no owner.** R3 makes
   `_get_due_jobs_locked` read-only, while current source stamps `run_claim` and
   removes exhausted one-shots there. Separate recurring candidate selection
   from the existing locked one-shot preparation owner; preserve its exact
   claim, exhaustion, and restart behavior.
2. **B2 — Chronos HTTP loses successor re-arm.** Current
   `ChronosCronScheduler.fire_due` owns `_arm_one_shot` after execution, but R3
   HTTP calls `run_claimed` directly. Make
   `ChronosCronScheduler.run_claimed` own post-finalization successor re-arm for
   both HTTP and synchronous paths, with a mocked-NAS assertion of exactly one
   correct re-arm and none on refusal/duplicate.
3. **B3 — Managed outcome cannot reach the canary.** Current `run_one_job`
   returns true when processing completes even when the job failed, while R3
   promises stage, output, delivery, finalization, and exit truth without an
   outcome owner. Define `ManagedRunOutcomeV1` from one internal owner; retain
   the bool wrapper for legacy callers; require canary and Chronos managed paths
   to consume the typed outcome and preserve failure dominance.
4. **B4 — Running OID has no read surface.** Current runtime status exposes no
   OID or loaded-module fields, and R3 names no callable or response. Define one
   live-process identity callable and read response containing PID, birth
   ticks, executable, loaded scheduler path, checkout, and OID without a state
   file; add its exact source inventory and one-field mutation tests.

## Improve gate

Apply B1 through B4 in one dependency-ordered correction, then reread the whole
proposal. The predeclared next result is
`4 -> 0 | cut 4 | 100% reduction`; no new authority, store, mutex, product-job
operation, NAS wire, digest authority, or downstream SYS-1029 acceptance may be
introduced.

## Control

- Freeze and identify exact candidate bytes before review; findings bind that
  immutable subject only.
- Normalize comments by `(owner/interface + invariant + minimal
  counterexample)` before counting; report raw, duplicate, overbroad,
  out-of-scope, and valid counts separately.
- A label closes only when its source owner, every caller, state cut, final
  consumer, restart successor, and mutation-sensitive oracle are literal.
- Independently enumerate expected owners and paths from source, never from the
  candidate or its disposition table.
- Any regression, P0 recurrence, new repository/authority boundary, product
  mutation, or candidate-derived expected set triggers STOP/RCA rather than a
  follow-on patch.
- Require exact-byte preapplication approval, apply one batch, and perform a
  whole-candidate reread. Formal review starts only after the `4 -> 0` prescreen
  passes; any residual means the target failed and requires another DMAIC
  decision before correction.
