# SYS-1030 Loop-1 R5 — finite replacement outcome

Status: **REJECTED; preserved before correction**.

The Product/Operations author froze the candidate and requested exact-byte
Architecture/Runtime and Systems/Concurrency/Data author audits plus independent
Six Sigma QA. No correction was applied before this outcome was recorded.

## Frozen subject

| Artifact | SHA-256 |
|---|---|
| `TECH_SPEC.md` | `389855e869a094cd22dcc76be77f405ef27113bb89755d7cdb3ec5e8ca16ea58` |
| `TECH_SPEC_R3_PROPOSED.md` | `0f769dc974cd47f0f4b4fa7ef932a909f0af511b94993df3da4c8836b0806ef8` |
| `FINITE_SCOPE_V1.json` | `6d3ba83e94500fee0079244bfb3ff18e1290f2faeaf7801e1b524c6dbd61e583` |
| `validate_finite_scope_v1.py` | `1f1ec58cde2e9f6ad4d1a2560aec7f27329cfa785b542cd66c61627176c05373` |
| `DMAIC_R5_FINITE_REPLACEMENT.md` | `d3a1c68f4d7fb638a2382a262be9568eff56dd528f6ed947d6278daa67e2f92c` |

The three R4 normative artifacts were deleted in the candidate. The manifest
phase reported PASS under Python 3.11 against the two pinned source OIDs. The
audits proved that PASS was insufficient.

## Measure — apples to apples

Prediction in the R5 plan: **13 →0**.

Actual at the same original C-family unit: **13→9; Δ−4; 30.8% reduction;
target 0 missed by 9 families**.

Detailed implementation atoms: **20 remain**. They are children of the nine
failed C families, not 20 new/replacement families. Genuinely new families: 0.

| Family | Result | Atomic children / disposition |
|---|---|---|
| C01 finite negative proof | FAIL | N04 structural AST partition; N05 dynamic-site complement; N17 retired absence; N18 exact test existence |
| C02 route×occurrence witnesses | FAIL | N10 exact route/occurrence/host/role/claim/stage relation |
| C03 ambiguity/cut/restart states | FAIL | N06 closed result schemas; N07 total cut/restart matrix |
| C04 canary conservation | FAIL | N08 CLI projection; N09 post-C2 refusal retains ACTIVE and B |
| C05 host/role shutdown | FAIL | N11 source host and nested-stop ownership |
| C06 auth/profile/home/store/provider binding | PASS | preserved; do not reopen |
| C07 admission-before-store reservation | PASS | preserved; do not reopen |
| C08 executing loaded-code identity | FAIL | N12 exact module set; N13 live executable-object provenance |
| C09 Git/deployment handoff | FAIL | N14 coordinator/order/handoff; N15 canonical URLs/refs; N16 subject/blob binding |
| C10 whole-archive truth | PASS | jobs-last/zero-jobs/partial/unknown semantics preserved |
| C11 pre-run zero-construction | PASS | eight script-supervisor attestations already present; no redesign |
| C12 closed direct authority | FAIL | N01 fail-closed lock; N02 independent owner set; N03 exact edges; N20 delete raw writer and migrate reverse set |
| C13 remote-owner skip | FAIL | N19 durable descendant-cleanup proof |

The 20 atoms are assigned once above. Cross-family checks are not counted twice.

## Analyze

One-line root cause: **the reset bounded the file list but not the contract
inside those files, so self-authored route, owner, type, evidence, and AST
partitions remained neither independently source-bound nor mutation-complete.**

Architecture/Runtime found five normalized families: incomplete closed
protocol/canary schemas; an unimplementable raw-writer ABI decision; unenforced
finite call/syntax rules; unbound evidence/tests; and incomplete/wrong
Git-loaded-code rollout authority.

Systems/Concurrency/Data found nine normalized manifestations: fail-open
cross-process locking; circular/incomplete authority inventory and edges;
uncovered module/class structure; constructed-reflection bypass; unbound
candidate evidence/tests; incomplete canary projection; unsafe raw-writer ABI;
unproved same-boot descendants; and incomplete manual-host/nested shutdown
ownership.

Independent Six Sigma normalized the union to N01–N20, mapped each atom to the
original C01–C13 denominator, found 0 out-of-scope items and 0 unresolved author
conflicts, and identified one false Product concern: the script-supervisor
unchanged control was already present. That existing control remains unchanged.

## Improve — next single batch

The correction is predeclared as **13→0 families and 20→0 atoms**:

1. fail-close the cross-process jobs lock;
2. add an independent exact authority set and complete direct edge relation;
3. cover module/class/signature/default/decorator/lambda structure and freeze
   only exact baseline dynamic sites;
4. materialize closed result records, total cut matrix, and exact canary/skip
   CLI results/exits, with post-C2 ACTIVE conservation;
5. validate exact route relations and every source host/nested shutdown owner;
6. define exact loaded-module/live-object receipts and one ordered deployment
   coordinator using canonical Hermes `origin/main` and MarketWatch
   `origin/master` URLs/refs;
7. bind the five current artifact blobs, three retired absences, candidate OIDs,
   and unique exact test nodes;
8. require same-boot durable supervisor/descendant cleanup COMPLETE before skip;
9. delete public raw `save_jobs`, enumerate its complete pinned production/test
   reverse set, and migrate tests to file-local isolated seeding or closed typed
   operations. Test paths are separate proof scope and do not widen the 25
   production paths.

## Control

This rejected checkpoint must be committed and pushed before correction. The next
candidate will receive positive baseline checks plus one mutation per N01–N20.
It will be frozen once, measured at both family and atom units, and audited by
the same three author roles before independent formal review. Git remains the
only durable iteration state; no READY flag, service, or local VCS replica is
introduced.
