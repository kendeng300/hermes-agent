# SYS-1030 Loop-1 R6 — finite-contract closure DMAIC

## Define

Quality goal: a source-real Loop-1 specification that passes matched
Architecture, Systems, and Product review in no more than three iterations.
Root observes; Product/Operations, Architecture/Runtime, and
Systems/Concurrency/Data coauthor one batch; independent Six Sigma measures it.
Git branch commits are the only durable checkpoint.

## Measure

R5 replaced the 1.469 MB open-world model and 148 KB analyzer with a literal
25-path scope, but independent QA measured only `13 -> 9`, delta `-4`, a 30.8%
reduction. C06 auth binding, C07 admission-before-store, C10 archive truth, and
C11 pre-run exclusion passed. Nine original families remained; the reviewers'
20 atomic findings are children of those families, not 20 new families:

| family | R6 atoms |
|---|---|
| C01 finite negative proof | N04 structural AST partition, N05 dynamic-site complement, N17 retired absence, N18 real test-node existence |
| C02 route coverage | N10 exact route relation |
| C03 cut/restart products | N06 closed schemas, N07 total cut matrix |
| C04 canary conservation | N08 CLI projection, N09 post-C2 conservation |
| C05 host lifecycle | N11 exact shutdown owners/nested pre-kill path |
| C08 loaded code | N12 exact module sets, N13 executing-object identity |
| C09 Git/deployment | N14 coordinator/order/handoff, N15 canonical refs, N16 subject/blob binding |
| C12 authority closure | N01 fail-closed lock, N02 independent inventory, N03 core edges, N20 complete raw-writer migration |
| C13 owner skip | N19 descendant cleanup proof |

Predeclared result: both `13 -> 0 remaining families` and
`20 -> 0 remaining atoms`, with no new defect family.

## Analyze

One-line root cause: R5 bounded the file set but not the contract inside it;
self-authored route, owner, type, evidence, and AST partitions were neither
independently source-bound nor mutation-complete.

The observed manifestations were same-count route substitution, arbitrary
well-formed test names, incomplete owner edges, module/class/default changes
outside function-body checks, constructed `getattr` authority, wrong Hermes
branch authority, disk-after-import standing in for executing bytes, and a raw
writer deletion without its complete reverse migration. More reviewer rounds
would not remove that common cause; an independently fixed finite relation and
its killer mutations do.

## Improve

The one R6 batch:

1. pins the exact route×occurrence×host/role×claim×submit×finalizer×re-arm,
   shutdown-owner, loaded-module, result-schema, and cut-product relations;
2. pins a source-derived authority inventory independent from exact direct
   caller edges, makes `_jobs_lock` fail closed, and deletes/migrates the full
   pinned semantic reverse set of public `save_jobs`;
3. checks whole declared functions including signatures/defaults/decorators,
   requires the residual module/import/assignment/class AST to be unchanged,
   freezes every baseline dynamic site, and refuses new reflection/dynamic
   import/callable-result/subscript/lambda authority selection;
4. binds commit-object subjects, executing checker/manifest, five externally
   approved artifact hashes, all current/retired paths, and real candidate Git
   test qualnames; and
5. specifies post-C2 ACTIVE conservation, exact CLI exits, descendant-safe
   operator skip, a central already-loaded object observer, canonical Hermes
   main/MarketWatch master authorities, and one typed deployment coordinator.

Positive control is Python 3.11 manifest PASS against the pinned commits. The
20 RED controls mutate one atom at a time; each must refuse while the positive
control remains PASS. Python 3.8 remains a deliberate semantic refusal.

## Control

The exact manifest relation and protected callable/edge/dynamic-site relation
are duplicated as canonical digests in the small checker. This is not a VCS or
runtime state replica: candidate mode binds both files to externally approved
Git blobs, and runtime behavior remains in parameterized product tests.
Candidate tests must kill same-count substitutions, unlisted structural syntax,
constructed authority, invented proof nodes, retired-artifact return,
stale-loaded/restored-disk substitution, wrong URL/ref/OID, unsafe parent-dead
skip, post-C2 rollback, and stale full-store overwrite.

The batch freezes only after exact-byte Product, Architecture, and Systems
author audits plus independent Six Sigma report both family and atomic counts.
If any count remains, findings are normalized once and corrected as one batch;
no piecemeal fixes, open-world analyzer, READY/state file, systemd, xdist,
global mutex, or local Git replica is permitted.
