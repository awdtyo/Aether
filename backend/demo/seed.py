"""One-command demo seeding against a running backend. No credentials needed.

Usage:
    python -m backend.demo.seed [--base http://localhost:8000]

Uses only stdlib (urllib). Safe to re-run: existing demo-seed memories are
cleared first; calendar/notes are deduplicated by id.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("AETHER_API_BASE", "http://localhost:8000")


def _req(method: str, path: str, body: dict | None = None):
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(base: str = BASE) -> None:
    global BASE
    BASE = base
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    from demo.seed_data import DEMO_EVENTS, DEMO_MEMORIES, DEMO_NOTES, DEMO_SOURCE

    mems = _req("GET", "/api/memory?limit=200")
    cleared = 0
    for m in mems:
        if m.get("source") == DEMO_SOURCE:
            _req("DELETE", f"/api/memory/{m['id']}")
            cleared += 1
    created = 0
    for mtype, content, conf in DEMO_MEMORIES:
        _req("POST", "/api/memory",
             {"type": mtype, "content": content, "source": DEMO_SOURCE, "confidence": conf})
        created += 1
    cal = _req("POST", "/api/tools/calendar/call",
               {"action": "read", "reason": "demo seed check"})
    existing = {e.get("id") for e in (cal.get("result") or {}).get("output", {}).get("events", [])}
    events = sum(1 for e in DEMO_EVENTS if e["id"] not in existing
                 and _req("POST", "/api/tools/calendar/call",
                          {"action": "create", "args": e, "reason": "demo seed"}))
    notes = _req("POST", "/api/tools/notes/call", {"action": "read", "reason": "demo seed check"})
    have = {n.get("id") for n in (notes.get("result") or {}).get("output", {}).get("notes", [])}
    added_notes = 0
    for n in DEMO_NOTES:
        if n["id"] not in have:
            _req("POST", "/api/tools/notes/call",
                 {"action": "write",
                  "args": {"id": n["id"], "title": n["title"], "body": n["body"]},
                  "reason": "demo seed"})
            added_notes += 1
    print(f"demo seed done: memories cleared={cleared} created={created} "
          f"events={events} notes={added_notes}")


if __name__ == "__main__":
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else BASE
    main(base)
