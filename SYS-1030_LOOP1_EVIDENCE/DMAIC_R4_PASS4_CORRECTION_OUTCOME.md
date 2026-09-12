# SYS-1030 R4 pass-4 correction DMAIC outcome

Status: **REJECTED CORRECTION — TESTS NOT RUN**

This file records the exact-byte result of the first correction to the pass-4
ownership-model candidate. It is review evidence only and does not amend the
proposal, implementation, runtime, jobs, or deployment. Git remains the sole
durable lifecycle and source authority.

## Define

The correction was required to make the complete forward-entrypoint ∩
reverse-managed-sink Python closure authoritative, without a later regex/name
prefilter, and to refuse unresolved dynamically constructed managed targets.
All already-passing typed route/module transport, provider, keyed-flow,
MarketWatch writer, matrix, and N01–N22 controls were to remain unchanged.

## Measure

Rejected exact correction:

- `R4_OWNERSHIP_DAG.md`: SHA-256
  `3e665f4e15c3a0709a7724d1d3aca8cb4d4db58854838bdf526de637c86ad0c7`,
  8,411 bytes, 157 LF;
- `R4_OWNERSHIP_MODEL.json`: SHA-256
  `1e865904696953a71d0da5b347d367f03f6b6b2ee64a28c7b686abb90b37fcbf`,
  1,469,053 bytes, 55,497 LF;
- `validate_r4_ownership_model.py`: SHA-256
  `d5344866e21d951d4a387baf3fef62c0c550456fc3a1642b9b3ff7bd58df038c`,
  115,205 bytes, 2,496 LF;
- unchanged `TECH_SPEC_R3_PROPOSED.md`: SHA-256
  `5db8fea1dd8ffddf72d7f3fc1403d397eb03323d516d8e05b90254d9517fdc47`.

Python 3.8 and 3.11 baselines passed with 360 literal fixed-point modules,
17 host-route edges, 22/22 killed model mutations, and the complete existing
writer/provider/cardinality controls. The inline and committed direct-expression
`hidden_dynamic_bridge` were rejected. The predicted residual movement was
one-to-zero; actual was one-to-one: delta zero and reduction zero percent.

## Analyze

Root cause: the correction mutation-tested one AST spelling and hand-inserted
one graph edge instead of testing semantic may-target flow through the real
source-to-oracle pipeline.

Surviving minimal counterexample, inside the already source-connected and
modeled `gateway.run` module:

```python
import cron.scheduler_provider as provider

def probe():
    target_name = "resolve_" + "cron_scheduler"
    return getattr(provider, target_name)
```

The validator returned PASS with the same 907 modules, 3,400 imports, 2,967
calls, 360 modeled modules, and 22/22 killed mutations. Its detector inspected
literal fragments only inside the `getattr` argument; `ast.Name` carried none,
and no scope-local value flow connected the assignment to the call.

## Improve

The sole authorized batch replaces spelling recognition with a source-map
may-value fixed point:

1. bounded finite-string or `UNKNOWN` values flow through imports, aliases,
   assignments, annotated/chained assignments, concatenation, f-strings,
   conditionals, parameters, and tracked helper returns;
2. `getattr`, `globals`, `locals`, `importlib.import_module`, and `__import__`
   are classified exactly `RESOLVED_MANAGED`, `RESOLVED_DISJOINT`, or
   `REFUSED`; known managed receiver/namespace/import candidates fail closed
   when their target remains `UNKNOWN`;
3. relation symbols come from the complete ticket set, including
   `_execute_job_now`, and their discovered wrapper closure; every
   forward-reachable tracked source is analyzed before reverse intersection;
4. resolved dynamic targets contribute real import/call edges; no manual
   `probe_graph` edge may stand in for source discovery;
5. the in-memory source-map falsifier passes the direct, local-variable,
   alias, chained/annotated, concat, f-string, conditional, and tracked-helper
   forms through the same full pipeline. Existing unrelated constant/dynamic
   attribute uses are negative controls and must remain accepted.

## Control

The next prediction is one-to-zero. Python 3.8 and 3.11 baselines, both exact
hidden-bridge commits, every semantic may-target matrix row, source-derived
module/call equality, same-count member substitutions, MarketWatch source
writer probes, provider authority, keyed fanout/fanin, invalid complements,
N01–N22, AST/JSON, and diff checks must pass. Independent DMAIC and Black Belt
must approve the same exact bytes before a correction commit.

Coauthors: Systems Panel; Runtime DevOps Panel; Six Sigma Panel.
