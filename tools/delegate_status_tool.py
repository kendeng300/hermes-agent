#!/usr/bin/env python3
"""delegate_status tool — real-time subagent visibility (SYS-2780).
Exposes list_active_subagents() to the agent so it can monitor
delegate_task subagent progress with facts, not guesses.

Quality goal: Zero blind-spawns. Agent always has factual subagent status
(subagent_id, uptime_seconds, tool_count, last_tool, api_call_count,
max_iterations, current_tool, budget_used, stale_count, status) within 10s of spawn.
"""
import time
from typing import Any, Dict

from tools.delegate_tool import list_active_subagents


DELEGATE_STATUS_SCHEMA = {
    "name": "delegate_status",
    "description": "Return live status of all running delegate_task subagents. Each record includes subagent_id, goal (truncated to 120 chars), status, uptime_seconds, tool_count, last_tool, api_call_count, max_iterations, current_tool, budget_used, stale_count, model, depth. Use this instead of guessing subagent state. Poll every 10-15s during calibration panel sequential spawns.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def _build_response() -> Dict[str, Any]:
    """Build the delegate_status response from live registry data."""
    records = list_active_subagents()
    now = time.time()
    result: Dict[str, Any] = {"active_count": len(records), "subagents": []}

    for r in records:
        started = r.get("started_at", 0)
        uptime = now - started if started else 0
        result["subagents"].append({
            "subagent_id": r.get("subagent_id", "?"),
            "goal": (r.get("goal", "") or "")[:120],
            "status": r.get("status", "unknown"),
            "started_at": started,
            "uptime_seconds": round(uptime, 1),
            "tool_count": r.get("tool_count", 0),
            "last_tool": r.get("last_tool", ""),
            "api_call_count": r.get("api_call_count", 0),
            "max_iterations": r.get("max_iterations", 0),
            "current_tool": r.get("current_tool", ""),
            "budget_used": r.get("budget_used", 0),
            "stale_count": r.get("stale_count", 0),
            "model": r.get("model", "?"),
            "depth": r.get("depth", 0),
        })

    return result


def delegate_status(**kw) -> str:
    """Return live status of all running delegate_task subagents.

    Each subagent record includes: subagent_id, goal (truncated), status,
    started_at, uptime_seconds, tool_count, last_tool, api_call_count,
    max_iterations, current_tool, budget_used, stale_count, model, depth.

    Use this instead of guessing subagent state. Poll every 10-15s during
    calibration panel sequential spawns.

    Quality-first: never fabricate timeout numbers. Read the facts.
    """
    import json
    return json.dumps(_build_response(), indent=2, default=str)


# ── Tool Registration ────────────────────────────────────────────────
from tools.registry import registry as _registry

_registry.register(
    name="delegate_status",
    toolset="delegation",
    schema=DELEGATE_STATUS_SCHEMA,
    handler=delegate_status,
    emoji="📊",
)
