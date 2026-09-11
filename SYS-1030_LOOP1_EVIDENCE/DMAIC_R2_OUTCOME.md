# SYS-1030 Loop 1 — DMAIC Round-2 outcome

Status: frozen end-of-iteration comparison; no implementation or tests

## Frozen subject and result

- Round-2 subject HEAD: `3b9ce12a32843a59af380d62e8281d0cdce50507`
- Round-2 `TECH_SPEC.md` SHA-256: `b874577967555c04cb75ba666a188e6b94cbb09f52800df9b04ae6345e2639e3`
- Reviews: 30 raw findings; Product 7, Architecture 11, Systems 12; 0/3 approvals.
- Normalization key: `(owner/interface + invariant + minimal counterexample)`.

`11 -> 19 | +8 | -72.7% | target <=2 FAILED`

## Root cause

Round 2 expanded schemas and happy-path tables but again treated caller, consumer, restart, and deployment closure as prose, allowing source-real edge cases and cross-repository authorities to escape into review.

## Normalized 19-defect ledger

| ID | Defect invariant and minimal counterexample | Origin |
|---|---|---|
| R2-01 | Every `jobs.json` writer must acquire the existing cross-process lock strictly; otherwise a legacy pause/update/save writer can overwrite a concurrent strict claim. | Residual |
| R2-02 | Canonical claim/preimage bytes must be injective across string normalization, map keys, and numeric kinds; decomposed/composed Unicode or numerically similar distinct values must not share a digest. | Correction-induced |
| R2-03 | Schedule-successor computation needs a closed success/failure result; `None`, malformed output, or exception must leave the row unchanged. | Correction-induced |
| R2-04 | Chronos provision, JWT, callback body, profile/store selection, provider, and claim must bind one exact NAS repository/version, profile identity, job, and scheduled instant. | Residual |
| R2-05 | A webhook may return 202 only after its exact occurrence is durably claimed; background creation or submission failure must terminalize only that claim without job execution. | Correction-induced |
| R2-06 | A later occurrence may not overwrite an active or ambiguous same-job `claimed`/`dispatched` claim; only an exact terminal disposition permits replacement. | Correction-induced |
| R2-07 | A submitted worker must wait behind an in-memory start barrier until the matching DISPATCHED CAS succeeds; CAS failure admits zero business execution. | Correction-induced |
| R2-08 | A paused canary must claim the caller-approved complete job preimage and digest; recomputing whatever row exists inside the claim owner does not preserve approval. | Residual |
| R2-09 | Cleanup, quarantine, exception, output, delivery, interruption, and finalization must receive the exact mode and claim identity; a job-ID-only branch can clear or fail a later run. | Residual |
| R2-10 | `RunLeaf` must encode successful pre-run followed by agent/session/provider failure; pre-run success cannot imply route success. | Residual |
| R2-11 | Silent run output, configured suppression, whitespace-empty output, and unconfigured delivery require disjoint source-derived result variants. | Residual |
| R2-12 | A finite terminal finalizer that removes a job requires a legal `FINISHED_REMOVED` result rather than a mandatory nonnull job postimage. | Correction-induced |
| R2-13 | The named SYS-666 post-delivery completeness gate must be an exact route leaf; failure or gate exception cannot preserve canary success, while already-produced delivery evidence remains visible. | Newly exposed |
| R2-14 | Unknown modes, malformed rows/claims, contradictory leaf fields, missing claims, and illegal skipped stages require a total invalid complement and pre-effect refusal where applicable. | Residual |
| R2-15 | Canary results must propagate through parser, `cron_command`, main dispatch, stdout/stderr, and shell status; only PASS exits zero. | Residual |
| R2-16 | Deployment must prove the configured running process—not merely a checkout—by stable profile, PID, start ticks, executable, loaded scheduler path, and Git OID. | Residual |
| R2-17 | Both MarketWatch watchdog copies require one reviewed OID, parity proof, deployment order, and compatibility readback before Hermes V2 claim activation. | Residual |
| R2-18 | Merge/deployment identity must use a fresh canonical-remote fetch immediately before ancestry comparison; a stale remote-tracking ref is not proof. | Correction-induced |
| R2-19 | All five named full-route canaries form one release cohort; every canary must pass before a strict-lock batch resume, and any mismatch/save failure leaves or restores all five paused. | Residual |

Origin totals are 11 residual, 7 correction-induced, and 1 newly exposed.

The durable redesign of every one-shot occurrence claim is rejected as overbroad. Existing `run_claim`, finite `claim_dispatch`, repeat, heartbeat, exhaustion, and restart behavior remain unchanged except for the in-memory mode identity and exact matching cleanup needed for non-regression. An unidentified external NAS implementation is not invented: exact NAS identity and deployment are activation prerequisites, and Chronos remains fail-closed until they are proven. Stored aware offsets, including `-04:00`, and the requirement to use the complete `run_one_job` route are retained passing controls.

## Seven-part bounded correction

No correction may begin until one exact proposed `TECH_SPEC.md` byte sequence containing all seven parts receives 3/3 preapplication approval.

1. **Strict store and canonical foundations.** Close the writer fixed point over every `jobs.json` mutation using the existing cross-process lock; define an injective typed canonical codec; retain exact stored aware timestamps; and add a closed successor-computation result.
2. **Recurring claim lifecycle.** Forbid active same-job claim replacement, define exact terminal replacement/disposition, and gate workers behind matching DISPATCHED persistence without adding durable state or another mutex.
3. **Chronos ingress.** Bind exact NAS repository/version, profile/store, job, and scheduled instant through provision, signed JWT/body, both ingress callers, provider, and claim; persist the claim synchronously before 202 and fail closed when the external prerequisite is absent.
4. **Execution identity and canary conservation.** Require caller-pinned complete paused preimages/digests and route the exact mode/claim identity through every cleanup, quarantine, interruption, and finalizer branch while preserving existing one-shot behavior.
5. **Total route product.** Define all legal and invalid run/output/delivery/gate/finalization combinations, including pre-run success then agent failure, silent/suppressed delivery, terminal job removal, SYS-666 failure, aggregate dominance, and exact CLI exit propagation.
6. **Two-repository deployment proof.** Fresh-fetch and verify the canonical remote; bind reviewed Hermes and MarketWatch OIDs; deploy watchdog compatibility before claim activation; and prove the exact configured running gateway identity before any canary or resume.
7. **Coupled acceptance and control.** Execute all five named jobs through the real full route, require every result and protected preimage readback, then resume the five-job cohort in one existing-lock batch; add one discriminating mutation test for each R2-01 through R2-19 counterexample.

## Frozen Round-3 comparison and stop rules

Round-3 outcome is predeclared as `19 -> Z<=2`; required cut is at least `17`; required reduction is at least `89.5%`.

Round 3 also requires no P0 recurrence, no new authority or repository boundary discovered during formal review, and 3/3 approval. Any `Z > 2`, P0 recurrence, regression, candidate-derived expected set, or new authority/boundary triggers another DMAIC reset rather than an incremental correction or a fourth review round.

Immediately after all three Round-3 reviews, publish the normalized `19 -> Z` comparison before any further correction or implementation action.
