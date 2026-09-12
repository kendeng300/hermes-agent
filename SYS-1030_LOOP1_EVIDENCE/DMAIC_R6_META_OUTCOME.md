# SYS-1030 Loop-1 R6 — meta-DMAIC outcome

Status: **NO-GO; preserve R6 as rejected evidence without correction**.

This outcome records the source-boundary audit of the uncommitted R6 candidate.
It changes no product, runtime, scheduler, jobs store, deployment, or test state.
The five R6 subject artifacts remain byte-exact until this outcome receives
Product/Operations, Architecture/Runtime, Systems/Concurrency/Data, and
independent Six Sigma concurrence.

## Frozen R6 subject

| Artifact | SHA-256 | Size |
|---|---|---:|
| `TECH_SPEC.md` | `3396ac63a7c4b16887c79e0ab2b9648b5de1885584b8b2aaf5c080ddb767d8a8` | 615 B / 12 LF |
| `TECH_SPEC_R3_PROPOSED.md` | `9c1b61d1ebc5b1803cff6df678b03308a88f06bbedffd5a2a4a127f15e32af16` | 52,926 B / 887 LF |
| `FINITE_SCOPE_V1.json` | `da2d133a59339f96759976711a7c37ff680293bc608e74e52815c6606f9fc793` | 121,598 B / 642 LF |
| `validate_finite_scope_v1.py` | `f02c0f2660c3d43ff52a5ccf7237918c9b417c07fe1221f6ec792b3b9155e1d9` | 46,587 B / 1,078 LF |
| `DMAIC_R6_FINITE_CLOSURE.md` | `2441b39822323fb23a12d4155470f8babf9c80dfca671e8de05f3fae35ac2e8a` | 4,710 B / 87 LF |

The R6 evidence footprint is 226,436 bytes. The manifest phase, Python syntax
check, diff check, typed Python-3.8 refusal, authority-graph acyclicity check,
and candidate-side adversarial syntax/evidence controls passed. Those are useful
mechanical controls, but none proves that the authored semantic expected set is
complete.

## Define

The quality goal is unchanged: every standard-process loop must produce an
organic high-quality deliverable within two iterations, three at most. For Loop
1, zero means that the specification is complete against independently derived
pinned source and product behavior, not merely internally consistent with its
own model, manifest, checker, or test names.

The meta-question is therefore: did the previous checkpoints validate a
source-derived requirement-to-effect boundary, or did they validate a boundary
authored by the same candidate?

## Measure

Sixteen durable checkpoint outcomes are shown in recorded order. Each count
retains its checkpoint's recorded unit (atomic defect or causal family);
magnitudes are not compared across a unit change:

`11 -> 19 -> 4 -> 1 -> 3 -> 0 -> 6 -> 1 -> 0 -> 12 -> 14 -> 22 -> 1 -> 1 -> 1 -> 9`

| # | Durable checkpoint | Result | Recorded unit | Retrospective class |
|---:|---|---:|---|---|
| 1 | R1 review | 11 | valid atomic blockers | REJECT: source boundary/self-authored frame |
| 2 | R2 outcome | 19 | valid atomic defects | REJECT: source boundary/self-authored frame |
| 3 | R3 prescreen 1 | 4 | valid blockers | REJECT: source boundary/self-authored frame |
| 4 | R3 prescreen 2 | 1 | valid atomic defect | REJECT: source boundary/self-authored frame |
| 5 | R3 prescreen 3 | 3 | valid atomic defects | REJECT: source boundary/self-authored frame |
| 6 | R3 final prescreen | 0 | valid defects | FALSE GREEN: overturned by whole-subject review |
| 7 | R3 formal review | 6 | valid causal families | REJECT: source boundary/self-authored frame |
| 8 | R3b panel preflight | 1 | valid correction-induced defect | REJECT: acceptance-versus-ordinary-readiness conflation |
| 9 | R3c panel result | 0 | valid defects | FALSE GREEN: overturned by whole-subject review |
| 10 | R4 formal review | 12 | valid causal families | REJECT: source boundary/self-authored frame |
| 11 | R4 panel preflight | 14 | valid atomic defects | REJECT: source boundary/self-authored frame |
| 12 | R4 ownership-DAG audit | 22 | valid atomic defects | REJECT: source boundary/self-authored frame |
| 13 | R4 pass-4 | 1 | residual finding | REJECT: source boundary/self-authored frame |
| 14 | R4 pass-4 correction | 1 | residual finding | REJECT: source boundary/self-authored frame |
| 15 | R4 open-world detector | 1 | residual finding | REJECT: source boundary/self-authored frame |
| 16 | R5 finite replacement | 9 | original C-families | REJECT: source boundary/self-authored frame |

- The table contains 14 rejects and two apparent zero/green gates later
  overturned by independent whole-subject review. R3 final prescreen and R3c
  panel result are the two false greens.
- 13 of the 14 rejects, `13 / 14 = 92.857%` (**92.9%** rounded), trace to an
  absent independent source boundary or a self-authored oracle. R3b's
  correction-induced `mandatory deployment verification gates ordinary runtime`
  reject is the sole non-dominant-root exception. The other 13 rejects map to
  the absent-independent-source-boundary/self-authored-oracle mechanism.
- The independently measured R1-through-R5 elapsed span was 41.56 hours with 26
  evidence/spec commits. R6 then grew the five current artifacts to 226,436
  bytes without closing the measurement-system defect.
- The comparable origin ledgers contain R2 `7 / 19`, R3b `1 / 1`, and R4
  formal `6 / 12` correction-induced observations: `(7 + 1 + 6) / (19 + 1 +
  12) = 14 / 32 = 43.75%`, or approximately **43.8%**. This is an
  observation-weighted checkpoint measure, not deduplicated prevalence among
  unique defect families. More representation and correction therefore created
  a material share of the next review's defects instead of converging
  monotonically.
- R5 predicted `13 -> 0`; independent review measured `13 -> 9` families and
  20 child atoms. R6 contains labels for those atoms, but source challenge shows
  that label coverage is not predictive closure. R6 receives **NO-GO**, not a
  new zero prediction.

## Analyze

One-line root cause: **the process repeatedly derived its review boundary from
the artifact under review, so omitted source owners and behavior became invisible
assumptions that the artifact, checker, and future test names then agreed upon.**

The failure mechanism recurred in four forms:

1. A proposal-defined owner or route list was called complete without an
   independent forward walk from every ingress and reverse walk from every
   durable/network/process effect.
2. Prose was copied into a DAG, model, manifest, and checker. Consistent copies
   detected drift between copies but could not detect one coordinated mistake.
3. A named schema, matrix, or test was counted as proof before a legal object,
   invalid complement, complete cross-product, or executable counterexample
   existed.
4. Corrections added abstraction and proof machinery before source feasibility
   was established. This induced new APIs, states, and contradictions that were
   discovered only by the next reviewer.

R6 repeats that mechanism in the following source-real ways:

| Escape | Why the R6 control is not an oracle |
|---|---|
| The 25 paths are authored, not independently discovered | The edit set can remain 25, but a separate read-only witness set is required. It currently omits exact binding for MarketWatch `restore.sh` and `scripts/restore.sh`. |
| Semantic relations are duplicated as checker digests | Recomputing both manifest and checker after the same mistaken edit passes; byte equality proves identity, not correctness. |
| Test names stand in for results | Candidate mode proves that a qualname exists, not that its parameters cover or kill the specified counterexample. |
| `CHRONOS_SYNC_RECURRING` and `CHRONOS_SYNC_ONESHOT` are called source-real routes | At the pinned Hermes source, the only production callers of `fire_due` are the two HTTP handlers. The direct method is a shared internal ABI, not an independent production ingress. |
| Result and cut closure remain prose | `result_schemas` contains string lists and English `legal` clauses rather than constructible tagged records and an executable invalid complement. Thirteen generic cut rows do not instantiate every route, occurrence, shutdown-before/after cut, and cold restart. |
| Loaded-code membership is incomplete | The exact route lists omit source-required home/verifier/secrets dependencies, including `hermes_constants` and the HTTP fire verifier. |
| Loaded-byte proof is unimplementable as written | A post-import observer cannot recover the discarded module initialization code object. It can attest live functions, classes, bindings, origins, and process identity; exact import-time bytes require an import-time observation boundary. |
| Deployment roles remain caller-authoritative | `accept_controlled_deployment(... intended_roles, ...)` permits the caller to omit a required role, repeating the previously rejected underdeclared-host case. |
| Same-boot skip promises evidence that is not retained | The claim stores no durable supervisor/descendant identities while the eight supervisor functions are unchanged. A current-boot dead parent cannot prove that descendants are gone. |
| Shutdown ownership contradicts the prose | The manifest routes `mark_running_jobs_interrupted` directly to quarantine after a global kill, while the specification says only the exact worker may publish cleanup and disposition its claim. |
| The raw-writer reverse check is not candidate-complete | It re-derives 72 pinned baseline Python owners, but its final zero-reference scan excludes newly allowed test paths that were not in that baseline reverse set. |

The finite AST, Git-object, canonical-ref, retired-path, and test-qualname checks
remain useful bounded implementation preflights. They cannot be the semantic
acceptance authority and must not be expanded into another source analyzer.

## Improve — mandatory source-first reset

Do not correct the current R6 spec, manifest, or checker. Preserve and push them
as rejected history. Before another specification is authored:

1. Freeze the two source OIDs and the product CTQs independently of any proposed
   design.
2. Product/Operations, Architecture/Runtime, and Systems/Concurrency/Data each
   derive their source sets independently. Reconcile one literal relation:
   `requirement -> ingress -> binding -> owner -> effect/store cut -> final
   consumer -> cold restart -> discriminating test`.
3. Keep the production edit set separate from the read-only source/witness set.
   Any source-real member outside the proposed edit set is dispositioned, never
   suppressed. Route count and grouping follow source reachability; they are not
   preselected to satisfy a prior model.
4. For every state/result union, instantiate every legal tagged product and its
   invalid complement. For every route, instantiate every applicable durable
   cut, shutdown-before/after cut, and restart postimage. Equivalence is allowed
   only after identical owners, reads, writes, results, and lifetime are proved.
5. Replay each historical minimal counterexample against the independent matrix
   before prose. Every old candidate must be RED for its known defect and the new
   candidate must be GREEN for the same executable control.
6. Author one canonical specification. Retain only a small mechanical preflight
   for Git diff scope, baseline AST attestations, declared direct calls, forbidden
   new indirect syntax, raw-writer migration, proof-node existence, and evidence
   presence/absence. Route/result semantics belong to direct behavioral tests,
   not duplicated hashes.
7. Require the three matched author roles and independent Six Sigma to audit the
   same exact bytes against the frozen source-first matrix. Formal review gets at
   most one normalized batch correction and one whole-subject rereview.

## Control

- This R6 candidate and this outcome must be committed and pushed as one rejected
  checkpoint before any reset work begins.
- The five subject hashes above must remain exact through the Product,
  Architecture, Systems, and Six Sigma checkpoint audit.
- Git commit OID remains the only durable lifecycle identity. Counts, hashes,
  manifests, and DMAIC records are evidence, never parallel semantic authority.
- No R6 correction, implementation, production test, canary, deployment, or
  merge is authorized by this outcome.
- The next candidate may start only from the independently reconciled source-first
  CTQ relation. Its control target is zero valid source-real defects within two
  review/correction cycles, three at most; any new authority boundary or P0 after
  round two triggers one reset rather than another artifact layer.
