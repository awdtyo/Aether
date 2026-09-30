"""Clearly-marked demo data only. No real personal information here."""
from __future__ import annotations

DEMO_SOURCE = "demo-seed"

DEMO_MEMORIES = [
    ("PROJECT", "Demo project: AETHER hackathon build — FastAPI backend, React command center, policy-gated tools.", 0.95),
    ("GOAL", "Demo goal: deliver a polished live demo of the meeting-preparation and approval workflows.", 0.9),
    ("DECISION", "Demo decision: the team chose React + Vite for the AETHER frontend.", 0.9),
    ("PREFERENCE", "Demo preference: concise briefs with Objective, Background, Key points, Open questions, Next actions.", 0.85),
    ("FACT", "Demo fact: the research group meets weekly to review experiment results.", 0.8),
    ("EXPERIENCE", "Demo experience: last dry-run showed approvals are the most compelling live moment.", 0.75),
]

DEMO_EVENTS = [
    {"id": "demo-e1", "title": "Research meeting (Q3 results review)",
     "when": "tomorrow 10:00", "attendees": ["research group"],
     "notes": "Demo event seeded for the hackathon walkthrough."},
    {"id": "demo-e2", "title": "Demo dry-run",
     "when": "today 16:00", "attendees": ["demo crew"],
     "notes": "Demo event seeded for the hackathon walkthrough."},
]

DEMO_NOTES = [
    {"id": "demo-n1", "title": "Demo research summary",
     "body": "Seeded note: Q3 experiments beat baseline on recall; open question is latency at scale."},
]
