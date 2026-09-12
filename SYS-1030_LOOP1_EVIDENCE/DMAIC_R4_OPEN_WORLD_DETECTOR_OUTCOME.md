# SYS-1030 R4 open-world detector DMAIC outcome

Status: **REJECTED CORRECTION — PRODUCT/RUNTIME TESTS NOT RUN**

This file records the terminal outcome of the semantic-detector experiment. It
is lifecycle evidence only: it does not amend the proposal, product code,
runtime, jobs, deployment, or the next replacement design. Git remains the sole
durable lifecycle and source authority.

## Define

The attempted correction claimed that a source-derived Python module/call
fixed point plus may-value analysis could reject every indirect path to the
managed scheduler/provider authority while accepting all disjoint dynamic
dispatch. The acceptance target was one residual finding to zero without
changing the already-passing provider, route/module transport, keyed-flow,
archive/writer, and N01-N22 controls.

## Measure

Rejected exact bytes:

- `R4_OWNERSHIP_DAG.md`: SHA-256
  `80456e8272e74433bea0150cbed6711067bcbbab0f3ada97618c8b20419d9e25`,
  9,104 bytes, 167 LF;
- `R4_OWNERSHIP_MODEL.json`: SHA-256
  `1e865904696953a71d0da5b347d367f03f6b6b2ee64a28c7b686abb90b37fcbf`,
  1,469,053 bytes, 55,497 LF;
- `validate_r4_ownership_model.py`: SHA-256
  `12e754b0dee30a8a3b57e5eac2f0a686227c6e4d5ced179897008b2bade0083d`,
  147,868 bytes, 3,209 LF;
- unchanged `TECH_SPEC_R3_PROPOSED.md`: SHA-256
  `5db8fea1dd8ffddf72d7f3fc1403d397eb03323d516d8e05b90254d9517fdc47`.

Prediction: `1 -> 0`. Actual: `1 -> 1`. Delta: `0`. Reduction: `0%`.

The built-in baselines reported PASS and retained the 360-module fixed point
and 22/22 killed modeled mutations. Their source-call census was not stable
across interpreters: Python 3.8 reported 2,948 calls and Python 3.11 reported
2,965. A lower interpreter therefore cannot issue the semantic PASS when any
protected source is unparseable; only one canonical product interpreter may
produce that verdict.

The surviving Black Belt source-shaped counterexample was committed only in a
scratch pinned-source clone and then removed. Inside the already reachable
`gateway.run.start_gateway` path it selected the managed provider callable
through a higher-order constructor:

```python
import operator as op
import cron.scheduler_provider as provider

op.attrgetter("resolve_cron_scheduler")(provider)
```

The validator returned PASS with unchanged modeled membership and mutation
counts. The scratch counterexample OID was
`19ab90d9cd3862880e014ff47003a478800ad011`; it is evidence, not workflow or
source authority.

## Analyze

Root cause: the experiment treated open-world Python reflective dispatch as a
finite syntax-recognition problem, so every newly handled spelling left an
equivalent unmodeled callable construction outside the claimed invariant.

The Python 3.8/3.11 call-count split is a second measurement failure, not a
product difference: a parser that omits an unparseable protected function
cannot prove closure. Adding `attrgetter`, `methodcaller`, or another syntax
handler would repeat the same non-falsifiable expansion and is forbidden.

## Improve: finite replacement contract

The next design removes the normative 1.469 MB ownership model, the 147 KB
semantic analyzer, the 360-module fixed point, the may-value domain, and the
open-ended dynamic-syntax zoo. They remain historical rejected evidence only.
The replacement is bounded to the literal 25-path production inventory in
proposal section 9: 18 unique Hermes paths and the seven exact MarketWatch
writer paths in section 3.0. No source-discovery result may enlarge or silently
shrink that protected set.

The replacement acceptance contract is:

1. Bind exact baseline and candidate Git OIDs. Under the one-deployer,
   no-concurrent-checkout-mutation assumption, require clean trees and read
   every one of the 25 literal paths from Git objects, not ambient files.
2. Use one declared canonical product interpreter to parse every protected
   path and protected function at both OIDs. Any parse omission or unsupported
   changed syntax is refusal. Python 3.8 may prove checker compatibility but
   cannot emit the semantic verdict.
3. Compare canonical baseline and candidate function ASTs. Classify every
   added, removed, and changed protected function; attest unchanged functions
   only by exact baseline-bound AST equality.
4. For each changed or added protected function, enumerate its allowed direct
   static authority calls. The candidate must contain exactly those literal
   direct calls with the declared caller, arguments, and consumer; omission,
   duplication, substitution, or a different caller refuses.
5. Changed protected functions may introduce no indirect authority dispatch.
   A changed AST containing `getattr`, `globals`, `locals`, `importlib`,
   `__import__`, `eval`, `exec`, `operator.attrgetter`,
   `operator.methodcaller`, callable aliases, or higher-order invocation on an
   authority path refuses. This is a finite candidate-diff rule, not a claim to
   decide arbitrary Python behavior.
6. Existing dynamic constructs are not proven globally disjoint. They are
   accepted only when their containing protected function is AST-identical to
   the bound baseline and the function is outside the changed direct-call set.
   A baseline change invalidates that attestation and forces explicit review.
7. Execute the ten literal public route witnesses from proposal section 4.3.
   Each witness binds host, route, profile/home/jobs store, selected provider,
   claim owner, result consumer, and expected direct authority call. The matrix
   must detect old/new target substitution, indirect dispatch, missing calls,
   extra calls, wrong binding, and wrong result consumer.
8. Require both proofs: the bounded Git function-AST/direct-call check and the
   ten-route behavioral matrix. A digest or member count is observational only
   and cannot substitute for either proof.

## Control

The replacement is acceptable only when the canonical parser covers all 25
paths at both OIDs; the function-AST diff has no unclassified member; every
changed authority edge is a declared literal direct call; no changed function
adds indirect authority dispatch; all baseline attestations bind unchanged
ASTs; and all ten route witnesses pass mutation-sensitive substitution,
omission, duplication, binding, and consumer controls.

This finite contract is the handoff boundary for the Product author. No
replacement bytes are authored in this lifecycle commit. Product/operations
role-parity preflight remains required before a future formal-review subject is
frozen.

Coauthors: Systems Panel; Runtime DevOps Panel; Six Sigma Panel.
