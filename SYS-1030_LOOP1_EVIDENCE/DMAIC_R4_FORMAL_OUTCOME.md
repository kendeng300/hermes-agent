# SYS-1030 Loop 1 — R4 formal DMAIC and preapplication control

Status: `0/3`; evidence frozen before correction. This file changes no proposal,
product, runtime, scheduler, deployment, or test state.

## Immutable subject

- Subject tip: `61915abd2e17321726b06d878f5ae25485f0cc07e`
- Proposal blob: `9617a5f8cf94cf768830ba39e487432fca3082c5`
- Proposal SHA-256: `b4c78fe2a8a8e0c2bb707d123f1527e00018fa4902c90187042a894bc4824587`
- Proposal size: 91,947 bytes / 1,407 LF lines

## Measure

- Formal findings: `13` raw -> `12` valid causal families; `0` out of scope or
  overbroad. Systems S2 and Architecture A1 are the sole formal duplicate:
  universal scheduled-one-shot authority/lifecycle. Independent audit I1
  duplicates Systems S1 but is not an additional formal raw finding.
- R3 formal: `6 -> 12 | delta +6 | 100% worse`.
- Panel preflight: `1 -> 12 | delta +11 | 1100% worse`.
- Actionable baseline: `17 -> 12 | delta -5 | 29.4% reduction`.
- Frozen ledger: `19 -> 12 | delta -7 | 36.8% reduction`.

RCA: `Prior audit accepted representative owners/tests as closed set instead of independently enumerating complete source graph, leaving unlisted occurrence, host, module, namespace, result, identity, temporal-interleaving cells invisible.`

## Normalized 12-family ledger

| ID | Origin; invariant and real owner | Minimal counterexample | Required replacement |
|---|---|---|---|
| F1 | S1/I1, correction-induced. `cron.scheduler.quarantine_active_execution_after_cleanup_uncertain` must conserve the canary's original pause image. | Cleanup quarantine overwrites `enabled`, `state`, `paused_at`, or `paused_reason` captured before the canary. | Preserve those four leaves byte-exact with the matching ACTIVE claim; publish the cleanup diagnostic outside those original pause leaves. |
| F2 | S2/A1, direct residual. Builtin and Chronos scheduled one-shots require universal durable non-replay authority and exact runtime context. | A submitted/uncertain one-shot retains only legacy expiring authority, is aged out, malformed-overwritten, or automatically replayed after restart. | Add the scheduled one-shot tagged claim/context without TTL or automatic replay after API entry; give it exact dead-owner operator disposition while preserving finite terminal removal and public ABI. |
| F3 | S3, correction-induced. The worker that owns an admitted HTTP Chronos context must exact-release it. | API/dashboard returns STARTED; the HTTP task succeeds, fails, is cancelled, or re-arm fails, but the registered context leaks or cancellation releases a still-running thread. | Both handlers invoke one named exact-release wrapper; release only after the worker exits, for success/error/cancellation/re-arm, and never from cancellation of a still-running `to_thread`. |
| F4 | S4, prior residual. `ManagedRunOutcomeV1` must represent whitespace/empty agent output truthfully through output and delivery. | Agent reports success with whitespace-only output and the product becomes success or conflates no saved content with configured suppression. | Add explicit `WHITESPACE_EMPTY|EMPTY_RESPONSE` failure outcomes; keep saved output and `SUPPRESSED_EMPTY` independent; close the complete content/output/delivery/finalization product and caller exits. |
| F5 | S5, correction-induced. Controlled deployment must verify identity before opening cron admission. | Restart starts the provider and claims work before the strict build/profile/store/provider verifier later fails. | Opt-in controlled deploy starts with cron admission closed, verifies the expected build/profile/store/provider, then opens it; verification failure leaves zero claim. Ordinary startup remains unchanged. |
| F6 | P1, incomplete remedy. Runtime attestation covers the full execution module closure, not scheduler alone. | `cron.scheduler` matches reviewed HEAD while jobs, provider, selected provider, HTTP, or manual owner code loaded from stale bytes. | Eagerly derive/load and attest jobs, scheduler, provider interface/loader/selected provider, and active HTTP/manual owner modules to one OID before controlled activation. |
| F7 | P2, correction-induced. Cron activation authority is not messaging `served_profiles`. | A profile is advertised for messaging while its cron profile/home/jobs file/provider/route belongs to another or was never activated. | Publish and verify the exact in-process cron activation tuple: profile, home, jobs file, provider, route, and process identity. |
| F8 | A2, correction-induced. Cleanup classification and shutdown interruption have one terminal owner. | Shutdown interruption finalizes/clears the claim before an INCOMPLETE/UNKNOWN cleanup quarantine can retain it. | Post-submit shutdown retains ACTIVE until the worker/exact owner commits the terminal cleanup disposition; UNKNOWN wins and quarantines; no generic clear. |
| F9 | A3, correction-induced. Every dashboard/desktop host closes admission and drains exact contexts. | A non-`GatewayRunner.stop` host tears down its executor/event loop while admission stays open or registered work is neither drained nor retained. | Every source-derived host uses shared close-before-admit, stop, and exact task/context drain semantics. |
| F10 | A4, prior residual. Archive namespaces for default and named profiles share the strict store owner. | An archive member `profiles/<name>/cron/jobs.json` bypasses the owner while root `cron/jobs.json` is protected. | Normalize root, optional prefix, and `profiles/<valid>/cron/jobs.json`; Hermes routes each selected store through the strict owner, and both MarketWatch fallback extractors refuse the whole archive before any write. |
| F11 | A5, newly exposed. Deployment proof covers every source-derived dashboard/desktop executor host. | The primary gateway is attested while an old dashboard/desktop process still runs stale scheduler/provider code and can claim work. | Freeze a static source-derived host manifest; before activation each role is stopped or exact PID/start/module/profile/store-attested. Add no host scan or state store. |
| F12 | A6, direct residual. Git proof binds reviewed, merged, deployed, and running identities rather than ancestry alone. | A reviewed candidate is merely an ancestor of a different merge, or deployment/running code differs while ancestry passes. | Require `Ch==Rh`, QA bound to merged `Mh`, `Dh==Mh`, and every live `R==Dh`; require the equivalent `Cmw/Rmw/Mmw/Dmw` chain. Only an explicitly declared evidence-only exclusion may differ. |

## Frozen source-derived closed sets

These are expected sets derived by forward source walk and reverse sink walk;
the correction is not their authority.

- **Executor roles and hosts:** builtin ticker; base/Chronos synchronous provider;
  gateway API Chronos handler; dashboard Chronos webhook; public canary/manual
  CLI; gateway host; dashboard host; desktop host.
- **Claim-path production modules:** `cron/jobs.py`, `cron/scheduler.py`,
  `cron/scheduler_provider.py`, `plugins/cron_providers/__init__.py`, selected
  provider `plugins/cron_providers/chronos/__init__.py`,
  `gateway/platforms/api_server.py`, `hermes_cli/web_server.py`,
  `hermes_cli/cron.py`, `hermes_cli/main.py`, and `tools/cronjob_tools.py`.
- **Routes and modes:** builtin recurring, builtin scheduled one-shot, Chronos
  recurring, Chronos scheduled one-shot, synchronous provider, API HTTP,
  dashboard HTTP, canary, and compatible manual/legacy route.
- **Stores/profiles:** default profile and every valid named profile; exact
  profile, canonical home, selected `cron/jobs.json`, provider, and route remain
  one tuple.
- **Archive namespaces:** normalized root `cron/jobs.json`, an allowed archive
  prefix followed by that root, and `profiles/<valid-profile>/cron/jobs.json`;
  duplicate, traversal, malformed, unknown-profile, or ambiguous members refuse.
- **Temporal cuts:** preclaim, postclaim, preregistration, postregistration,
  pre-API, API-entered/unknown, accepted, preworker, worker-started, pre/post
  cleanup classification, quarantine, shutdown snapshot, interruption,
  finalization, context release, and cold restart.
- **Complete product:** content `NONEMPTY|WHITESPACE_EMPTY|EMPTY_RESPONSE|FAILED`
  crossed with output, delivery, finalization, result/exit, and every invalid
  nullability combination; no success projection may hide an earlier failure.
- **Deployment stages:** source freeze, preflight, MarketWatch deploy, Hermes
  deploy, controlled start with admission closed, full-module/cron-activation
  verification, admission open, and SYS-1029 handoff.
- **Git identities:** Hermes candidate `Ch`, fresh remote review head `Rh`,
  merged/QA-bound `Mh`, deployed `Dh`, and each running role `R`, with
  `Ch==Rh`, `Rh` ancestor-or-equal `Mh`, `Dh==Mh`, and every `R==Dh`.
  MarketWatch equivalently uses `Cmw==Rmw`, `Rmw` ancestor-or-equal `Mmw`, and
  `Dmw==Mmw` before Hermes activation.

## Preapplication control

For every reachable cell in the closed sets, record exactly one source owner,
caller, preimage, cut, postimage, typed result/exit, and deterministic negative
control. A forward walk starts at every executable/HTTP/CLI entrypoint; a reverse
walk starts at every jobs write, claim submit/start, result/output/delivery,
context release, shutdown/finalization, archive write, deployment activation,
and acceptance sink. Iterate both until their union reaches a fixed point.

An exclusion passes only with a source-level impossibility proof. Coverage is
exact-set equality, not representative sampling: ownership, reachable-cell
coverage, and mutation kill rate must each be `100%`. Required mutations include
omitted role/host/module/namespace, swapped profile/store, missing context
release, reordered cleanup/shutdown or verification/admission, collapsed result
variant, stale loaded module, and each broken Git equality/ancestry edge.

Predeclared next comparison: `12 -> 0 | delta -12 | 100% reduction`. Apply one
complete correction only after exact bytes pass this gate. Any surviving/new
family, uncovered reachable cell, candidate-derived expected set, new authority,
or non-killed mutation triggers stop/reset.
