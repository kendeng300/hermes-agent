#!/usr/bin/env python3
"""Small, read-only SYS-1030 scope and protected-callable preflight.

Production bytes are read only from named Git objects.  This checker proves the
finite manifest contract; it deliberately does not perform reachability or
whole-program semantic analysis.
"""

from __future__ import annotations

import argparse
import ast
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


class Refused(Exception):
    pass


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


def dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def import_bindings(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    out[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
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


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Refused(f"manifest read: {exc}") from exc
    require(isinstance(value, dict), "manifest root must be an object")
    return value


def validate_shape(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(manifest.get("schema") == "sys1030-finite-scope-v1", "wrong schema")
    require(sys.version_info[:2] == (3, 11), "semantic PASS requires Python 3.11")
    require(set(manifest.get("host_labels", [])) == HOSTS, "host labels are not exact")
    require(set(manifest.get("process_roles", [])) == ROLES, "process roles are not exact")
    require(manifest.get("route_stage_names") == STAGES, "route stages are not exact")
    repositories = manifest.get("repositories")
    require(isinstance(repositories, list) and len(repositories) == 2, "need two repos")
    by_repo: dict[str, dict[str, Any]] = {}
    for record in repositories:
        repo = record.get("repo")
        require(repo in REPOS and repo not in by_repo, f"bad/duplicate repo {repo!r}")
        require(bool(H40.fullmatch(record.get("baseline_oid", ""))), f"bad {repo} OID")
        require(record.get("canonical_ref") == "refs/remotes/origin/master", f"bad {repo} ref")
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
        require(set(route.get("host_labels", [])) <= HOSTS, "unknown route host")
        require(set(route.get("process_roles", [])) <= ROLES, "unknown route role")
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
        require(isinstance(rule.get("baseline_dynamic_sites"), list), f"dynamic sites {key}")
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
        else:
            require(node is not None, f"baseline function absent {key}:{rule['qualname']}")
            require(ast_hash(node) == rule["baseline_ast_sha256"], f"baseline AST mismatch {key}:{rule['qualname']}")


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


def verify_candidate(
    manifest: dict[str, Any], repos: dict[str, dict[str, Any]], roots: dict[str, Path],
    candidates: dict[str, str],
) -> None:
    rules_by_file: dict[tuple[str, str], list[dict[str, Any]]] = {}
    authority_leaves: set[str] = set()
    for rule in manifest["protected_functions"]:
        rules_by_file.setdefault((rule["repo"], rule["path"]), []).append(rule)
        authority_leaves.update(e["callee_qualname"].split(".")[-1] for e in rule["allowed_direct_calls"])
    for repo, record in repos.items():
        baseline, candidate = record["baseline_oid"], candidates[repo]
        require(bool(H40.fullmatch(candidate)), f"bad {repo} candidate OID")
        changed = diff_paths(roots[repo], baseline, candidate)
        allowed = set(PRODUCTION_PATHS[repo]) | test_paths(manifest, repo)
        if repo == "HERMES":
            allowed |= set(manifest["evidence_paths"]) | set(manifest["retired_evidence_paths"])
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
            tree = ast.parse(after_data, filename=path) if after_data is not None else ast.Module(body=[], type_ignores=[])
            imports = import_bindings(tree)
            module = module_name(path)
            module_statements = ast.Module(
                body=[n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
                type_ignores=[],
            )
            for node in ast.walk(module_statements):
                if isinstance(node, (ast.Name, ast.Attribute)):
                    reference = dotted(node)
                    require(
                        not reference or reference.split(".")[-1] not in authority_leaves,
                        f"module-level authority reference {repo}:{path}:{reference}",
                    )
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
                expected = Counter(
                    (e["callee_module"], e["callee_qualname"])
                    for e in rule["allowed_direct_calls"] for _ in range(e["exact_count"])
                )
                actual: Counter[tuple[str, str]] = Counter()
                calls = [n for n in ast.walk(new) if isinstance(n, ast.Call)]
                direct_targets = {id(call.func) for call in calls}
                for call in calls:
                    resolved = resolve_call(call, imports, module, name)
                    if resolved in expected:
                        actual[resolved] += 1
                    target = dotted(call.func)
                    if target and target.split(".")[-1] in authority_leaves:
                        require(resolved in expected, f"unapproved authority call {repo}:{path}:{name}:{target}")
                    if target is None:
                        text = ast.dump(call.func, include_attributes=False)
                        require(not any(leaf in text for leaf in authority_leaves), f"dynamic authority call {repo}:{path}:{name}")
                require(actual == expected, f"direct-call mismatch {repo}:{path}:{name}: {actual} != {expected}")
                for node in ast.walk(new):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        require(node.value not in authority_leaves, f"string-built authority {repo}:{path}:{name}")
                    if isinstance(node, (ast.Name, ast.Attribute)):
                        reference = dotted(node)
                        if reference and reference.split(".")[-1] in authority_leaves:
                            require(
                                id(node) in direct_targets,
                                f"authority value escapes direct call {repo}:{path}:{name}:{reference}",
                            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--marketwatch-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("manifest", "candidate"), default="manifest")
    parser.add_argument("--hermes-candidate")
    parser.add_argument("--marketwatch-candidate")
    args = parser.parse_args()
    result: dict[str, Any] = {"status": "REFUSED", "errors": []}
    try:
        manifest = load_manifest(args.manifest)
        repositories = validate_shape(manifest)
        roots = {"HERMES": args.hermes_root, "MARKETWATCH": args.marketwatch_root}
        verify_baselines(manifest, repositories, roots)
        if args.phase == "candidate":
            require(bool(args.hermes_candidate and args.marketwatch_candidate), "candidate phase needs both OIDs")
            verify_candidate(
                manifest, repositories, roots,
                {"HERMES": args.hermes_candidate, "MARKETWATCH": args.marketwatch_candidate},
            )
        result["status"] = "PASS"
    except Refused as exc:
        result["errors"].append({"code": "FINITE_SCOPE_REFUSED", "detail": str(exc)})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
