# SYS-1030 Loop 1 — R3b panel-preflight MSA

Status: one correction-induced defect; evidence recorded before correction. No
proposal, product, runtime, scheduler, deployment, or test state is changed.

## Immutable subject

- Subject tip: `59b5280152a6495ee0b7525d81bff021c8a65462`
- Proposal blob: `21ef171b9e08439567ccf7fc4a542f761ca12c13`
- Proposal SHA-256: `77bed285e3a59a7ff03884feeaa42d383c29b0259e0703e0dfe8fde3a08a790b`
- Proposal size: 91,041 bytes / 1,397 LF lines

## Measure

- Panel findings: `2` raw; `1` exact duplicate; `1` valid
  correction-induced defect.
- Comparison: `6 -> 1 | delta -5 | 83.3% reduction | zero target missed by 1`.

## Analyze

RCA: `Mandatory deployment verification conflated ticket-specific acceptance with ordinary runtime admission, making unavailable Git/Linux evidence a global gateway outage.`

## Bounded correction

- Startup always publishes the closed observation `AVAILABLE|UNAVAILABLE`.
- Missing Git checkout, dirty development tree, non-Linux runtime evidence, or
  transient Git failure never blocks ordinary gateway readiness, adapters, or
  cron-provider startup.
- The strict build-identity CLI maps `UNAVAILABLE` to exit `4`.
- SYS-1030 deployment acceptance and the SYS-1029 handoff accept only
  `VERIFIED` with CLI exit `0`; ordinary startup is not acceptance evidence.

Deterministic negative controls exercise a non-Git packaged installation, a
dirty development checkout, a non-Linux environment, and transient Git
failure. Each gateway starts its ordinary readiness/adapters/provider path and
publishes `UNAVAILABLE`; each strict deployment check exits `4`, and neither
SYS-1030 acceptance nor the SYS-1029 handoff proceeds.

## Predeclared control

Next comparison: `1 -> 0 | delta -1 | 100% reduction`. Re-review exact corrected
bytes for this boundary and all six R3b families; any remaining or new valid
defect triggers stop/reset rather than another incremental correction.
