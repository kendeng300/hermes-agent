# SYS-1030 Loop-1 R5 — finite replacement DMAIC

## Define

Quality goal: a complete, source-real specification that reaches independent
3/3 review in two to three iterations, with no author/reviewer role-coverage gap
and no open-world analyzer standing in for product behavior.

The root runner observes. Product/Operations, Architecture/Runtime, and
Systems/Concurrency/Data coauthor the same bytes. Six Sigma is independent QA;
it is not an author substitute. Formal Architecture, Systems, and Product
reviewers are different people with matching role coverage.

## Measure

R4 began this correction with 13 normalized defects:

| ID | Measured defect |
|---|---|
| C01 | 1.469 MB open-world model and 148 KB analyzer could not prove a finite negative |
| C02 | ten source-real route×occurrence cells were collapsed |
| C03 | claim/admission/cut/restart ambiguity states were incomplete |
| C04 | canary did not state exact B/C2 byte conservation at every cut |
| C05 | six roles replaced the source-real nine-host/11-role lifecycle |
| C06 | auth/profile/home/store/provider ownership was not one immutable binding |
| C07 | claim-before-admission contradicted admission-before-first-store-open |
| C08 | current-disk hashes were presented as actual loaded-byte proof |
| C09 | candidate/remote/merge/deploy/running Git identity was incomplete |
| C10 | archive rules ignored non-jobs, zero-jobs, and partial-result truth |
| C11 | pre-run did not exclude every constructor/setup/business effect |
| C12 | generic mutator/starter callbacks carried executable authority |
| C13 | local PID absence could falsely classify a remote claim dead |

Baseline normalized defect count: **13**. Target after this batch: **0**.

## Analyze

One-line root cause: **the author panel lacked Product/Operations role coverage
and tried to compensate with an inferred open-world model, so reviewers saw
routes, operator outcomes, and source boundaries the authors had never enumerated.**

Fishbone summary:

- People: author roles were architecture/systems/Six Sigma while reviewers were
  architecture/systems/product; QA did not supply product authorship.
- Method: review findings were patched into an expanding graph rather than
  normalized into one pre-edit contract and one batch.
- Measurement: node/edge counts measured model size, not route/cut behaviors.
- Machine/tool: a whole-program syntax fixed point produced false confidence and
  high disk/CPU cost.
- Material/source: ambient and loaded bytes, production edit scope and witness
  scope, and route and host axes were conflated.
- Environment: imagined multi-writer/race recovery requirements contradicted the
  one-runner/one-deployer operating assumption and duplicated Git lifecycle.

## Improve

The three matched author roles first froze one contract, including the boundary
warnings. This batch then:

1. deletes the R4 DAG/model/analyzer from current normative evidence;
2. replaces them with one 25-path manifest and a short Git-object/AST syntax
   preflight;
3. makes the canonical spec enumerate ten semantic routes, nine hosts, 11 roles,
   all occurrence/cut/restart states, exact owners, and exact proof nodes;
4. resolves the lifecycle contradiction with a RESERVED record created before
   first store-open and a no-nested-lock rule;
5. replaces executable callback authority with closed data-only operations and
   direct branches;
6. makes archive, canary, remote-owner, loaded-code, and Git handoff truth
   explicit and falsifiable.

Expected defect change: **13 -> 0 (−13)** before independent formal review.

## Control

The control is deliberately small:

- Git branch/commits are the only durable iteration status.
- The manifest phase must pass under Python 3.11 against both pinned source OIDs.
- Candidate phase admits only the exact 25 production paths, exact declared
  function dispositions, and exact direct authority edges.
- Parameterized behavior tests, not graph labels, prove routes and cuts.
- Author-panel Product, Architecture, and Systems audit the same exact bytes 3/3;
  independent Six Sigma reports the actual C01–C13 count; only then do three
  matched formal reviewers review.
- If post-batch count is nonzero, findings are normalized once, root-caused
  against C01–C13, corrected in one batch, and the predicted-versus-actual count
  is recorded. A new general analyzer, state file, READY flag, systemd unit,
  xdist dependency, or local Git replica is not an allowed correction.
