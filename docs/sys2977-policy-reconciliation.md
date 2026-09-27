# SYS-2977: reconcile the deployed policy identity

Registered cron agents failed during construction because the renderer trusted
a different policy body from the deployed SOUL. The failure occurs in
`activate_initial_profile()` -> `prepare_model_switch()` -> `render_profile()`,
before conversation dispatch. This reconciliation approves the exact existing
runtime policy identity after fresh semantic and security review under the
user's scoped SYS-2977 authorization. It does not edit the deployed policy.

| Identity | Previous renderer contract | Reviewed deployed policy |
| --- | --- | --- |
| Normalized body SHA-256 | `9175c49e20f242f42ca1d043486c5edae742628b0ed551ecf882e662e0fe1d24` | `94075360d64c1bde30039428c3295c8721330043f03edf07bbb2d6cd55bd515e` |
| Ordered REQ manifest SHA-256 | `7963ac5a1f6bbc99c5d3fcb064ca50cc5062b729fe7135b3ea515cee69660f55` | `71c71b61aa36002e0c9d3bbdeff75860f7de275ebe2e075ca506aa2800bc5eaa` |
| Total and unique REQ tuples | 152 | 150 |

The body normalization and ordered JSON tuple encoding are unchanged. The
renderer still accepts exactly one reviewed body and one ordered manifest.
Default rendering now uses the existing `default_core_path()` through
`load_policy_core()`: the active `HERMES_HOME/SOUL.md`, rather than a separate
hardcoded HOME policy. Explicit content and path overrides must satisfy the
same identity checks; there is no fallback to another profile's SOUL.

## Semantic review

These are all differences from the previously bound body:

- Additional same-turn execution, quality-gated productivity, passivity
  self-check, and data-flow investigation wording reinforces existing duties.
  The root-cause heading also adds "NEVER SKIP".
- The extended forbidden-dismissal block is removed, leaving its marker. The
  SYSTEM STEWARD paragraph still forbids all seven dismissal rationales and
  requires unresolved failures to be fixed within authority or reported as
  blockers. The five protected safety blocks are unchanged.
- Four REQs change their gate label from `standard_process_confidence` to
  `process_evidence_required`: `loop1_spec_finalization`,
  `loop2_impl_code_review`, `loop3_ci_test_gate`, and
  `standard_process_confidence`.
- The `SYS-2070`/`effectiveness_tracking` REQ becomes gate-journal observability
  prose. The `post_merge_verification` and `no_force_push` REQs become prose
  naming `mechanical_post_merge_transaction_verification` and
  `mechanical_push_ref_integrity`. No-force-push, force-with-lease prohibition,
  and post-merge verification imperatives remain in the policy.
- The liveness gate label becomes `gate_agent_liveness_watchdog_enabled`, and
  `gate_registry_single_authority`/`gate_registry_projection_sync` is added.
  Three removed tuples and one added tuple account for the count of 150.

Review found no permission to weaken the protected safety duties in this
delta. Reapproval authenticates these exact bytes; it does not certify that
their named legacy gates or transaction controls exist or remain enabled.
Current MarketWatch SYS-1000 uses a different six-step workflow, while this
deployed body and its adapters retain older LOOP/process and observer-command
claims. The body still names `/home/linux/MarketWatch` while the adapters name
`/home/linux/.hermes/scripts`, and their legacy arguments differ from today's
observer CLI. Resolving those semantic discrepancies is outside this repair. The old
`soul_mandate_survival` marker-window assertion is not reinstated, and this
change does not claim that its obsolete local gate passes.

## History and evidence boundaries

Hermes commit `6e34a40f05903d017810c37bb120850265bcfe6b` included the deployed
94075360 identity inside the much larger TEST-034 candidate. Its later revert,
`685f8f763f00e89affa0d526f4673186bfead03a`, restored the previous renderer
contract while the live SOUL retained the newer bytes. That history explains
the mismatch; historical commit labels and review prose are not reused as
fresh approval. This ticket restores none of TEST-034's 125-file candidate
infrastructure.

Regression evidence must include both registered model routes using the exact
policy fixture and unchanged production pins, deterministic render identity,
isolated default-source selection, and rejection of old or tampered policy
through every supported input. Existing synthetic fixtures remain useful for
isolated checks but cannot establish that deployed bytes match production
pins. Full committed-branch validation and applicable existing CI/gates remain
required before release. This note claims no test result, behavioral A/B parity,
provider execution, or predictive-quality improvement.

## Release and rollback

Publish only the reviewed, validated Hermes ticket branch to canonical `main`.
The active config checkout and the MarketWatch scripts checkout are separate
repositories; a scripts observer result does not certify Hermes. No scheduler,
job, pause, disable, adapter, model-switch transaction, harness, or gate is
changed by this batch.

Runtime processes that already imported the renderer retain its old constants
until reloaded through the existing authorized service procedure. Preserve all
job pause/disable settings through deployment. Check the policy boundary
offline: running a cron job can execute its pre-script before rendering.
Do not rebuild an existing conversation's cached prompt mid-turn. This patch
does not perform a service reload, resume jobs, or prove provider admission
beyond the validation actually recorded for its committed version.

Rollback is a normal revert of this ticket's renderer, tests, and documentation
as one unit. With the live SOUL unchanged, rollback reinstates the diagnosed
fail-closed mismatch. Restoring an old SOUL or disabling integrity checks is
not an authorized rollback route.
