# SYS-1030 Loop 1 — R4 Ownership-DAG Audit Outcome

## Immutable subject

- Git tip: `17ec2a58f8f79b7a3b371471bd27b4792edb6958`
- Audited artifact: `SYS-1030_LOOP1_EVIDENCE/R4_OWNERSHIP_DAG.md`
- Artifact Git blob: `d3c87942fc3be577b67aaa2471a56342f36a1447`
- Artifact SHA-256: `e59086c543fc240e51aa03b222b6e50e0c501966be9531eb5480c1873b5a7a7e`
- Artifact size: 67,242 bytes / 1,119 LF lines
- Proposal remained unchanged during this audit: blob
  `efcdd5901d9a81c324ce6d57978337affc6b9038`, SHA-256
  `5db8fea1dd8ffddf72d7f3fc1403d397eb03323d516d8e05b90254d9517fdc47`.

This is evidence recorded before correction. The audit assumes the declared
single-deployer/non-hostile environment. All 22 defects below are valid and in
scope; none depends on a hostile race.

## Measure

The predeclared result was `14 -> 0`. The independently reconciled result is:

`14 -> 22 | +8 | -57.1% reduction (57.1% worse) | target missed by 22`

The increase is measured in normalized valid atomic defects, not raw reviewer
containers. The next predeclared target is:

`22 -> 0 | -22 | 100% reduction`

## One-line RCA

Panel substituted shorthand prose for promised closed source-derived typed DAG, so exact owner/type/set checks never executed and unproduced wires, incomplete source closures, contradictory unions survived.

## Analyze — normalized N01–N22 ledger

Each key is atomic under `(owner/interface + invariant + minimal
counterexample)`. A correction is incomplete unless its listed counterexample
is rejected by the canonical model and an independent source-derived proof.

| ID | Atomic defect and minimal counterexample | Required closure discriminator |
|---|---|---|
| N01 | Schema instantiation is incomplete: a named schema can remain prose or lack a constructible legal value while the DAG check passes. | Materialize every field, tag, presence rule, constructor, and legal/invalid value; instantiate every union row and reject an omitted field or impossible product. |
| N02 | A singular resolved provider is used for multiple allowed bindings: two bindings needing distinct provider objects collapse into one authority. | Derive one typed provider binding per exact selected binding, prove injective binding-to-provider ownership, and reject a swapped or shared instance. |
| N03 | Allowed bindings remain operator-selected: a caller can omit or add a binding and thereby redefine the controlled host set. | Derive the complete binding set from the pinned source/profile configuration; compare caller transport only to that set and reject omission/addition. |
| N04 | Edge E29 carries an exact Chronos bundle from R12 although R12 produces an aggregate, not the retained bundle. | Give the immutable bundle its real producer and explicit lifetime edge through R13; removing that edge must make re-arm unconstructible. |
| N05 | Edge E27 hides “prior stages” instead of naming their producers: finalization and aggregate can consume unproduced stage facts. | Add one typed edge from every stage producer to the exact consumer and reject removal or substitution of any stage wire. |
| N06 | The executor-host set omits model-tool gateway, chat, ACP, and TUI hosts. | Forward-walk all source entrypoints and reverse-walk all execution sinks; require exact host-set equality and reject omission of each of these hosts. |
| N07 | The module closure is incomplete: a transitive authority/effect module can be absent while module-set equality still passes. | Derive the full transitive module set from the fixed-point call/import graph and reject omission, replacement, duplication, or provenance retagging. |
| N08 | Cross-process receipts have no literal transport: a process-local typed value is treated as if it reaches another process. | Define the exact serialization, transport owner, decoder, identity binding, failure result, and lifetime for every cross-process edge; reject dropped or altered bytes. |
| N09 | A bytes-versus-string type mismatch permits a producer and consumer to disagree while the edge is called typed. | Choose one canonical wire type and literal encoding/decoding rule; reject implicit conversion and byte/string substitution. |
| N10 | The intentional-silence owner names a callable that does not exist in pinned source. | Bind silence classification to one source-real callable/signature and reject the invented owner. |
| N11 | Intentional silence is not saved through the output owner, so its promised output/result observation cannot be constructed. | Route the silence result through the exact output product or define its explicit typed bypass and terminal consumer; reject lost silence evidence. |
| N12 | Result dominance rules contradict one another for a reachable combination, allowing two terminal aggregates for one input. | Publish one total, disjoint precedence table over the complete reachable cross-product and reject every overlapping result pair. |
| N13 | The result/state table lacks a shutdown row for a reachable shutdown cut. | Add the exact shutdown preimage, successor/postimage, result, exit, and restart behavior; kill a mutation that falls through to an ordinary row. |
| N14 | Activation mapping is not total: a reachable observation/controlled-result/reason/nullability combination has no unique status and exit. | Enumerate the complete legal product plus invalid complement and prove exactly one status/reason/exit for each cell. |
| N15 | The no-jobs archive case has no successful result, so a valid archive containing zero jobs stores cannot complete truthfully. | Define the exact zero-target success result/postimage and distinguish it from malformed, unreadable, and partial archive failure. |
| N16 | The MarketWatch source/edit inventory cardinality is nine, but the DAG’s claimed set/count does not conserve all nine members. | List and source-prove all nine exact members, require set equality, and reject each one-member omission or addition. |
| N17 | D07 opens targets before D08 deployment acceptance, so controlled cron can become available before the deployment aggregate succeeds. | Keep every target closed through D08; only a successful exact aggregate may open the verified set atomically, and any failed aggregate must yield zero admission. |
| N18 | `CHRONOS_SYNC` is an invented execution route without a pinned reachable source owner. | Remove it unless a forward and reverse source walk proves a real entrypoint-to-sink path; an exclusion requires the source impossibility proof. |
| N19 | Gateway Chronos HTTP reachability is treated as unconditional although it is configuration/provider dependent. | Encode the exact enablement predicate and derive route membership from it; prove enabled and disabled witnesses and reject unconditional inclusion. |
| N20 | Provider/auth/request authority is lost before R03: early construction does not carry the exact selected bundle into the claim owner. | Construct one typed immutable early bundle at its real owner and transport it without caller reconstruction through admission and claim; reject ambient-profile replacement. |
| N21 | Edge E28 again hides “prior stages” on the quarantine branch, so CLEANUP_UNVERIFIED can be aggregated from facts with no producer. | Give every quarantine aggregate input its own typed producer edge and reject omission/substitution independently of the ordinary finalization branch. |
| N22 | S01 snapshots registry records but the DAG has no producer edge for those records. | Connect the exact registration owner/output to the lifecycle snapshot owner with process lifetime and identity; reject snapshots synthesized from job IDs or resampled state. |

## Improve — one bounded correction experiment

Before changing the proposal, replace shorthand ownership prose with one
canonical literal machine-readable model and a self-contained user-space
validator. Git OID is evidence input only; the model and validator create no
runtime state, service, mutex, scan, or operational authority.

The model must contain the literal schema definitions, union variants, nodes,
typed edges, producers, consumers, lifetimes, ranks, terminal dispositions,
source-derived set members, exclusions, and N01–N22 mutation witnesses. The
validator must deterministically prove:

1. every schema and union variant has at least one constructible literal image,
   and its invalid complement is rejected;
2. each edge endpoint and wire type exists, each input has exactly one real
   producer, and each nonterminal output has an explicit consumer;
3. every edge advances rank, a topological sort consumes all nodes, and no
   hidden “prior stages,” bundle, receipt, context, or registry value remains;
4. route, host, module, provider, profile/store, archive, lifecycle-cut,
   result, deployment, and proof sets equal independently derived source sets;
5. a forward walk from every entrypoint and a reverse walk from every sink
   reach the same fixed point, with source proof for every exclusion;
6. every N01–N22 mutant and every retained prior-17 regression mutant is killed.

Equivalence partitions are permitted only when source proves identical owner,
read/write set, transition, failure result, and consumer. Otherwise the model
must retain explicit cells. Expected values may not be derived from the
candidate being validated.

## Control / release gate

- Freeze the source OID and independently derive both forward and reverse sets
  before authoring the corrected model.
- Run the self-contained validator on the frozen model and on each N01–N22
  mutant; require 100% schema, edge, producer/consumer, set, and mutant coverage.
- Require the panel and two independent auditors to report zero undefined
  schema/edge, cycle, unowned effect, ambiguous union, inventory mismatch,
  surviving mutant, or prior-17 regression on the same exact bytes.
- On any nonzero result, record DMAIC before correction, apply one complete
  bounded batch, and repeat against a newly frozen exact identity.
- Only a measured `22 -> 0` permits one proposal update and subsequent
  whole-proposal review. The validator and Git evidence remain review artifacts
  and are excluded from runtime/product authority.
