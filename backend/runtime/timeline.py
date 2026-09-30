"""Execution timeline: concise, visual, metadata-only.

Maps audit events + state history onto a fixed step vocabulary. Never exposes
model chain-of-thought — only actions, reasons, policy decisions, timestamps.
"""
from __future__ import annotations


_STEP_ORDER = [
    ("user_request", "USER REQUEST"),
    ("intent_classified", "PLANNER"),
    ("memory_read", "MEMORY RETRIEVAL"),
    ("agent_started", "AGENT"),
    ("tool", "TOOL"),
    ("policy", "POLICY CHECK"),
    ("approval", "APPROVAL"),
    ("agent_finished", "RESULT"),
    ("done", "COMPLETED"),
]

_ACTION_STEP = {
    "intent_classified": "intent_classified",
    "memory_read": "memory_read",
    "agent_started": "agent_started",
    "agent_finished": "agent_finished",
    "approval_requested": "approval",
    "approval_granted": "approval",
    "approval_denied": "approval",
    "error": "error",
}


def _step_for(action: str, permission: str) -> str:
    if action in _ACTION_STEP:
        return _ACTION_STEP[action]
    if "." in action and not action.startswith("approval"):
        return "policy" if permission else "tool"
    return "tool"


def build_timeline(execution, events: list) -> list[dict]:
    steps: list[dict] = [{
        "key": "user_request", "label": "USER REQUEST",
        "detail": (execution.user_request or "")[:300],
        "timestamp": str(execution.created_at), "status": "ok",
    }]
    for e in sorted(events, key=lambda x: str(x.timestamp)):
        action = e.action or ""
        if action in ("memory_created",):
            continue  # bookkeeping, not a demo step
        step = _step_for(action, e.permission or "")
        label = "FAILED" if step == "error" else dict(_STEP_ORDER).get(step, step.upper())
        status = {"ok": "ok", "checked": "ok", "started": "running",
                  "pending": "waiting", "denied": "denied",
                  "failed": "failed", "approved": "approved"}.get(e.status, e.status or "ok")
        detail = " ".join(x for x in [e.agent, e.resource, e.reason] if x)[:300]
        step_obj = {"key": step, "label": label, "detail": detail,
                    "timestamp": str(e.timestamp), "status": status,
                    "permission": e.permission or None}
        # Collapse consecutive benign duplicates (e.g. policy checked+executed)
        # so the demo timeline reads as one step per action.
        prev = steps[-1] if steps else None
        if (prev is not None and prev["key"] == step and
                prev.get("permission") == step_obj.get("permission") and
                prev["status"] in ("ok", "checked", "running") and
                status in ("ok", "checked", "running")):
            prev["detail"] = (prev["detail"] + " | " + detail)[:300]
            prev["timestamp"] = step_obj["timestamp"]
            continue
        steps.append(step_obj)
    final = (execution.state or "").upper() if hasattr(execution.state, "upper") \
        else execution.state.value
    steps.append({"key": "done",
                  "label": "COMPLETED" if final == "COMPLETED" else final,
                  "detail": (execution.result or execution.error or "")[:300],
                  "timestamp": str(execution.updated_at), "status": "ok"
                  if final == "COMPLETED" else ("waiting" if "WAITING" in final else "failed")})
    return steps
