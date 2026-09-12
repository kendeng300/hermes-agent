# SYS-1030 R4 pass-4 DMAIC outcome

Status: **REJECTED INTERMEDIATE CANDIDATE — TESTS NOT RUN**

This evidence records the panel's exact-byte pass-4 preapplication result. It
does not amend `TECH_SPEC_R3_PROPOSED.md`, product code, runtime, jobs, or
deployment. Git remains the sole durable lifecycle and source authority.

## Define

The pass-4 CTQs were:

1. literal sorted typed `RouteSetV1` and `ModuleSetV1` members must survive
   construction, verification, activation, and admission; their digests are
   observational only, and same-count substitution must fail;
2. the source oracle must discover the complete tracked Python import/call
   graph and relevant TypeScript/shell call/write graph before semantic
   filtering, then compute forward entrypoint and reverse sink closure;
3. MarketWatch writer discovery must cover aliases, function-local and direct
   destination expressions, and both shell wrappers; unsupported relevant
   dynamic syntax must refuse.

## Measure

Rejected exact subject:

- `R4_OWNERSHIP_DAG.md`: SHA-256
  `2a1ea55874cde51963a25df5f3a964b2281898969e48ec8f1cef462a34b23fc2`,
  8,078 bytes, 152 LF;
- `R4_OWNERSHIP_MODEL.json`: SHA-256
  `1c5877ad5bcb53262cb7737f9997f137da812968fa5c31a52ddf312a502e6d2c`,
  1,342,956 bytes, 52,076 LF;
- `validate_r4_ownership_model.py`: SHA-256
  `24eb30e04793be599d4fa48f6205a8427bb1405f0d4eb83b0530050aa2cd8299`,
  112,093 bytes, 2,426 LF;
- unchanged proposal `TECH_SPEC_R3_PROPOSED.md`: SHA-256
  `5db8fea1dd8ffddf72d7f3fc1403d397eb03323d516d8e05b90254d9517fdc47`.

The read-only validator passed under Python 3.8 and Python 3.11 with 54 nodes,
100 edges, 89 types, 11 manifests/139 members, 2,393 matrix rows, 17 host-route
edges, 45 modeled modules, 907 tracked production Python modules scanned,
3,400 import edges, 2,950 call edges, 76 relevant TypeScript/shell relations,
and 22/22 killed mutations. Black Belt nevertheless reproduced one surviving
source mutation. The prior two residuals therefore reduced to one, a 50%
reduction, rather than the predicted two-to-zero closure.

## Analyze

Root cause: source-connected closure was incorrectly intersected with a
regex/name-seeded `relevant_modules` prefilter, and unresolved dynamic call
relations were not rejected.

Minimal reproduced counterexample: add a tracked `hidden_dynamic_bridge.py`
that is imported/called by `gateway.run`, imports `cron.scheduler_provider`,
and resolves `resolve_` + `cron_scheduler` through `getattr`. The validator
observed 908 modules and 3,402 import edges but still accepted the unchanged
45-member module manifest and all 22 mutations. The bridge was in the complete
forward/reverse source closure, yet the later named prefilter removed it;
`getattr` also escaped the static call relation without a refusal.

## Improve

One bounded correction is authorized:

- the module authority set is the complete `source_connected` fixed point,
  never its intersection with a named/regex prefilter;
- a source-connected unresolved `getattr`, `globals`, `importlib`, dynamic
  import, or dynamically constructed managed target refuses before model
  acceptance;
- the full-validator falsifier commits the source-shaped hidden bridge to an
  isolated source fixture and requires module-set change or the exact dynamic
  refusal before any effect.

No provider, keyed fanout/fanin, lifecycle, archive, result, proposal, or
runtime authority changes are included in this correction.

## Control

The next candidate is predicted to reduce one residual to zero. Before freeze,
both Python 3.8 and 3.11 baseline runs, the hidden dynamic bridge, all existing
same-count route/module substitutions, MarketWatch alias/local/direct writer
falsifiers, N01-N22, AST/JSON, and diff checks must pass. The Black Belt must
challenge the same exact bytes before a correction commit. Any surviving
source-connected omission or accepted unresolved dynamic target is a hard
reject.

Coauthors: Systems Panel; Runtime DevOps Panel; Six Sigma Panel.
