# SYS-1030 Loop 1 — Round-3 formal-review DMAIC

Status: `0/3`; evidence recorded before correction. No proposal, product,
runtime, scheduler, deployment, or test state is changed by this record.

## Immutable subject

- Review tip: `6f4a6ca2d7bc27c7e768eab2e0cfd9916a81c467`
- Proposal commit: `0a130a162c0bbf004e7f089fa4b56771292f637a`
- Proposal blob: `edf268647b557f087c86d878f5ae25485f0cc07e`
- Proposal SHA-256: `7861f107c5613d96a89dc28d4989534001351e3b8ebb0069c22cceaf4172c77f`

## Measure

- Raw findings: `8`; valid causal families: `6`; overbroad/out of scope: `0`.
- Duplicate normalization: Architecture `A2` = Systems `S1`; Architecture
  `A3` = Product `P1`.
- Formal-review escape: `0 -> 6 | delta +6 | target missed by 6 | reduction undefined`.
- Frozen-ledger comparison: `19 -> 6 | delta -13 | 68.4% reduction | <=2 target missed by 4`.

## Analyze

RCA: `Prescreen confirmed previous three repairs but reused proposal proof inventory instead of generating independent executable negative controls at shutdown, cleanup, terminal-claim, deployment-consumer cuts.`

| ID | Conserved causal invariant | Discriminating negative control |
|---|---|---|
| F1 | Production identity verification is mandatory and reachable in the deployed topology, not optional transport. | Remove or make the production verifier unreachable/nonzero while all Git checks pass; activation must fail closed. |
| F2 | Running identity attests the bytes already loaded by the process, not merely current clean `HEAD`. | Start on old scheduler bytes, then fast-forward the checkout to the reviewed OID; verification must reject the old loaded module. |
| F3 | Shutdown atomically closes admission and snapshots exact claimed context before any start cut. | Begin shutdown after durable `ACTIVE` claim but before in-memory registration/submit; the occurrence must be captured and must not start outside the shutdown snapshot. |
| F4 | Cleanup-uncertain canary state retains the exact `ACTIVE` claim and blocks clear/replay/resume. | Make cleanup outcome unknown after canary launch, then invoke generic cleanup/restart; it must preserve `ACTIVE` and refuse another canary or resume. |
| F5 | A later exact canary after `OPERATOR_SKIPPED` has an explicit conserved predecessor and successor postimage. | Persist first-canary `OPERATOR_SKIPPED`, then request the second canary; the transition must preserve the first row/preimage and create only the defined successor, never overwrite it. |
| F6 | MarketWatch deployed identity satisfies `Dmw = Mmw` for a clean checkout of the reviewed bytes. | Leave canonical remote/ref/fetch valid but deploy a dirty or different MarketWatch checkout; acceptance must fail before execution or resume. |

## One bounded correction

- **A — runtime/deployment proof:** close F1, F2, and F6 with one mandatory
  production verifier that attests loaded Hermes bytes and the clean deployed
  MarketWatch checkout against the reviewed identities.
- **B — lifecycle admission/cleanup:** close F3 and F4 with one atomic
  shutdown-admission/snapshot/start contract and a total cleanup-uncertainty
  postimage/restart table.
- **C — terminal canary:** close F5 with the literal
  `OPERATOR_SKIPPED -> second-canary` preimage, transition, postimage, restart,
  and refusal cases.

## Predeclared control

Next comparison: `6 -> 0 | delta -6 | 100% reduction`. Before correction,
challenge exact proposed bytes with all six negative controls. After one batch,
repeat the whole source-to-final-consumer review across temporal interleavings,
restart generations, and deployment observability. Any valid residual, optional
proof route, newly discovered owner, or candidate-derived expected set is a
stop/reset rather than another incremental patch.
