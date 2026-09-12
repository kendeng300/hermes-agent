#!/usr/bin/env python3
"""Small, read-only SYS-1030 scope and protected-callable preflight.

Production bytes are read only from named Git objects.  This checker proves the
finite manifest contract; it deliberately does not perform reachability or
whole-program semantic analysis.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


H40 = re.compile(r"^[0-9a-f]{40}$")
H64 = re.compile(r"^[0-9a-f]{64}$")
REPOS = {"HERMES", "MARKETWATCH"}
ROUTES = {
    "BUILTIN_RECURRING", "BUILTIN_ONESHOT",
    "CHRONOS_SYNC_RECURRING", "CHRONOS_SYNC_ONESHOT",
    "CHRONOS_GATEWAY_HTTP_RECURRING", "CHRONOS_GATEWAY_HTTP_ONESHOT",
    "CHRONOS_DASHBOARD_HTTP_RECURRING", "CHRONOS_DASHBOARD_HTTP_ONESHOT",
    "CANARY", "MANUAL_COMPAT",
}
HOSTS = {
    "GATEWAY", "STANDALONE_DASHBOARD", "ELECTRON_PRIMARY", "ELECTRON_PROFILE",
    "TUI_STDIO", "TUI_WS", "ACP_STDIO", "CLI_CHAT", "GATEWAY_API_CHAT",
}
ROLES = {
    "ACP_STDIO", "CANARY", "CLI_CHAT", "CLI_MANUAL", "CLI_TICK",
    "ELECTRON_PRIMARY", "ELECTRON_PROFILE", "GATEWAY", "STANDALONE_DASHBOARD",
    "TUI_STDIO", "TUI_WS",
}
STAGES = [
    "AUTHENTICATE_OR_ACTIVATE", "RESERVE_ADMISSION", "OPEN_SELECTED_STORE",
    "CLAIM_AND_READBACK", "REGISTER_LIFECYCLE", "SUBMIT_TASK_OR_202",
    "WORKER_START", "PRE_RUN_OR_BUSINESS", "TYPED_RESULT", "EXACT_FINALIZER",
    "CHRONOS_REARM_IF_ELIGIBLE", "RELEASE",
]
PRODUCTION_PATHS = {
    "HERMES": {
        "cron/jobs.py", "cron/scheduler.py", "cron/scheduler_provider.py",
        "plugins/cron_providers/chronos/__init__.py",
        "gateway/platforms/api_server.py", "hermes_cli/web_server.py",
        "hermes_cli/subcommands/cron.py", "hermes_cli/cron.py",
        "hermes_cli/subcommands/gateway.py", "hermes_cli/subcommands/dashboard.py",
        "hermes_cli/gateway.py", "hermes_cli/main.py", "tools/cronjob_tools.py",
        "gateway/run.py", "gateway/status.py", "agent/curator_backup.py",
        "hermes_cli/backup.py", "docs/chronos-managed-cron-contract.md",
    },
    "MARKETWATCH": {
        "utilities/market_holiday_manager.py",
        "scripts/utilities/market_holiday_manager.py",
        "utilities/holiday_watchdog.py", "scripts/utilities/holiday_watchdog.py",
        "enforcement/calibration_cron_watchdog.py", "utilities/_extract_backup.py",
        "scripts/utilities/_extract_backup.py",
    },
}

# Exact relations are duplicated here deliberately.  A manifest-only mutation
# cannot substitute a same-count route/owner/result relation.  Candidate mode
# additionally binds these checker bytes to an externally approved digest.
EXACT_FIELD_DIGESTS = {
    "routes": "97264cfc2cdc9053e2ab1c7fbf4d6527cf5b2d704f3e8141fb07d17016ca7eb8",
    "authority_interfaces": "3f449ac153098ce4d95551cda5ae0e42a124bf8a5c1665c6fa8eb519ebe4d5c9",
    "authority_roots": "9e2434a62da29d6dc9755429a125fdf8605a64fad31f0d85071c1df751fc165c",
    "shutdown_owners": "d7577859f059db3ab53116a39029f51a6d7a6243d6ede2045ccfdf6f5c1fc245",
    "result_schemas": "17e25d0f8a8d107e95a81105936a2f4395f6ab80f118dd37d18ab1e735c6c776",
    "cut_products": "14f803293df01f53bfdc7ef084d0855fd507876c385780a9a1626ae488fd1efe",
    "acceptance": "d304527a87ecea4b8cf7297a9dc8443bb8b8c589d6d5286c93aa51febb494fa1",
    "save_jobs_migration": "e159d5f4d8f9a8f7f062b097da541f648c99a40855d307545721f00863b66cfd",
    "candidate_binding": "c980a869c978dda3548e33e0049d56785bdef61a75b54948939bfdb9532f736e",
    "dynamic_site_policy": "7989ca55811ea08572db626258140626b32db6b4c5d3d6a78fada3bdf55138d5",
    "evidence_paths": "f47fdb3bd192efcc798d04e4bcf2c1d44dda7d9dc9705c4c531b1616bbf9b3b6",
    "history_paths": "922f6ab9e12d5bdfa61616753d5569d588ad13ce794efd8b7ab19eb122e9a494",
    "retired_evidence_paths": "2ddd6848772a6d6810a216bf9f0f8f434e5b1e0ae3baabd19f3975b67e916cd7",
}
EXACT_PROTECTED_CONTRACT_DIGEST = (
    "9d985282bf30b8a4923830997a52ff228f60145d409ba0ffe7d4a145e94becb0"
)


class Refused(Exception):
    def __init__(
        self,
        detail: str,
        *,
        code: str = "FINITE_SCOPE_REFUSED",
        path: str = "",
        qualname: str = "",
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.path = path
        self.qualname = qualname


def git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.output.decode("utf-8", "replace").strip()
        raise Refused(f"git {' '.join(args)}: {detail}") from exc


def blob(root: Path, oid: str, path: str) -> bytes | None:
    try:
        return git(root, "show", f"{oid}:{path}")
    except Refused:
        return None


def require_commit(root: Path, oid: str, label: str) -> None:
    require(bool(H40.fullmatch(oid)), f"bad {label} OID")
    kind = git(root, "cat-file", "-t", oid).decode().strip()
    require(kind == "commit", f"{label} OID is not a commit: {kind}")


def verify_remote_authority(root: Path, record: dict[str, Any]) -> None:
    repo = record["repo"]
    configured = git(root, "remote", "get-url", "origin").decode().strip()
    require(configured == record["canonical_url"], f"{repo} origin URL mismatch")
    remote_oid = git(root, "rev-parse", record["canonical_ref"]).decode().strip()
    require(bool(H40.fullmatch(remote_oid)), f"{repo} canonical ref is not an OID")
    try:
        git(root, "merge-base", "--is-ancestor", record["baseline_oid"], remote_oid)
    except Refused as exc:
        raise Refused(f"{repo} baseline is not contained by canonical ref") from exc


def ast_hash(node: ast.AST) -> str:
    value = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(value.encode()).hexdigest()


class FunctionIndex(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.nodes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = ".".join([*self.stack, node.name])
        if qualname in self.nodes:
            raise Refused(f"duplicate lexical function: {qualname}")
        self.nodes[qualname] = node
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def parse_functions(data: bytes | None, label: str) -> dict[str, ast.AST]:
    if data is None:
        return {}
    try:
        tree = ast.parse(data, filename=label)
    except (SyntaxError, ValueError) as exc:
        raise Refused(f"cannot parse {label}: {exc}") from exc
    index = FunctionIndex()
    index.visit(tree)
    return index.nodes


def parse_tree(data: bytes | None, label: str) -> ast.Module:
    if data is None:
        return ast.Module(body=[], type_ignores=[])
    try:
        return ast.parse(data, filename=label)
    except (SyntaxError, ValueError) as exc:
        raise Refused(f"cannot parse {label}: {exc}") from exc


class OwnScope(ast.NodeVisitor):
    """Visit one function including its shell, but not nested definitions."""

    def __init__(self, root: ast.AST) -> None:
        self.root = root
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def own_nodes(node: ast.AST) -> list[ast.AST]:
    visitor = OwnScope(node)
    visitor.visit(node)
    return visitor.nodes


def function_shell_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    shell = copy.deepcopy(node)
    shell.body = [ast.Pass()]
    return ast_hash(shell)


class Residualizer(ast.NodeTransformer):
    """Remove declared whole functions; everything else must remain exact."""

    def __init__(self, declared: set[str]) -> None:
        self.declared = declared
        self.stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST | None:
        self.stack.append(node.name)
        result = self.generic_visit(node)
        self.stack.pop()
        return result

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST | None:
        qualname = ".".join([*self.stack, node.name])
        if qualname in self.declared:
            return None
        self.stack.append(node.name)
        result = self.generic_visit(node)
        self.stack.pop()
        return result

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST | None:
        return self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST | None:
        return self._function(node)


def residual_hash(tree: ast.Module, declared: set[str]) -> str:
    residual = Residualizer(declared).visit(copy.deepcopy(tree))
    assert isinstance(residual, ast.Module)
    return ast_hash(residual)


DYNAMIC_NAMES = {
    "getattr": "GETATTR",
    "setattr": "SETATTR",
    "globals": "GLOBALS",
    "locals": "LOCALS",
    "vars": "VARS",
    "__import__": "DYNAMIC_IMPORT",
    "importlib.import_module": "DYNAMIC_IMPORT",
}


def dynamic_sites(node: ast.AST) -> list[dict[str, str]]:
    sites: list[dict[str, str]] = []
    for item in own_nodes(node):
        if not isinstance(item, ast.Call):
            continue
        name = dotted(item.func)
        kind = DYNAMIC_NAMES.get(name or "")
        if kind is None and isinstance(item.func, ast.Call):
            kind = "CALL_RESULT"
        elif kind is None and isinstance(item.func, ast.Subscript):
            kind = "SUBSCRIPT_CALL"
        elif kind is None and isinstance(item.func, ast.Lambda):
            kind = "LAMBDA_CALL"
        if kind is None:
            continue
        sites.append(
            {
                "kind": kind,
                "source_span": (
                    f"{item.lineno}:{item.col_offset}-"
                    f"{item.end_lineno}:{item.end_col_offset}"
                ),
                "ast_sha256": ast_hash(item),
                "reason": (
                    "pinned baseline syntax; candidate may preserve this exact site "
                    "but may not add or change one"
                ),
            }
        )
    return sites


def dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def import_bindings(
    tree: ast.Module,
    owner_node: ast.AST | None = None,
    current_module: str = "",
) -> dict[str, str]:
    out: dict[str, str] = {}
    nodes: Iterable[ast.AST] = tree.body
    if owner_node is not None:
        nodes = [*tree.body, *own_nodes(owner_node)]
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    out[root] = root
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = current_module.rsplit(".", node.level)[0]
                base = ".".join(part for part in (package, base) if part)
            if not base:
                continue
            for alias in node.names:
                out[alias.asname or alias.name] = f"{base}.{alias.name}"
    return out


def resolve_call(
    call: ast.Call, imports: dict[str, str], module: str, owner: str
) -> tuple[str, str] | None:
    name = dotted(call.func)
    if not name:
        return None
    parts = name.split(".")
    if parts[0] in imports:
        full = ".".join([imports[parts[0]], *parts[1:]])
    elif parts[0] in {"self", "cls"} and "." in owner:
        return module, f"{owner.rsplit('.', 1)[0]}." + ".".join(parts[1:])
    elif len(parts) == 1:
        full = f"{module}.{name}"
    else:
        full = name
    mod, _, qualname = full.rpartition(".")
    return mod, qualname


def resolve_reference(
    node: ast.AST, imports: dict[str, str], module: str, owner: str
) -> tuple[str, str] | None:
    name = dotted(node)
    if not name:
        return None
    parts = name.split(".")
    if parts[0] in imports:
        full = ".".join([imports[parts[0]], *parts[1:]])
    elif parts[0] in {"self", "cls"} and "." in owner:
        return module, f"{owner.rsplit('.', 1)[0]}." + ".".join(parts[1:])
    elif len(parts) == 1:
        full = f"{module}.{name}"
    else:
        full = name
    mod, _, qualname = full.rpartition(".")
    return mod, qualname


def resolve_authority_reference(
    node: ast.AST,
    imports: dict[str, str],
    module: str,
    owner: str,
    authority_targets: set[tuple[str, str]],
) -> tuple[str, str] | None:
    resolved = resolve_reference(node, imports, module, owner)
    if resolved in authority_targets:
        return resolved
    if isinstance(node, ast.Name):
        lexical = (module, f"{owner}.{node.id}")
        if lexical in authority_targets:
            return lexical
    return resolved


def module_name(path: str) -> str:
    path = path[:-3] if path.endswith(".py") else path
    if path.endswith("/__init__"):
        path = path[:-9]
    return path.replace("/", ".")


def diff_paths(root: Path, baseline: str, candidate: str) -> dict[str, str]:
    raw = git(root, "diff", "--name-status", "--no-renames", baseline, candidate)
    out: dict[str, str] = {}
    for line in raw.decode().splitlines():
        status, sep, path = line.partition("\t")
        if not sep or status not in {"A", "M", "D"} or path in out:
            raise Refused(f"unsupported or duplicate diff record: {line!r}")
        out[path] = status
    return out


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Refused(message)


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Refused(f"duplicate JSON key: {key}", code="MANIFEST_JSON")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    raise Refused(f"non-finite JSON number: {value}", code="MANIFEST_JSON")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
        )
    except Refused:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Refused(f"manifest read: {exc}") from exc
    require(isinstance(value, dict), "manifest root must be an object")
    return value


def validate_shape(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(manifest.get("schema") == "sys1030-finite-scope-v1", "wrong schema")
    require(sys.version_info[:2] == (3, 11), "semantic PASS requires Python 3.11")
    require(manifest.get("canonical_python") == "3.11", "wrong canonical Python")
    for field, expected in EXACT_FIELD_DIGESTS.items():
        require(field in manifest, f"missing exact field {field}")
        require(
            canonical_digest(manifest[field]) == expected,
            f"exact field relation changed: {field}",
        )
    protected_contract = [
        {
            key: rule[key]
            for key in (
                "repo",
                "path",
                "qualname",
                "baseline_ast_sha256",
                "disposition",
                "signature_policy",
                "allowed_direct_calls",
                "baseline_dynamic_sites",
            )
        }
        for rule in manifest.get("protected_functions", [])
    ]
    require(
        canonical_digest(protected_contract) == EXACT_PROTECTED_CONTRACT_DIGEST,
        "protected callable/edge/dynamic-site contract changed",
    )
    require(set(manifest.get("host_labels", [])) == HOSTS, "host labels are not exact")
    require(set(manifest.get("process_roles", [])) == ROLES, "process roles are not exact")
    require(manifest.get("route_stage_names") == STAGES, "route stages are not exact")
    shutdown = manifest.get("shutdown_owners", [])
    require({item.get("host_label") for item in shutdown} == HOSTS, "shutdown host coverage")
    require({item.get("process_role") for item in shutdown} == ROLES, "shutdown role coverage")
    repositories = manifest.get("repositories")
    require(isinstance(repositories, list) and len(repositories) == 2, "need two repos")
    by_repo: dict[str, dict[str, Any]] = {}
    for record in repositories:
        repo = record.get("repo")
        require(repo in REPOS and repo not in by_repo, f"bad/duplicate repo {repo!r}")
        require(bool(H40.fullmatch(record.get("baseline_oid", ""))), f"bad {repo} OID")
        expected_ref = (
            "refs/remotes/origin/main"
            if repo == "HERMES"
            else "refs/remotes/origin/master"
        )
        expected_url = (
            "https://github.com/kendeng300/hermes-agent.git"
            if repo == "HERMES"
            else "https://github.com/kendeng300/marketwatch.git"
        )
        require(record.get("canonical_ref") == expected_ref, f"bad {repo} ref")
        require(record.get("canonical_url") == expected_url, f"bad {repo} URL")
        paths = record.get("paths")
        require(isinstance(paths, list), f"{repo} paths must be list")
        actual = {p.get("path") for p in paths}
        require(actual == PRODUCTION_PATHS[repo], f"{repo} production path set is not exact")
        require(len(actual) == len(paths), f"{repo} duplicate path")
        for item in paths:
            require(item.get("repo") == repo, f"{repo} path repo mismatch")
            require(item.get("baseline_state") == "EXISTS", f"{repo} non-EXISTS baseline")
            require(item.get("policy") in {"EDIT", "DELETE"}, f"{repo} bad policy")
            suffix = Path(item["path"]).suffix
            expected = {".py": "PYTHON", ".ts": "TYPESCRIPT", ".sh": "SHELL", ".md": "MARKDOWN"}[suffix]
            require(item.get("language") == expected, f"{repo}:{item['path']} language mismatch")
        by_repo[repo] = record
    routes = manifest.get("routes")
    require(isinstance(routes, list) and len(routes) == 10, "need exactly ten routes")
    require({r.get("route") for r in routes} == ROUTES, "route names are not exact")
    for route in routes:
        require(route.get("ordered_stage_names") == STAGES, f"{route.get('route')} stage order")
        pairs = route.get("host_role_pairs")
        require(isinstance(pairs, list) and pairs, f"{route.get('route')} host-role pairs")
        pair_hosts = {item.get("host_label") for item in pairs}
        pair_roles = {item.get("process_role") for item in pairs}
        require(pair_hosts <= HOSTS, "unknown route host")
        require(pair_roles <= ROLES, "unknown route role")
        require(pair_hosts == set(route.get("host_labels", [])), "route host projection")
        require(pair_roles == set(route.get("process_roles", [])), "route role projection")
        require(len(pairs) == len({(p["host_label"], p["process_role"]) for p in pairs}), "duplicate route pair")
        require(route.get("occurrence_kind") in {"RECURRING", "ONESHOT", "PAUSED_CANARY", "MANUAL"}, "route occurrence")
        require(isinstance(route.get("claim_owner"), str), "route claim owner")
        require(isinstance(route.get("submit_owner"), str), "route submit owner")
        require(route.get("finalizer_owner") is None or isinstance(route.get("finalizer_owner"), str), "route finalizer")
        require(route.get("rearm_owner") is None or isinstance(route.get("rearm_owner"), str), "route rearm")
        modules = route.get("loaded_modules")
        require(isinstance(modules, list) and modules == list(dict.fromkeys(modules)), "route loaded modules")
        entrypoints = route.get("entrypoint_modules_by_host")
        require(isinstance(entrypoints, dict) and set(entrypoints) == pair_hosts, "route entrypoint host set")
        require("::" in route.get("test_node", ""), "route lacks exact test node")
    rules = manifest.get("protected_functions")
    require(isinstance(rules, list) and rules, "protected_functions must be nonempty")
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        key = (rule.get("repo"), rule.get("path"), rule.get("qualname"))
        require(key not in seen, f"duplicate function rule {key}")
        seen.add(key)
        repo, path, qualname = key
        require(repo in REPOS and path in PRODUCTION_PATHS[repo], f"out-of-scope function {key}")
        require(path.endswith(".py") and isinstance(qualname, str) and qualname, f"bad function {key}")
        disposition = rule.get("disposition")
        require(disposition in {"CHANGE", "ADD", "DELETE", "UNCHANGED_ATTESTATION"}, f"bad disposition {key}")
        signature_policy = rule.get("signature_policy")
        expected_signature_policy = (
            "SPEC_DECLARED" if disposition == "ADD"
            else "ABSENT" if disposition == "DELETE"
            else "BASELINE_EXACT"
        )
        require(signature_policy == expected_signature_policy, f"signature policy {key}")
        digest = rule.get("baseline_ast_sha256")
        require((digest is None) == (disposition == "ADD"), f"baseline hash/disposition {key}")
        if digest is not None:
            require(bool(H64.fullmatch(digest)), f"bad AST hash {key}")
        require(set(rule.get("required_routes", [])) <= ROUTES, f"unknown function route {key}")
        tests = rule.get("required_tests")
        require(isinstance(tests, list) and tests and all("::" in x for x in tests), f"test node {key}")
        for edge in rule.get("allowed_direct_calls", []):
            require(set(edge) == {"callee_module", "callee_qualname", "exact_count"}, f"bad edge {key}")
            require(isinstance(edge["exact_count"], int) and edge["exact_count"] >= 0, f"edge count {key}")
        sites = rule.get("baseline_dynamic_sites")
        require(isinstance(sites, list), f"dynamic sites {key}")
        for site in sites:
            require(
                set(site) == {"kind", "source_span", "ast_sha256", "reason"},
                f"dynamic site shape {key}",
            )
            require(site["kind"] in manifest["dynamic_site_policy"]["universe"], f"dynamic site kind {key}")
            require(bool(H64.fullmatch(site["ast_sha256"])), f"dynamic site hash {key}")
    interfaces = manifest.get("authority_interfaces")
    require(isinstance(interfaces, list) and interfaces, "authority inventory")
    interface_keys: set[tuple[str, str, str]] = set()
    for item in interfaces:
        require(set(item) == {"repo", "path", "qualname", "kind"}, "authority item shape")
        identity = (item["repo"], item["path"], item["qualname"])
        require(identity not in interface_keys, f"duplicate authority {identity}")
        require(identity in seen, f"authority lacks protected rule {identity}")
        interface_keys.add(identity)
    interface_targets = {
        (module_name(path), qualname): (repo, path, qualname)
        for repo, path, qualname in interface_keys
    }
    require(len(interface_targets) == len(interface_keys), "ambiguous authority target")
    roots = set(manifest.get("authority_roots", []))
    expected_root_ids = {f"{repo}:{path}::{qualname}" for repo, path, qualname in interface_keys}
    require(roots <= expected_root_ids, "authority root outside inventory")
    inbound: set[tuple[str, str, str]] = set()
    for rule in rules:
        edge_targets: set[tuple[str, str]] = set()
        for edge in rule.get("allowed_direct_calls", []):
            target = (edge["callee_module"], edge["callee_qualname"])
            require(target not in edge_targets, f"duplicate authority edge {target}")
            require(target in interface_targets, f"edge target outside authority inventory {target}")
            edge_targets.add(target)
            inbound.add(interface_targets[target])
    for identity in interface_keys:
        root_id = f"{identity[0]}:{identity[1]}::{identity[2]}"
        require(identity in inbound or root_id in roots, f"authority has no exact caller or root: {root_id}")
    tests = manifest.get("required_tests")
    require(isinstance(tests, list) and len(tests) == len(set(tests)), "required tests duplicate")
    require(all(t.split(":", 1)[0] in REPOS and "::" in t for t in tests), "bad required test")
    return by_repo


def verify_baselines(
    manifest: dict[str, Any], repos: dict[str, dict[str, Any]], roots: dict[str, Path]
) -> None:
    indexes: dict[tuple[str, str], dict[str, ast.AST]] = {}
    for repo, record in repos.items():
        oid = record["baseline_oid"]
        require(git(roots[repo], "cat-file", "-t", oid).strip() == b"commit", f"{repo} baseline is not a commit")
        require(
            git(roots[repo], "remote", "get-url", "origin").decode().strip()
            == record["canonical_url"],
            f"{repo} origin URL mismatch",
        )
        remote_oid = git(roots[repo], "rev-parse", record["canonical_ref"]).decode().strip()
        require(bool(H40.fullmatch(remote_oid)), f"{repo} canonical ref is not an OID")
        try:
            git(roots[repo], "merge-base", "--is-ancestor", oid, remote_oid)
        except Refused as exc:
            raise Refused(f"{repo} baseline not contained by canonical ref") from exc
        for path in PRODUCTION_PATHS[repo]:
            data = blob(roots[repo], oid, path)
            require(data is not None, f"missing baseline blob {repo}:{path}")
            if path.endswith(".py"):
                indexes[(repo, path)] = parse_functions(data, f"{repo}:{oid}:{path}")
    for rule in manifest["protected_functions"]:
        key = (rule["repo"], rule["path"])
        node = indexes[key].get(rule["qualname"])
        if rule["disposition"] == "ADD":
            require(node is None, f"ADD already exists {key}:{rule['qualname']}")
            require(rule["baseline_dynamic_sites"] == [], f"ADD has baseline dynamic sites {key}:{rule['qualname']}")
        else:
            require(node is not None, f"baseline function absent {key}:{rule['qualname']}")
            require(ast_hash(node) == rule["baseline_ast_sha256"], f"baseline AST mismatch {key}:{rule['qualname']}")
            require(
                dynamic_sites(node) == rule["baseline_dynamic_sites"],
                f"baseline dynamic-site mismatch {key}:{rule['qualname']}",
            )
    baseline = repos["HERMES"]["baseline_oid"]
    reverse_nodes: set[str] = set()
    for path in grep_python_paths(roots["HERMES"], baseline, "save_jobs"):
        data = blob(roots["HERMES"], baseline, path)
        assert data is not None
        for owner in save_jobs_reference_owners(data, f"HERMES:{baseline}:{path}"):
            reverse_nodes.add(f"HERMES:{path}::{owner}")
    require(
        reverse_nodes == set(manifest["save_jobs_migration"]["baseline_reverse_nodes"]),
        "save_jobs pinned reverse set is not exact: "
        f"missing={sorted(reverse_nodes-set(manifest['save_jobs_migration']['baseline_reverse_nodes']))}; "
        f"extra={sorted(set(manifest['save_jobs_migration']['baseline_reverse_nodes'])-reverse_nodes)}",
    )


def test_paths(manifest: dict[str, Any], repo: str) -> set[str]:
    prefix = f"{repo}:"
    paths = {
        node[len(prefix):].split("::", 1)[0]
        for node in manifest["required_tests"] if node.startswith(prefix)
    }
    paths.update(
        node.split("::", 1)[0]
        for rule in manifest["protected_functions"] if rule["repo"] == repo
        for node in rule["required_tests"]
    )
    return paths


def grep_python_paths(root: Path, oid: str, needle: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "grep", "-l", "-e", needle, oid, "--", "*.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise Refused(result.stdout.decode("utf-8", "replace").strip())
    paths: list[str] = []
    for line in result.stdout.decode().splitlines():
        prefix = f"{oid}:"
        require(line.startswith(prefix), f"unexpected git grep result: {line!r}")
        paths.append(line[len(prefix):])
    return paths


def save_jobs_reference_owners(data: bytes, label: str) -> set[str]:
    tree = parse_tree(data, label)
    owners: set[str] = set()
    stack: list[str] = []

    class References(ast.NodeVisitor):
        def _owner(self) -> str:
            return ".".join(stack) or "<module>"

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "save_jobs":
                owners.add(self._owner())

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == "save_jobs":
                owners.add(self._owner())
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module == "cron.jobs" and any(alias.name == "save_jobs" for alias in node.names):
                owners.add(self._owner())

        def visit_Constant(self, node: ast.Constant) -> None:
            if node.value == "save_jobs":
                owners.add(self._owner())

    References().visit(tree)
    return owners


def save_jobs_reverse_nodes(root: Path, oid: str, repo: str) -> set[str]:
    nodes: set[str] = set()
    for path in grep_python_paths(root, oid, "save_jobs"):
        data = blob(root, oid, path)
        assert data is not None
        for owner in save_jobs_reference_owners(data, f"{repo}:{oid}:{path}"):
            nodes.add(f"{repo}:{path}::{owner}")
    return nodes


def verify_save_jobs_migration_baseline(
    manifest: dict[str, Any], roots: dict[str, Path], repos: dict[str, dict[str, Any]]
) -> None:
    expected = set(manifest["save_jobs_migration"]["baseline_reverse_nodes"])
    actual = save_jobs_reverse_nodes(
        roots["HERMES"], repos["HERMES"]["baseline_oid"], "HERMES"
    )
    require(actual == expected, f"save_jobs reverse set mismatch: missing={sorted(actual-expected)} extra={sorted(expected-actual)}")


def verify_save_jobs_removed(
    manifest: dict[str, Any], root: Path, candidate: str
) -> None:
    baseline_paths = {
        node.split(":", 1)[1].split("::", 1)[0]
        for node in manifest["save_jobs_migration"]["baseline_reverse_nodes"]
    }
    checked = baseline_paths | {
        path for path in PRODUCTION_PATHS["HERMES"] if path.endswith(".py")
    }
    residual: list[str] = []
    for path in sorted(checked):
        data = blob(root, candidate, path)
        if data is None:
            continue
        owners = save_jobs_reference_owners(data, f"HERMES:{candidate}:{path}")
        residual.extend(f"{path}::{owner}" for owner in owners)
    require(not residual, f"public save_jobs references remain: {residual}")


def split_node(value: str, default_repo: str | None = None) -> tuple[str, str, str]:
    if default_repo is None:
        repo, separator, rest = value.partition(":")
        require(bool(separator) and repo in REPOS, f"bad repo-qualified node: {value}")
    else:
        repo, rest = default_repo, value
    path, separator, qualname = rest.partition("::")
    require(bool(separator) and path.endswith(".py") and qualname, f"bad node: {value}")
    return repo, path, qualname


def verify_node_exists_once(root: Path, oid: str, repo: str, path: str, qualname: str) -> None:
    data = blob(root, oid, path)
    require(data is not None, f"test witness path absent: {repo}:{path}")
    if qualname == "<module>":
        parse_tree(data, f"{repo}:{oid}:{path}")
        return
    functions = parse_functions(data, f"{repo}:{oid}:{path}")
    require(qualname in functions, f"test witness qualname absent: {repo}:{path}::{qualname}")


def verify_candidate_nodes(
    manifest: dict[str, Any], roots: dict[str, Path], candidates: dict[str, str]
) -> None:
    nodes: set[tuple[str, str, str]] = set()
    for value in manifest["required_tests"]:
        nodes.add(split_node(value))
    for rule in manifest["protected_functions"]:
        for value in rule["required_tests"]:
            nodes.add(split_node(value, rule["repo"]))
    for value in manifest["save_jobs_migration"]["baseline_reverse_nodes"]:
        repo, path, qualname = split_node(value)
        if path.startswith("tests/"):
            nodes.add((repo, path, qualname))
    for repo, path, qualname in sorted(nodes):
        verify_node_exists_once(roots[repo], candidates[repo], repo, path, qualname)


def parse_approved_artifacts(values: list[str], expected_paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        path, separator, digest = value.rpartition("=")
        require(bool(separator) and path and bool(H64.fullmatch(digest)), f"bad approved artifact: {value}")
        require(path not in result, f"duplicate approved artifact: {path}")
        result[path] = digest
    require(set(result) == set(expected_paths), "approved artifact path set is not exact")
    return result


def verify_candidate_artifacts(
    manifest: dict[str, Any],
    root: Path,
    candidate: str,
    manifest_path: Path,
    approved_values: list[str],
) -> None:
    approved = parse_approved_artifacts(approved_values, manifest["evidence_paths"])
    for path in manifest["evidence_paths"]:
        data = blob(root, candidate, path)
        require(data is not None, f"current evidence absent: {path}")
        require(hashlib.sha256(data).hexdigest() == approved[path], f"unapproved evidence bytes: {path}")
    for path in manifest["history_paths"]:
        require(blob(root, candidate, path) is not None, f"history evidence absent: {path}")
    for path in manifest["retired_evidence_paths"]:
        require(blob(root, candidate, path) is None, f"retired evidence reintroduced: {path}")
    manifest_blob = blob(root, candidate, "SYS-1030_LOOP1_EVIDENCE/FINITE_SCOPE_V1.json")
    checker_blob = blob(root, candidate, "SYS-1030_LOOP1_EVIDENCE/validate_finite_scope_v1.py")
    require(manifest_path.read_bytes() == manifest_blob, "executing manifest differs from candidate blob")
    require(Path(__file__).read_bytes() == checker_blob, "executing checker differs from candidate blob")


def verify_candidate(
    manifest: dict[str, Any], repos: dict[str, dict[str, Any]], roots: dict[str, Path],
    candidates: dict[str, str],
    fetched_ref_oids: dict[str, str],
    manifest_path: Path,
    approved_artifacts: list[str],
) -> None:
    rules_by_file: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rule in manifest["protected_functions"]:
        rules_by_file.setdefault((rule["repo"], rule["path"]), []).append(rule)
    authority_targets = {
        (module_name(item["path"]), item["qualname"])
        for item in manifest["authority_interfaces"]
    }
    authority_leaves = {qualname.split(".")[-1] for _, qualname in authority_targets}
    sensitive_unresolved_leaves = {
        leaf
        for leaf in authority_leaves
        if leaf.startswith("_")
        or leaf.startswith("claim_")
        or leaf.startswith("finalize_")
        or leaf.startswith("skip_")
        or leaf.startswith("quarantine_")
        or leaf in {
            "pause_job",
            "resume_job",
            "trigger_job",
            "remove_job",
            "mark_job_run",
            "advance_next_run",
            "set_dispatch_claim_status",
        }
    }
    for repo, record in repos.items():
        baseline, candidate = record["baseline_oid"], candidates[repo]
        require_commit(roots[repo], candidate, f"{repo} candidate")
        fetched_ref_oid = fetched_ref_oids[repo]
        require_commit(roots[repo], fetched_ref_oid, f"{repo} fetched canonical ref")
        actual_ref_oid = git(roots[repo], "rev-parse", record["canonical_ref"]).decode().strip()
        require(
            fetched_ref_oid == actual_ref_oid,
            f"{repo} supplied fetched OID does not equal canonical ref",
        )
        changed = diff_paths(roots[repo], baseline, candidate)
        allowed = set(PRODUCTION_PATHS[repo]) | test_paths(manifest, repo)
        if repo == "HERMES":
            allowed |= (
                set(manifest["evidence_paths"])
                | set(manifest["history_paths"])
                | set(manifest["retired_evidence_paths"])
            )
            for value in manifest["save_jobs_migration"]["baseline_reverse_nodes"]:
                node_repo, path, _ = split_node(value)
                if node_repo == repo and path.startswith("tests/"):
                    allowed.add(path)
        require(set(changed) <= allowed, f"{repo} diff outside finite scope: {sorted(set(changed)-allowed)}")
        for path in changed:
            if path in PRODUCTION_PATHS[repo]:
                policy = next(p["policy"] for p in record["paths"] if p["path"] == path)
                require(not (changed[path] == "D" and policy != "DELETE"), f"unapproved delete {repo}:{path}")
        for path in PRODUCTION_PATHS[repo]:
            if not path.endswith(".py"):
                continue
            before_data, after_data = blob(roots[repo], baseline, path), blob(roots[repo], candidate, path)
            before = parse_functions(before_data, f"{repo}:{baseline}:{path}")
            after = parse_functions(after_data, f"{repo}:{candidate}:{path}")
            listed = {r["qualname"]: r for r in rules_by_file.get((repo, path), [])}
            actual_changed = {
                name for name in set(before) | set(after)
                if name not in before or name not in after or ast_hash(before[name]) != ast_hash(after[name])
            }
            require(actual_changed <= set(listed), f"unlisted changed functions {repo}:{path}: {sorted(actual_changed-set(listed))}")
            before_tree = parse_tree(before_data, f"{repo}:{baseline}:{path}")
            after_tree = parse_tree(after_data, f"{repo}:{candidate}:{path}")
            require(
                residual_hash(before_tree, set(listed)) == residual_hash(after_tree, set(listed)),
                f"undeclared module/class/import/assignment structure changed {repo}:{path}",
            )
            module = module_name(path)
            for name, rule in listed.items():
                old, new = before.get(name), after.get(name)
                disposition = rule["disposition"]
                require((disposition == "ADD") == (old is None and new is not None), f"ADD disposition {repo}:{path}:{name}")
                require((disposition == "DELETE") == (old is not None and new is None), f"DELETE disposition {repo}:{path}:{name}")
                if disposition == "CHANGE":
                    require(old is not None and new is not None and ast_hash(old) != ast_hash(new), f"CHANGE disposition {repo}:{path}:{name}")
                if disposition == "UNCHANGED_ATTESTATION":
                    require(old is not None and new is not None and ast_hash(old) == ast_hash(new), f"attestation {repo}:{path}:{name}")
                if new is None:
                    continue
                if rule["signature_policy"] == "BASELINE_EXACT":
                    assert old is not None
                    require(
                        function_shell_hash(old) == function_shell_hash(new),
                        f"signature/default/decorator changed {repo}:{path}:{name}",
                    )
                allowed_sites = Counter(
                    (site["kind"], site["ast_sha256"])
                    for site in rule["baseline_dynamic_sites"]
                )
                candidate_sites = Counter(
                    (site["kind"], site["ast_sha256"])
                    for site in dynamic_sites(new)
                )
                require(
                    not (candidate_sites - allowed_sites),
                    f"new or changed dynamic site {repo}:{path}:{name}: {candidate_sites-allowed_sites}",
                )
                imports = import_bindings(after_tree, new, module)
                expected = Counter(
                    (e["callee_module"], e["callee_qualname"])
                    for e in rule["allowed_direct_calls"] for _ in range(e["exact_count"])
                )
                actual: Counter[tuple[str, str]] = Counter()
                calls = [n for n in own_nodes(new) if isinstance(n, ast.Call)]
                direct_targets = {id(call.func) for call in calls}
                for call in calls:
                    resolved = resolve_authority_reference(
                        call.func, imports, module, name, authority_targets
                    )
                    if resolved in authority_targets:
                        actual[resolved] += 1
                    target = dotted(call.func)
                    if target and target.split(".")[-1] in sensitive_unresolved_leaves:
                        require(resolved in authority_targets, f"unresolved authority call {repo}:{path}:{name}:{target}")
                require(actual == expected, f"direct-call mismatch {repo}:{path}:{name}: {actual} != {expected}")
                for node in own_nodes(new):
                    if isinstance(node, (ast.Name, ast.Attribute)):
                        resolved = resolve_authority_reference(
                            node, imports, module, name, authority_targets
                        )
                        reference = dotted(node) or ""
                        if resolved in authority_targets:
                            require(
                                id(node) in direct_targets,
                                f"authority value escapes direct call {repo}:{path}:{name}:{reference}",
                            )
                        elif reference.split(".")[-1] in sensitive_unresolved_leaves:
                            require(
                                id(node) in direct_targets and resolved in authority_targets,
                                f"unresolved authority reference {repo}:{path}:{name}:{reference}",
                            )
    verify_candidate_artifacts(
        manifest, roots["HERMES"], candidates["HERMES"], manifest_path, approved_artifacts
    )
    verify_candidate_nodes(manifest, roots, candidates)
    verify_save_jobs_removed(
        manifest, roots["HERMES"], candidates["HERMES"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--marketwatch-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("manifest", "candidate"), default="manifest")
    parser.add_argument("--hermes-candidate")
    parser.add_argument("--marketwatch-candidate")
    parser.add_argument("--hermes-fetched-ref-oid")
    parser.add_argument("--marketwatch-fetched-ref-oid")
    parser.add_argument(
        "--approved-artifact-sha256",
        action="append",
        default=[],
        metavar="PATH=SHA256",
    )
    args = parser.parse_args()
    result: dict[str, Any] = {"status": "REFUSED", "errors": []}
    try:
        manifest = load_manifest(args.manifest)
        repositories = validate_shape(manifest)
        roots = {"HERMES": args.hermes_root, "MARKETWATCH": args.marketwatch_root}
        verify_baselines(manifest, repositories, roots)
        if args.phase == "candidate":
            require(
                bool(
                    args.hermes_candidate
                    and args.marketwatch_candidate
                    and args.hermes_fetched_ref_oid
                    and args.marketwatch_fetched_ref_oid
                ),
                "candidate phase needs both candidate and fetched-ref OIDs",
            )
            verify_candidate(
                manifest, repositories, roots,
                {"HERMES": args.hermes_candidate, "MARKETWATCH": args.marketwatch_candidate},
                {
                    "HERMES": args.hermes_fetched_ref_oid,
                    "MARKETWATCH": args.marketwatch_fetched_ref_oid,
                },
                args.manifest,
                args.approved_artifact_sha256,
            )
        result["status"] = "PASS"
    except Refused as exc:
        result["errors"].append(
            {
                "code": exc.code,
                "path": exc.path,
                "qualname": exc.qualname,
                "detail": str(exc),
            }
        )
    except Exception as exc:
        result["errors"].append(
            {
                "code": "PREFLIGHT_INTERNAL_REFUSAL",
                "path": "",
                "qualname": "",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
