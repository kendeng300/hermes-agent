# SYS-1030 Loop 1 — Round-3 independent prescreen 2

## Immutable subject

- Commit: `01e532481d065d3cd3f57258e463d41366f47159`
- Proposal blob: `9c524b1e4a2af053e8e2950db47e5e9f98b1067d`
- Proposal SHA-256: `29e64aa260c61c7ea1f06af2a51a027678863e013ef3ff3a6a084f43e2a4732f`
- Review result: `REJECT`; one valid atomic defect remains.

## Predeclared comparisons

- `4 -> 1 | -3 | 75.0% | expected 0 MISSED by 1`
- `17 -> 1 | -16 | 94.1%`
- `19 -> 1 | -18 | 94.7% | frozen target <=2 MET`

One-line RCA: `B2 fixed who re-arms but not where it runs: the split claim/result contract drops the resolver-selected profile/store/provider context, allowing the final consumer to execute against the caller's ambient profile.`

## Sole residual — R2-04 / ambient-profile Chronos continuation

Invariant: the exact profile, jobs store, and Chronos provider selected from
`(job_id, fire_at)` must remain the execution and successor-re-arm context
through the terminal consumer. Caller ambient context is never authority.

Exact A/B counterexample:

1. HTTP handler process context and its available `ChronosCronScheduler` are
   bound to profile A, jobs store A, and provider A.
2. `resolve_chronos_fire_target(job_id, fire_at)` uniquely selects a matching
   row in profile B/jobs store B; no row in A matches that occurrence.
3. B's claim commits correctly. The proposed `ChronosClaimResultV1` carries a
   job postimage and an `ExecutionContextV1` with jobs-file path, job ID, mode,
   and claim ID, but it does not carry the resolver-selected profile and bound
   Chronos provider as the required `run_claimed` receiver.
4. The handler can therefore invoke `run_claimed` on ambient scheduler A.
   Execution/finalization may address B through the jobs-file field while
   `ChronosCronScheduler.run_claimed` performs `_arm_one_shot` through provider
   A, or an ambient read can inspect store A. B's occurrence then has the wrong
   final consumer even though the initial resolver and claim were correct.

Minimum correction:

- Make `resolve_chronos_fire_target` return the exact in-memory target binding:
  selected profile, jobs-file realpath, and its already configured
  `ChronosCronScheduler`/provider instance. Add no durable field or new store.
- Invoke `claim_due` and `run_claimed` only through that returned bound
  scheduler. Carry selected profile and jobs-file realpath in the internal
  claim/result context.
- Before execution, finalization, or re-arm, `run_claimed` requires exact
  equality between its receiver's profile/store and the result context.
  Mismatch returns/refuses before job execution or `_arm_one_shot`; it never
  falls back to ambient profile lookup.
- The sole re-arm owner remains `ChronosCronScheduler.run_claimed`, using the
  provider on that verified receiver. The NAS wire and persistent schemas stay
  unchanged.
- Add the discriminating two-profile proof above: A ambient/B selected must
  claim, execute, finalize, and re-arm B exactly once through provider B while
  store/provider A remain untouched. Swapping the receiver or either context
  field must refuse with zero execution and zero re-arm.

## Next control point

Predeclared next result: `1 -> 0 | cut 1 | 100%`.

No correction may start from a summary or mutable identity. The bounded exact
proposal bytes must be corrected once, frozen, and independently reread as a
whole. Any residual, regression, new authority, persistent state, NAS change,
or ambient-profile fallback fails the zero-defect gate.
