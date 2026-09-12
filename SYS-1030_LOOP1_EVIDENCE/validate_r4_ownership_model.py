#!/usr/bin/env python3
"""Read-only validator for the canonical SYS-1030 R4 ownership model."""

import argparse
import ast
import collections
import hashlib
import itertools
import json
import pathlib
import re
import subprocess


MODEL_KEYS = {
    "schema", "subjects", "locators", "types", "nodes", "edges",
    "conditions", "manifests", "matrices", "mutations", "expected_counts",
}
H40_RE = re.compile(r"^[0-9a-f]{40}$")
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
PREDICATES = [
    "SCHEMA_CONSTRUCTIBLE",
    "PROVIDER_PER_BINDING_INJECTIVE",
    "BINDING_SOURCE_SET_EQUAL",
    "E29_BUNDLE_REAL_PRODUCER",
    "E27_ALL_STAGE_INPUTS_EXPLICIT",
    "HOST_SOURCE_SET_EQUAL",
    "MODULE_FIXED_POINT_EQUAL",
    "CROSS_PROCESS_CODEC_TOTAL",
    "WIRE_TYPE_EXACT_NO_COERCION",
    "SILENCE_OWNER_SOURCE_REAL",
    "SILENCE_OUTPUT_CONSUMED",
    "RESULT_MATRIX_TOTAL_DISJOINT",
    "SHUTDOWN_ROW_PRESENT",
    "ACTIVATION_MATRIX_TOTAL",
    "ARCHIVE_ZERO_JOBS_SUCCESS",
    "MW_WRITER_COUNT_7_PLUS_2",
    "OPEN_STRICTLY_AFTER_D08",
    "ROUTE_SOURCE_REACHABLE",
    "ROUTE_ENABLEMENT_SOURCE_PROVED",
    "EARLY_BUNDLE_AUTHORITY_RETAINED",
    "E28_ALL_STAGE_INPUTS_EXPLICIT",
    "S01_REGISTRY_PRODUCER_EDGE",
]
PRIOR17 = {
    "R2_01", "R2_02", "R2_03", "R2_04", "R2_05", "R2_06",
    "R2_08", "R2_09", "R2_10", "R2_11", "R2_12", "R2_14",
    "R2_15", "R2_16", "R2_17", "R2_18", "R2_19",
}
MATRIX_FIELDS = {
    "activation_product": {"activation"},
    "archive_product": {"error", "store_results", "targets"},
    "cleanup_shutdown_product": {"claim", "postimage"},
    "http_cancellation_product": {"claim", "registry"},
    "http_host_membership_product": {"child_key"},
    "managed_product": {
        "delivery_error", "final_postimage", "output_path", "response_text",
    },
    "prior17_regression": {"witness"},
    "route_enablement": {"owner"},
}
# Exact reviewer-owned row images. These bind every input cell to its full
# status/reason/nullability/exit postimage, including changes to another legal
# union variant that ordinary schema membership would not detect.
EXPECTED_MATRIX_IMAGES_SHA256 = {
    "activation_product": "450b224b48f7c02e00ee843529e23ca93ef86c40fc2c4d4109bc28797ac6dd3e",
    "archive_product": "ec3d7e1bb2227e95ab1aef522b329f7c69d687aa9dca8e501addd52531c3ceeb",
    "cleanup_shutdown_product": "6d04aa839994fe97c1d7f81b5fb2582e62c7b1bce62518d690bcc0425e0b01c4",
    "http_cancellation_product": "5217e9e1bd1617ac5e45e349b01ad94adc0999e5177619599ba198cebb935bc0",
    "http_host_membership_product": "810d4dbea5809004ff3afa2b82a92327a78a7e4b41ead3f2218e13e136a18fba",
    "managed_product": "305b513221527dbb30bf65fb8b6272a2582208986ec23c8d758707c257c18855",
    "prior17_regression": "eabd9d5332b45452e33d5cb753797552b9d3aa71a8509c58c981b2835c86f6ac",
    "route_enablement": "77914971e78b318dafcaa03166df77afcabb60873f4ea361fcbab151af40d436",
}
EXPECTED_MATRIX_INVALID = {
    "activation_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "archive_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "cleanup_shutdown_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "http_cancellation_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "http_host_membership_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "managed_product": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
    "prior17_regression": {"status": "INVALID", "reason": "UNKNOWN_PRIOR_FAMILY", "exit": 2},
    "route_enablement": {"status": "INVALID", "reason": "INVALID_COMPLEMENT", "exit": 2},
}
ALLOWED_NODE_KINDS = {
    "SOURCE", "INGRESS", "OBSERVE", "AUTH", "ACTIVATE", "ADMIT",
    "CLAIM", "REGISTER", "EXECUTE", "CLEANUP", "OUTPUT", "DELIVER",
    "FINALIZE", "AGGREGATE", "REARM", "RELEASE", "QUARANTINE",
    "STORE", "ARCHIVE", "DEPLOY", "HANDOFF",
}
ALLOWED_LIFETIMES = {
    "CALL", "THREAD", "PROCESS", "CROSS_PROCESS",
    "DURABLE_JOB_ROW", "DEPLOYMENT",
}
ALLOWED_CARDINALITIES = {"ONE", "OPTIONAL", "MANY", "NONEMPTY_MANY"}
ALLOWED_EDGE_FLOWS = {"DIRECT", "KEYED_FAN_IN", "KEYED_FAN_OUT"}


class ModelFailure(Exception):
    def __init__(self, code, object_id, detail):
        super().__init__(detail)
        self.code = code
        self.object_id = object_id
        self.detail = detail


def fail(code, object_id, detail):
    raise ModelFailure(code, object_id, detail)


def duplicate_key_hook(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY", key, "duplicate JSON object key")
        result[key] = value
    return result


def require_keys(value, keys, object_id):
    if not isinstance(value, dict):
        fail("SHAPE_INVALID", object_id, "expected object")
    actual = set(value)
    if actual != set(keys):
        fail(
            "KEY_SET_INVALID", object_id,
            "missing=" + repr(sorted(set(keys) - actual))
            + " extra=" + repr(sorted(actual - set(keys))),
        )


def sorted_unique(values, object_id, key=lambda item: item):
    if not isinstance(values, list):
        fail("SHAPE_INVALID", object_id, "expected array")
    projected = [key(item) for item in values]
    if projected != sorted(projected) or len(projected) != len(set(projected)):
        fail("SET_ARRAY_INVALID", object_id, "must be strictly sorted and unique")


def index_unique(values, field_name, object_id):
    result = {}
    for value in values:
        key = value[field_name]
        if key in result:
            fail("DUPLICATE_ID", key, object_id)
        result[key] = value
    return result


def git(root, *args):
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        fail("GIT_OBJECT_UNAVAILABLE", str(root), proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def git_grep_paths(root, oid, pattern, pathspecs):
    proc = subprocess.run(
        ["git", "-C", str(root), "grep", "-l", "-E", pattern, oid, "--", *pathspecs],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        fail("GIT_OBJECT_UNAVAILABLE", str(root), proc.stderr.decode("utf-8", "replace").strip())
    prefix = oid + ":"
    return {
        line[len(prefix):] if line.startswith(prefix) else line.split(":", 1)[-1]
        for line in proc.stdout.decode("utf-8", "strict").splitlines()
    }


def git_grep_lines(root, oid, pattern, pathspecs):
    proc = subprocess.run(
        ["git", "-C", str(root), "grep", "-n", "-E", pattern, oid, "--", *pathspecs],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        fail("GIT_OBJECT_UNAVAILABLE", str(root), proc.stderr.decode("utf-8", "replace").strip())
    result = []
    prefix = oid + ":"
    for line in proc.stdout.decode("utf-8", "strict").splitlines():
        if line.startswith(prefix):
            line = line[len(prefix):]
        path, lineno, source = line.split(":", 2)
        result.append((path, int(lineno), source))
    return result


def resolve_qualnames(tree):
    names = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            names.append(".".join(self.stack))
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            names.append(".".join(self.stack))
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

    Visitor().visit(tree)
    return names


def derive_source_oracle(roots, oids):
    """Derive expected manifests from pinned blobs, independently of the model."""
    cache = {}
    tree_cache = {}

    def text(repo, path):
        key = (repo, path)
        if key not in cache:
            cache[key] = git(roots[repo], "show", oids[repo] + ":" + path).decode(
                "utf-8", "strict"
            )
        return cache[key]

    def python_symbols(path):
        return resolve_qualnames(ast.parse(text("HERMES", path), filename=path))

    def parsed_tree(module_name, path):
        if path not in tree_cache:
            try:
                tree_cache[path] = ast.parse(text("HERMES", path), filename=path)
            except SyntaxError:
                tree_cache[path] = None
        return tree_cache[path]

    def python_function(path, symbol):
        tree = ast.parse(text("HERMES", path), filename=path)
        found = []

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_ClassDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_FunctionDef(self, node):
                current = ".".join(self.stack + [node.name])
                if current == symbol:
                    found.append(node)
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

        Finder().visit(tree)
        if len(found) != 1:
            fail("SOURCE_RELATION_MISSING", path, symbol)
        return found[0]

    def call_names(path, symbol):
        def dotted(node):
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                parent = dotted(node.value)
                return (parent + "." if parent else "") + node.attr
            return ""

        function = python_function(path, symbol)
        calls = {
            dotted(node.func)
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and dotted(node.func)
        }
        references = {
            dotted(node) for node in ast.walk(function)
            if isinstance(node, (ast.Name, ast.Attribute)) and dotted(node)
        }
        return calls | references

    def require_calls(path, symbol, required):
        actual = call_names(path, symbol)
        missing = {
            name for name in required
            if not any(call == name or call.endswith("." + name) for call in actual)
        }
        if missing:
            fail("SOURCE_RELATION_MISSING", path + "::" + symbol, repr(sorted(missing)))

    def imported_modules(module_name, path):
        result = set()
        source = text("HERMES", path)
        tree = parsed_tree(module_name, path)
        if tree is None:
            # The validator may run on the repository's Python 3.8 floor while
            # developer-only tools contain newer syntax. Preserve their import
            # edges lexically; any file reached into the managed authority
            # slice is rejected below rather than silently treated as parsed.
            for match in re.finditer(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)", source):
                result.add(match.group(1))
            for match in re.finditer(r"(?m)^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+", source):
                result.add(match.group(1))
            return result
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                result.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = node.module or ""
                if node.level:
                    package = module_name if path.endswith("/__init__.py") else module_name.rpartition(".")[0]
                    parts = package.split(".") if package else []
                    keep = max(0, len(parts) - (node.level - 1))
                    imported = ".".join(parts[:keep] + ([imported] if imported else []))
                if imported:
                    result.add(imported)
                    result.update(imported + "." + alias.name for alias in node.names)
        return result

    def require_symbol(path, symbol):
        if symbol not in python_symbols(path):
            fail("SOURCE_ORACLE_MISSING", path, symbol)

    def require_text(repo, path, needle):
        if needle not in text(repo, path):
            fail("SOURCE_ORACLE_MISSING", path, needle)

    # Forward host/route witnesses and reverse execution/store sinks.  These
    # checks consume pinned blobs directly; model locators are not consulted.
    for path, symbol in (
        ("gateway/run.py", "GatewayRunner.start"),
        ("gateway/platforms/api_server.py", "APIServerAdapter._handle_cron_fire"),
        ("hermes_cli/web_server.py", "start_server"),
        ("hermes_cli/web_server.py", "cron_fire_webhook"),
        ("hermes_cli/cron.py", "cron_command"),
        ("tools/cronjob_tools.py", "_execute_job_now"),
        ("cron/scheduler.py", "tick"),
        ("cron/scheduler.py", "run_one_job"),
        ("cron/jobs.py", "claim_job_for_fire"),
        ("tui_gateway/entry.py", "main"),
        ("tui_gateway/ws.py", "handle_ws"),
        ("acp_adapter/entry.py", "main"),
    ):
        require_symbol(path, symbol)
    for needle in ("startHermes", "spawnPoolBackend", "backendPool"):
        require_text("HERMES", "apps/desktop/electron/main.ts", needle)
    require_text("HERMES", "gateway/platforms/api_server.py", '"/api/cron/fire"')
    require_text("HERMES", "tools/cronjob_tools.py", "run_one_job")

    # Derive the semantic host/route relation from actual caller-to-sink
    # witnesses. Host labels are review seeds; membership is emitted only after
    # the pinned function body proves the complete call chain. Dynamic model
    # tool dispatch additionally requires the pinned registry mapping and the
    # concrete execution leaf; a declaration in this artifact is insufficient.
    require_calls("gateway/run.py", "start_gateway", {"resolve_cron_scheduler", "Thread"})
    require_calls(
        "gateway/platforms/api_server.py", "APIServerAdapter._handle_cron_fire",
        {"get_fire_verifier", "resolve_cron_scheduler", "fire_due", "create_task"},
    )
    require_calls(
        "hermes_cli/web_server.py", "cron_fire_webhook",
        {"get_fire_verifier", "_find_cron_job_profile", "create_task", "to_thread"},
    )
    require_calls(
        "hermes_cli/web_server.py", "_fire_cron_job_for_profile",
        {"_cron_profile_home", "resolve_cron_scheduler", "fire_due"},
    )
    require_calls(
        "tools/cronjob_tools.py", "_execute_job_now",
        {"claim_job_for_fire", "run_one_job", "mark_job_run"},
    )
    require_text("HERMES", "model_tools.py", '"cronjob_tools": ["cronjob"]')
    require_text("HERMES", "apps/desktop/electron/main.ts", "startHermes")
    require_text("HERMES", "apps/desktop/electron/main.ts", "spawnPoolBackend")
    require_text("HERMES", "hermes_cli/web_server.py", "HERMES_DESKTOP")

    host_entries = {
        "H1_GATEWAY": ("gateway/run.py", "start_gateway"),
        "H2_STANDALONE_DASHBOARD": ("hermes_cli/web_server.py", "start_server"),
        "H3_ELECTRON_PRIMARY": ("apps/desktop/electron/main.ts", "startHermes"),
        "H4_ELECTRON_PROFILE": ("apps/desktop/electron/main.ts", "spawnPoolBackend"),
        "H5_TUI_STDIO": ("tui_gateway/entry.py", "main"),
        "H6_TUI_WS": ("tui_gateway/ws.py", "handle_ws"),
        "H7_ACP_STDIO": ("acp_adapter/entry.py", "main"),
        "H8_CLI_CHAT": ("hermes_cli/main.py", "main"),
        "H9_GATEWAY_API_CHAT": ("gateway/platforms/api_server.py", "APIServerAdapter"),
    }
    for path, symbol in host_entries.values():
        if path.endswith(".py"):
            if not any(
                name == symbol or name.startswith(symbol + ".")
                for name in python_symbols(path)
            ):
                fail("SOURCE_HOST_MISSING", path, symbol)
        elif symbol not in text("HERMES", path):
            fail("SOURCE_HOST_MISSING", path, symbol)

    # Enumerate the complete pinned Python tree before selecting any ownership
    # slice. Expected module membership is then derived from source relations;
    # there is deliberately no authored list of expected module names here.
    tracked = set(git(roots["HERMES"], "ls-tree", "-r", "--name-only", oids["HERMES"]).decode("utf-8", "strict").splitlines())
    tracked_modules = {}
    for path in tracked:
        if not path.endswith(".py") or path.startswith("tests/") or "/tests/" in path:
            continue
        module = (
            path[:-12].replace("/", ".")
            if path.endswith("/__init__.py")
            else path[:-3].replace("/", ".")
        )
        tracked_modules[module] = path
    authority_paths = git_grep_paths(
        roots["HERMES"], oids["HERMES"],
        r"^def (claim_job_for_fire|run_one_job|resolve_cron_scheduler|get_fire_verifier|build_profile_secret_scope|atomic_replace|write_runtime_status|read_runtime_status)|^class .*CronScheduler",
        ["*.py", ":!tests/**"],
    )
    authority_modules = {
        module for module, path in tracked_modules.items() if path in authority_paths
    }

    def module_for_path(path):
        return next(
            (module for module, candidate in tracked_modules.items() if candidate == path),
            None,
        )

    # Entrypoints are derived from the already source-validated host witnesses,
    # the console-script declarations, and the exact parser/dispatcher symbols.
    entry_modules = {
        module_for_path(path) for path, _symbol in host_entries.values()
        if path.endswith(".py")
    }
    entry_modules.discard(None)
    pyproject = text("HERMES", "pyproject.toml")
    for match in re.finditer(
        r'(?m)^([-A-Za-z0-9_]+)\s*=\s*"([A-Za-z_][\w.]*):[A-Za-z_][\w]*"\s*$',
        pyproject,
    ):
        if match.group(1) in {"hermes", "hermes-acp"} and match.group(2) in tracked_modules:
            entry_modules.add(match.group(2))

    semantic_entry_symbols = {
        "CLIAgentSetupMixin", "build_acp_parser", "build_cron_parser",
        "build_dashboard_parser", "build_gateway_parser", "run_gateway",
        "run_oneshot", "write_json",
    }
    support_symbols = {
        "NasCronClient", "atomic_replace", "build_profile_secret_scope",
        "check_gateway_lifecycle", "cfg_get", "get_fallback_chain",
        "get_fire_verifier", "get_hermes_home", "load_config",
        "load_cron_scheduler", "now", "read_runtime_status",
        "resolve_nous_access_token", "resolve_profile_env",
        "write_runtime_status", "_get_default_hermes_home",
    }
    relation_paths = git_grep_paths(
        roots["HERMES"], oids["HERMES"],
        r"claim_job_for_fire|run_one_job|\.fire_due\(|get_fire_verifier|_execute_job_now|resolve_cron_scheduler\(",
        ["*.py", ":!tests/**"],
    )
    relation_symbols = {
        "_execute_job_now", "claim_job_for_fire", "fire_due",
        "get_fire_verifier", "resolve_cron_scheduler", "run_one_job",
    }

    def execution_relation_in_tree(tree):
        aliases = set(relation_symbols)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in relation_symbols:
                        aliases.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in relation_symbols:
                return True
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else ""
                )
                if called in aliases:
                    return True
        return False

    relation_paths = {
        path for path in relation_paths
        if (
            parsed_tree(module_for_path(path) or path, path) is not None
            and execution_relation_in_tree(parsed_tree(module_for_path(path) or path, path))
        )
    }
    alias_probe = ast.parse(
        "from cron.scheduler_provider import resolve_cron_scheduler as choose\n"
        "def wrapper():\n    return choose()\n"
    )
    if not execution_relation_in_tree(alias_probe):
        fail("SOURCE_RELATION_DETECTOR_BLIND", "alias_wrapper", "aliased call")
    semantic_symbol_pattern = (
        r"^(async )?def (" + "|".join(sorted(
            semantic_entry_symbols | support_symbols
        )) + r")\b|^class (" + "|".join(sorted(
            semantic_entry_symbols | support_symbols
        )) + r")\b"
    )
    semantic_paths = git_grep_paths(
        roots["HERMES"], oids["HERMES"], semantic_symbol_pattern,
        ["*.py", ":!tests/**"],
    )
    relevant_paths = set(authority_paths) | set(relation_paths) | set(semantic_paths)
    relevant_paths.update(
        path for path, _symbol in host_entries.values() if path.endswith(".py")
    )
    relevant_modules = {
        module for module, path in tracked_modules.items() if path in relevant_paths
    }
    # Recursively admit tracked package initializers for every discovered
    # module. They are graph candidates, not automatically expected members.
    for module in list(relevant_modules):
        parts = module.split(".")[:-1]
        while parts:
            package = ".".join(parts)
            if package in tracked_modules:
                relevant_modules.add(package)
            parts.pop()

    # Build import *and call* relations over every tracked Python module before
    # applying the semantic projection.  A source file is never omitted merely
    # because it is not already named by the model.  Python newer than the
    # validator interpreter is retained lexically for imports, but it is a hard
    # refusal when it contains a managed execution/store relation that cannot
    # be parsed soundly.
    all_import_graph = {module: set() for module in tracked_modules}
    all_call_graph = {module: set() for module in tracked_modules}
    unresolved_dynamic_modules = set()
    all_reverse_import_graph = {module: set() for module in tracked_modules}
    path_modules = {path: module for module, path in tracked_modules.items()}

    def resolve_import_targets(module, path, source_line):
        try:
            statement = ast.parse(source_line.strip()).body[0]
        except (SyntaxError, IndexError):
            return set()
        names = set()
        if isinstance(statement, ast.Import):
            names.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            imported = statement.module or ""
            if statement.level:
                package = module if path.endswith("/__init__.py") else module.rpartition(".")[0]
                parts = package.split(".") if package else []
                keep = max(0, len(parts) - (statement.level - 1))
                imported = ".".join(parts[:keep] + ([imported] if imported else []))
            if imported:
                names.add(imported)
                names.update(imported + "." + alias.name for alias in statement.names)
        targets = set()
        for name in names:
            candidate = name
            while candidate:
                if candidate in tracked_modules:
                    targets.add(candidate)
                    break
                candidate = candidate.rpartition(".")[0]
        return targets

    managed_relation_pattern = re.compile(
        r"claim_job_for_fire\s*\(|run_one_job\s*\(|resolve_cron_scheduler\s*\("
        r"|\.fire_due\s*\(|get_fire_verifier\s*\(|jobs\.json"
    )

    def dotted_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return (parent + "." if parent else "") + node.attr
        return ""

    managed_dynamic_targets = {
        "claim_job_for_fire", "fire_due", "get_fire_verifier",
        "resolve_cron_scheduler", "run_one_job",
    }

    def literal_fragments(node):
        return "".join(
            item.s for item in ast.walk(node) if isinstance(item, ast.Str)
        )

    def unresolved_managed_dynamic_call(node):
        if not isinstance(node, ast.Call):
            return False
        called = dotted_name(node.func)
        candidate = ""
        if called.endswith("getattr") and len(node.args) >= 2:
            if isinstance(node.args[1], ast.Str):
                return False
            candidate = literal_fragments(node.args[1])
        elif called in {"globals", "locals"}:
            candidate = literal_fragments(node)
        elif called in {"__import__", "importlib.import_module"} and node.args:
            if isinstance(node.args[0], ast.Str):
                return False
            candidate = literal_fragments(node.args[0])
        return any(target in candidate for target in managed_dynamic_targets)

    for module, path in tracked_modules.items():
        source = text("HERMES", path)
        tree = parsed_tree(module, path)
        if tree is None:
            if managed_relation_pattern.search(source):
                fail("SOURCE_UNSUPPORTED_RELEVANT_SYNTAX", path, "managed Python relation")
            # Preserve ordinary import reachability even on the Python 3.8
            # validation floor.  Such a module cannot become a managed call
            # owner without triggering the refusal above.
            for source_line in source.splitlines():
                if re.match(r"^\s*(from|import)\s+", source_line):
                    for target in resolve_import_targets(module, path, source_line):
                        if target != module:
                            all_import_graph[module].add(target)
            continue

        aliases = {}
        local_symbols = {
            item.name for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name
                    candidate = alias.name
                    while candidate:
                        if candidate in tracked_modules:
                            if candidate != module:
                                all_import_graph[module].add(candidate)
                            break
                        candidate = candidate.rpartition(".")[0]
            elif isinstance(item, ast.ImportFrom):
                imported = item.module or ""
                if item.level:
                    package = module if path.endswith("/__init__.py") else module.rpartition(".")[0]
                    parts = package.split(".") if package else []
                    keep = max(0, len(parts) - (item.level - 1))
                    imported = ".".join(parts[:keep] + ([imported] if imported else []))
                for alias in item.names:
                    if alias.name == "*":
                        continue
                    aliases[alias.asname or alias.name] = (
                        imported + "." + alias.name if imported else alias.name
                    )
                for name in [imported] + [
                    imported + "." + alias.name
                    for alias in item.names if imported and alias.name != "*"
                ]:
                    candidate = name
                    while candidate:
                        if candidate in tracked_modules:
                            if candidate != module:
                                all_import_graph[module].add(candidate)
                            break
                        candidate = candidate.rpartition(".")[0]
            elif isinstance(item, ast.Call):
                if unresolved_managed_dynamic_call(item):
                    unresolved_dynamic_modules.add(module)
                called = dotted_name(item.func)
                if not called:
                    continue
                first, dot, suffix = called.partition(".")
                qualified = aliases.get(first)
                if qualified is not None and dot:
                    qualified += "." + suffix
                elif qualified is None and first in local_symbols:
                    qualified = module + "." + called
                if qualified is None:
                    continue
                candidate = qualified
                while candidate:
                    if candidate in tracked_modules:
                        if candidate != module:
                            all_call_graph[module].add(candidate)
                        break
                    candidate = candidate.rpartition(".")[0]

    # The reverse relation is built only after the complete source pass. Calls
    # and imports are both legitimate reachability edges; semantic filtering
    # happens below, never while discovering them.
    all_source_graph = {
        module: all_import_graph[module] | all_call_graph[module]
        for module in tracked_modules
    }
    hidden_bridge_tree = ast.parse(
        "import cron.scheduler_provider as provider\n"
        "def hidden_bridge():\n"
        "    return getattr(provider, 'resolve_' + 'cron_scheduler')()\n"
    )
    if not any(
        unresolved_managed_dynamic_call(node) for node in ast.walk(hidden_bridge_tree)
    ):
        fail("SOURCE_DYNAMIC_FALSIFIER_BLIND", "hidden_dynamic_bridge.py", "getattr target")
    for module, targets in all_source_graph.items():
        for target in targets:
            if target != module:
                all_reverse_import_graph[target].add(module)

    symbol_modules = collections.defaultdict(set)
    for module in relevant_modules:
        path = tracked_modules[module]
        tree = parsed_tree(module, path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbol_modules[node.name].add(module)
    imported_by_entry = set().union(*(
        all_import_graph[module] for module in entry_modules
    ))
    for symbol in semantic_entry_symbols:
        entry_modules.update(
            module for module in symbol_modules.get(symbol, set())
            if module in imported_by_entry
            or module.startswith("hermes_cli.")
            or module.startswith("tui_gateway.")
        )

    # Actual execution relations were discovered across the full tracked tree,
    # not by intersecting with an expected-path list. A newly added caller or
    # owner therefore changes the oracle and model equality.
    relation_modules = {
        module for module, path in tracked_modules.items() if path in relation_paths
    }
    support_candidates = set().union(*(
        symbol_modules.get(symbol, set()) for symbol in support_symbols
    ))
    support_candidates = {
        module for module in support_candidates
        if module in {"hermes_constants", "hermes_time", "utils"}
        or module.startswith(("agent.", "cron.", "gateway.", "hermes_cli."))
        or module.startswith("plugins.cron_providers")
    }

    # Package re-export owners are found from the complete import relation:
    # an __init__ module that directly reexports a discovered cron authority is
    # part of the public authority surface. Provider siblings reached directly
    # by a discovered provider module are likewise retained.
    reexport_modules = {
        module for module, path in tracked_modules.items()
        if path.endswith("/__init__.py")
        and module in all_import_graph
        and all_import_graph[module] & authority_modules
    }
    provider_family = {
        module for module in relevant_modules
        if module.startswith("plugins.cron_providers")
        and (
            module in relation_modules
            or any(
                module in all_import_graph[source]
                for source in relation_modules
                if source in all_import_graph
            )
        )
    }
    support_importers = relation_modules | authority_modules | provider_family
    directly_required_support = set().union(*(
        all_import_graph[module] for module in support_importers
    ))
    support_modules = support_candidates & directly_required_support

    def walk(graph, seeds):
        reached = set(seeds)
        pending = list(seeds)
        while pending:
            current = pending.pop()
            for target in graph[current]:
                if target not in reached:
                    reached.add(target)
                    pending.append(target)
        return reached

    # `relation_modules` and `authority_modules` are all-tree discoveries;
    # semantic entry/support symbols are reviewer-owned behavior seeds. The
    # CREATE module is the one explicit target seam absent from pinned source.
    all_forward = walk(all_source_graph, entry_modules)
    all_reverse = walk(all_reverse_import_graph, authority_modules)
    source_connected = all_forward & all_reverse
    probe_graph = {module: set(targets) for module, targets in all_source_graph.items()}
    probe_graph["hidden_dynamic_bridge"] = {"cron.scheduler_provider"}
    probe_graph["gateway.run"].add("hidden_dynamic_bridge")
    probe_reverse = {module: set() for module in probe_graph}
    for module, targets in probe_graph.items():
        for target in targets:
            probe_reverse.setdefault(target, set()).add(module)
    if "hidden_dynamic_bridge" not in (
        walk(probe_graph, entry_modules) & walk(probe_reverse, authority_modules)
    ):
        fail("SOURCE_FIXED_POINT_FALSIFIER_BLIND", "hidden_dynamic_bridge.py", "forward/reverse")
    unresolved_connected = source_connected & unresolved_dynamic_modules
    if unresolved_connected:
        fail(
            "SOURCE_UNRESOLVED_DYNAMIC_TARGET", "python",
            repr(sorted(unresolved_connected)),
        )
    module_names = (
        entry_modules | relation_modules | authority_modules | support_modules
        | reexport_modules | provider_family | source_connected
        | {"hermes_cli.cron_deployment"}
    )

    # Derive each host/route pair from an entry-to-owner relationship. Manual
    # execution requires the host entry to reach the real model-tool registry,
    # its literal cronjob mapping, and the concrete execution leaf. Scheduled
    # and HTTP routes require their already validated call-chain owners and
    # source-owned enablement surfaces. CANARY is the sole target CREATE
    # seam and remains rooted at the pinned cron parser/dispatcher owner.
    host_entry_modules = {
        host: module_for_path(path)
        for host, (path, _symbol) in host_entries.items() if path.endswith(".py")
    }
    host_entry_modules["H3_ELECTRON_PRIMARY"] = module_for_path("hermes_cli/web_server.py")
    host_entry_modules["H4_ELECTRON_PROFILE"] = module_for_path("hermes_cli/web_server.py")
    manual_bridge = "run_agent"
    if manual_bridge not in tracked_modules:
        fail("SOURCE_ROUTE_RELATION_MISSING", manual_bridge, "agent tool bridge")
    require_text("HERMES", "run_agent.py", "from model_tools import (")
    require_text("HERMES", "model_tools.py", '"cronjob_tools": ["cronjob"]')
    host_routes = collections.defaultdict(set)
    for host, entry_module in host_entry_modules.items():
        if entry_module is None or manual_bridge not in walk(all_source_graph, {entry_module}):
            fail("SOURCE_ROUTE_RELATION_MISSING", host, "entry -> run_agent -> model_tools")
        host_routes[host].add("MANUAL_TOOL")
    host_routes["H1_GATEWAY"].update({"BUILTIN_TICK", "GATEWAY_CHRONOS_HTTP"})
    host_routes["H2_STANDALONE_DASHBOARD"].add("DASHBOARD_CHRONOS_HTTP")
    for host in ("H3_ELECTRON_PRIMARY", "H4_ELECTRON_PROFILE"):
        host_routes[host].update({"BUILTIN_TICK", "DASHBOARD_CHRONOS_HTTP"})
    if "cron_command" not in python_symbols("hermes_cli/cron.py"):
        fail("SOURCE_ROUTE_EDIT_SEAM_MISSING", "hermes_cli/cron.py", "cron_command")
    host_routes["H8_CLI_CHAT"].add("CANARY")
    host_routes = {key: set(value) for key, value in host_routes.items()}

    # Discover the complete MW set from every tracked Python/shell candidate;
    # no prewritten path allowlist can hide a tenth writer. Direct writers are
    # identified by a module-level jobs.json path flowing to a write/replace
    # primitive. Generic fallback extractors are identified by their actual
    # safe_extract wb sink, and shell callers by the extractor invocation.
    mw_paths = set(git(
        roots["MARKETWATCH"], "ls-tree", "-r", "--name-only", oids["MARKETWATCH"],
    ).decode("utf-8", "strict").splitlines())

    # Build the relevant TypeScript/shell call/write relation over the complete
    # pinned trees before selecting Electron hosts or archive wrappers.  The
    # relation is intentionally lexical (standard-library-only) but closed:
    # relevant dynamic eval/source/process substitutions are unsupported and
    # refuse instead of disappearing from the graph.
    script_paths = {
        (repo, path)
        for repo, root, oid in (
            ("HERMES", roots["HERMES"], oids["HERMES"]),
            ("MARKETWATCH", roots["MARKETWATCH"], oids["MARKETWATCH"]),
        )
        for path in git(root, "ls-tree", "-r", "--name-only", oid).decode("utf-8", "strict").splitlines()
        if path.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs", ".sh"))
        and not path.startswith("tests/") and "/tests/" not in path
    }
    script_relations = set()
    relevant_script_pattern = re.compile(
        r"startHermes|spawnPoolBackend|backendPool|_extract_backup\.py|jobs\.json"
    )
    unsupported_script_pattern = re.compile(r"\beval\s*\(|\bFunction\s*\(|\bsource\s+\$|\.\s+\$")
    for repo, path in sorted(script_paths):
        source = text(repo, path)
        relevant = bool(relevant_script_pattern.search(source))
        if relevant and unsupported_script_pattern.search(source):
            fail("SOURCE_UNSUPPORTED_RELEVANT_SYNTAX", path, "dynamic TS/shell relation")
        if not relevant:
            continue
        for match in re.finditer(
            r"(?:from\s+|require\s*\(|import\s*\()\s*['\"]([^'\"]+)['\"]",
            source,
        ):
            script_relations.add((repo, path, "IMPORT", match.group(1)))
        for match in re.finditer(
            r"\b(startHermes|spawnPoolBackend|backendPool|safe_extract|_extract_backup\.py)\b",
            source,
        ):
            script_relations.add((repo, path, "CALL", match.group(1)))
        if "jobs.json" in source:
            script_relations.add((repo, path, "WRITE_CANDIDATE", "jobs.json"))
    if not any(row[:3] == ("HERMES", "apps/desktop/electron/main.ts", "CALL") for row in script_relations):
        fail("SOURCE_SCRIPT_GRAPH_MISSING", "apps/desktop/electron/main.ts", "host calls")
    for wrapper in ("restore.sh", "scripts/restore.sh"):
        if ("MARKETWATCH", wrapper, "CALL", "_extract_backup.py") not in script_relations:
            fail("SOURCE_SCRIPT_GRAPH_MISSING", wrapper, "extractor call")

    def node_references(node, names):
        if node is None:
            return False
        return any(
            isinstance(item, ast.Name) and item.id in names
            for item in ast.walk(node)
        )

    def call_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = call_name(node.value)
            return (prefix + "." if prefix else "") + node.attr
        return ""

    def classify_mw_jobs_writer_source(path, source):
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            fail("SOURCE_ORACLE_PARSE", path, "invalid Python")
        def is_jobs_destination(node):
            if node is None:
                return False
            strings = {
                item.value for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            return "jobs.json" in strings and (
                "cron" in strings or any("cron/jobs.json" in value for value in strings)
            )

        jobs_vars = set()
        assignments = []
        for statement in ast.walk(tree):
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            value = statement.value
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            target_names = {item.id for item in targets if isinstance(item, ast.Name)}
            assignments.append((target_names, value))
            if is_jobs_destination(value):
                jobs_vars.update(target_names)
        changed = True
        while changed:
            changed = False
            for target_names, value in assignments:
                if target_names - jobs_vars and node_references(value, jobs_vars):
                    jobs_vars.update(target_names)
                    changed = True

        def references_jobs_destination(node):
            return node_references(node, jobs_vars) or is_jobs_destination(node)

        writes_jobs = False
        for item in ast.walk(tree):
            if not isinstance(item, ast.Call):
                continue
            called = call_name(item.func)
            if called == "open" and item.args and references_jobs_destination(item.args[0]):
                mode = item.args[1].value if len(item.args) > 1 and isinstance(item.args[1], ast.Constant) else ""
                writes_jobs |= isinstance(mode, str) and mode.startswith(("w", "a", "x"))
            elif called in {"os.replace", "replace"} and len(item.args) > 1:
                writes_jobs |= references_jobs_destination(item.args[1])
            elif called.endswith(".replace") and item.args:
                writes_jobs |= references_jobs_destination(item.args[0])
            elif called.endswith(".write_text"):
                writes_jobs |= references_jobs_destination(item.func)
        definitions = {
            item.name for item in ast.walk(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        generic_extractor = (
            "safe_extract" in definitions
            and any(
                isinstance(item, ast.Call) and call_name(item.func) == "open"
                and len(item.args) > 1 and isinstance(item.args[1], ast.Constant)
                and item.args[1].value == "wb"
                for item in ast.walk(tree)
            )
            and any(
                isinstance(item, ast.Call) and call_name(item.func).endswith(".write")
                for item in ast.walk(tree)
            )
        )
        return writes_jobs or generic_extractor

    def is_mw_jobs_writer(path):
        return classify_mw_jobs_writer_source(path, text("MARKETWATCH", path))

    # Detector self-probes are source-shaped, not model-shaped. They prove that
    # a newly added tenth direct writer would enter the independently derived
    # oracle rather than disappear behind the current nine-member result.
    synthetic_writers = {
        "alias": (
            "def replace_jobs(home, tmp):\n"
            "    path = home / 'cron' / 'jobs.json'\n"
            "    destination = path\n"
            "    tmp.replace(destination)\n"
        ),
        "direct": (
            "def replace_jobs(home, tmp):\n"
            "    tmp.replace(home / 'cron' / 'jobs.json')\n"
        ),
        "function_local": (
            "def replace_jobs(tmp):\n"
            "    from pathlib import Path\n"
            "    jobs_file = Path('/controlled') / 'cron' / 'jobs.json'\n"
            "    tmp.replace(jobs_file)\n"
        ),
    }
    for probe, source in synthetic_writers.items():
        if not classify_mw_jobs_writer_source(
            "synthetic/" + probe + "_jobs_writer.py", source,
        ):
            fail("SOURCE_WRITER_DETECTOR_BLIND", "marketwatch", probe)

    mw_writers = {
        path for path in mw_paths
        if (
            path.endswith(".py")
            and "/tests/" not in path and not path.startswith("tests/")
            and is_mw_jobs_writer(path)
        ) or (
            path.endswith(".sh")
            and "_extract_backup.py" in text("MARKETWATCH", path)
        )
    }
    if len(mw_writers) != 9:
        fail("SOURCE_ORACLE_MISSING", "marketwatch", "7 writers + 2 callers")
    for path in mw_writers:
        if path.endswith("_extract_backup.py"):
            require_text("MARKETWATCH", path, "def safe_extract")
        elif path.endswith(".py"):
            require_text("MARKETWATCH", path, "jobs.json")
        else:
            require_text("MARKETWATCH", path, "_extract_backup.py")

    bindings = {"default", "named", "request_scoped"}
    resolution_kinds = {
        "builtin_alias", "builtin_default", "chronos", "fallback_load_error",
        "fallback_missing", "fallback_unavailable", "user_plugin_refused",
    }
    providers = {binding + ":" + kind for binding in bindings for kind in resolution_kinds}
    return {
        "_authority_modules": authority_modules,
        "_module_paths": {
            module: (
                tracked_modules[module] if module in tracked_modules
                else "CREATE:hermes_cli/cron_deployment.py"
            )
            for module in module_names
        },
        "_python_graph_counts": {
            "modules": len(tracked_modules),
            "import_edges": sum(len(value) for value in all_import_graph.values()),
            "call_edges": sum(len(value) for value in all_call_graph.values()),
        },
        "_script_graph_count": len(script_relations),
        "archive_members": {
            ".hermes/cron/jobs.json", "cron/jobs.json", "hermes/cron/jobs.json",
            "profiles/<valid>/cron/jobs.json",
        },
        "bindings": bindings,
        "cuts": {
            "body_complete", "cleanup_classified", "cold_restart",
            "http_cancel_after_worker", "http_cancel_before_worker",
            "http_worker_exit_after_cancel", "interruption", "postclaim_preregister",
            "postfinalizer", "postrearm", "postregister_preworker", "postrelease",
            "preclaim", "prefinalizer", "prerearm", "prerelease",
            "quarantine_postcommit", "quarantine_precommit", "shutdown_close",
            "shutdown_snapshot", "worker_started",
        },
        "hosts": set(host_routes),
        "host_routes": host_routes,
        "modules": module_names,
        "mw_writers": mw_writers,
        "providers": providers,
        "results": {
            "AGENT_FAILED", "CLEANUP_UNVERIFIED", "DELIVERY_FAILED", "EMPTY_RESPONSE",
            "FINALIZATION_FAILED", "OUTPUT_FAILED", "PRE_RUN_FAILED", "REFUSED",
            "SHUTDOWN_INTERRUPTED", "SUCCESS", "WHITESPACE_EMPTY",
        },
        "routes": set().union(*host_routes.values()),
        "stores": {"default:<home>/cron/jobs.json", "named:<home>/cron/jobs.json"},
        "tests": {
            "activation_and_git", "archive", "chronos_bundle", "lifecycle",
            "managed_product", "marketwatch_writers", "module_fixed_point",
            "pause_quarantine", "route_witnesses",
        },
    }


def load_sources(model, roots, oids):
    cache = {}
    for locator in model["locators"]:
        require_keys(
            locator,
            {
                "id", "repo", "path", "language", "proof", "symbol",
                "anchor", "expected_occurrences",
            },
            locator.get("id", "locator"),
        )
        lid = locator["id"]
        repo = locator["repo"]
        if repo not in roots:
            fail("SOURCE_REPO_INVALID", lid, repo)
        path = pathlib.PurePosixPath(locator["path"])
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            fail("SOURCE_PATH_INVALID", lid, locator["path"])
        tracked = git(roots[repo], "ls-tree", "-r", "--name-only", oids[repo], "--", locator["path"])
        if tracked.decode("utf-8").splitlines() != [locator["path"]]:
            fail("SOURCE_PATH_UNTRACKED", lid, locator["path"])
        raw = git(roots[repo], "show", oids[repo] + ":" + locator["path"])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            fail("SOURCE_UTF8_INVALID", lid, locator["path"])
        if locator["proof"] == "PYTHON_AST":
            if locator["symbol"] is None or locator["anchor"] is not None:
                fail("SOURCE_LOCATOR_INVALID", lid, "PYTHON_AST shape")
            try:
                names = resolve_qualnames(ast.parse(text, filename=locator["path"]))
            except SyntaxError as exc:
                fail("SOURCE_AST_INVALID", lid, str(exc))
            count = names.count(locator["symbol"])
        elif locator["proof"] == "EXACT_TEXT":
            if not locator["anchor"] or locator["symbol"] is not None:
                fail("SOURCE_LOCATOR_INVALID", lid, "EXACT_TEXT shape")
            count = text.count(locator["anchor"])
        else:
            fail("SOURCE_LOCATOR_INVALID", lid, locator["proof"])
        if count != locator["expected_occurrences"]:
            fail(
                "SOURCE_LOCATOR_MISSING", lid,
                "expected " + str(locator["expected_occurrences"]) + " got " + str(count),
            )
        cache[lid] = {
            "text": text,
            "digest": hashlib.sha256(raw).hexdigest(),
            "path": locator["path"],
            "repo": repo,
            "qualnames": tuple(names) if locator["proof"] == "PYTHON_AST" else (),
        }
    return cache


def validate_cached_sources(model, cache):
    """Revalidate mutated locator declarations against immutable pinned blobs."""
    if {item["id"] for item in model["locators"]} != set(cache):
        fail("SOURCE_LOCATOR_SET_MISMATCH", "locators", "cached pinned set")
    for locator in model["locators"]:
        require_keys(
            locator,
            {"id", "repo", "path", "language", "proof", "symbol", "anchor", "expected_occurrences"},
            locator.get("id", "locator"),
        )
        pinned = cache[locator["id"]]
        if locator["repo"] != pinned["repo"] or locator["path"] != pinned["path"]:
            fail("SOURCE_LOCATOR_MISSING", locator["id"], "pinned path changed")
        source_text = pinned["text"]
        if locator["proof"] == "PYTHON_AST":
            if locator["symbol"] is None or locator["anchor"] is not None:
                fail("SOURCE_LOCATOR_INVALID", locator["id"], "PYTHON_AST shape")
            count = pinned["qualnames"].count(locator["symbol"])
        elif locator["proof"] == "EXACT_TEXT":
            if not locator["anchor"] or locator["symbol"] is not None:
                fail("SOURCE_LOCATOR_INVALID", locator["id"], "EXACT_TEXT shape")
            count = source_text.count(locator["anchor"])
        else:
            fail("SOURCE_LOCATOR_INVALID", locator["id"], locator["proof"])
        if count != locator["expected_occurrences"]:
            fail("SOURCE_LOCATOR_MISSING", locator["id"], "cached pinned mismatch")
    return cache


def validate_field(field_value, type_names, object_id):
    require_keys(field_value, {"name", "type", "presence", "nullable"}, object_id)
    if field_value["type"] not in type_names:
        fail("TYPE_REFERENCE_UNDEFINED", object_id, field_value["type"])
    if field_value["presence"] not in {"REQUIRED", "OPTIONAL"}:
        fail("FIELD_PRESENCE_INVALID", object_id, field_value["presence"])
    if type(field_value["nullable"]) is not bool:
        fail("FIELD_NULLABILITY_INVALID", object_id, "nullable must be bool")


def scalar_sample(type_def):
    base = type_def["base"]
    constraints = type_def["constraints"]
    if base == "BOOL":
        return False
    if base == "INT":
        return max(0, constraints.get("minimum", 0))
    if base == "BYTES":
        return b"x"
    if base == "UUID4":
        return "00000000-0000-4000-8000-000000000000"
    if base == "H40":
        return "0" * 40
    if base == "ABS_PATH":
        return "/model"
    if base == "TIMESTAMP":
        return "2026-01-01T00:00:00+00:00"
    if base == "STRING":
        pattern = constraints.get("pattern", "")
        if "{64}" in pattern:
            return "0" * 64
        return "a"
    fail("TYPE_INVALID", type_def["name"], base)


def validate_scalar_value(type_def, value):
    base = type_def["base"]
    if base == "BOOL" and type(value) is not bool:
        return False
    if base == "INT" and (type(value) is not int or value < type_def["constraints"].get("minimum", 0)):
        return False
    if base == "BYTES" and type(value) is not bytes:
        return False
    if base in {"STRING", "UUID4", "H40", "ABS_PATH", "TIMESTAMP"} and not isinstance(value, str):
        return False
    if base == "UUID4" and not UUID4_RE.fullmatch(value):
        return False
    if base == "H40" and not H40_RE.fullmatch(value):
        return False
    if base == "ABS_PATH" and not pathlib.PurePosixPath(value).is_absolute():
        return False
    pattern = type_def["constraints"].get("pattern")
    if pattern and not re.fullmatch(pattern, value):
        return False
    if isinstance(value, str) and len(value) < type_def["constraints"].get("min_length", 0):
        return False
    return True


def validate_types(model):
    sorted_unique(model["types"], "types", key=lambda item: item["name"])
    type_map = index_unique(model["types"], "name", "types")
    names = set(type_map)
    for name, type_def in type_map.items():
        kind = type_def.get("kind")
        if kind == "SCALAR":
            require_keys(type_def, {"name", "kind", "base", "constraints"}, name)
            if not isinstance(type_def["constraints"], dict):
                fail("TYPE_INVALID", name, "constraints")
            sample = scalar_sample(type_def)
            if not validate_scalar_value(type_def, sample):
                fail("TYPE_NOT_CONSTRUCTIBLE", name, "scalar sample")
        elif kind == "ENUM":
            require_keys(type_def, {"name", "kind", "values"}, name)
            sorted_unique(type_def["values"], name)
            if not type_def["values"]:
                fail("TYPE_NOT_CONSTRUCTIBLE", name, "empty enum")
        elif kind == "RECORD":
            require_keys(type_def, {"name", "kind", "fields"}, name)
            field_names = []
            for field_value in type_def["fields"]:
                validate_field(field_value, names, name)
                field_names.append(field_value["name"])
            if len(field_names) != len(set(field_names)):
                fail("TYPE_INVALID", name, "duplicate field")
        elif kind == "UNION":
            require_keys(
                type_def,
                {"name", "kind", "discriminator", "variants", "invalid_complement"},
                name,
            )
            if type_def["invalid_complement"] != "REJECT":
                fail("TYPE_INVALID", name, "invalid complement")
            tags = []
            for variant in type_def["variants"]:
                require_keys(variant, {"tag", "fields"}, name)
                tags.append(variant["tag"])
                field_names = []
                for field_value in variant["fields"]:
                    validate_field(field_value, names, name + "." + variant["tag"])
                    field_names.append(field_value["name"])
                if len(field_names) != len(set(field_names)):
                    fail("TYPE_INVALID", name, "duplicate variant field")
            if len(tags) != len(set(tags)) or not tags:
                fail("TYPE_INVALID", name, "variant tags")
        else:
            fail("TYPE_INVALID", name, repr(kind))

    constructing = set()
    constructed = {}

    def construct(name, variant_tag=None):
        key = (name, variant_tag)
        if key in constructed:
            return constructed[key]
        if name in constructing:
            fail("TYPE_CYCLE", name, "recursive construction")
        constructing.add(name)
        type_def = type_map[name]
        if type_def["kind"] == "SCALAR":
            value = scalar_sample(type_def)
        elif type_def["kind"] == "ENUM":
            value = type_def["values"][0]
        else:
            if type_def["kind"] == "UNION":
                variants = {item["tag"]: item for item in type_def["variants"]}
                chosen = variants[variant_tag or type_def["variants"][0]["tag"]]
                fields = chosen["fields"]
                value = {"tag": chosen["tag"]}
            else:
                fields = type_def["fields"]
                value = {}
            for item in fields:
                if item["presence"] == "OPTIONAL":
                    if item["nullable"]:
                        value[item["name"]] = None
                    continue
                value[item["name"]] = construct(item["type"])
        constructing.remove(name)
        constructed[key] = value
        return value

    for name, type_def in type_map.items():
        if type_def["kind"] == "UNION":
            for item in type_def["variants"]:
                construct(name, item["tag"])
        else:
            construct(name)
    required_body = {
        "REFUSED": {"response_text", "error"},
        "PRE_RUN_FAILED": {"response_text", "error"},
        "AGENT_FAILED": {"response_text", "error"},
        "EMPTY_RESPONSE": {"response_text", "error"},
        "WHITESPACE_EMPTY": {"response_text", "error"},
        "INTENTIONAL_SILENCE": {"response_text", "error"},
        "NONEMPTY": {"response_text", "error"},
        "SHUTDOWN_INTERRUPTED": {"response_text", "error"},
    }
    body = type_map["ManagedBodyResultV1"]
    actual = {v["tag"]: {f["name"] for f in v["fields"]} for v in body["variants"]}
    if actual != required_body:
        fail("TYPE_INVALID", "ManagedBodyResultV1", "variant field set")
    if type_map["ManagedBodyResultV1"]["variants"][0].get("invalid_complement") is not None:
        fail("TYPE_INVALID", "ManagedBodyResultV1", "variant-local complement")
    return type_map


def validate_typed_membership_sets(type_map, source_oracle):
    route_members = sorted(source_oracle["routes"])
    module_members = sorted(source_oracle["modules"])
    if type_map["MembershipEncodingV1"] != {
        "name": "MembershipEncodingV1", "kind": "ENUM",
        "values": ["SORTED_UNIQUE_NONNULL_PREFIX_NULL_TAIL_V1"],
    }:
        fail("MEMBERSHIP_ENCODING_INVALID", "MembershipEncodingV1", "closed literal")
    if type_map["MembershipDigestRoleV1"] != {
        "name": "MembershipDigestRoleV1", "kind": "ENUM",
        "values": ["OBSERVATIONAL_ONLY_CANONICAL_MEMBER_ARRAY_SHA256"],
    }:
        fail("MEMBERSHIP_DIGEST_AS_AUTHORITY", "MembershipDigestRoleV1", "closed literal")
    if type_map["RouteV1"]["values"] != route_members:
        fail("ROUTE_TYPED_MEMBERSHIP_MISMATCH", "RouteV1", repr(route_members))
    if type_map["ModuleNameV1"]["values"] != module_members:
        fail("MODULE_TYPED_MEMBERSHIP_MISMATCH", "ModuleNameV1", repr(module_members))

    route_tuple = type_map["RouteMemberTupleV1"]
    expected_route_fields = ["member_" + str(index) for index in range(len(route_members))]
    if [field["name"] for field in route_tuple["fields"]] != expected_route_fields or any(
        field["type"] != "RouteV1" or field["presence"] != "REQUIRED"
        or field["nullable"] is not True
        for field in route_tuple["fields"]
    ):
        fail("ROUTE_TYPED_MEMBERSHIP_MISMATCH", "RouteMemberTupleV1", "literal slots")

    module_tuple = type_map["ModuleMemberTupleV1"]
    module_slot_width = len(str(len(module_members) - 1))
    expected_module_fields = [
        "member_" + str(index).zfill(module_slot_width)
        for index in range(len(module_members))
    ]
    if [field["name"] for field in module_tuple["fields"]] != expected_module_fields or any(
        field["type"] != "ModuleNameV1" or field["presence"] != "REQUIRED"
        or field["nullable"] is not True
        for field in module_tuple["fields"]
    ):
        fail("MODULE_TYPED_MEMBERSHIP_MISMATCH", "ModuleMemberTupleV1", "literal slots")

    expected_sets = {
        "RouteSetV1": {
            "encoding": "MembershipEncodingV1", "members": "RouteMemberTupleV1",
            "count": "Int", "digest": "SHA256", "digest_role": "MembershipDigestRoleV1",
        },
        "ModuleSetV1": {
            "encoding": "MembershipEncodingV1", "members": "ModuleMemberTupleV1",
            "count": "Int", "digest": "SHA256", "digest_role": "MembershipDigestRoleV1",
        },
    }
    for name, expected in expected_sets.items():
        actual = {field["name"]: field["type"] for field in type_map[name]["fields"]}
        if actual != expected or any(
            field["presence"] != "REQUIRED" or field["nullable"] is not False
            for field in type_map[name]["fields"]
        ):
            code = "ROUTE_TYPED_MEMBERSHIP_MISMATCH" if name.startswith("Route") else "MODULE_TYPED_MEMBERSHIP_MISMATCH"
            fail(code, name, repr(actual))

    bootstrap_fields = {
        field["name"]: field["type"]
        for field in type_map["BootstrapObservationV2"]["fields"]
    }
    if bootstrap_fields.get("externally_bound_modules") != "ModuleSetV1":
        fail("MODULE_TYPED_MEMBERSHIP_MISMATCH", "BootstrapObservationV2", "partition absent")
    activation_fields = {
        field["name"]: field["type"]
        for field in type_map["ActivationOpenV1"]["fields"]
    }
    if activation_fields.get("routes") != "RouteSetV1" or activation_fields.get("modules") != "ModuleSetV1":
        fail("ACTIVATION_TYPED_MEMBERSHIP_MISSING", "ActivationOpenV1", repr(activation_fields))

    def canonical_member_image(universe, members, width, prefix):
        ordered = sorted(members)
        if len(ordered) != len(set(ordered)) or not set(ordered) <= set(universe):
            fail("MEMBERSHIP_LITERAL_INVALID", prefix, repr(ordered))
        slot_width = len(str(width - 1))
        slots = {
            prefix + str(index).zfill(slot_width): (
                ordered[index] if index < len(ordered) else None
            )
            for index in range(width)
        }
        digest = hashlib.sha256(json.dumps(
            ordered, ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        return slots, len(ordered), digest

    # Construct every concrete source-owned route subset and the complete
    # module set.  Nullable slots are only a fixed-width wire encoding; the
    # nonnull prefix remains the literal authority.
    for host, members in source_oracle["host_routes"].items():
        slots, count, _digest = canonical_member_image(
            route_members, members, len(route_members), "member_",
        )
        values = list(slots.values())
        if values[:count] != sorted(members) or any(value is not None for value in values[count:]):
            fail("ROUTE_TYPED_MEMBERSHIP_MISMATCH", host, "canonical prefix")
    slots, count, _digest = canonical_member_image(
        module_members, module_members, len(module_members), "member_",
    )
    if count != len(module_members) or list(slots.values()) != module_members:
        fail("MODULE_TYPED_MEMBERSHIP_MISMATCH", "modules", "canonical prefix")


def validate_failure_ref(ref, type_map, object_id):
    require_keys(ref, {"wire_type", "variant"}, object_id)
    type_def = type_map.get(ref["wire_type"])
    if not type_def or type_def["kind"] != "UNION":
        fail("FAILURE_TYPE_INVALID", object_id, ref["wire_type"])
    if ref["variant"] not in {item["tag"] for item in type_def["variants"]}:
        fail("FAILURE_VARIANT_INVALID", object_id, ref["variant"])


def validate_graph(model, type_map, locator_map):
    flow_type = type_map.get("EdgeFlowV1")
    if not flow_type or flow_type.get("kind") != "ENUM" or set(flow_type["values"]) != ALLOWED_EDGE_FLOWS:
        fail("EDGE_FLOW_TYPE_INVALID", "EdgeFlowV1", "closed flow discriminator")
    sorted_unique(model["nodes"], "nodes", key=lambda item: item["id"])
    sorted_unique(model["edges"], "edges", key=lambda item: item["id"])
    nodes = index_unique(model["nodes"], "id", "nodes")
    edges = index_unique(model["edges"], "id", "edges")
    required_edges = {
        "E29_BUNDLE", "E027_BODY", "E027_CLEANUP", "E027_OUTPUT",
        "E027_DELIVERY", "E027_FINAL", "E028_BODY", "E028_CLEANUP",
        "E028_OUTPUT", "E028_DELIVERY", "E028_QUARANTINE",
        "E043_REGISTRY_SNAPSHOT", "E048_SILENCE_SAVE", "E035",
    }
    if not required_edges <= set(edges):
        missing = required_edges - set(edges)
        edge_codes = {
            "E29_BUNDLE": "BUNDLE_PRODUCER_MISSING",
            "E027_BODY": "AGGREGATE_INPUT_MISSING",
            "E028_BODY": "AGGREGATE_INPUT_MISSING",
            "E043_REGISTRY_SNAPSHOT": "REGISTRY_EDGE_MISSING",
            "E048_SILENCE_SAVE": "OUTPUT_UNCONSUMED",
            "E035": "EARLY_BUNDLE_EDGE_MISSING",
        }
        first = sorted(missing)[0]
        fail(edge_codes.get(first, "REQUIRED_EDGE_MISSING"), first, "required edge")
    ports_in = {}
    ports_out = {}
    for node_id, node_value in nodes.items():
        require_keys(
            node_value,
            {
                "id", "owner", "source", "kind", "inputs", "outputs",
                "failure_result", "terminal",
            },
            node_id,
        )
        if node_value["owner"] not in locator_map:
            fail("SOURCE_REFERENCE_UNDEFINED", node_id, node_value["owner"])
        sorted_unique(node_value["source"], node_id + ".source")
        if not node_value["source"]:
            fail("SOURCE_REFERENCE_UNDEFINED", node_id, "empty source")
        if any(item not in locator_map for item in node_value["source"]):
            fail("SOURCE_REFERENCE_UNDEFINED", node_id, "source")
        if node_value["kind"] not in ALLOWED_NODE_KINDS:
            fail("NODE_KIND_INVALID", node_id, node_value["kind"])
        if type(node_value["terminal"]) is not bool:
            fail("NODE_TERMINAL_INVALID", node_id, "terminal")
        validate_failure_ref(node_value["failure_result"], type_map, node_id)
        for direction, values, table in (
            ("input", node_value["inputs"], ports_in),
            ("output", node_value["outputs"], ports_out),
        ):
            names = []
            for item in values:
                require_keys(item, {"name", "wire_type", "cardinality"}, node_id)
                names.append(item["name"])
                if item["wire_type"] not in type_map:
                    fail("TYPE_REFERENCE_UNDEFINED", node_id, item["wire_type"])
                if item["cardinality"] not in ALLOWED_CARDINALITIES:
                    fail("CARDINALITY_INVALID", node_id, item["cardinality"])
                table[(node_id, item["name"])] = item
            if len(names) != len(set(names)):
                fail("PORT_DUPLICATE", node_id, direction)

    incoming = collections.Counter()
    outgoing = collections.Counter()
    graph = {node_id: set() for node_id in nodes}
    indegree = {node_id: 0 for node_id in nodes}
    for edge_id, edge_value in edges.items():
        require_keys(
            edge_value,
            {
                "id", "from_node", "from_output", "wire_type", "to_node",
                "to_parameter", "flow", "lifetime", "authority", "cut",
                "failure_result", "mutant",
            },
            edge_id,
        )
        source_key = (edge_value["from_node"], edge_value["from_output"])
        target_key = (edge_value["to_node"], edge_value["to_parameter"])
        if source_key not in ports_out:
            fail("EDGE_SOURCE_INVALID", edge_id, repr(source_key))
        if target_key not in ports_in:
            fail("EDGE_TARGET_INVALID", edge_id, repr(target_key))
        if (
            ports_out[source_key]["wire_type"] != edge_value["wire_type"]
            or ports_in[target_key]["wire_type"] != edge_value["wire_type"]
        ):
            fail("WIRE_TYPE_MISMATCH", edge_id, edge_value["wire_type"])
        source_cardinality = ports_out[source_key]["cardinality"]
        target_cardinality = ports_in[target_key]["cardinality"]
        flow = edge_value["flow"]
        if flow not in ALLOWED_EDGE_FLOWS:
            fail("EDGE_FLOW_INVALID", edge_id, flow)
        legal_pair = {
            "DIRECT": source_cardinality == target_cardinality
            or {source_cardinality, target_cardinality} == {"ONE", "OPTIONAL"},
            "KEYED_FAN_OUT": (
                source_cardinality == "NONEMPTY_MANY"
                and target_cardinality == "ONE"
            ),
            "KEYED_FAN_IN": (
                source_cardinality == "ONE"
                and target_cardinality == "NONEMPTY_MANY"
            ),
        }[flow]
        if not legal_pair:
            fail(
                "EDGE_CARDINALITY_FLOW_INVALID", edge_id,
                f"{flow}:{source_cardinality}->{target_cardinality}",
            )
        if flow != "DIRECT":
            wire = type_map[edge_value["wire_type"]]
            variants = wire["variants"] if wire["kind"] == "UNION" else [wire]
            for candidate in variants:
                child_fields = [
                    field for field in candidate["fields"]
                    if field["name"] == "child_key"
                ]
                if len(child_fields) != 1 or child_fields[0] != {
                    "name": "child_key", "type": "HostKeyV1",
                    "presence": "REQUIRED", "nullable": False,
                }:
                    fail("KEYED_FLOW_IDENTITY_MISSING", edge_id, edge_value["wire_type"])
        if edge_value["lifetime"] not in ALLOWED_LIFETIMES:
            fail("EDGE_LIFETIME_INVALID", edge_id, edge_value["lifetime"])
        if edge_value["authority"] not in locator_map:
            fail("SOURCE_REFERENCE_UNDEFINED", edge_id, edge_value["authority"])
        validate_failure_ref(edge_value["failure_result"], type_map, edge_id)
        if not re.fullmatch(r"N(?:0[1-9]|1[0-9]|2[0-2])", edge_value["mutant"]):
            fail("EDGE_MUTANT_INVALID", edge_id, edge_value["mutant"])
        incoming[target_key] += 1
        outgoing[source_key] += 1
        source_node = edge_value["from_node"]
        target_node = edge_value["to_node"]
        if target_node not in graph[source_node]:
            graph[source_node].add(target_node)
            indegree[target_node] += 1
        if edge_value["lifetime"] == "CROSS_PROCESS":
            wire = type_map[edge_value["wire_type"]]
            variants = wire["variants"] if wire["kind"] == "UNION" else [wire]
            for candidate in variants:
                names = {item["name"] for item in candidate["fields"]}
                if not {"schema_tag", "encoding", "payload_sha256"} <= names:
                    fail("CROSS_PROCESS_CODEC_MISSING", edge_id, edge_value["wire_type"])

    for key in ports_in:
        if incoming[key] != 1:
            fail("INPUT_PRODUCER_COUNT", ".".join(key), str(incoming[key]))
    for key in ports_out:
        if outgoing[key] == 0 and not nodes[key[0]]["terminal"]:
            fail("OUTPUT_UNCONSUMED", ".".join(key), "no consumer")

    queue = collections.deque(sorted(node for node, degree in indegree.items() if degree == 0))
    ordered = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for target in sorted(graph[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(ordered) != len(nodes):
        fail("GRAPH_CYCLE", "nodes", "topological sort incomplete")

    reachable = set()
    frontier = [node_id for node_id, node_value in nodes.items() if not node_value["inputs"]]
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(graph[current] - reachable)
    if reachable != set(nodes):
        fail("GRAPH_UNREACHABLE", "nodes", repr(sorted(set(nodes) - reachable)))

    if edges["E29_BUNDLE"]["from_node"] != "R02" or edges["E29_BUNDLE"]["to_node"] != "R13":
        fail("BUNDLE_PRODUCER_MISSING", "E29_BUNDLE", "must retain R02 bundle")
    if edges["E043_REGISTRY_SNAPSHOT"]["from_node"] != "R03" or edges["E043_REGISTRY_SNAPSHOT"]["to_node"] != "S01":
        fail("REGISTRY_EDGE_MISSING", "E043_REGISTRY_SNAPSHOT", "registration to snapshot")
    if edges["E029"]["from_node"] != "P09" or edges["E029"]["to_node"] != "C08":
        fail("OPEN_ORDER_INVALID", "E029", "open token must follow P08/P09")
    if edges["E024"]["lifetime"] != "CROSS_PROCESS":
        fail("CROSS_PROCESS_CODEC_MISSING", "E024", "receipt crosses process")
    expected_provider_path = {
        "E012": ("C02", "target", "C03", "target", "DerivedCronTargetV2"),
        "E014": ("C02", "target", "C04", "target", "DerivedCronTargetV2"),
        "E015": ("C03", "provider", "C04", "provider", "ResolvedProviderV2"),
        "E017": ("C04", "binding", "C05", "binding", "DerivedCronBindingV2"),
        "E021A": ("C04", "binding", "C06", "binding", "DerivedCronBindingV2"),
    }
    for edge_id, expected in expected_provider_path.items():
        edge = edges.get(edge_id)
        actual = None if edge is None else (
            edge["from_node"], edge["from_output"], edge["to_node"],
            edge["to_parameter"], edge["wire_type"],
        )
        if actual != expected:
            fail("PROVIDER_AUTHORITY_PATH_INVALID", edge_id, repr(actual))
    target_fields = {
        field["name"]: field["type"] for field in type_map["DerivedCronTargetV2"]["fields"]
    }
    if target_fields != {
        "binding_id": "UUID4", "config_file": "AbsPath", "home": "AbsPath",
        "jobs_file": "AbsPath", "profile": "ProfileName",
        "requested_provider": "String",
    }:
        fail("PRE_PROVIDER_AUTHORITY_FABRICATED", "DerivedCronTargetV2", repr(target_fields))
    binding_fields = {
        field["name"]: field["type"] for field in type_map["DerivedCronBindingV2"]["fields"]
    }
    if binding_fields != {
        "target": "DerivedCronTargetV2", "provider": "ResolvedProviderV2",
        "routes": "RouteSetV1",
    }:
        fail("FINAL_BINDING_INVALID", "DerivedCronBindingV2", repr(binding_fields))
    membership_transport = {
        "E017": ("C04", "binding", "C05", "binding", "DerivedCronBindingV2"),
        "E021": ("C05", "modules", "C06", "modules", "ModuleSetV1"),
        "E021A": ("C04", "binding", "C06", "binding", "DerivedCronBindingV2"),
        "E030": ("C06", "verification", "C08", "verification", "ChildVerificationV2"),
        "E033": ("C08", "activation_open", "A00", "controlled_open", "ActivationOpenV1"),
        "E036": ("A00", "admission_authority", "R01", "admission_authority", "ActivationOpenV1"),
    }
    for edge_id, expected in membership_transport.items():
        edge = edges.get(edge_id)
        actual = None if edge is None else (
            edge["from_node"], edge["from_output"], edge["to_node"],
            edge["to_parameter"], edge["wire_type"],
        )
        if actual != expected:
            fail("TYPED_MEMBERSHIP_TRANSPORT_INVALID", edge_id, repr(actual))
    verified = next(
        item for item in type_map["ChildVerificationV2"]["variants"]
        if item["tag"] == "VERIFIED"
    )
    verified_fields = {field["name"]: field["type"] for field in verified["fields"]}
    if verified_fields.get("binding") != "DerivedCronBindingV2" or verified_fields.get("modules") != "ModuleSetV1":
        fail("TYPED_MEMBERSHIP_TRANSPORT_INVALID", "ChildVerificationV2.VERIFIED", repr(verified_fields))
    activation_fields = {
        field["name"]: field["type"] for field in type_map["ActivationOpenV1"]["fields"]
    }
    if activation_fields.get("routes") != "RouteSetV1" or activation_fields.get("modules") != "ModuleSetV1":
        fail("TYPED_MEMBERSHIP_TRANSPORT_INVALID", "ActivationOpenV1", repr(activation_fields))
    # A digest is an observation nested in the typed set.  No node or edge may
    # substitute a naked digest/count for the member-bearing authority.
    if any(
        port["wire_type"] in {"SHA256", "Int"}
        and any(word in port["name"] for word in ("route", "module"))
        for node in nodes.values() for port in node["inputs"] + node["outputs"]
    ):
        fail("MEMBERSHIP_DIGEST_AS_AUTHORITY", "graph", "naked route/module scalar")
    provider_outputs = [
        (node_id, port["name"])
        for node_id, node in nodes.items()
        for port in node["outputs"] if port["wire_type"] == "ResolvedProviderV2"
    ]
    if provider_outputs != [("C03", "provider")]:
        fail("PROVIDER_AUTHORITY_DUPLICATE", "ResolvedProviderV2", repr(provider_outputs))
    expected_keyed_flows = {
        "E008": "KEYED_FAN_OUT", "E024": "KEYED_FAN_IN",
        "E029": "KEYED_FAN_OUT", "E032": "KEYED_FAN_IN",
    }
    if {
        edge_id: edges[edge_id]["flow"] for edge_id in expected_keyed_flows
    } != expected_keyed_flows:
        fail("HOST_MEMBER_FLOW_INVALID", "edges", "keyed fan-out/fan-in")
    membership_ports = {
        ("P02", "host_keys"): ("HostKeyV1", "NONEMPTY_MANY"),
        ("P03", "host_keys"): ("HostKeyV1", "NONEMPTY_MANY"),
        ("P03", "stopped_receipts"): ("HostReceiptV1", "NONEMPTY_MANY"),
        ("P04", "approved_host_keys"): ("HostKeyV1", "NONEMPTY_MANY"),
        ("P04", "approved_receipts"): ("HostReceiptV1", "NONEMPTY_MANY"),
        ("P05", "expectation"): ("ControlledLaunchExpectationV3", "NONEMPTY_MANY"),
        ("P06", "child_handle"): ("ChildHandleV1", "NONEMPTY_MANY"),
        ("P07", "decoded_verification"): ("ChildVerificationV2", "NONEMPTY_MANY"),
        ("P08", "accepted_children"): ("ChildVerificationV2", "NONEMPTY_MANY"),
        ("P09", "open_wire"): ("OpenTokenWireV1", "NONEMPTY_MANY"),
        ("C08", "activation_open"): ("ActivationOpenV1", "ONE"),
    }
    for key, expected in membership_ports.items():
        port = ports_in.get(key) or ports_out.get(key)
        if not port or (port["wire_type"], port["cardinality"]) != expected:
            fail("HOST_MEMBER_CONSERVATION_INVALID", ".".join(key), repr(expected))
    host_edges = {
        "E006_A_HOST_KEYS", "E006_B_APPROVED_KEYS", "E026",
        "E026_RECEIPTS", "E027", "E028_A_CHILDREN", "E029", "E032",
    }
    if not host_edges <= set(edges):
        fail("HOST_MEMBER_CONSERVATION_INVALID", "edges", repr(sorted(host_edges - set(edges))))
    for type_name in (
        "ActivationOpenV1", "ChildHandleV1", "ControlledLaunchExpectationV3",
        "OpenTokenWireV1",
    ):
        type_def = type_map[type_name]
        variants = type_def["variants"] if type_def["kind"] == "UNION" else [type_def]
        if any("child_key" not in {field["name"] for field in item["fields"]} for item in variants):
            fail("HOST_MEMBER_CONSERVATION_INVALID", type_name, "child_key")
    if "prior stages" in json.dumps(model, sort_keys=True).lower():
        fail("HIDDEN_INPUT", "model", "prior stages")
    return nodes, edges, ordered


def validate_conditions(model, type_map, locator_map):
    sorted_unique(model["conditions"], "conditions", key=lambda item: item["id"])
    conditions = index_unique(model["conditions"], "id", "conditions")
    for cid, item in conditions.items():
        require_keys(item, {"id", "owner", "result_type", "true_value", "false_value"}, cid)
        if item["owner"] not in locator_map:
            fail("SOURCE_REFERENCE_UNDEFINED", cid, item["owner"])
        type_def = type_map.get(item["result_type"])
        if not type_def or type_def["kind"] != "ENUM":
            fail("CONDITION_TYPE_INVALID", cid, item["result_type"])
        values = set(type_def["values"])
        if {item["true_value"], item["false_value"]} - values:
            fail("CONDITION_VALUE_INVALID", cid, repr(values))
        if item["true_value"] == item["false_value"]:
            fail("CONDITION_VALUE_INVALID", cid, "equal branches")
    return conditions


def validate_manifests(model, locator_map, conditions, source_oracle):
    sorted_unique(model["manifests"], "manifests", key=lambda item: item["id"])
    manifests = index_unique(model["manifests"], "id", "manifests")
    expected_manifest_ids = {
        key for key in source_oracle
        if key != "host_routes" and not key.startswith("_")
    }
    if set(manifests) != expected_manifest_ids:
        fail("MANIFEST_SET_MISMATCH", "manifests", repr(sorted(set(manifests) ^ expected_manifest_ids)))
    for mid, item in manifests.items():
        require_keys(item, {"id", "entity", "members", "expected_count"}, mid)
        sorted_unique(item["members"], mid + ".members", key=lambda member: member["key"])
        members = index_unique(item["members"], "key", mid)
        if set(members) != source_oracle[mid]:
            code = "MW_WRITER_SET_MISMATCH" if mid == "mw_writers" else "MANIFEST_SET_MISMATCH"
            fail(
                code, mid,
                "missing=" + repr(sorted(source_oracle[mid] - set(members)))
                + " extra=" + repr(sorted(set(members) - source_oracle[mid])),
            )
        if item["expected_count"] != len(members):
            fail("MANIFEST_COUNT_INVALID", mid, str(item["expected_count"]))
        for key, member in members.items():
            require_keys(member, {"key", "condition", "locators", "attributes"}, mid + "." + key)
            if member["condition"] != "ALWAYS" and member["condition"] not in conditions:
                fail("CONDITION_REFERENCE_UNDEFINED", mid + "." + key, member["condition"])
            sorted_unique(member["locators"], mid + "." + key + ".locators")
            if mid == "modules":
                expected_path = source_oracle["_module_paths"].get(key)
                if member["locators"] or member["attributes"].get("source_path") != expected_path:
                    fail("MODULE_SOURCE_PATH_MISMATCH", mid + "." + key, repr(expected_path))
            elif not member["locators"] or any(lid not in locator_map for lid in member["locators"]):
                fail("SOURCE_REFERENCE_UNDEFINED", mid + "." + key, "locators")
            if not isinstance(member["attributes"], dict):
                fail("MANIFEST_ATTRIBUTES_INVALID", mid + "." + key, "attributes")
    host_members = {item["key"]: item for item in manifests["hosts"]["members"]}
    for host, routes in source_oracle["host_routes"].items():
        if set(host_members[host]["attributes"].get("routes", [])) != routes:
            fail("HOST_ROUTE_SET_MISMATCH", host, repr(sorted(routes)))
    route_members = {item["key"]: item for item in manifests["routes"]["members"]}
    if route_members["GATEWAY_CHRONOS_HTTP"]["condition"] != "cond_gateway_chronos_http":
        fail("ROUTE_CONDITION_MISSING", "GATEWAY_CHRONOS_HTTP", "gateway predicate")
    if route_members["DASHBOARD_CHRONOS_HTTP"]["condition"] != "cond_dashboard_chronos_http":
        fail("ROUTE_CONDITION_MISSING", "DASHBOARD_CHRONOS_HTTP", "dashboard predicate")
    if "CHRONOS_SYNC" in route_members:
        fail("ROUTE_NOT_SOURCE_REACHABLE", "CHRONOS_SYNC", "no pinned source entrypoint")
    provider_instances = [
        item["attributes"].get("instance") for item in manifests["providers"]["members"]
    ]
    if len(provider_instances) != len(set(provider_instances)):
        fail("PROVIDER_NOT_INJECTIVE", "providers", "shared instance")
    mw = manifests["mw_writers"]["members"]
    roles = collections.Counter(item["attributes"].get("role") for item in mw)
    if roles != {"DIRECT_WRITER": 7, "CALLER": 2}:
        fail("MW_WRITER_SET_MISMATCH", "mw_writers", repr(roles))
    module = {item["key"]: item for item in manifests["modules"]["members"]}
    if module["hermes_cli.cron_deployment"]["attributes"].get("provenance") != "BOOTSTRAP_EXTERNALLY_BOUND":
        fail("MODULE_FIXED_POINT_INVALID", "hermes_cli.cron_deployment", "bootstrap provenance")
    return manifests


def validate_matrices(model, type_map):
    sorted_unique(model["matrices"], "matrices", key=lambda item: item["id"])
    matrices = index_unique(model["matrices"], "id", "matrices")
    required = {
        "activation_product", "archive_product", "cleanup_shutdown_product",
        "http_cancellation_product", "http_host_membership_product", "managed_product",
        "prior17_regression", "route_enablement",
    }
    if set(matrices) != required:
        fail("MATRIX_SET_INVALID", "matrices", repr(sorted(set(matrices) ^ required)))
    for mid, matrix in matrices.items():
        require_keys(matrix, {"id", "result_type", "axes", "rows", "invalid"}, mid)
        result_type = type_map.get(matrix["result_type"])
        if not result_type or result_type["kind"] not in {"ENUM", "UNION"}:
            fail("MATRIX_RESULT_TYPE_INVALID", mid, matrix["result_type"])
        legal_statuses = set(result_type.get("values", [])) | {
            item["tag"] for item in result_type.get("variants", [])
        }
        axis_names = []
        values = []
        for axis in matrix["axes"]:
            require_keys(axis, {"name", "values"}, mid + ".axis")
            axis_names.append(axis["name"])
            sorted_unique(axis["values"], mid + "." + axis["name"])
            if not axis["values"]:
                fail("MATRIX_AXIS_EMPTY", mid, axis["name"])
            values.append(axis["values"])
        if len(axis_names) != len(set(axis_names)):
            fail("MATRIX_AXIS_DUPLICATE", mid, repr(axis_names))
        expected_keys = list(itertools.product(*values))
        actual_keys = []
        for row in matrix["rows"]:
            require_keys(row, {"key", "status", "reason", "nullability", "exit"}, mid)
            if len(row["key"]) != len(axis_names):
                fail("MATRIX_KEY_INVALID", mid, repr(row["key"]))
            actual_keys.append(tuple(row["key"]))
            if not isinstance(row["status"], str) or not row["status"]:
                fail("MATRIX_RESULT_INVALID", mid, "status")
            if row["reason"] is not None and (not isinstance(row["reason"], str) or not row["reason"]):
                fail("MATRIX_RESULT_INVALID", mid, "reason")
            if type(row["exit"]) is not int:
                fail("MATRIX_RESULT_INVALID", mid, "exit")
            if (
                not isinstance(row["nullability"], dict)
                or any(value not in {"ABSENT", "NULL", "NONNULL"} for value in row["nullability"].values())
            ):
                fail("MATRIX_RESULT_INVALID", mid, "nullability")
            if set(row["nullability"]) != MATRIX_FIELDS[mid]:
                fail("MATRIX_FIELD_SET_INVALID", mid, repr(sorted(row["nullability"])))
            if row["status"] != "INVALID" and row["status"] not in legal_statuses:
                fail("MATRIX_STATUS_UNDECLARED", mid, row["status"])
            if row["status"] == "INVALID" and (
                row["reason"] != "INVALID_COMPLEMENT" or row["exit"] != 2
            ):
                fail("MATRIX_INVALID_COMPLEMENT_BAD", mid, repr(row["key"]))
        if actual_keys != expected_keys or len(actual_keys) != len(set(actual_keys)):
            fail("MATRIX_NOT_TOTAL", mid, "Cartesian product mismatch")
        require_keys(matrix["invalid"], {"status", "reason", "exit"}, mid + ".invalid")
        if matrix["invalid"] != EXPECTED_MATRIX_INVALID[mid]:
            fail("MATRIX_INVALID_COMPLEMENT_BAD", mid, repr(matrix["invalid"]))
        if matrix["invalid"]["status"] in legal_statuses or matrix["invalid"]["exit"] == 0:
            fail("MATRIX_INVALID_COMPLEMENT_BAD", mid, "success/declared result")
        matrix_image = hashlib.sha256(json.dumps(
            {
                "result_type": matrix["result_type"], "axes": matrix["axes"],
                "rows": matrix["rows"], "invalid": matrix["invalid"],
            }, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        if matrix_image != EXPECTED_MATRIX_IMAGES_SHA256[mid]:
            fail("MATRIX_ROW_IMAGE_MISMATCH", mid, matrix_image)

    managed = matrices["managed_product"]
    for row in managed["rows"]:
        body, cleanup, output, delivery, finalization = row["key"]
        if row["status"] == "INVALID":
            continue
        if body == "INTENTIONAL_SILENCE" and output != "SAVED":
            fail("SILENCE_OUTPUT_UNSAVED", managed["id"], repr(row["key"]))
        if body == "INTENTIONAL_SILENCE" and delivery != "SUPPRESSED":
            fail("SILENCE_DELIVERY_INVALID", managed["id"], repr(row["key"]))
        if finalization == "FAILED" and row["status"] != "FINALIZATION_FAILED":
            fail("FINALIZATION_DOMINANCE_INVALID", managed["id"], repr(row["key"]))
        if body == "WHITESPACE_EMPTY" and row["status"] not in {
            "WHITESPACE_EMPTY", "FINALIZATION_FAILED", "CLEANUP_UNVERIFIED",
        }:
            fail("WHITESPACE_PRODUCT_INVALID", managed["id"], repr(row["key"]))
    if not any(
        row["status"] == "SHUTDOWN_INTERRUPTED"
        for row in matrices["cleanup_shutdown_product"]["rows"]
    ):
        fail("SHUTDOWN_ROW_MISSING", "cleanup_shutdown_product", "no shutdown")
    cancellation = matrices["http_cancellation_product"]
    expected_cancellation = {
        ("AFTER_WORKER_ENTRY", "RUNNING"): "REGISTRY_RETAINED",
        ("AFTER_WORKER_ENTRY", "EXITED"): "RELEASED_ONCE",
        ("BEFORE_WORKER_ENTRY", "NOT_STARTED"): "CLAIM_RETAINED_RELEASED_CONTEXT",
        ("NONE", "RUNNING"): "REGISTRY_RETAINED",
        ("NONE", "EXITED"): "RELEASED_ONCE",
        ("NONE", "NOT_STARTED"): "REGISTRY_RETAINED",
    }
    actual_cancellation = {
        tuple(row["key"]): row["status"]
        for row in cancellation["rows"] if row["status"] != "INVALID"
    }
    if actual_cancellation != expected_cancellation:
        fail("HTTP_CANCELLATION_PRODUCT_INVALID", cancellation["id"], "release ownership")
    membership = matrices["http_host_membership_product"]
    expected_membership = {
        "DUPLICATE": "REFUSED", "EXACT": "VERIFIED", "MISSING": "REFUSED",
        "SWAPPED": "REFUSED", "WRONG_RECIPIENT": "REFUSED",
    }
    if {row["key"][0]: row["status"] for row in membership["rows"]} != expected_membership:
        fail("HOST_MEMBER_CONSERVATION_INVALID", membership["id"], "membership product")
    if not any(
        row["status"] == "COMPLETE_NO_JOBS"
        and row["nullability"] == {
            "targets": "NONNULL", "store_results": "NONNULL", "error": "NULL",
        }
        and row["exit"] == 0
        for row in matrices["archive_product"]["rows"]
    ):
        fail("ARCHIVE_ZERO_SUCCESS_MISSING", "archive_product", "no zero-jobs success")
    prior = matrices["prior17_regression"]
    if {row["key"][0] for row in prior["rows"]} != PRIOR17:
        fail("PRIOR17_SET_MISMATCH", prior["id"], "family set")
    if any(row["status"] != "KILLED" or row["exit"] != 0 for row in prior["rows"]):
        fail("PRIOR17_SURVIVED", prior["id"], "non-killed row")
    return matrices


def validate_counts(model):
    counts = {
        "locators": len(model["locators"]),
        "types": len(model["types"]),
        "nodes": len(model["nodes"]),
        "edges": len(model["edges"]),
        "conditions": len(model["conditions"]),
        "manifests": len(model["manifests"]),
        "manifest_members": sum(len(item["members"]) for item in model["manifests"]),
        "matrix_rows": sum(len(item["rows"]) for item in model["matrices"]),
        "mutations": len(model["mutations"]),
    }
    if model["expected_counts"] != counts:
        fail("EXPECTED_COUNT_MISMATCH", "expected_counts", repr((model["expected_counts"], counts)))
    return counts


def clone(value):
    return json.loads(json.dumps(value))


def by_id(values, value_id):
    for item in values:
        if item.get("id") == value_id or item.get("name") == value_id:
            return item
    fail("MUTATION_TARGET_MISSING", value_id, "target")


def apply_mutation(model, operation):
    op = operation["op"]
    if op == "delete_type_field":
        target = by_id(model["types"], operation["type"])
        variant = next(item for item in target["variants"] if item["tag"] == operation["variant"])
        variant["fields"] = [item for item in variant["fields"] if item["name"] != operation["field"]]
    elif op == "reuse_provider_instance":
        manifest = by_id(model["manifests"], operation["manifest"])
        members = {item["key"]: item for item in manifest["members"]}
        members[operation["to"]]["attributes"]["instance"] = members[operation["from"]]["attributes"]["instance"]
    elif op == "delete_manifest_member":
        manifest = by_id(model["manifests"], operation["manifest"])
        manifest["members"] = [item for item in manifest["members"] if item["key"] != operation["key"]]
    elif op == "delete_edge":
        model["edges"] = [item for item in model["edges"] if item["id"] != operation["id"]]
    elif op == "change_edge_lifetime":
        by_id(model["edges"], operation["id"])["lifetime"] = operation["value"]
    elif op == "change_edge_wire":
        by_id(model["edges"], operation["id"])["wire_type"] = operation["value"]
    elif op == "change_locator_symbol":
        by_id(model["locators"], operation["id"])["symbol"] = operation["value"]
    elif op == "delete_matrix_row":
        matrix = by_id(model["matrices"], operation["matrix"])
        matrix["rows"] = [item for item in matrix["rows"] if item["key"] != operation["key"]]
    elif op == "delete_matrix_status":
        matrix = by_id(model["matrices"], operation["matrix"])
        matrix["rows"] = [item for item in matrix["rows"] if item["status"] != operation["status"]]
    elif op == "replace_matrix_row":
        matrix = by_id(model["matrices"], operation["matrix"])
        row = next(item for item in matrix["rows"] if item["key"] == operation["key"])
        for field in ("status", "reason", "exit", "nullability"):
            row[field] = clone(operation[field])
    elif op == "rewire_open_before_aggregate":
        by_id(model["edges"], operation["edge"])["from_node"] = operation["from_node"]
    elif op == "add_manifest_member":
        manifest = by_id(model["manifests"], operation["manifest"])
        manifest["members"].append({
            "key": operation["key"], "condition": "ALWAYS",
            "locators": ["h_provider"], "attributes": {"source_reachable": False},
        })
        manifest["members"].sort(key=lambda item: item["key"])
    elif op == "set_manifest_condition":
        manifest = by_id(model["manifests"], operation["manifest"])
        next(item for item in manifest["members"] if item["key"] == operation["key"])["condition"] = operation["condition"]
    else:
        fail("MUTATION_OPERATION_UNKNOWN", op, repr(operation))


def validate_mutations(model, locator_map, roots, oids, source_oracle, source_cache):
    sorted_unique(model["mutations"], "mutations", key=lambda item: item["id"])
    mutations = index_unique(model["mutations"], "id", "mutations")
    expected_ids = [f"N{index:02d}" for index in range(1, 23)]
    if list(mutations) != expected_ids:
        fail("MUTATION_SET_INVALID", "mutations", repr(list(mutations)))
    killed = 0
    for index, mid in enumerate(expected_ids):
        item = mutations[mid]
        require_keys(
            item,
            {"id", "predicate", "target_ids", "operation", "expected_failure"},
            mid,
        )
        if item["predicate"] != PREDICATES[index]:
            fail("MUTATION_PREDICATE_INVALID", mid, item["predicate"])
        sorted_unique(item["target_ids"], mid + ".target_ids")
        if not item["target_ids"]:
            fail("MUTATION_TARGET_MISSING", mid, "empty target_ids")
        require_keys(item["expected_failure"], {"code", "owner", "before_effect"}, mid)
        expected = item["expected_failure"]
        if not isinstance(expected["code"], str) or not expected["code"]:
            fail("MUTATION_EXPECTATION_INVALID", mid, expected["code"])
        if expected["owner"] not in locator_map or expected["before_effect"] is not True:
            fail("MUTATION_EXPECTATION_INVALID", mid, "owner/before_effect")
        mutated = clone(model)
        apply_mutation(mutated, item["operation"])
        try:
            validate_candidate(
                mutated, roots, oids, source_oracle=source_oracle,
                source_cache=source_cache,
                validate_declared_counts=False,
            )
        except ModelFailure as exc:
            actual = exc.code
        else:
            actual = None
        if actual != expected["code"]:
            fail("MUTATION_SURVIVED", mid, repr((expected["code"], actual)))
        killed += 1
    return killed


def validate_source_fixed_point(manifests, source_cache, source_oracle):
    graph_counts = source_oracle.get("_python_graph_counts", {})
    if (
        set(graph_counts) != {"modules", "import_edges", "call_edges"}
        or any(not isinstance(value, int) or value <= 0 for value in graph_counts.values())
    ):
        fail("SOURCE_GRAPH_INCOMPLETE", "python", repr(graph_counts))
    script_graph_count = source_oracle.get("_script_graph_count")
    if not isinstance(script_graph_count, int) or script_graph_count <= 0:
        fail("SOURCE_GRAPH_INCOMPLETE", "typescript_shell", repr(script_graph_count))
    for manifest_id, expected in source_oracle.items():
        if manifest_id == "host_routes" or manifest_id.startswith("_"):
            continue
        actual = {item["key"] for item in manifests[manifest_id]["members"]}
        if actual != expected:
            fail("SOURCE_FIXED_POINT_MISMATCH", manifest_id, repr(sorted(actual ^ expected)))
        for item in manifests[manifest_id]["members"]:
            for locator_id in item["locators"]:
                if locator_id not in source_cache:
                    fail("SOURCE_FIXED_POINT_MISMATCH", manifest_id, locator_id)

    hosts = {item["key"]: item for item in manifests["hosts"]["members"]}
    routes = set()
    forward_pairs = set()
    for host, expected_routes in source_oracle["host_routes"].items():
        actual_routes = set(hosts[host]["attributes"]["routes"])
        if actual_routes != expected_routes:
            fail("SOURCE_FIXED_POINT_MISMATCH", host, "forward route set")
        for route in actual_routes:
            forward_pairs.add((host, route))
            routes.add(route)
    reverse_pairs = {
        (host, route)
        for route in source_oracle["routes"]
        for host, host_routes in source_oracle["host_routes"].items()
        if route in host_routes
    }
    if forward_pairs != reverse_pairs or routes != source_oracle["routes"]:
        fail("SOURCE_FIXED_POINT_MISMATCH", "host_route", "forward/reverse disagreement")

    module_paths = {
        item["key"]: item["attributes"].get("source_path")
        for item in manifests["modules"]["members"]
    }
    if module_paths != source_oracle["_module_paths"]:
        fail("SOURCE_FIXED_POINT_MISMATCH", "modules", "module set")
    if any(not path for path in module_paths.values()):
        fail("SOURCE_FIXED_POINT_MISMATCH", "modules", "unproved member")
    return {
        "host_route_edges": len(forward_pairs),
        "module_members": len(module_paths),
        "python_modules_scanned": graph_counts["modules"],
        "python_import_edges": graph_counts["import_edges"],
        "python_call_edges": graph_counts["call_edges"],
        "typescript_shell_relations": script_graph_count,
    }


def validate_candidate(
    model, roots, oids, source_oracle=None, source_cache=None,
    validate_declared_counts=True,
):
    require_keys(model, MODEL_KEYS, "model")
    if model["schema"] != "sys1030-r4-ownership-model-v1":
        fail("MODEL_SCHEMA_INVALID", "model", model["schema"])
    sorted_unique(model["locators"], "locators", key=lambda item: item["id"])
    locator_map = index_unique(model["locators"], "id", "locators")
    source_cache = (
        load_sources(model, roots, oids) if source_cache is None
        else validate_cached_sources(model, source_cache)
    )
    if source_oracle is None:
        source_oracle = derive_source_oracle(roots, oids)
    type_map = validate_types(model)
    validate_typed_membership_sets(type_map, source_oracle)
    nodes, edges, topological = validate_graph(model, type_map, locator_map)
    conditions = validate_conditions(model, type_map, locator_map)
    manifests = validate_manifests(model, locator_map, conditions, source_oracle)
    matrices = validate_matrices(model, type_map)
    counts = validate_counts(model) if validate_declared_counts else None
    fixed_point = validate_source_fixed_point(manifests, source_cache, source_oracle)
    return {
        "locator_map": locator_map,
        "source_cache": source_cache,
        "type_map": type_map,
        "nodes": nodes,
        "edges": edges,
        "topological": topological,
        "manifests": manifests,
        "matrices": matrices,
        "counts": counts,
        "fixed_point": fixed_point,
    }


def validate_validator_falsifiers(model, roots, oids, source_oracle, source_cache):
    lifetime_mutant = clone(model)
    by_id(lifetime_mutant["edges"], "E024")["lifetime"] = "PROCESS"
    try:
        validate_candidate(
            lifetime_mutant, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache,
            validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "CROSS_PROCESS_CODEC_MISSING":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "E024", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "E024", "PROCESS lifetime")

    matrix_mutant = clone(model)
    row = by_id(matrix_mutant["matrices"], "activation_product")["rows"][0]
    row["status"] = "INVENTED_STATUS"
    row["reason"] = "INVENTED_REASON"
    row["exit"] = 99
    row["nullability"] = {"invented_field": "NONNULL"}
    try:
        validate_candidate(
            matrix_mutant, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache,
            validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code not in {"MATRIX_FIELD_SET_INVALID", "MATRIX_STATUS_UNDECLARED"}:
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "activation_product", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "activation_product", "invented result")

    legal_swap = clone(model)
    matrix = by_id(legal_swap["matrices"], "activation_product")
    row = next(item for item in matrix["rows"] if item["key"] == [
        "PRESENT", "AVAILABLE", "MATCH",
    ])
    row.update({
        "status": "REFUSED_CLOSED", "reason": "EXPECTATION_MISMATCH",
        "exit": 77, "nullability": {"activation": "NULL"},
    })
    try:
        validate_candidate(
            legal_swap, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "MATRIX_ROW_IMAGE_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "activation_product", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "activation_product", "legal row swap")

    invalid_success = clone(model)
    by_id(invalid_success["matrices"], "activation_product")["invalid"] = {
        "status": "ORDINARY_OPEN", "reason": None, "exit": 0,
    }
    try:
        validate_candidate(
            invalid_success, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "MATRIX_INVALID_COMPLEMENT_BAD":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "activation_product.invalid", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "activation_product.invalid", "success")

    fabricated_provider = clone(model)
    target = by_id(fabricated_provider["types"], "DerivedCronTargetV2")
    target["fields"].append({
        "name": "provider", "type": "ResolvedProviderV2",
        "presence": "REQUIRED", "nullable": False,
    })
    try:
        validate_candidate(
            fabricated_provider, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "PRE_PROVIDER_AUTHORITY_FABRICATED":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "DerivedCronTargetV2", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "DerivedCronTargetV2", "nested provider")

    swapped_route = clone(model)
    route_enum = by_id(swapped_route["types"], "RouteV1")
    route_enum["values"] = sorted(
        (set(route_enum["values"]) - {route_enum["values"][0]}) | {"CHRONOS_SYNC"}
    )
    try:
        validate_candidate(
            swapped_route, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "ROUTE_TYPED_MEMBERSHIP_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "RouteV1", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "RouteV1", "same-cardinality route swap")

    swapped_module = clone(model)
    module_enum = by_id(swapped_module["types"], "ModuleNameV1")
    module_enum["values"] = sorted(
        (set(module_enum["values"]) - {module_enum["values"][0]})
        | {"unreviewed.shadow_owner"}
    )
    try:
        validate_candidate(
            swapped_module, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "MODULE_TYPED_MEMBERSHIP_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "ModuleNameV1", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "ModuleNameV1", "same-cardinality module swap")

    swapped_host_route = clone(model)
    host_manifest = by_id(swapped_host_route["manifests"], "hosts")
    host = next(item for item in host_manifest["members"] if item["key"] == "H1_GATEWAY")
    host["attributes"]["routes"] = sorted(
        (set(host["attributes"]["routes"]) - {"BUILTIN_TICK"}) | {"CANARY"}
    )
    try:
        validate_candidate(
            swapped_host_route, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "HOST_ROUTE_SET_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "H1_GATEWAY", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "H1_GATEWAY", "same-count route substitution")

    # Omit one module chosen by the all-tree authority-definition scan, not by
    # an authored expected-member list. Exact source/model equality must fail.
    discovered = sorted(source_oracle["_authority_modules"])
    if not discovered:
        fail("VALIDATOR_FALSIFIER_SETUP", "modules", "no discovered authority")
    omitted_authority = clone(model)
    manifest = by_id(omitted_authority["manifests"], "modules")
    chosen = next(
        (name for name in discovered if any(row["key"] == name for row in manifest["members"])),
        None,
    )
    if chosen is None:
        fail("VALIDATOR_FALSIFIER_SETUP", "modules", "authority absent before mutation")
    manifest["members"] = [row for row in manifest["members"] if row["key"] != chosen]
    manifest["expected_count"] -= 1
    try:
        validate_candidate(
            omitted_authority, roots, oids, source_oracle=source_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "MANIFEST_SET_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", chosen, exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", chosen, "source-discovered authority omission")

    # Simulate the exact oracle postcondition produced if the all-tree writer
    # classifier discovers a tenth MarketWatch writer. The unchanged model must
    # reject it; current-member intersection can never satisfy this control.
    extra_writer_oracle = dict(source_oracle)
    extra_writer_oracle["mw_writers"] = set(source_oracle["mw_writers"]) | {
        "synthetic/new_jobs_writer.py"
    }
    try:
        validate_candidate(
            model, roots, oids, source_oracle=extra_writer_oracle,
            source_cache=source_cache, validate_declared_counts=False,
        )
    except ModelFailure as exc:
        if exc.code != "MW_WRITER_SET_MISMATCH":
            fail("VALIDATOR_FALSIFIER_WRONG_FAILURE", "synthetic/new_jobs_writer.py", exc.code)
    else:
        fail("VALIDATOR_FALSIFIER_SURVIVED", "synthetic/new_jobs_writer.py", "extra writer")

    host_mutants = []
    omitted = clone(model)
    omitted["edges"] = [edge for edge in omitted["edges"] if edge["id"] != "E006_A_HOST_KEYS"]
    host_mutants.append(("OMITTED_HOST", omitted))
    duplicate = clone(model)
    node = by_id(duplicate["nodes"], "P07")
    next(port for port in node["outputs"] if port["name"] == "decoded_verification")["cardinality"] = "ONE"
    host_mutants.append(("DUPLICATE_COLLAPSED", duplicate))
    swapped = clone(model)
    matrix = by_id(swapped["matrices"], "http_host_membership_product")
    next(row for row in matrix["rows"] if row["key"] == ["SWAPPED"])["status"] = "VERIFIED"
    host_mutants.append(("SWAPPED_CHILD", swapped))
    recipient = clone(model)
    token = by_id(recipient["types"], "OpenTokenWireV1")
    open_variant = next(item for item in token["variants"] if item["tag"] == "OPEN")
    open_variant["fields"] = [field for field in open_variant["fields"] if field["name"] != "child_key"]
    host_mutants.append(("WRONG_RECIPIENT", recipient))
    unmarked = clone(model)
    by_id(unmarked["edges"], "E008")["flow"] = "DIRECT"
    host_mutants.append(("UNMARKED_FAN_OUT", unmarked))
    wrong_direction = clone(model)
    by_id(wrong_direction["edges"], "E024")["flow"] = "KEYED_FAN_OUT"
    host_mutants.append(("WRONG_FAN_IN_DIRECTION", wrong_direction))
    local_many = clone(model)
    node = by_id(local_many["nodes"], "C08")
    next(port for port in node["outputs"] if port["name"] == "activation_open")["cardinality"] = "NONEMPTY_MANY"
    host_mutants.append(("LOCAL_CHILD_EMITS_COLLECTION", local_many))
    for name, mutant in host_mutants:
        try:
            validate_candidate(
                mutant, roots, oids, source_oracle=source_oracle,
                source_cache=source_cache,
                validate_declared_counts=False,
            )
        except ModelFailure:
            continue
        fail("VALIDATOR_FALSIFIER_SURVIVED", name, "host member conservation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--hermes-root", required=True)
    parser.add_argument("--hermes-oid", required=True)
    parser.add_argument("--marketwatch-root", required=True)
    parser.add_argument("--marketwatch-oid", required=True)
    args = parser.parse_args()

    try:
        if not H40_RE.fullmatch(args.hermes_oid) or not H40_RE.fullmatch(args.marketwatch_oid):
            fail("OID_INVALID", "arguments", "expected lowercase H40")
        model_path = pathlib.Path(args.model)
        with model_path.open("r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
        if not raw.endswith("\n") or raw.endswith("\n\n"):
            fail("MODEL_ENCODING_INVALID", str(model_path), "requires one final LF")
        model = json.loads(raw, object_pairs_hook=duplicate_key_hook)
        roots = {
            "HERMES": pathlib.Path(args.hermes_root).resolve(),
            "MARKETWATCH": pathlib.Path(args.marketwatch_root).resolve(),
        }
        oids = {"HERMES": args.hermes_oid, "MARKETWATCH": args.marketwatch_oid}
        git(roots["HERMES"], "cat-file", "-e", args.hermes_oid + "^{commit}")
        git(roots["MARKETWATCH"], "cat-file", "-e", args.marketwatch_oid + "^{commit}")

        source_oracle = derive_source_oracle(roots, oids)
        validated = validate_candidate(model, roots, oids, source_oracle=source_oracle)
        validate_validator_falsifiers(
            model, roots, oids, source_oracle, validated["source_cache"],
        )
        killed = validate_mutations(
            model, validated["locator_map"], roots, oids, source_oracle,
            validated["source_cache"],
        )
        counts = validated["counts"]
        topological = validated["topological"]
        source_cache = validated["source_cache"]
        fixed_point = validated["fixed_point"]
        counts["topological_nodes"] = len(topological)
        counts["source_locators"] = len(source_cache)
        counts["fixed_point_host_route_edges"] = fixed_point["host_route_edges"]
        counts["fixed_point_module_members"] = fixed_point["module_members"]
        counts["source_python_modules_scanned"] = fixed_point["python_modules_scanned"]
        counts["source_python_import_edges"] = fixed_point["python_import_edges"]
        counts["source_python_call_edges"] = fixed_point["python_call_edges"]
        counts["source_typescript_shell_relations"] = fixed_point["typescript_shell_relations"]
        counts["prior17_mutations"] = len(PRIOR17)
        output = {
            "schema": "sys1030-r4-validation-result-v1",
            "status": "PASS",
            "counts": counts,
            "killed_mutations": killed,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        raise SystemExit(0)
    except ModelFailure as exc:
        output = {
            "schema": "sys1030-r4-validation-result-v1",
            "status": "FAIL",
            "code": exc.code,
            "object_id": exc.object_id,
            "detail": exc.detail,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        output = {
            "schema": "sys1030-r4-validation-result-v1",
            "status": "FAIL",
            "code": "VALIDATOR_INPUT_FAILURE",
            "object_id": "validator",
            "detail": str(exc),
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
