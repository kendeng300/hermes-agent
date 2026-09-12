# SYS-1030 R4 Ownership Model — Nonnormative Reading Guide

> **NONNORMATIVE.** This file is a navigation aid only. It does not define or
> override a node, edge, type, manifest member, condition, status, count,
> matrix row, mutation, or expected result.

The sole canonical ownership artifact is
`R4_OWNERSHIP_MODEL.json`. The sole mechanical preapplication check is
`validate_r4_ownership_model.py`. If this guide and either artifact differ,
the JSON plus a successful validator result controls review.

## Scope

The model is evidence for a future SYS-1030 implementation correction. It is
not imported by Hermes or MarketWatch and creates no runtime authority. It
adds no service, store, mutex, state ledger, READY file, host scan, systemd
unit, process group, xdist workflow, or VCS replica. Git objects remain the
only source identity.

The operating assumption is one trusted deployer, clean ordinary Git
worktrees, and no concurrent checkout mutation during a controlled attempt.
Violation aborts the attempt; the model does not implement exclusivity.

## Reading order

1. Start with `subjects` and `locators`; every locator is checked from the
   supplied Git object, never from mutable working-tree bytes.
2. Read `types` before `nodes`. Every scalar, enum, record, and union is
   instantiated by the validator, including every union variant.
3. Follow deployment nodes `P00` through `P10`, then ordinary/controlled
   admission through `O00` and `A00`.
4. Follow runtime nodes `R00` through `R13`; branch only at the explicit
   ordinary, quarantine, and shutdown aggregate nodes.
5. Follow lifecycle closure `S00` through `S02`, and the exact registry
   producer edge `E043_REGISTRY_SNAPSHOT`.
6. Follow archive nodes `B00` through `B05` and writer nodes `W00`
   through `W01`.
7. Use `manifests` for the source-derived host, route, module, provider,
   binding, store, archive, MarketWatch writer, cut, result, and proof sets.
8. Use `matrices` for complete activation, managed-result, cleanup/shutdown,
   HTTP cancellation/release, exact host membership, archive,
   route-enablement, and prior-regression products.
9. Use `mutations` to trace N01 through N22. Each mutation changes only an
   in-memory clone during validation and must fail before an effect.

## Lifecycle trace guide

For a scheduled or manual witness, begin at its manifest member and source
locator. Trace its source-owned ingress to `R00`, exact admission to `R01`,
durable or compatible claim ownership at `R02`, registry production at
`R03`, the one outer wrapper at `R04`, and the nonregistering body leaf at
`R05`.

The retained body, cleanup decision, output, delivery, and finalization values
have separately named edges into each aggregate. The Chronos re-arm reads the
claim/bundle from its real producer edge `E29_BUNDLE`, not from an aggregate.
Release occurs only after the actual worker path finishes.

Cleanup uncertainty follows the quarantine branch. Shutdown follows the
shutdown branch. Neither branch fabricates unnamed “prior stages,” and neither
can be folded into the ordinary finalizer. The canonical matrices determine
all exact products and precedence.

## Activation trace guide

A controlled attempt follows the parent prelaunch aggregate, an owner-held
child, child bootstrap, provider-free target derivation, sole provider
resolution, final binding/route construction, and module verification while
admission remains closed. It then carries a canonical owner-local receipt into
the complete postlaunch aggregate and only then the open-token edge. No type or
edge before `C03` may contain `ResolvedProviderV2`. Ordinary startup uses its
separate source path and is unaffected when no controlled expectation is
present.

Every cross-process collection boundary is explicit: `KEYED_FAN_OUT` carries
one exact `child_key` from a nonempty parent set to one child, and
`KEYED_FAN_IN` returns one child value into an exact nonempty parent set.
Unmarked cardinality changes, lost/duplicate/swapped keys, a token delivered
to the wrong child, or a child locally fabricating a collection are invalid.

The model distinguishes process hosts from routes and keeps conditional HTTP
reachability source-owned. Messaging profile observations never select cron
bindings. Callers do not supply home, jobs-file, provider, module, route, or
host sets.

`RouteSetV1.members` and `ModuleSetV1.members` are the authority. They are
packed as a nonnull, strictly increasing, duplicate-free prefix of their typed
nullable tuple and null in every remaining slot. `count` equals that prefix
length. `digest` is an observational SHA-256 of the compact canonical JSON
array of the same prefix; it cannot add, remove, replace, or reorder a member.
`C04` constructs the exact conditional route set inside
`DerivedCronBindingV2`; `C05` constructs the exact source-derived module set;
`C06` verifies and returns both; `C08` copies them into `ActivationOpenV1`;
`A00` preserves that value byte-for-byte for `R01` admission. Exact member
equality, not count or digest equality, is the admission predicate. A
same-count route or module substitution refuses before provider/store access.

## Archive and deployment trace guide

Archive preflight precedes all writes. Zero jobs targets, one store, multiple
stores, refusal, partial progress, and unknown commit truth are represented in
the canonical archive matrix. Each accepted store reaches the existing strict
store owner; MarketWatch fallback extraction reaches only the modeled refusal
path for a jobs member.

Deployment evidence follows the Git and owner-local host edges in the model.
Cross-process values use only the modeled canonical receipt types and existing
owner-local transports. No persisted observation becomes scheduling,
recovery, retry, or admission authority.

## Validation

Run from the Hermes worktree with locally available pinned objects:

```bash
python3 SYS-1030_LOOP1_EVIDENCE/validate_r4_ownership_model.py \
  --model SYS-1030_LOOP1_EVIDENCE/R4_OWNERSHIP_MODEL.json \
  --hermes-root /path/to/hermes-agent \
  --hermes-oid <40-hex-object> \
  --marketwatch-root /path/to/marketwatch \
  --marketwatch-oid <40-hex-object>
```

The validator is standard-library-only and read-only. It does not fetch,
write, create temporary files, inspect mutable source bytes, or scan host
processes. It first enumerates each complete pinned tree, then selects and
parses source-relevant entry, authority, caller, import, writer, and wrapper
relationships without intersecting them with a model member list. Before that
selection it builds the complete tracked production-Python import/call graph
and the relevant tracked TypeScript/shell call/write graph. Unsupported syntax
on a managed relation refuses; it is never silently filtered. The module
authority is the complete intersection of forward source-derived-entrypoint
reachability and reverse managed-sink reachability, with no later regex/name
intersection. A source-connected `getattr`, `globals`, `importlib`, dynamic
import, or constructed managed target is evaluated by one bounded may-value
fixed point over finite strings or `UNKNOWN`, import/callable aliases,
ordinary/annotated/chained assignments, concatenation, finite f-strings and
conditionals, and local/tracked helper parameters and returns. Every reached
dynamic site is exactly `RESOLVED_MANAGED`, `RESOLVED_DISJOINT`, or `REFUSED`.
A resolved dynamic managed dispatch, or an unresolved target on a known
managed receiver/namespace/import candidate, is a hard refusal; proven
disjoint source-valid loaders remain legal. Forward entrypoint reachability is
checked for refusals before reverse sink intersection. Forward entrypoint
reachability and reverse sink reachability
must reach that same source-owned projection. MarketWatch writer discovery
parses every tracked
production Python candidate, including aliases, function-local bindings, and
direct destination expressions, plus both shell extractor callers. It checks
keyed fan-in/fan-out cardinality and identity conservation and binds every
finite-matrix cell—including its invalid complement—to an exact
reviewer-owned status/reason/nullability/exit image. Its self-falsifiers add an
independently detected source-shaped writer; exercise alias/local/direct
writer forms and a full in-memory source-map matrix for literal, constructed,
aliased, helper-returned, namespace, and dynamic-import targets; replace
route/module members without changing cardinality,
omit a source-derived module, fabricate an early provider, and alter legal and
invalid matrix images. A PASS is
preapplication evidence only; it is not implementation or runtime acceptance.

## Freeze rule

The JSON and validator must be reviewed as exact bytes. Panel review and two
independent audits must report no undefined schema or edge, cycle, unowned
effect, ambiguous union, source-set mismatch, surviving N01–N22 mutation, or
prior-family regression before the proposal is changed. Any failure stops the
batch. The future implementation remains panel-authored and independently
three-reviewed.
