"""Clean stub tools with real interfaces: github, web, calendar, notes, email.

Each exposes SPEC + async execute(). Stubs return honest 'not configured'
results instead of fake data, except notes/calendar which work locally.
"""
from __future__ import annotations

from tools.schemas import RiskLevel, ToolResult, ToolSpec

GITHUB_SPEC = ToolSpec(name="github", description="GitHub read/branch/commit (stub without token)",
                       required_permissions=["github:read", "github:write"], risk_level=RiskLevel.MEDIUM,
                       kind="stub")
WEB_SPEC = ToolSpec(name="web", description="Web search (stub without API key)",
                    required_permissions=["web:search"], risk_level=RiskLevel.LOW, kind="stub")
CALENDAR_SPEC = ToolSpec(name="calendar", description="Local calendar (MVP in-memory + file-free)",
                         required_permissions=["calendar:read", "calendar:write"], risk_level=RiskLevel.LOW,
                         kind="demo")
NOTES_SPEC = ToolSpec(name="notes", description="Local notes store",
                      required_permissions=["notes:read", "notes:write"], risk_level=RiskLevel.LOW,
                      kind="demo")
EMAIL_SPEC = ToolSpec(name="email", description="Email draft/send (send gated by approval)",
                      required_permissions=["email:read", "email:send"], risk_level=RiskLevel.HIGH,
                      kind="demo")


def ensure_demo(events: list[dict], notes: list[dict]) -> dict[str, int]:
    """Idempotent in-process demo seeding (used when DEMO_MODE=true)."""
    added = {"events": 0, "notes": 0}
    have_events = {e.get("id") for e in _events}
    for e in events:
        if e.get("id") not in have_events:
            _events.append(dict(e))
            added["events"] += 1
    have_notes = {n.get("id") for n in _notes}
    for n in notes:
        if n.get("id") not in have_notes:
            _notes.append(dict(n))
            added["notes"] += 1
    return added

_notes: list[dict] = [
    {"id": "n1", "title": "AETHER direction", "body": "Memory, skills, agents, tools, policy, audit."},
]
_events: list[dict] = [
    {"id": "e1", "title": "Research meeting", "when": "tomorrow 10:00",
     "attendees": ["research group"], "notes": "Q3 results review"},
]
_drafts: list[dict] = []
_sent: list[dict] = []


async def github_execute(action: str, args: dict, resource: str) -> ToolResult:
    if action == "read":
        return ToolResult(ok=True, output={"repo": resource, "info": "GitHub stub: connect GITHUB_TOKEN for live data."})
    if action == "branch":
        return ToolResult(ok=True, output={"branch": args.get("name", "aether/work"), "stub": True})
    return ToolResult(ok=False, error="GitHub stub: only read/branch in MVP without credentials")


async def web_execute(action: str, args: dict, resource: str) -> ToolResult:
    q = args.get("query", resource)
    return ToolResult(ok=True, output={"query": q, "results": [],
        "note": "Web search stub: configure SERPER_API_KEY for live results."})


async def calendar_execute(action: str, args: dict, resource: str) -> ToolResult:
    if action == "read":
        return ToolResult(ok=True, output={"events": _events})
    if action == "create":
        ev = {"id": args.get("id") or f"e{len(_events)+1}", "title": args.get("title", "Untitled"),
              "when": args.get("when", ""), "attendees": args.get("attendees", [])}
        if "notes" in args:
            ev["notes"] = args["notes"]
        _events.append(ev)
        return ToolResult(ok=True, output=ev)
    if action == "delete":
        _events[:] = [e for e in _events if e["id"] != args.get("id")]
        return ToolResult(ok=True, output={"deleted": args.get("id")})
    return ToolResult(ok=False, error=f"Unknown calendar action: {action}")


async def notes_execute(action: str, args: dict, resource: str) -> ToolResult:
    if action == "read":
        return ToolResult(ok=True, output={"notes": _notes})
    if action == "write":
        n = {"id": args.get("id") or f"n{len(_notes)+1}", "title": args.get("title", "Note"),
             "body": args.get("body", "")}
        _notes.append(n)
        return ToolResult(ok=True, output=n)
    return ToolResult(ok=False, error=f"Unknown notes action: {action}")


async def email_execute(action: str, args: dict, resource: str) -> ToolResult:
    if action == "draft":
        d = {"id": f"d{len(_drafts)+1}", "to": args.get("to", []),
             "subject": args.get("subject", ""), "body": args.get("body", "")}
        _drafts.append(d)
        return ToolResult(ok=True, output=d)
    if action == "send":
        m = {"to": args.get("to", []), "subject": args.get("subject", ""),
             "body": args.get("body", "")[:2000]}
        _sent.append(m)
        return ToolResult(ok=True, output={"sent": m, "note": "MVP outbox (no SMTP configured)"})
    if action == "read":
        return ToolResult(ok=True, output={"drafts": _drafts, "sent": _sent})
    return ToolResult(ok=False, error=f"Unknown email action: {action}")
