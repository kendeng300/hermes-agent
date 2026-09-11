# SYS-1030 Loop 1 — DMAIC Round-1 baseline

Status: predeclared comparison evidence; no implementation or tests

## Frozen subjects

- Round 1 subject commit: `b8b52dca072535f7aa4d3cd2af31a91255a2343a`
- Round 1 `TECH_SPEC.md` SHA-256: `6eae5473d97415c39039d8586bbd4d64305fdd80e2fa9ac2abe3fdcc4fd83a2c`
- Round 1 review result: 28 raw findings, 11 valid atomic blockers, 6 deduplicated causal families, 0/3 approvals.
- Round 2 TECH commit: `82a4ee8d5570eb7704f00f5795dcf90d3d3e177c`
- Round 2 `TECH_SPEC.md` SHA-256: `b874577967555c04cb75ba666a188e6b94cbb09f52800df9b04ae6345e2639e3`

## Root cause

R1 specified local happy-path APIs before closing each operation through every ingress, persisted representation, compatibility consumer, finalizer, restart path, live data shape, and deployment proof.

## Round-2 correction batch

The Round-2 review must test this complete seven-part correction as one batch:

1. **Scalar and lock foundations.** Separate exact stored aware timestamps from generated canonical UTC timestamps; use collision-safe typed claim identities; require the existing cross-process jobs lock to fail closed for every new claim, transition, finalization, and repair mutation.
2. **Recurring claim and Chronos ABI.** Define one versioned, total recurring-claim state machine; carry the exact scheduled occurrence through Chronos provisioning, signed callback, webhook, provider, and claim owner; preserve manual and one-shot semantics and fail closed when the scheduled occurrence cannot be verified.
3. **Compatibility-consumer closure.** Preserve or explicitly migrate legacy lowercase dispatch claims; update every root and shipped watchdog reader; prohibit replay or rearm of tagged SYS-1030 ambiguous claims; define the disposition of every legacy and unknown claim version.
4. **Execution-context and cleanup closure.** Thread a closed execution-mode and claim identity through submission, execution, cleanup, output, delivery, interruption, and finalization; canaries bypass finite one-shot accounting; no branch may clear a foreign or later claim.
5. **Canary conservation.** Claim and compare the complete normalized paused-job preimage plus canonical comparison digest; admit real stored offset timestamps; define every restart cut; run all five SYS-1029 jobs through the real execution, output, configured-delivery, and pause-preserving finalizer route.
6. **Total result products.** Give every request and result a closed schema, nullability, reason set, and aggregate failure precedence while retaining execution, output, delivery, and finalization leaf truth; invalid or malformed input refuses before mutation; pre-run failure can never become success.
7. **Proof and deployment.** Add mutation-sensitive lock, Chronos, legacy, mode, timestamp, preimage, result-product, shutdown-identity, and five-job tests; prove the configured running gateway's stable PID, executable, cwd, deployed Git OID, and merge OID without a host scan or new state authority.

## Predeclared Round-2 comparison

Outcome is `11 -> Y`; target `Y <= 2`; delta is `Y - 11`; required reduction is `((11 - Y) / 11) * 100 >= 81.8%`.

`Y` is the number of valid atomic defects after deduplicating all three Round-2 reviews using the stable key `(owner/interface + invariant + minimal counterexample)`. Raw comments and reviewer overlap are reported separately. Round 3 is permitted only for at most two localized integration defects already represented by the Round-2 correction; a P0 recurrence, regression, new authority or repository boundary, or `Y > 2` requires an RCA reset rather than another incremental correction.

## Control rule

Immediately after all three reviews of every current or future round, run and publish the DMAIC normalization, deduplication, causal analysis, and `X -> Y` comparison before authoring or applying any correction.
