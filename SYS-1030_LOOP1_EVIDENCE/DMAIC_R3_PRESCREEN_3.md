# SYS-1030 Loop 1 — Round-3 independent prescreen 3

## Immutable subject

- Commit: `f5fb59631276ebb9c224bfb137a6f9d35fba23d6`
- Proposal blob: `b76ed8659bf29c76511a2ea733d14fd555b3450d`
- Proposal SHA-256: `c7d29f7f6fa4172aac33077f70e633f8005172d41fa53a7a85590b43bc08a753`
- Review result: `REJECT`; three valid atomic defects remain.

## Predeclared comparisons

- `1 -> 3 | +2 | 200.0% | expected 0 MISSED by 3`
- `17 -> 3 | -14 | 82.4%`
- `19 -> 3 | -16 | 84.2% | frozen target <=2 MISSED by 1`

One-line RCA: `The audit frame still trusted the proposal’s inventories and began at the corrected claim boundary, so pre-auth profile authority, omitted live writers, and unnamed canonical Git authorities escaped source-to-final-consumer enumeration.`

## R2-04 — JWT authority is not bound to the selected profile

Owners and evidence: both handlers load verifier audience, issuer, and JWKS
from the ambient profile before parsing or resolving the target at
`hermes_cli/web_server.py:10561` and
`gateway/platforms/api_server.py:3817`.

Counterexample: an A-profile token with a body naming B can resolve and execute
B, while a legitimate B-profile token can be rejected by A's ambient verifier
configuration.

Minimum correction: one shared authenticated Chronos target owner verifies the
token against profile-scoped verifier configurations. Only profiles for which
the token verifies are eligible for `(job_id, fire_at)` resolution, and the
owner returns the exact bound target. An invalid token searches no job store.
The discriminating proof sends an A token with a B body and requires refusal,
then sends a legitimate B token through both handlers and requires the same
exact B target and execution path.

## R2-01 — Writer inventory is incomplete

Omitted Hermes owners:

- `hermes_cli.backup.run_import`
- `hermes_cli.backup.restore_quick_snapshot`

Both directly overwrite `jobs.json`.

Omitted MarketWatch owners:

- `utilities/market_holiday_manager.py`
- `scripts/utilities/market_holiday_manager.py`
- `utilities/holiday_watchdog.py`
- `scripts/utilities/holiday_watchdog.py`

These owners load before locking, replace the whole document, and use
`jobs.lock` rather than Hermes `.jobs.lock`, so they can erase a concurrently
committed claim.

Counterexample: a listed owner reads the preclaim document, the scheduler
commits an ACTIVE claim, and the owner then replaces the whole document from
its stale image, erasing the claim despite the proposal's strict-lock rule for
the incomplete inventory.

Minimum correction: route every direct write above through strict Hermes jobs
owners that preserve or refuse ACTIVE claims. Add a claim-between-read/write
test for each root and shipped MarketWatch path and both Hermes restore/import
paths; the stale writer must write zero bytes or merge only explicitly allowed
leaves while preserving the exact claim.

## R2-18 — Canonical remote is undefined

Counterexample: because the proposal names no canonical URL and ref, an
attacker- or operator-retargeted `origin` containing the candidate can satisfy
the ancestry check without proving either canonical repository.

Minimum correction:

- Hermes authority is exactly
  `https://github.com/kendeng300/hermes-agent.git` at `refs/heads/main`.
- MarketWatch authority is exactly
  `https://github.com/kendeng300/marketwatch.git` at `refs/heads/master`.
- Validate each URL and ref, fetch that exact ref immediately before the
  comparison, and reject a wrong URL, wrong ref, or stale pre-fetch value.

The discriminating proof substitutes each wrong URL/ref and a stale cached
remote-tracking ref; all must fail before deployment. Fresh exact-ref fetch and
ancestry comparison for both repositories must pass.

## Next control point

Predeclared next result: `3 -> 0 | cut 3 | 100%`.

A repository-wide, source-derived owner/caller/writer/authority census is
required before correction. The next batch must close these three source-to-
final-consumer paths without trusting proposal inventories, adding ambient
fallback, or narrowing repository scope. Exact corrected bytes then require a
whole-document independent reread before freeze.
