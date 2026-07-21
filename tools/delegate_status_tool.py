#!/usr/bin/env python3
"""delegate_status tool — real-time subagent visibility (SYS-2780).
Exposes list_active_subagents() to the agent so it can monitor
delegate_task subagent progress with facts, not guesses.

Quality goal: Zero blind-spawns. Agent always has factual subagent status
(subagent_id, uptime_seconds, tool_count, status) within 10s of spawn.
"""
import time
from typing import Any, Dict, List

from tools.delegate_tool import list_active_subagents


def delegate_status() -> Dict[str, Any]:
    """Return live status of all running delegate_task subagents.

    Each subagent record includes: subagent_id, goal (truncated), status,
    started_at, uptime_seconds, tool_count, model, depth.

    Use this instead of guessing subagent state. Poll every 10-15s during
    calibration panel sequential spawns.

    Quality-first: never fabricate timeout numbers. Read the facts.
    """
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
            "model": r.get("model", "?"),
            "depth": r.get("depth", 0),
        })

    return result
