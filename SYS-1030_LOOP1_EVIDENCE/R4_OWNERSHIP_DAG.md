# SYS-1030 R4 preapplication ownership DAG

Status: panel-authored preapplication authority. This file does not amend
`TECH_SPEC_R3_PROPOSED.md`, implementation, tests, jobs, runtime, or deployment.
It must pass two independent source-derived audits before one proposal edit.

Coauthors: Systems Panel; Runtime DevOps Panel; Six Sigma Panel.

## 1. Scope, source identity, and operating axiom

This DAG closes the fourteen normalized families in
`DMAIC_R4_PANEL_PREFLIGHT_OUTCOME.md`. It covers claim admission, exact target
selection, durable occurrence authority, process-local execution ownership,
cleanup, output, delivery, finalization, Chronos re-arm, context release,
shutdown, archive writes, loaded-code evidence, host control, Git deployment,
and the read-only SYS-1029 handoff.

The operating axiom is exact: one trusted deployer/operator owns one attempt;
candidate and deployed directories are ordinary clean Git worktrees; and no
checkout or tracked-file mutation occurs between parent preflight and process
exit. A violated axiom aborts the attempt. Tests deliberately violate it only
before cron admission and require refusal. No exclusivity mechanism is added.

Controlled activation is opt-in. Without `CronDeploymentExpectationV2`, current
gateway, dashboard, desktop, provider, readiness, messaging, and manual behavior
is unchanged. With it, the existing process-local cron lifecycle begins CLOSED.
Only this DAG can OPEN an exact target. `served_profiles` is never cron authority.

Out of scope: a new service, store, ledger, mutex, process group, systemd unit,
READY/status authority, hash registry, host scan, xdist control, NAS wire change,
product canary, product pause/resume, or SYS-1029 result acceptance.

Pinned implementation source for derivation is Hermes Git OID
`82e0a91352e3f1ac8f3a8fce2beee66d2339a2cc`; MarketWatch is the freshly fetched
canonical candidate/review/merge identity defined in section 12. Git identity,
not this document or a generated list, is the source-set authority.

## 2. DAG grammar and scalar types

```text
H40 := exactly 40 lowercase hexadecimal characters
UUID4 := canonical lowercase RFC-4122 version-4 string
AbsPath := absolute canonical path string
ProfileName := nonempty source-valid canonical profile name

DagNodeV1={
  id:nonempty unique stable token,
  repo:"HERMES"|"MARKETWATCH"|"CONTROL",
  source_oid:H40,
  module_path:repository-relative path,
  owner:qualified callable|"ONE_DEPLOYER",
  kind:"SOURCE"|"INGRESS"|"OBSERVE"|"AUTH"|"ACTIVATE"|"ADMIT"|
       "CLAIM"|"REGISTER"|"EXECUTE"|"CLEANUP"|"OUTPUT"|"DELIVER"|
       "FINALIZE"|"AGGREGATE"|"REARM"|"RELEASE"|"QUARANTINE"|
       "STORE"|"ARCHIVE"|"DEPLOY"|"HANDOFF",
  inputs:closed tuple[Type.field],
  outputs:closed tuple[Type.field],
  failure_result:closed union tag
}
DagEdgeV1={
  id:nonempty unique stable token,
  from_node:DagNodeV1.id, from_output:Type.field,
  wire_type:closed type, to_node:DagNodeV1.id, to_parameter:Type.field,
  lifetime:"CALL"|"TASK"|"THREAD"|"PROCESS"|"DURABLE_JOB_ROW"|"DEPLOYMENT",
  authority:"SOURCE_DERIVED"|"PRODUCER_OWNED",
  cut:"PRE"|"COMMITTED"|"ACK_UNKNOWN"|"POST",
  consumer_result:closed union tag,
  negative_mutant:nonempty test mutation
}
```

Every node and edge ID occurs once. Every input has exactly one incoming edge
except a pinned source/Git/operator input. Every output has one consumer or is
explicitly terminal. `object`, `dict`, `result`, `context`, `appropriate`, and
`applicable` are not wire types. A caller cannot create a claim, target, route,
module set, cleanup decision, finalization result, host set, or deployment set.

## 3. Closed host, binding, module, provider, and activation types

```text
CronProcessRoleV2="GATEWAY"|"DASHBOARD"|"DESKTOP_PRIMARY"|
  "DESKTOP_PROFILE"|"CLI_TICK"|"CLI_MANUAL"|"CANARY"
CronHostModeV1="GATEWAY_HOST"|"PLAIN_DASHBOARD"|"DESKTOP_CHILD"|
  "COMMAND_TICK"|"COMMAND_MANUAL"|"COMMAND_CANARY"
CronProviderNameV1="builtin"|"chronos"
CronOccurrenceKindV1="RECURRING"|"SCHEDULED_ONESHOT"|"MANUAL"|"CANARY"
CronClaimRouteV1="BUILTIN_SCHEDULED"|"CHRONOS_SYNC"|
  "GATEWAY_CHRONOS_HTTP"|"DASHBOARD_CHRONOS_HTTP"|
  "CLI_MANUAL"|"CANARY"

CronBindingExpectationV1={
  profile:ProfileName,
  home_realpath:AbsPath,
  jobs_file_realpath:AbsPath exactly home_realpath+"/cron/jobs.json",
  provider_name:CronProviderNameV1
}
CronDeploymentExpectationV2={
  schema:"hermes-cron-deployment-expectation-v2",
  expected_git_oid:H40,
  process_role:CronProcessRoleV2,
  host_mode:CronHostModeV1,
  allowed_bindings:nonempty sorted unique tuple[CronBindingExpectationV1]
}
ControlledChildTargetV1="GATEWAY_RUN"|"DASHBOARD"|"SERVE"|
  "CRON_TICK"|"CRON_RUN"|"CANARY"
ControlledChildArgvV1={
  discriminator:exact tuple["cron","deployment","child"],
  target:ControlledChildTargetV1,
  expectation:CronDeploymentExpectationV2,
  ordinary_target_argv:nonempty tuple[string]
}
CronExpectationParseResultV1=
  ORDINARY{controlled:false,argv:null,expectation:null,error:null}|
  VALID{controlled:true,argv:ControlledChildArgvV1,
    expectation:CronDeploymentExpectationV2,error:null}|
  INVALID{controlled:true,argv:null,expectation:null,
    error:nonempty string,process_exit:2}
```

Ordinary `gateway run`, `dashboard`, `serve`, `cron tick`, `cron run`, and
canary retain their exact ABI and produce ORDINARY. A controlled child is
invoked only through the distinct existing-CLI extension:

```text
hermes cron deployment child --target <ControlledChildTargetV1>
  --cron-deployment-expect-oid <H40>
  --cron-deployment-expect-role <CronProcessRoleV2>
  --cron-deployment-expect-host-mode <CronHostModeV1>
  --cron-deployment-binding <ProfileName> <AbsPath-home> <AbsPath-jobs> <provider>
  [--cron-deployment-binding <ProfileName> <AbsPath-home> <AbsPath-jobs> <provider>]...
  -- <exact ordinary target argv>
```

The discriminator, target, three singleton flags, repeated bindings, delimiter,
and target argv occur in that order. Bindings are nonempty and sorted by
`(profile,home,jobs,provider)`. The ordinary tail is exactly one of `gateway
run`, `dashboard`, `serve`, `cron tick`, `cron run <source-valid-job-id>`, or
`cron canary <source-valid-job-id>` and must match `--target`; it contains no
deployment flags. Missing discriminator, target mismatch, partial group,
duplicate singleton, zero/reordered/duplicate binding, unknown/extra value,
relative/noncanonical path, or `jobs != home/cron/jobs.json` is INVALID/exit 2
before cron import or target dispatch. The controlled parser never falls back
to the ordinary parser. An invocation that did not enter the distinct
`cron deployment child` path is ORDINARY and preserves current behavior.

The controlled parser owner is
`hermes_cli.cron_deployment.parse_controlled_child_argv`; the existing cron
parser recognizes only the literal discriminator and hands the remaining argv
to it before importing any target/cron module. It returns VALID or INVALID,
never ORDINARY. The parent deployment owner builds `ControlledChildArgvV1` from
its source-derived `ExecutorHostKeyV1` set. A controlled coordinator is forbidden
from calling an ordinary launch owner directly: its sole launch API accepts the
typed `ControlledChildArgvV1`, encodes the literal grammar above, parses that
exact encoding back to `VALID`, and compares both the parsed typed value and the
final Popen argv byte-for-byte with the parent value immediately before spawn.
Therefore deleting the complete discriminator/suffix cannot silently select the
ordinary path: it is a parent-side launch refusal and no child is created.
Electron performs the same literal prefix/grammar/typed-key assertion before
`spawn`. `startHermes` uses target SERVE with role DESKTOP_PRIMARY and the
primary bindings. `spawnPoolBackend` uses target SERVE with role
DESKTOP_PROFILE and exactly the binding whose profile/home/store equals its
injective `backendPool[profile]` key.

In the child, `parse_controlled_child_argv` is the only producer of a controlled
expectation. `VALID.expectation` feeds the pure route/module constructors and
the externally-bound bootstrap verifier. The constructor's exact downstream
module set feeds `observe_loaded_cron_modules`, which alone performs normal
imports and returns `tuple[ObservedModuleV2]`; that tuple and the independently
derived expected set feed `verify_cron_host_code`. A syntactically legal
role/provider substitution fails byte equality with the parent value before
spawn or exact expectation/host/binding equality before provider/store access.
`backend-command.ts` formats but cannot select a binding. Deleting the complete
expectation portion still leaves the mandatory controlled discriminator and is
INVALID; deleting the discriminator makes the parent byte comparison refuse
before spawn. A parent/child key mismatch, extra binding, or reordered argv also
refuses before target dispatch or cron import.

```text
LoadedModuleProjectionV2={
  role:"BOOTSTRAP"|"ENTRYPOINT"|"STORE"|"ORCHESTRATOR"|"RESOLVER"|
       "CONFIG"|"PROFILE"|"HOME"|"SECRET"|"AUTH"|"PROVIDER_INTERFACE"|
       "PROVIDER_LOADER"|"SELECTED_PROVIDER"|"FIRE_VERIFIER"|"NAS_CLIENT"|
       "HTTP_OWNER"|"MANUAL_OWNER",
  module_name:nonempty dotted string,
  module_realpath:AbsPath to ordinary nonsymlink file,
  checkout_realpath:AbsPath,
  relative_path:canonical repository-relative path,
  git_oid:H40, git_blob_oid:H40,
  provenance:"BOOTSTRAP_EXTERNALLY_BOUND"|"IMPORT_OBSERVED"
}
ObservedModuleV2=in-memory pair(
  module_object:ModuleType,
  projection:LoadedModuleProjectionV2,
  activation_id:UUID4
)
ProviderBindingProjectionV1={
  requested_name:CronProviderNameV1,
  canonical_name:CronProviderNameV1,
  provider_kind:"BUILTIN"|"BUNDLED_PLUGIN",
  loader_module_name:string|null,
  selected_module_name:nonempty dotted string,
  provider_class_qualname:nonempty dotted string,
  instance_name:CronProviderNameV1
}
ResolvedProviderBindingV1=in-memory pair(
  provider_object:CronScheduler,
  projection:ProviderBindingProjectionV1,
  loader_observation:ObservedModuleV2|null,
  selected_observation:ObservedModuleV2
)
```

Before process start, ONE_DEPLOYER proves the exact executable/launcher and the
source-derived bootstrap/entry module paths and blobs against clean Dh. A fresh
child is then spawned through that proof's controlled invocation path. At the child's first
stdlib-only cut, it validates the executing entry realpath and expected OID and
snapshots `sys.modules`. Every already-loaded module required by the source
entry/import graph must appear exactly once as BOOTSTRAP_EXTERNALLY_BOUND and
must equal the parent's path/blob/OID proof. Every downstream claim-path module
must be absent from that snapshot, then imported normally and recorded as
IMPORT_OBSERVED immediately after that import transaction and before an exported
symbol is read or called. The two sets are disjoint and their union must equal
`derive_cron_module_names`; overlap, omission, an unexpected preload, or an
expected import-observed module already present refuses.

The retained module object—not a later `module.__file__` read—is execution
provenance. Under the one-deployer/no-mutation axiom, the externally proven entry
bytes and immediately observed downstream bytes are the loaded code. Tests that
run an old entry with new disk, or import downstream A then replace disk with B,
must refuse without demanding that the executing entry was absent from its own
`sys.modules` snapshot.

The provider table has exactly two legal rows:

| requested | loader | selected module/class | required equality |
|---|---|---|---|
| builtin | null | `cron.scheduler_provider.InProcessCronScheduler` | `instance.name=canonical=requested="builtin"` |
| chronos | `plugins.cron_providers` | `plugins.cron_providers.chronos.ChronosCronScheduler` | `instance.name=canonical=requested="chronos"` |

The loader returns exactly one provider object whose actual class object belongs
to the retained selected module object. Alias, fallback, collision, second
instance, cached foreign module, class/module swap, or unequal `.name` refuses.
Uncontrolled resolver fallback remains unchanged.

```text
HostCodeIdentityV1={
  activation_id:UUID4, role:CronProcessRoleV2, host_mode:CronHostModeV1,
  pid:positive int, process_start_ticks:positive int,
  executable_realpath:AbsPath, checkout_realpath:AbsPath,
  git_oid:H40, modules:sorted unique tuple[LoadedModuleProjectionV2]
}
HostCodeVerificationResultV1=
  VERIFIED{identity:HostCodeIdentityV1,reason:null}|
  UNAVAILABLE{identity:null,reason:"PROCESS_IDENTITY_UNAVAILABLE"|
    "GIT_UNAVAILABLE"|"IMPORT_FAILED"}|
  MISMATCH{identity:null,reason:"OBSERVATION_MISSING"|
    "EXPECTED_OID_MISMATCH"|"DIRTY_CHECKOUT"|"PRELOADED_CLAIM_MODULE"|
    "MODULE_SET_MISMATCH"|"MODULE_ORIGIN_MISMATCH"|
    "MODULE_BLOB_MISMATCH"|"MIXED_CHECKOUT"|"MIXED_OID"|
    "ROLE_ENTRYPOINT_MISMATCH"}
CronTargetActivationV1={
  target_activation_id:UUID4, host:HostCodeIdentityV1,
  binding:CronBindingExpectationV1, provider:ProviderBindingProjectionV1,
  routes:sorted unique tuple[CronClaimRouteV1],
  modules:sorted unique tuple[LoadedModuleProjectionV2]
}
TargetActivationResultV1=
  VERIFIED{target:CronTargetActivationV1,reason:null}|
  UNAVAILABLE{target:null,reason:"PROFILE_UNAVAILABLE"|"CONFIG_UNAVAILABLE"|
    "SECRET_UNAVAILABLE"|"PROVIDER_UNAVAILABLE"}|
  MISMATCH{target:null,reason:"BINDING_NOT_ALLOWED"|"PROFILE_MISMATCH"|
    "HOME_MISMATCH"|"STORE_MISMATCH"|"PROVIDER_MISMATCH"|
    "ROUTE_SET_MISMATCH"|"MODULE_SET_MISMATCH"|"HOST_NOT_VERIFIED"}|
  REFUSED_CLOSED{target:null,reason:"SHUTDOWN_CLOSED"}
CronAdmissionResultV2=
  ADMITTED{target:CronTargetActivationV1,reason:null}|
  REFUSED{target:null,reason:"ACTIVATION_NOT_OPEN"|
    "ACTIVATION_ID_MISMATCH"|"BINDING_MISMATCH"|
    "ROUTE_NOT_ALLOWED"|"SHUTDOWN_CLOSED"}
BindingDiscoveryResultV1=
  AVAILABLE{bindings:nonempty sorted unique tuple[CronBindingExpectationV1],
    reason:null}|
  UNAVAILABLE{bindings:empty tuple,reason:"PROFILE_CATALOG_UNAVAILABLE"|
    "CONFIG_UNAVAILABLE"|"SECRET_SCOPE_UNAVAILABLE"}|
  MISMATCH{bindings:empty tuple,reason:"DUPLICATE_PROFILE"|
    "DUPLICATE_HOME"|"BINDING_NOT_ALLOWED"|"BINDING_SET_MISMATCH"}
CronActivationObservationV1=
  AVAILABLE{target:CronTargetActivationV1,reason:null}|
  UNAVAILABLE{target:null,reason:"PROCESS_IDENTITY_UNAVAILABLE"|
    "MODULE_UNAVAILABLE"|"MODULE_NOT_REGULAR"|"MODULE_UNTRACKED"|
    "PROCESS_IDENTITY_UNREADABLE"}
ControlledCronActivationV1=
  VERIFIED{target:CronTargetActivationV1,activation_id:UUID4,
    reason:null,admission:"OPEN",cli_exit:0}|
  UNAVAILABLE{target:null,activation_id:null,
    reason:CronActivationObservationV1.UNAVAILABLE.reason,
    admission:"CLOSED",cli_exit:4}|
  MISMATCH{target:null,activation_id:null,
    reason:"DIRTY_CHECKOUT"|"LOADED_CODE_MISMATCH"|
      "MODULE_BLOB_MISMATCH"|"MIXED_CHECKOUT"|"MIXED_OID"|
      "PROVIDER_AMBIGUOUS"|"EXPECTATION_MISMATCH"|"SHUTDOWN_CLOSED",
    admission:"CLOSED",cli_exit:5}
CronActivationCheckV1=
  VERIFIED{target:CronTargetActivationV1,reason:null,cli_exit:0}|
  NOT_RUNNING{target:null,reason:"RUNTIME_STATUS_MISSING"|
    "PROCESS_NOT_RUNNING",cli_exit:3}|
  UNAVAILABLE{target:null,reason:"PROCESS_IDENTITY_UNREADABLE"|
    "ACTIVATION_UNAVAILABLE",cli_exit:4}|
  MISMATCH{target:null,reason:"RUNTIME_STATUS_INVALID"|"PID_REUSED"|
    "COMMAND_MISMATCH"|"EXPECTATION_MISMATCH",cli_exit:5}
```

Every union row above is disjoint and total. Only VERIFIED/ADMITTED carries a
target or identity and null reason. Every other row has a null payload and one
listed reason. `CronActivationObservationV1` is always publishable and never
gates ordinary startup. Under controlled deployment only
`ControlledCronActivationV1.VERIFIED` opens admission. The source-backed live
reader emits exactly one `CronActivationCheckV1`; argparse failure is exit 2
outside the union. A non-VERIFIED check blocks deployment acceptance and
SYS-1029 handoff, not ordinary uncontrolled startup.

## 4. Source-derived route and module constructors

Callers never supply `routes` or `modules`.
`cron.scheduler_provider.derive_cron_claim_routes(role,host_mode,provider)` and
`derive_cron_module_names(role,host_mode,provider)` are total pure owners.

| role / host mode / provider | exact derived routes |
|---|---|
| GATEWAY / GATEWAY_HOST / builtin | BUILTIN_SCHEDULED |
| GATEWAY / GATEWAY_HOST / chronos | CHRONOS_SYNC, GATEWAY_CHRONOS_HTTP |
| DASHBOARD / PLAIN_DASHBOARD / builtin | invalid: no execution route |
| DASHBOARD / PLAIN_DASHBOARD / chronos | DASHBOARD_CHRONOS_HTTP |
| DESKTOP_PRIMARY / DESKTOP_CHILD / builtin | BUILTIN_SCHEDULED |
| DESKTOP_PRIMARY / DESKTOP_CHILD / chronos | CHRONOS_SYNC, DASHBOARD_CHRONOS_HTTP |
| DESKTOP_PROFILE / DESKTOP_CHILD / builtin | BUILTIN_SCHEDULED |
| DESKTOP_PROFILE / DESKTOP_CHILD / chronos | CHRONOS_SYNC, DASHBOARD_CHRONOS_HTTP |
| CLI_TICK / COMMAND_TICK / builtin | BUILTIN_SCHEDULED |
| CLI_MANUAL / COMMAND_MANUAL / builtin or chronos | CLI_MANUAL |
| CANARY / COMMAND_CANARY / builtin or chronos | CANARY |

Every other tuple refuses before activation. Recurring versus scheduled
one-shot is derived from the strict job row/claim and never caller-selected.

The common Python module set is exactly `hermes_cli.cron_deployment`, `cron`,
`cron.jobs`, `cron.scheduler`, `cron.scheduler_provider`, `hermes_constants`,
`hermes_cli.config`, `hermes_cli.profiles`, and `agent.secret_scope`.
`hermes_cli.cron_deployment` is BOOTSTRAP_EXTERNALLY_BOUND exactly once because
it owns the controlled discriminator parser and deployment verifier before any
target import; it may never be omitted, duplicated as IMPORT_OBSERVED, or
reconstructed from current disk after parsing. Authenticated Chronos adds
`hermes_cli.auth`, `plugins.cron_providers`,
`plugins.cron_providers.chronos`, `plugins.cron_providers.chronos.verify`, and
`plugins.cron_providers.chronos._nas_client`. Role entry modules are:

- gateway: `hermes_cli.main`, `hermes_cli.subcommands.gateway`,
  `hermes_cli.gateway`, `gateway.run`, `gateway.platforms.api_server`;
- dashboard/desktop: `hermes_cli.main`, `hermes_cli.subcommands.dashboard`,
  `hermes_cli.web_server`;
- CLI tick: `hermes_cli.main`, `hermes_cli.subcommands.cron`,
  `hermes_cli.cron`;
- CLI manual/canary: the CLI-tick parser/dispatcher set plus
  `tools.cronjob_tools` when that tool route is selected.

The exact root-of-trust classifier derives which role-entry modules are already
loaded at the stdlib cut from the pinned import graph; it does not accept a
caller list. Set equality and exactly one provenance tag are mandatory.
Identical module objects deduplicate; two names, objects, origins, OIDs, or
blobs do not.

## 5. Runtime authority types

```text
RecurringExecutionClaimV1={
  schema:"cron-recurring-claim-v1",claim_id:UUID4,
  job_id:nonempty source-valid ID,
  mode:"BUILTIN_RECURRING"|"CHRONOS_RECURRING",
  scheduled_for:aware exact string,claimed_at:aware exact string,
  next_run_after:aware exact string,owner_profile:ProfileName,
  owner_pid:positive int,owner_start_ticks:positive int,
  status:"ACTIVE"|"NOT_SUBMITTED"|"OPERATOR_SKIPPED",
  terminal_error:string|null
}
OneShotExecutionClaimV1={
  schema:"cron-oneshot-execution-claim-v1",claim_id:UUID4,
  job_id:nonempty source-valid ID,
  mode:"BUILTIN_ONESHOT"|"CHRONOS_ONESHOT",
  scheduled_for:aware exact string,claimed_at:aware exact string,
  owner_profile:ProfileName,owner_pid:positive int,
  owner_start_ticks:positive int,
  repeat_completed_before:nonnegative int|null,
  repeat_completed_after:positive int|null,
  status:"ACTIVE"|"OPERATOR_SKIPPED",terminal_error:string|null
}
ExecutionModeV2="BUILTIN_RECURRING"|"BUILTIN_ONESHOT"|
  "CHRONOS_RECURRING"|"CHRONOS_ONESHOT"|"MANUAL"|"CANARY"
ExecutionContextV2={
  schema:"cron-execution-context-v2", lifecycle_id:UUID4,
  target_activation_id:UUID4|null,
  ingress:"BUILTIN_TICK"|"CLI_TICK"|"CHRONOS_SYNC"|
    "CHRONOS_GATEWAY_HTTP"|"CHRONOS_DASHBOARD_HTTP"|
    "MANUAL_TOOL"|"CANARY_CLI",
  mode:ExecutionModeV2, jobs_file_realpath:AbsPath,
  owner_profile:ProfileName, job_id:nonempty source-valid ID,
  claim_id:UUID4, claim_field:"recurring_claim"|"run_claim"|"fire_claim",
  owner_pid:positive int, owner_start_ticks:positive int,
  scheduled_for:aware exact string|null, exact_job_postimage:immutable mapping
}
RegisteredExecutionV2={
  key:(jobs_file_realpath,job_id,mode,claim_id),
  context:ExecutionContextV2,
  phase:"REGISTERED"|"WORKER_STARTED"|"SCRIPT_CLEANUP_PENDING"|
    "CLEANUP_COMPLETE"|"CLEANUP_UNCERTAIN"|"EFFECTS_STARTED"|
    "FINALIZING"|"RELEASED",
  shutdown_requested:bool,
  cleanup:CleanupResultV1|null,
  release_owner:"OUTER_PREWORKER"|"WORKER"|null
}
```

All scheduled modes have nonnull `scheduled_for` byte-equal to their durable
claim. MANUAL and CANARY have null `scheduled_for`. The claim/store owner—not
the HTTP body or operator—constructs every context leaf. Uncontrolled manual
compatibility may have null `target_activation_id`; controlled execution must
match its admitted target.

```text
ChronosFireRequestV2={job_id:nonempty source-valid ID,
  fire_at:aware exact string}
ChronosAuthProfileV2={profile:ProfileName,home_realpath:AbsPath,
  jobs_file_realpath:AbsPath,provider_name:"chronos",portal_url:nonempty string,
  expected_audience:nonempty string,nas_jwks_url:nonempty string,
  callback_url:nonempty string}
ChronosClaimedExecutionV2=in-memory immutable object {
  request:ChronosFireRequestV2, auth_profile:ChronosAuthProfileV2,
  target:CronTargetActivationV1,
  provider_binding:ResolvedProviderBindingV1,
  claim:RecurringExecutionClaimV1|OneShotExecutionClaimV1,
  execution_context:ExecutionContextV2,
  exact_job_postimage:immutable mapping
}
ChronosClaimResultV2=
  CLAIMED{bundle:ChronosClaimedExecutionV2,error:null}|
  GONE{bundle:null,error:null}|DUPLICATE{bundle:null,error:null}|
  ALREADY_ADVANCED{bundle:null,error:null}|
  INVALID_REQUEST{bundle:null,error:nonempty string}|
  UNAUTHORIZED{bundle:null,error:nonempty string}|
  CONFLICT{bundle:null,error:nonempty string}|
  CLAIM_REFUSED{bundle:null,error:nonempty string}|
  UNAVAILABLE{bundle:null,error:nonempty string}|
  COMMIT_UNKNOWN{bundle:null,error:nonempty string}
```

The CLAIMED bundle retains the provider and module objects, target, profile,
home, store, auth projection, exact claim/context, and postimage end-to-end.
Nothing reconstructs these from a string ID or ambient state.

For both claim types, ACTIVE has null `terminal_error`; every terminal tag has
one nonempty error. The one-shot repeat pair is simultaneously null or satisfies
`after=before+1<=repeat.times`. Neither ACTIVE claim expires or is automatically
replayed. A recurring claim commits its exact future successor in the same store
mutation; a scheduled one-shot commits its finite increment in the same store
mutation. COMMIT_UNKNOWN never creates an execution edge.

## 6. Acyclic runtime DAG

The only legal ranks are:

```text
R0 entry
R1 strict decode/auth/allowed-binding selection without jobs-store access
R2 exact target lookup and target admission
R3 durable claim
R4 process-local registration
R5 worker-entry acknowledgement
R6 nonregistering bound execution leaf
R7 ManagedBodyResultV1
R8 CleanupResultV1
R9 OutputResultV1
R10 DeliveryResultV2
R11 FinalizationResultV1
R12 ManagedRunOutcomeV3 aggregate
R13 Chronos re-arm/observer
R14 exact release
```

Every edge increases rank. Cold restart begins at a durable claim reader and is
not a back edge. Re-arm reads only the R11 postimage and cannot invoke R3 for the
same occurrence.

The sole wrapper graph is:

```text
entry -> strict decode/auth/select allowed binding -> exact target lookup
 -> require_cron_target_admission -> exact store open/claim -> register
 -> run_registered_execution -> worker acknowledgement
 -> nonregistering bound leaf -> body -> cleanup -> output -> delivery
 -> exact finalizer -> aggregate -> optional Chronos re-arm -> release
```

`cron.scheduler.run_registered_execution(context, job_postimage, runner)` is the
only outer registered worker wrapper. `runner` is a producer-owned callable
bound by the admission owner, never caller authority. It invokes exactly one of
`CronScheduler._run_claimed_in_active_store(bundle)` or the builtin/canary/manual
nonregistering leaf. Those leaves call `_run_one_job_managed_body` directly and
never register, admit, or call the outer wrapper. The outer wrapper never calls
itself. Its `finally` exact-releases once after the actual worker returns or
raises.

`ChronosCronScheduler.run_claimed(bundle)` enters only bundle-owned home,
secret, and jobs-store scopes; calls the nonregistering leaf; consumes the exact
finalizer result; reads/re-arms only the valid recurring successor with the same
retained provider object; resets scopes; and returns to the wrapper. Re-arm
failure is a typed `ChronosRearmError` containing the completed aggregate and is
observed exactly once; it never retries or changes the already returned HTTP 202.

## 7. Normative edge table

### 7.1 Exact nodes and ranks

| ID / rank | source owner | typed terminal output |
|---|---|---|
| D00 / D0 | `ONE_DEPLOYER` | literal candidate, canonical remote, QA, deployed-root inputs |
| D01 / D1 | `hermes_cli.cron_deployment.resolve_git_release_identities` | exact pair of `GitReleaseIdentityV1` |
| D02 / D2 | source host stop owners | `tuple[HostControlReceiptV1.STOPPED]` |
| D03 / D3 | deployment coordinator MW stage | verified clean Dmw and writer-set result |
| D04 / D4 | deployment coordinator Hermes stage | verified clean Dh result |
| D05A / D5 | CLI/Electron expectation builders | typed `ControlledChildArgvV1` plus injective host key |
| D05 / D5.1 | source host controlled launch owners | exact argv and controlled child handles |
| D05P / D5.2 | child `parse_controlled_child_argv` | `CronExpectationParseResultV1.VALID` or pre-import exit 2 |
| D06S / D5.3 | pure role/mode/provider constructors | exact source-derived route and module sets |
| D05O / D5.4 | `observe_loaded_cron_modules` normal-loader owner | exact `tuple[ObservedModuleV2]` |
| D06 / D6 | externally-bound bootstrap plus `verify_cron_host_code` | `HostCodeVerificationResultV1` |
| D07 / D7 | binding/provider/route owners plus `verify_and_open_cron_target` | `TargetActivationResultV1` |
| D08 / D8 | `hermes_cli.cron_deployment.verify_cron_deployment` | `DeploymentAcceptanceResultV1` and read-only SYS-1029 handoff |
| R00 / R0 | exact executable/HTTP/CLI entrypoint | source-derived host/route/occurrence input |
| R01 / R1 | shared strict decoder/authenticated allowed-binding selector | target-bound request/binding or refusal; no jobs-store access |
| R02 / R2 | exact target lookup plus `require_cron_target_admission` | `CronAdmissionResultV2` |
| R03 / R3 | recurring, one-shot, canary, or manual claim owner | exact committed claim/context/postimage or refusal |
| R04 / R4 | lifecycle registration under existing `_running_lock` | byte-equal `RegisteredExecutionV2` |
| R05 / R5 | outer wrapper first-instruction acknowledgement | exact worker-entry token |
| R06 / R6 | bound nonregistering execution leaf | completed execution-body facts |
| R07 / R7 | `cron.scheduler._run_one_job_managed_body` | `ManagedBodyResultV1` |
| R08 / R8 | unchanged supervisor protocol classifier | `CleanupResultV1` |
| Q01 / R8.1 | `quarantine_active_execution_after_cleanup_uncertain` | exact ACTIVE quarantine postimage/result |
| Q02 / R14.1 | durable claim reader and exact dead-owner skip owner | blocked/rejected/skipped restart result |
| R09 / R9 | existing output saver projected by typed owner | `OutputResultV1` |
| R10 / R10 | `_deliver_result_typed` | `DeliveryResultV2` |
| R11 / R11 | exact mode/claim finalizer | `FinalizationResultV1` |
| R12 / R12 | pure aggregate constructor | `ManagedRunOutcomeV3` |
| R13 / R13 | bound Chronos successor reader/re-arm owner | unchanged outcome or `ChronosRearmError` |
| R14 / R14 | outer wrapper `finally` | one exact release plus caller projection |
| S00 / S0 | gateway/dashboard/desktop/command close owner | lifecycle CLOSED |
| S01 / S1 | lifecycle snapshot owner | sorted immutable `tuple[ExecutionContextV2]` |
| S02 / S2 | owner-local drain/interruption owner | exact cleanup/finalization successor input |
| B00 / B0 | `hermes_cli.backup` whole-archive preflight | exact `tuple[ArchiveJobsTargetV1]` or zero-write refusal |
| B01 / B1 | selected-store strict mutation owner | `ArchiveStoreResultV1` |
| B02 / B2 | per-store readback owner | verified per-store truth |
| B03 / B3 | archive aggregate owner | `ArchiveImportResultV1` |
| W00 / W0 | `cron.jobs._commit_jobs_mutation` under selected `.jobs.lock` | exact jobs-file postimage/refusal/unknown |
| W01 / W-1 | source-derived live jobs writer entrypoints | typed selected-store mutation requests |

### 7.2 Topological edges

Each fan-out has its own edge ID and consumer; no row denotes two hidden edges.

| ID | from -> to; exact wire/lifetime | failure and discriminating mutant |
|---|---|---|
| E00 | D00 -> D05A; operator-selected controlled binding inputs / DEPLOYMENT | caller-created route/module/host sets are rejected |
| E01 | D00 -> D01; literal Git inputs / DEPLOYMENT | wrong URL/ref/stale fetch refuses |
| E02 | D01 -> D02; reviewed identities / DEPLOYMENT | broken Ch/Rh or Cmw/Rmw refuses before host stop |
| E03 | D01 -> D03; MW identity / DEPLOYMENT | broken Rmw/Mmw edge refuses |
| E04 | D03 -> D04; clean exact Dmw+writer proof / DEPLOYMENT | Hermes deploy before MW proof fails |
| E05 | D02 -> D05; complete STOPPED receipts / DEPLOYMENT | omitted desktop/profile child fails set equality |
| E06 | D04 -> D05; clean exact Dh / DEPLOYMENT | wrong/dirty deployment cannot launch controlled child |
| E07 | D05P -> D06; parsed expectation+externally-bound bootstrap/entry proof / PROCESS | partial/extra/changed argv leaf exits 2 |
| E08 | D05O -> D06; immediate normal-import `tuple[ObservedModuleV2]` / PROCESS | old import then current disk refuses |
| E09 | D06 -> D07; `HostCodeVerificationResultV1.VERIFIED` / PROCESS | any other row leaves cron CLOSED |
| E09A | D05P -> D06S; `VALID.expectation` role/host/provider tuple / CALL | caller cannot inject a derived set |
| E10A | D06S -> D05O; exact downstream IMPORT_OBSERVED module set / CALL | omitted/additional module fails before host verification |
| E10C | D06S -> D06; exact complete provenance-partitioned module set / CALL | overlap, gap, or extra module fails host verification |
| E10B | D06S -> D07; exact derived route set / CALL | omitted/additional route fails target verification |
| E10D | D05P -> D07; exact parsed `allowed_bindings` / PROCESS | child may not add a target binding |
| E11 | D07 -> D08; exact target activation set / DEPLOYMENT | omitted binding/activation fails aggregate equality |
| E12 | D02 -> D08; exact host receipt set / DEPLOYMENT | independent per-host PASS cannot hide missing host |
| E13A | D01 -> D08; reviewed/merged `GitReleaseIdentityV1` pair / DEPLOYMENT | any Ch/Rh/Mh or Cmw/Rmw/Mmw mutation refuses |
| E13B | D03 -> D08; clean exact Dmw+writer result / DEPLOYMENT | Dmw or writer mutation refuses |
| E13C | D04 -> D08; clean exact Dh result / DEPLOYMENT | Dh mismatch or dirt refuses |
| E14 | D07 -> R02; VERIFIED activation map / PROCESS | OPEN-before-compare fails |
| E15 | R00 -> R01; strict request plus source-derived route identity / CALL | malformed or caller-underdeclared route refuses |
| E16 | R01 -> R02; authenticated exact allowed binding/request / CALL | ambient A used for selected B fails |
| E17 | R02 -> R03; `CronAdmissionResultV2.ADMITTED.target` / CALL | any jobs-store open before exact target admission fails |
| E18 | R03 -> R04; committed context/postimage/bundle / DURABLE_JOB_ROW | COMMIT_UNKNOWN never starts |
| E19 | R04 -> R05; registered record / TASK or THREAD | submit-before-register fails |
| E20 | R05 -> R06; worker token+immutable bundle / THREAD | generic scheduler or recursive wrapper fails |
| E21 | R06 -> R07; body call inputs / CALL | execution leaf may not aggregate/finalize |
| E22 | R07 -> R08; `ManagedBodyResultV1` / CALL | body depending on final result is a cycle |
| E23 | R08 COMPLETE/NOT_APPLICABLE -> R09; cleanup decision / CALL | unknown cleanup cannot enter output |
| E24 | R08 INCOMPLETE/UNKNOWN -> Q01; sticky decision / DURABLE_JOB_ROW | late COMPLETE cannot overwrite UNKNOWN |
| E25 | R09 -> R10; `OutputResultV1` / CALL | output failure forbids delivery |
| E26A | R07 -> R11; exact body result / CALL | body tag cannot be reconstructed from output |
| E26B | R08 -> R11; exact nonuncertain cleanup result / CALL | INCOMPLETE/UNKNOWN cannot reach finalizer |
| E26C | R09 -> R11; exact output result / CALL | save result cannot be inferred from a path |
| E26D | R10 -> R11; exact delivery result / CALL | job-ID-only or delivery-null alias refuses |
| E27 | R11 -> R12; `FinalizationResultV1`+prior stages / CALL | aggregate cannot be finalizer input |
| E28 | Q01 -> R12; quarantine result+prior stages / CALL | quarantined aggregate must be CLEANUP_UNVERIFIED |
| E29 | R12 -> R13; aggregate+exact Chronos bundle / THREAD | ambient-store or dropped-bundle re-arm fails |
| E30 | R12 -> R14; non-Chronos aggregate / CALL or THREAD | non-Chronos route cannot enter re-arm |
| E31 | R13 -> R14; outcome or `ChronosRearmError` / TASK or THREAD | actual worker still releases exactly once |
| E32 | S00 -> S01; CLOSED lifecycle / PROCESS | post-close admission fails |
| E33 | S01 -> S02; immutable exact context snapshot / PROCESS | post-kill job-ID resample fails |
| E34 | S02 -> R08; exact interrupted cleanup input / PROCESS | shutdown cannot invent COMPLETE |
| E35 | S02 -> R11; non-uncertain exact interruption tuple / DURABLE_JOB_ROW | UNKNOWN path is excluded and must use Q01 |
| E36 | Q01 -> Q02; ACTIVE postimage / DURABLE_JOB_ROW | generic clear/retry/resume fails |
| E37 | B00 -> B01; one normalized selected target / CALL | bad later member discovered after first write fails |
| E38 | B01 -> W00; exact store mutation request / DURABLE_JOB_ROW | nested/wrong-store lock fails |
| E39 | W00 -> B02; committed/refused/unknown postimage / CALL | readback uncertainty cannot claim success |
| E40 | B02 -> B03; ordered per-store results / CALL | cross-store atomicity may not be fabricated |
| E41 | W01 -> W00; typed selected-store mutation / DURABLE_JOB_ROW | direct save/replace or lock-failure write fails |
| E42 | D05A -> D05; typed expectation argv+injective child key / PROCESS | deleting the whole controlled discriminator/suffix refuses before spawn |
| E42A | D05 -> D05P; actual child argv byte-equal to parent `ControlledChildArgvV1` / PROCESS | legal role/provider substitution or ordinary-path fallthrough exits 2 before import |

## 8. Body, cleanup, output, delivery, finalization, and aggregate

```text
ManagedBodyResultV1=
  REFUSED{processed:false,pre_run:"NOT_CONFIGURED",agent:"NOT_APPLICABLE",
    content_bytes:null,error:nonempty string}|
  LEGACY_ALREADY_HANDLED{processed:true,pre_run:"NOT_CONFIGURED",
    agent:"NOT_APPLICABLE",content_bytes:null,error:fixed compatibility text}|
  PRE_RUN_FAILED{processed:true,pre_run:"FAILED",agent:"NOT_RUN",
    content_bytes:nonempty diagnostic bytes,error:nonempty string}|
  AGENT_FAILED{processed:true,pre_run:"SUCCESS"|"NOT_CONFIGURED",
    agent:"FAILED",content_bytes:nonempty diagnostic bytes,error:nonempty string}|
  EMPTY_RESPONSE{processed:true,pre_run:"SUCCESS"|"NOT_CONFIGURED",
    agent:"SUCCESS",content_bytes:exact zero bytes,error:nonempty string}|
  WHITESPACE_EMPTY{processed:true,pre_run:"SUCCESS"|"NOT_CONFIGURED",
    agent:"SUCCESS",content_bytes:nonempty all-whitespace bytes,error:nonempty string}|
  INTENTIONAL_SILENCE{processed:true,pre_run:"SUCCESS",
    agent:"NOT_APPLICABLE"|"SUCCESS",content_bytes:source value accepted by
    `cron.scheduler._is_silent_response`,error:null}|
  NONEMPTY{processed:true,pre_run:"SUCCESS"|"NOT_CONFIGURED",
    agent:"NOT_APPLICABLE"|"SUCCESS",content_bytes:nonempty nonsilent bytes,
    error:null}
CleanupResultV1=
  NOT_APPLICABLE{evidence:null}|COMPLETE{evidence:exact supervisor protocol|null}|
  INCOMPLETE{evidence:exact bounded protocol evidence}|
  UNKNOWN{evidence:exact bounded uncertainty evidence}
OutputResultV1=
  NOT_REQUESTED{path:null,error:null}|
  SAVED{path:AbsPath,error:null}|
  FAILED{path:null,error:nonempty string}
DeliveryResultV2=
  NOT_REQUESTED{error:null}|SUPPRESSED{error:null}|
  SUPPRESSED_EMPTY{error:null}|NOT_CONFIGURED{error:null}|
  DELIVERED{error:null}|FAILED{error:nonempty string}
FinalizationResultV1=
  NOT_ATTEMPTED{claim_id:UUID4|null,postimage:null,error:null}|
  APPLIED{claim_id:UUID4,postimage:immutable mapping,error:null}|
  REMOVED{claim_id:UUID4,postimage:null,error:null}|
  FAILED{claim_id:UUID4,postimage:null,error:nonempty string}
ManagedRunOutcomeV3={schema:"cron-managed-run-outcome-v3",
  context:ExecutionContextV2|null,body:ManagedBodyResultV1,
  cleanup:CleanupResultV1,output:OutputResultV1,
  delivery:DeliveryResultV2,finalization:FinalizationResultV1,
  overall:"REFUSED"|"LEGACY_ALREADY_HANDLED"|"CLEANUP_UNVERIFIED"|
    "SHUTDOWN_INTERRUPTED"|"PRE_RUN_FAILED"|"AGENT_FAILED"|
    "EMPTY_RESPONSE"|"OUTPUT_FAILED"|"DELIVERY_FAILED"|
    "FINALIZATION_FAILED"|"SUCCESS"
}
```

`ManagedBodyResultV1` contains no cleanup, output, delivery, finalization, or
overall leaf. The exact finalizer consumes the body/stage values, never an
aggregate. The aggregate owner runs last and is pure.

The sole finalizer dispatch is closed and qualified:

```text
cron.jobs.finalize_recurring_occurrence(
  context:ExecutionContextV2, body:ManagedBodyResultV1,
  cleanup:CleanupResultV1, output:OutputResultV1,
  delivery:DeliveryResultV2) -> FinalizationResultV1
cron.jobs.finalize_oneshot_occurrence(
  context:ExecutionContextV2, body:ManagedBodyResultV1,
  cleanup:CleanupResultV1, output:OutputResultV1,
  delivery:DeliveryResultV2) -> FinalizationResultV1
cron.jobs.finalize_paused_job_canary(
  context:ExecutionContextV2, body:ManagedBodyResultV1,
  cleanup:CleanupResultV1, output:OutputResultV1,
  delivery:DeliveryResultV2) -> FinalizationResultV1
cron.jobs.finalize_compatible_manual_fire(
  context:ExecutionContextV2|null, body:ManagedBodyResultV1,
  cleanup:CleanupResultV1, output:OutputResultV1,
  delivery:DeliveryResultV2) -> FinalizationResultV1
cron.scheduler.build_managed_run_outcome(
  context,body,cleanup,output,delivery,finalization) -> ManagedRunOutcomeV3
```

Each managed finalizer validates the exact mode, claim field, claim ID, store,
profile, and committed postimage under the selected store's existing lock.
Quarantine never dispatches a finalizer. The compatible manual owner projects
to existing `mark_job_run`/public booleans and creates no scheduled authority.

Cleanup tags come only from the unchanged supervisor protocol classifier:
verified ordinary completion is COMPLETE; exit 124 with the sole bounded line
`CLEANUP INCOMPLETE\n` is INCOMPLETE; exit 124 with `CLEANUP UNKNOWN\n`, or any
missing, extra, malformed, unreadable, unexpected-status, or otherwise unproved
attestation is UNKNOWN. A message substring or caller argument cannot choose it.

The complete legal product families are:

| body | cleanup | output | delivery | finalization | aggregate |
|---|---|---|---|---|---|
| REFUSED | NOT_APPLICABLE | NOT_REQUESTED | NOT_REQUESTED | NOT_ATTEMPTED | REFUSED |
| LEGACY_ALREADY_HANDLED | NOT_APPLICABLE | NOT_REQUESTED | NOT_REQUESTED | NOT_ATTEMPTED | LEGACY_ALREADY_HANDLED |
| any entered body | INCOMPLETE or UNKNOWN | NOT_REQUESTED | NOT_REQUESTED | NOT_ATTEMPTED | CLEANUP_UNVERIFIED |
| PRE_RUN_FAILED | NOT_APPLICABLE or COMPLETE | SAVED | NOT_CONFIGURED, DELIVERED, or FAILED | APPLIED, REMOVED, or FAILED | precedence below |
| AGENT_FAILED | NOT_APPLICABLE or COMPLETE | SAVED | NOT_CONFIGURED, DELIVERED, or FAILED | APPLIED, REMOVED, or FAILED | precedence below |
| EMPTY_RESPONSE | NOT_APPLICABLE or COMPLETE | SAVED | SUPPRESSED_EMPTY | APPLIED, REMOVED, or FAILED | EMPTY_RESPONSE unless finalization failed |
| WHITESPACE_EMPTY | NOT_APPLICABLE or COMPLETE | SAVED | SUPPRESSED_EMPTY | APPLIED, REMOVED, or FAILED | EMPTY_RESPONSE unless finalization failed |
| INTENTIONAL_SILENCE | NOT_APPLICABLE or COMPLETE | SAVED or source-compatible NOT_REQUESTED | SUPPRESSED | APPLIED, REMOVED, or FAILED | SUCCESS unless finalization failed |
| NONEMPTY | NOT_APPLICABLE or COMPLETE | SAVED | NOT_CONFIGURED, DELIVERED, or FAILED | APPLIED, REMOVED, or FAILED | precedence below |
| any nonrefused, nonquarantined body | NOT_APPLICABLE or COMPLETE | FAILED | NOT_REQUESTED | APPLIED, REMOVED, or FAILED | OUTPUT_FAILED unless earlier failure |

Only exact claimed nonquarantined work may have APPLIED, REMOVED, or FAILED
finalization. Compatible manual `None` context uses existing `mark_job_run` and
is projected into the same finalization union without inventing a claim.
Pre-run/agent diagnostic output may be saved/delivered, but cannot turn the
upstream failure into success. Delivery failure cannot hide an earlier failure.

Dominance is:

```text
REFUSED > CLEANUP_UNVERIFIED > SHUTDOWN_INTERRUPTED >
PRE_RUN_FAILED > AGENT_FAILED > EMPTY_RESPONSE > OUTPUT_FAILED >
DELIVERY_FAILED > FINALIZATION_FAILED > SUCCESS
```

`LEGACY_ALREADY_HANDLED` is its sole closed no-effect family. Any tuple not
generated by the table and dominance function is rejected; it is never coerced.

## 9. Monotonic cleanup, shutdown, and release

All transitions use the existing `_running_lock`; this DAG creates no second
lock. Legal process-local transitions are:

| prephase | event/owner | postphase | durable action | later COMPLETE? |
|---|---|---|---|---|
| REGISTERED | outer cancellation proves worker not entered | RELEASED | exact pre-API disposition or retain ACTIVE | impossible worker token |
| REGISTERED | worker acknowledgement | WORKER_STARTED | none | n/a |
| WORKER_STARTED | script starts cleanup | SCRIPT_CLEANUP_PENDING | none | allowed only from this exact phase |
| SCRIPT_CLEANUP_PENDING | worker proves COMPLETE | CLEANUP_COMPLETE | exact finalizer may follow | already selected |
| SCRIPT_CLEANUP_PENDING | worker proves INCOMPLETE/UNKNOWN | CLEANUP_UNCERTAIN | exact quarantine only | refused |
| SCRIPT_CLEANUP_PENDING | shutdown drain expires | CLEANUP_UNCERTAIN with UNKNOWN | exact quarantine only | refused |
| WORKER_STARTED/EFFECTS_STARTED | shutdown requests interruption without cleanup uncertainty | same phase plus shutdown flag | worker exact interrupted finalizer or ACTIVE retention | n/a |
| CLEANUP_COMPLETE | exact worker finalizer starts | FINALIZING | exact claim CAS | n/a |
| CLEANUP_UNCERTAIN | any finalizer/generic clear/late result | CLEANUP_UNCERTAIN | no write except idempotent exact quarantine | refused |
| FINALIZING | final result obtained | RELEASED | exact readback retained | n/a |

The first transition from `SCRIPT_CLEANUP_PENDING` is terminal for cleanup.
UNKNOWN/INCOMPLETE is sticky for the exact claim generation. A worker that later
obtains COMPLETE observes CLEANUP_UNCERTAIN and may only return the existing
quarantine result. The quarantine CAS retains the exact ACTIVE claim; a canary
also preserves its captured `enabled`, `state`, `paused_at`, and `paused_reason`
byte-for-byte, putting the bounded diagnostic only in its authorized result leaf.
Recurring/one-shot quarantine may perform its separately defined pause merge but
never clears, completes, advances, re-arms, or retries the claim.

Shutdown atomically closes admission and returns one sorted immutable context
snapshot before provider stop, task cancellation, process cleanup, or kill. A
close winner permits no register/API/worker effect; an admission winner appears
in the snapshot. Shutdown never resamples job IDs after process cleanup.

For HTTP, the outer coroutine owns a task handle plus a worker-entry token.
Cancellation before token acquisition removes only its byte-equal REGISTERED
record and starts no business action. A late thread sees the absent record and
returns without effects. Cancellation after token acquisition cannot release;
the actual thread retains the immutable bundle through result, finalization,
re-arm/error, and the outer wrapper's one release. Success, execution failure,
cleanup uncertainty, re-arm failure, and both cancellation cuts have one result.

Cold restart reads only durable claim truth. ACTIVE blocks replay, another
canary, resume, or trigger. Only the existing exact dead-owner operator skip may
consume it; PID reuse or unknown/inaccessible liveness refuses. No process-local
registry row is restart authority.

Compatibility is exact: public `cron.scheduler.run_one_job(...)->bool`,
`cron.jobs.claim_job_for_fire(...)->bool`, base/Chronos
`CronScheduler.fire_due(...)->bool`, one-shot finite completion/removal, and the
existing Chronos `{job_id,fire_at}` request remain unchanged projections. Only
private typed owners consume the new values. The current script-supervisor
process envelope, containment, protocol bytes, and cleanup implementation are
unchanged; this DAG only makes its existing classification a total input.

## 10. Two-stage activation and request admission

Exact owners in `cron.scheduler_provider` are:

```python
derive_cron_claim_routes(role, host_mode, provider_name)
derive_cron_module_names(role, host_mode, provider_name)
verify_cron_host_code(expectation: CronDeploymentExpectationV2)
    -> HostCodeVerificationResultV1
discover_cron_binding_configs(host: HostCodeIdentityV1)
    -> BindingDiscoveryResultV1
resolve_controlled_provider(host, binding) -> ResolvedProviderBindingV1
verify_and_open_cron_target(host, binding, provider)
    -> TargetActivationResultV1
require_cron_target_admission(target_id, route) -> CronAdmissionResultV2
```

The stdlib parent preflight runs before the child imports any claim module and
proves the clean expected Git/launcher/bootstrap inputs plus the allowed
preloaded-entry set. Stage 1 in the fresh child then imports/observes the exact
downstream module set and constructs `HostCodeVerificationResultV1`; only after
VERIFIED may binding discovery begin. Binding discovery is a bounded read-only
walk of `profiles_to_serve`, canonical homes, `read_raw_config`, and profile
secret scopes; it cannot open `cron/jobs.json`, inspect a job row, or claim.
Each discovered tuple must equal an allowed binding.

Process activation constructs one distinct resolved provider and VERIFIED target
for every allowed binding before any provider starts or jobs store opens. For a
Chronos HTTP request, strict body decode and the selected profile configs plus
unchanged `get_fire_verifier` first authenticate purpose/audience/issuer/expiry
and select only an allowed binding, still without a jobs-store open. The owner
then looks up that binding's preverified target and calls
`require_cron_target_admission(target_id,route)`. ADMITTED alone permits entry to
that exact home/secret/store, exact `(job_id,fire_at)` matching, and claim. An A
activation cannot open or claim B. Zero or multiple exact occurrences refuse.
Provider start follows VERIFIED OPEN only.

Both handlers pass the entire `ChronosClaimedExecutionV2` to the outer wrapper.
HTTP mapping is exact: syntax 400; auth 401; GONE/DUPLICATE/ALREADY_ADVANCED
200; CONFLICT/CLAIM_REFUSED 409; UNAVAILABLE/COMMIT_UNKNOWN/closed admission
503; and successfully created registered task after CLAIMED only 202.

Absent controlled expectation, ordinary startup remains OPEN and current
behavior is unchanged. Observation failure remains diagnostic. Under controlled
deployment, any non-VERIFIED target remains CLOSED and yields zero store open,
claim, provider start, task/thread, or 202; messaging/readiness/non-cron APIs
remain ordinary.

## 11. Concrete route, host, and profile witnesses

| host | route / occurrence | claim and worker witness | profile/store witness |
|---|---|---|---|
| gateway | BUILTIN_SCHEDULED / recurring | recurring claim -> registered wrapper -> builtin leaf | launch profile exact home/store |
| gateway | BUILTIN_SCHEDULED / one-shot | tagged nonexpiring one-shot claim -> wrapper -> finite exact finalizer | launch profile exact home/store |
| gateway | CHRONOS_SYNC / recurring | immutable Chronos bundle -> wrapper -> bound run/re-arm | launch allowed binding |
| gateway | CHRONOS_SYNC / one-shot | immutable bundle with tagged one-shot -> wrapper -> removal/no re-arm | launch allowed binding |
| gateway API | GATEWAY_CHRONOS_HTTP / recurring | admitted task -> thread token -> bundle run/re-arm/release | token-selected exact allowed binding |
| gateway API | GATEWAY_CHRONOS_HTTP / one-shot | admitted task -> thread token -> tagged bundle/removal/release | token-selected exact allowed binding |
| plain dashboard | DASHBOARD_CHRONOS_HTTP / recurring | admitted task -> bound bundle/re-arm/release | selected allowed profile/home/store |
| plain dashboard | DASHBOARD_CHRONOS_HTTP / one-shot | admitted task -> tagged bundle/removal/release | selected allowed profile/home/store |
| desktop primary | BUILTIN_SCHEDULED / recurring and one-shot | child-local wrapper and exact claim | primary child's binding/store |
| desktop profile | BUILTIN_SCHEDULED / recurring and one-shot | pool-child-local wrapper and exact claim | injective pool profile/home/store |
| desktop primary/profile | DASHBOARD_CHRONOS_HTTP / both scheduled kinds | child-local admitted HTTP bundle | that child's allowed binding only |
| CLI tick | BUILTIN_SCHEDULED / recurring and one-shot | command lifecycle wrapper; outer finally drains | parsed exact binding/store |
| manual tool/CLI | CLI_MANUAL / MANUAL | private exact legacy postimage/context; public bool unchanged | selected current store; no scheduled authority |
| canary CLI | CANARY / CANARY | pause-preserving ACTIVE claim -> full wrapper -> exact finalizer | exact paused-row profile/store |

Gateway `_handle_run_job` and dashboard `_trigger_cron_job_sync` call
`cron.jobs.trigger_job`; they are strict writer callers that change future
schedule eligibility and do not directly execute or construct MANUAL context.
They enter W01 -> W00 and remain in the caller/edit/module inventory, not the
execution-route table. Default and named profiles with equal job IDs/basenames
are distinct witnesses. An impossible role/provider/mode cell returns the typed
activation/admission refusal before a store opens.

Every witness row is crossed with this cut/outcome/restart table. A cell is
excluded only when the row's source path cannot reach the cut (for example,
manual work has no Chronos re-arm), and the exclusion retains that locator.

| cut | exact immediate outcome/postimage | same-process successor | cold restart |
|---|---|---|---|
| before admission/claim | typed refusal or no mutation | caller returns nonzero/false as its ABI requires | ordinarily eligible |
| claim committed, registration absent | durable ACTIVE; only source-proved pre-API rollback/NOT_SUBMITTED may change it | register once or retain | ACTIVE blocks; terminal pre-API disposition follows schedule |
| registered, starter not entered | exact REGISTERED record plus ACTIVE | close winner proves no worker and exact-disposes or retains | ACTIVE blocks |
| task/thread API entered, acknowledgement unknown | ACTIVE plus registered record | worker token decides; never automatic retry | ACTIVE blocks |
| worker token acquired, body not entered | WORKER_STARTED plus ACTIVE | exact worker runs or shutdown-interrupted successor | ACTIVE blocks if owner dies |
| body/result obtained | exact stage results retained | cleanup/output/delivery | durable claim remains until finalizer |
| cleanup pending | SCRIPT_CLEANUP_PENDING | first COMPLETE versus INCOMPLETE/UNKNOWN decision wins | uncommitted crash retains ACTIVE |
| cleanup uncertain before/after quarantine CAS | sticky CLEANUP_UNCERTAIN; exact ACTIVE retained | Q01 only; no output/finalizer/re-arm | quarantine postimage blocks; CAS uncertainty conservatively blocks |
| output/delivery | exact independent typed results | matching finalizer only | pre-finalizer crash retains ACTIVE |
| finalizer before/after commit | exact preimage or exact APPLIED/REMOVED postimage; unknown fresh-read only | aggregate from observed truth | ACTIVE blocks or committed terminal truth applies |
| Chronos re-arm before/after call | final result retained; valid recurring successor armed once or typed error | observer then release | final store truth is authoritative; same occurrence never reclaims |
| outer HTTP cancellation before worker | no worker effects; exact preworker disposition or ACTIVE retention | outer releases REGISTERED once | durable row decides |
| outer HTTP cancellation after worker | no release by outer coroutine | thread finishes all owned stages then releases once | durable row decides if process dies |
| release | process record removed exactly once | caller consumes immutable outcome/error | jobs row alone is restart truth |
| shutdown close/snapshot/drain | CLOSED plus immutable exact contexts; no later admission | each context follows cleanup/finalizer row above | no process registry authority survives |

Recurring, scheduled one-shot, canary, and claimed manual rows all use this
table. Scheduled one-shot ACTIVE is tagged and nonexpiring; its legal terminal
result preserves current finite completion/removal and public boolean behavior.
Canary UNKNOWN/INCOMPLETE additionally preserves the original pause quartet.

## 12. Archive/store and Git/host deployment subgraphs

`hermes_cli.backup.run_import` first normalizes every archive member. Accepted
jobs members are exactly `cron/jobs.json`, a single common `.hermes/` or
`hermes/` prefix plus that path, and
`profiles/<valid-profile>/cron/jobs.json` under that prefix. Duplicate normalized
destination, traversal, malformed/unknown profile, symlink, or root/named
ambiguity refuses the entire archive before any write.

```text
ArchiveJobsTargetV1={member_path:canonical relative path,profile:ProfileName,
  home_realpath:AbsPath,jobs_file_realpath:AbsPath}
ArchiveStoreResultV1=
  UNCHANGED{target,before_count,after_count=same,error:null}|
  REPLACED{target,before_count,after_count,error:null}|
  REFUSED{target,before_count:null|int,after_count:null,error:nonempty string}|
  COMMIT_UNKNOWN{target,before_count:null|int,after_count:null,error:nonempty string}
ArchiveImportResultV1=
  COMPLETE{stores:nonempty tuple,error:null}|
  REFUSED{stores:empty tuple,error:nonempty string}|
  PARTIAL{stores:nonempty tuple,error:nonempty string}|
  COMMIT_UNKNOWN{stores:nonempty tuple,error:nonempty string}
```

After full preflight, selected stores commit default first then named profiles
lexically through the existing per-store `.jobs.lock` mutation owner. Locks are
never nested and no cross-store atomicity is claimed. Quick/emptied restore and
curator skill-link restore use that same selected-store owner. Both MarketWatch
root/shipped `_extract_backup.py` owners refuse the whole archive before any
write when any normalized jobs member exists; root/shipped `restore.sh` cannot
bypass it. All other jobs writers enter the same strict conservation owner.

```text
ExecutorHostKeyV1={role:CronProcessRoleV2,profile:ProfileName,
  home_realpath:AbsPath,jobs_file_realpath:AbsPath,
  provider_name:CronProviderNameV1}
HostControlReceiptV1=
  STOPPED{key,owner:qualified callable,pid:null,start_ticks:null,
    activation:null,reason:null}|
  VERIFIED{key,owner:qualified callable,pid:positive int,
    start_ticks:positive int,activation:HostCodeIdentityV1,reason:null}|
  REFUSED{key,owner:qualified callable,pid:null|positive int,
    start_ticks:null|positive int,activation:null,reason:nonempty string}
GitReleaseIdentityV1={repository:"HERMES"|"MARKETWATCH",
  origin_url:literal canonical HTTPS URL,candidate_ref:full ref,
  canonical_ref:full ref,candidate_oid:H40,reviewed_remote_oid:H40,
  merged_qa_oid:H40,deployed_oid:H40}
DeploymentAcceptanceV1={hermes:GitReleaseIdentityV1,
  marketwatch:GitReleaseIdentityV1,
  hosts:sorted tuple[HostControlReceiptV1],
  activations:sorted tuple[CronTargetActivationV1]}
DeploymentAcceptanceResultV1=
  VERIFIED{acceptance:DeploymentAcceptanceV1,reason:null}|
  UNAVAILABLE{acceptance:null,reason:"FETCH_UNAVAILABLE"|
    "HOST_OWNER_UNAVAILABLE"}|
  MISMATCH{acceptance:null,reason:"ORIGIN_MISMATCH"|"REF_MISMATCH"|
    "CANDIDATE_REVIEW_MISMATCH"|"MERGE_NOT_QA_BOUND"|
    "ANCESTRY_MISMATCH"|"DEPLOYED_OID_MISMATCH"|"DIRTY_DEPLOYMENT"|
    "HOST_SET_MISMATCH"|"HOST_NOT_STOPPED_OR_VERIFIED"|
    "RUNNING_OID_MISMATCH"|"ACTIVATION_SET_MISMATCH"|
    "MW_WRITER_SET_MISMATCH"}
```

STOPPED is emitted only after the source owner waits its exact known child/PID,
or proves it owns no handle under the one-deployer axiom. VERIFIED carries exact
PID/start/activation. No process scan substitutes. Source owners are gateway
`GatewayRunner.stop`; standalone dashboard lifespan plus invoking handle;
Electron `startHermes`/`hermesProcess` and every
`spawnPoolBackend`/`backendPool[profile].process`, using
`teardownPrimaryBackendAndWait`, `teardownPoolBackendAndWait`, and
`waitForBackendExit`; and command-scoped invocation handles. Electron appends the
exact expectation argv for each injective child key. Remote backends refuse local
controlled acceptance.

`hermes_cli.cron_deployment.verify_cron_deployment(...)` is the one nonpersistent
coordinator, exposed as `hermes cron deployment verify`. It accepts no host,
route, module, or activation list; it derives them and collects owner receipts.
It prints one compact sorted-key JSON result plus LF: VERIFIED exit 0,
UNAVAILABLE exit 3, MISMATCH exit 4; argparse is exit 2. It writes no authority.

Canonical identities are literal:

```text
Hermes origin=https://github.com/kendeng300/hermes-agent.git
Hermes candidate=refs/heads/fix/sys1030
Hermes canonical=refs/heads/main
MarketWatch origin=https://github.com/kendeng300/marketwatch.git
MarketWatch candidate=refs/heads/fix/sys1030
MarketWatch canonical=refs/heads/master
```

Fresh bounded canonical HTTPS fetches bind Hermes `Ch==Rh`, QA names `Mh`, `Rh<=Mh`,
clean `Dh==Mh`, and every live role `R==Dh`. MarketWatch binds `Cmw==Rmw`, QA
names `Mmw`, `Rmw<=Mmw`, and clean `Dmw==Mmw`. The exact seven MarketWatch
writer/caller set is proven before Hermes activation. Order is Git review/QA,
STOPPED receipts, MW deploy/proof, Hermes deploy/proof, controlled child launch,
every exact activation/VERIFIED receipt, aggregate set equality, then read-only
SYS-1029 handoff. Failure leaves cron CLOSED or hosts stopped and causes zero
claim. Rollback uses the last reviewed clean pair through the same proof.

## 13. Complete source, edit, dependency, and proof inventory

Hermes CREATE: `hermes_cli/cron_deployment.py`, a stdlib in-process verifier and
coordinator—not a service, store, status authority, or workflow daemon.

Hermes EDIT: `cron/jobs.py`, `cron/scheduler.py`,
`cron/scheduler_provider.py`, `plugins/cron_providers/__init__.py`,
`plugins/cron_providers/chronos/__init__.py`, `gateway/run.py`,
`gateway/platforms/api_server.py`, `gateway/status.py`, `hermes_cli/main.py`,
`hermes_cli/subcommands/cron.py`, `hermes_cli/subcommands/gateway.py`,
`hermes_cli/subcommands/dashboard.py`, `hermes_cli/cron.py`,
`hermes_cli/gateway.py`, `hermes_cli/web_server.py`, `hermes_cli/backup.py`,
`agent/curator_backup.py`, `tools/cronjob_tools.py`,
`apps/desktop/electron/main.ts`, and
`apps/desktop/electron/backend-command.ts`.

Hermes ATTEST/PRESERVE: `cron/__init__.py`, `hermes_constants.py`,
`hermes_cli/config.py`, `hermes_cli/profiles.py`, `agent/secret_scope.py`,
`hermes_cli/auth.py`, `plugins/cron_providers/chronos/verify.py`, and
`plugins/cron_providers/chronos/_nas_client.py`. The existing script supervisor,
process containment, public one-shot booleans, and NAS request wire remain
unchanged.

MarketWatch EDIT/caller closure: root/shipped
`utilities/market_holiday_manager.py`; root/shipped
`utilities/holiday_watchdog.py`; sole
`enforcement/calibration_cron_watchdog.py`; root/shipped
`utilities/_extract_backup.py`; and root/shipped `restore.sh` callers.
Root/shipped `recovery/restore_crons_from_manifest.py` remain read-only.

Literal future proof owners:

- `tests/hermes_cli/test_cron_deployment.py::test_controlled_child_discriminator_parser_parent_value_and_target_tail_are_exact` deletes the whole discriminator, deletes each remaining group, changes a syntactically legal role/provider/binding, reorders bindings, and substitutes an ordinary target tail; every controlled mutant refuses before spawn or before target import, while a separately invoked ordinary command retains current behavior;
- `tests/hermes_cli/test_cron_deployment.py::test_controlled_parser_and_deployment_owner_module_is_bootstrap_bound_exactly_once` omits, replaces, duplicates, or retags `hermes_cli.cron_deployment`; every mutant refuses before controlled launch/acceptance and before store/provider access;
- `tests/cron/test_scheduler_provider.py::test_parent_clean_oid_precedes_every_claim_module_import_and_preloaded_module_refuses`;
- `tests/cron/test_scheduler_provider.py::test_import_observation_module_set_and_provider_relation_are_exact`;
- `tests/cron/test_scheduler_provider.py::test_role_provider_mode_derives_total_routes_and_rejects_caller_underdeclaration`;
- `tests/plugins/test_chronos_cron.py::test_claimed_bundle_retains_auth_target_provider_context_finalizer_and_rearm`;
- `tests/cron/test_scheduler_shutdown.py::test_all_modes_share_one_lifecycle_and_exact_shutdown_cut`;
- `tests/cron/test_scheduler_shutdown.py::test_cleanup_decision_is_monotonic_and_unknown_quarantines_before_release`;
- `tests/gateway/test_cron_fire_webhook.py::test_controlled_gateway_admission_precedes_profile_store_claim_task_and_202`;
- `tests/hermes_cli/test_cron_fire_dashboard.py::test_each_selected_profile_requires_its_own_allowed_binding_and_activation_before_store_open`;
- both preceding HTTP files also test cancellation before worker entry and after worker entry through actual release;
- `tests/cron/test_scheduler.py::test_managed_product_is_total_acyclic_and_failure_dominant`;
- `tests/cron/test_canary.py::test_cleanup_result_preserves_pause_quartet_and_active_claim_across_restart`;
- `tests/cron/test_jobs.py::test_scheduled_oneshot_claim_context_finalizer_and_operator_skip_are_exact`;
- `tests/cron/test_jobs_crossprocess_lock.py::test_every_jobs_writer_uses_one_strict_conservation_owner`;
- `tests/hermes_cli/test_backup.py::test_default_named_prefixed_jobs_members_use_strict_owner_with_honest_per_store_result`;
- `tests/gateway/test_status_command.py::test_deployment_coordinator_exact_git_host_activation_and_writer_set_equalities`;
- `tests/gateway/test_status.py::test_activation_result_reason_nullability_and_cli_exit_partition`;
- `apps/desktop/electron/backend-command.test.ts::test_primary_and_every_pool_child_propagate_expectation_and_return_stop_receipts`;
- MarketWatch `tests/test_extract_backup.py::test_both_fallback_extractors_refuse_every_jobs_namespace_before_any_write`;
- MarketWatch `tests/test_restore_backup_fallback.py::test_restore_callers_cannot_bypass_jobs_owner`.

## 14. Independent validation and mutation matrix

At one pinned Git OID, independent auditors use `rg` only to seed:

1. executable/argparse/FastAPI/aiohttp/thread/provider entrypoints; and
2. sinks for jobs-file open/write/replace/save, archive extraction,
   submit/create_task/to_thread/thread/provider start, output/delivery,
   finalizer/release, shutdown, activation/status/deployment, and handoff.

Tracked Python/TypeScript is parsed with its AST/parser to resolve imports,
reexports, aliases, decorators, registry providers, and direct calls. Auditors
forward-walk every entry to sinks and independently reverse-walk every sink to
entries. Dynamic edges require literal registry/config source witnesses. Iterate
the union until the next exact set equals the current set. Compare exact node,
edge, host, route, module, store, archive, cut, result, and test sets to this DAG.
An exclusion requires a source path and impossibility proof. Ephemeral audit
output is not authority; no manifest hash or state file is created.

Each mutation below must fail one self-contained user-space proof:

| family | required RED |
|---|---|
| F1 | move admission after any profile/store search, open, claim, start, or 202 |
| F2 | use A activation/ambient scope to inspect or execute B target |
| F3 | import old module, replace disk with clean current bytes, accept current |
| F4 | alias/swap provider instance, name, class, or module |
| F5 | outer wrapper recurses, registers twice, or dual-releases |
| F6 | drop immutable auth/target/provider/context bundle before execute/re-arm |
| F7 | finalizer consumes aggregate or aggregate precedes finalizer |
| F8 | whitespace becomes SUCCESS or silence aliases empty/suppression |
| F9 | UNKNOWN then late COMPLETE/generic finalizer clears ACTIVE |
| F10 | omit one host/activation/Git result from deployment aggregate |
| F11 | omit Electron argv, child identity, pool member, or stop receipt |
| F12 | caller underdeclares or adds one route |
| F13 | replace/omit one transitive authority/effect module |
| F14 | map one activation reason/nullability case to two statuses/exits |

The same pass retains the seventeen actionable R2 closures: strict writer/ACTIVE
conservation; type-strict preimages; total successor failure; exact
JWT/profile/store/provider/job/fire-at through re-arm; claim before submit/task/
202; ACTIVE/ambiguous nonoverwrite; exact canary base/pause; exact context
through every lifecycle consumer; pre-run/agent failure dominance; disjoint
content/output/delivery; legal finite removal; malformed complement refusal;
parser-to-process exit propagation; controlled loaded/live verification without
ordinary-start gating; MarketWatch writer/watchdog closure; canonical reviewed/
merged/deployed/running identities; and unchanged product rows with SYS-1029 as
sole product acceptance/resume owner. R2-07 remains superseded by claim-before-
submit without dispatched CAS; R2-13 remains SYS-1029-owned.

Static checks are mandatory before freeze:

- every edge endpoint exists and IDs are unique;
- every non-source input has exactly one producer;
- every nonterminal output has a consumer;
- every runtime/deployment/archive edge advances its declared rank;
- a topological sort consumes every node with no remainder;
- all union tags, reasons, presence rules, HTTP/CLI exits, and invalid
  complements are unique;
- route, host, profile class, module, archive, claim mode, cut, cleanup,
  shutdown, result, release, restart, Git, edit, and proof inventories equal the
  two independently derived source sets;
- every F1-F14 mutation and prior-R2 regression mutation is killed.

Freeze requires Systems, Architecture, and Six Sigma panel agreement plus two
independent audits reporting zero undefined edge, cycle, caller-created
authority, unowned effect, ambiguous union, inventory mismatch, surviving
mutation, or prior-17 regression. Target is `14 -> 0`. Only then may the proposal
be changed once and reread in full.
