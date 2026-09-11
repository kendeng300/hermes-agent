# SYS-1030 Loop 1 — R4 panel-preflight DMAIC outcome

Status: evidence frozen before proposal correction; no implementation or tests.

## Immutable subject

- Subject tip: `edcf99ac6d10d019c92f2f8386687d246135eb5e`
- Proposal blob: `efcdd5901d9a81c324ce6d57978337affc6b9038`
- Proposal SHA-256: `5db8fea1dd8ffddf72d7f3fc1403d397eb03323d516d8e05b90254d9517fdc47`
- Proposal size: 109,419 bytes / 1,717 LF lines

## Measure

- Panel preflight: `17` raw comments -> `14` valid atomic defects; `0` false
  positives and `0` out-of-scope findings.
- Architecture/System overlap contained six reviewer pairs; normalization removed
  three duplicate comments from the raw union.
- Prior formal baseline: `12 -> 14 | delta +2 | 16.7% worse`.
- Predeclared next result: `14 -> 0 | delta -14 | 100% reduction`.
- Two independent auditors converged on 14. A third reported 13 by merging F11
  and F12. The panel retains them separately because their mutations are
  orthogonal: Electron argv/child propagation can be correct while a
  caller-supplied route set remains incomplete, and route derivation can be
  correct while Electron propagation remains absent.

RCA: `The frozen manifest enumerated nodes but never proved its typed edges constructible, acyclic, uniquely owned, provenance-safe, and total.`

## Normalized atomic ledger

| ID | Required invariant and discriminating counterexample |
|---|---|
| F1 | Controlled admission closes before every store search/open, claim, task, provider start, or HTTP 202. RED: an authenticated HTTP path opens a profile store before `require_admission` proves the matching activation OPEN. |
| F2 | Cross-profile execution binds the exact selected profile, home, store, provider, and activation. RED: an A-activated process accepts a legitimate B token/body and executes B without a separately verified B target activation. |
| F3 | Attestation proves the code objects actually loaded, not merely the bytes currently present after import. RED: a module is imported from old bytes, its file is replaced with reviewed HEAD, and disk hashing passes while the process still executes stale code. |
| F4 | Provider identity has one typed registry/name/instance/class/module relation. RED: aliasing or a registry/name swap returns a different provider class/module while the expected provider string still compares equal. |
| F5 | One lifecycle wrapper has an acyclic call graph and exactly one release owner. RED: the generic registered wrapper must invoke a bound scheduler it does not receive, or recursively re-enters admission/release. |
| F6 | Immutable Chronos authentication, claim, target, envelope, and bound scheduler survive execution, finalization, and re-arm. RED: the HTTP wrapper retains only context/postimage, bypasses `ChronosCronScheduler.run_claimed`, executes in ambient scope, or never re-arms. |
| F7 | Managed body, finalizer, and aggregate ownership form an acyclic pre-finalization -> finalization -> aggregate flow. RED: aggregate construction requires finalization while the finalizer consumes an already-final outcome. |
| F8 | Intentional silence, empty/whitespace content, saved output, configured suppression, delivery, failure, and finalization form one total disjoint result product. RED: a saved whitespace result becomes SUCCESS, or delivery suppression aliases intentional silence and empty failure. |
| F9 | Cleanup `INCOMPLETE|UNKNOWN` is sticky for the exact claim generation. RED: late `COMPLETE`, shutdown interruption, or a generic finalizer clears or overwrites the quarantined ACTIVE claim. |
| F10 | One executable deployment coordinator owns the complete Git-and-host aggregate and proves exact set equality. RED: per-host checks pass independently while one required host/result is omitted from the aggregate handoff. |
| F11 | Electron primary/profile owners propagate exact expectation argv, retain injective child identity, and produce exact stop receipts; the production edit inventory includes those owners. RED: a desktop child starts without the controlled expectation while gateway-only evidence passes. |
| F12 | Role/provider/mode determines one total source-derived route set; callers cannot supply or underdeclare it. RED: omit `GATEWAY_CHRONOS_HTTP` from the free `routes` argument and still obtain VERIFIED. |
| F13 | The attested module set is the complete transitive authority/effect closure. RED: a foreign cached `cron.__init__`, Chronos verifier/NAS client, or profile/config/home/store/secret authority changes authentication, routing, claim, or re-arm while all listed modules pass. |
| F14 | Observation and controlled activation results have total status/reason/identity/nullability/admission/CLI-exit unions. RED: `DIRTY_CHECKOUT`, `SHUTDOWN_CLOSED`, `RUNTIME_STATUS_MISSING`, or null expectation admits two statuses or exit codes. |

## Preapplication control

Before any prose correction, the panel freezes one immutable ownership DAG and
type-flow artifact. It must topologically sort. Every real entrypoint edge names
its exact producer, value, type, consumer, lifetime, and pinned-source locator;
no caller-supplied value may replace source authority. The DAG must contain:

- exhaustive result/nullability/transition unions and invalid complements;
- literal route witnesses for every role/provider/mode cell;
- module closure derived from the DAG's authority and effect owners;
- one deployment coordinator that consumes exact equality across every host;
- deterministic, independent mutation controls for F1–F14 and the prior 17
  actionable R2 families.

Coverage requires `100%` entrypoint-edge ownership, result/transition cells,
source-derived route witnesses, authority/effect modules, deployment hosts, and
mutation kills. Equivalent cells may be collapsed only when pinned source proves
identical owner, read set, write set, result, and lifetime; otherwise they remain
explicit. Any cycle, unnamed edge, caller authority, uncovered cell, surviving
mutation, inventory mismatch, regression, or new scope is NO-GO.

Two independent source-derived audits must each return zero before prose is
edited. After one bounded application, the complete exact proposal requires
3/3 panel approval and another independent whole-document fixed-point review.
