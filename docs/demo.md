# AETHER hackathon demo script (~5 minutes)

> Backend: `cd backend && python -m uvicorn main:app --port 8000`
> Frontend: `cd frontend && npm install && npm run dev` → http://localhost:5173
> Optional zero-credential setup: `DEMO_MODE=true` in `.env`, or
> `python -m backend.demo.seed --base http://localhost:8000` (re-runnable).

All demo data is marked `demo-seed` / `DEMO` in the UI. No personal
credentials are required; the mock provider narrates every step.

## Act 1 — Memory (1 min)

1. Open **Memory**. Point out the seeded demo cards: PROJECT, GOAL,
   DECISION, PREFERENCE, FACT, EXPERIENCE.
2. Open a card's **details**: source, confidence, why-kept, related memories.
3. Say: *"AETHER remembers this. Let's use it."*

## Act 2 — Meeting brief (2 min)

4. In **Command Center**, click the suggested command:
   **"Prepare my research meeting for tomorrow."**
5. Narrate the live activity feed: `intent_classified → memory_read →
   agent_started → calendar.read → agent_finished`.
6. Show the brief. Note the grounded phrasing (*"per your calendar"*).
7. Open **Activity**, click the execution: walk the visual timeline
   USER REQUEST ↓ PLANNER ↓ MEMORY RETRIEVAL ↓ AGENT ↓ POLICY CHECK ↓ RESULT.

## Act 3 — Permission boundary (2 min, the climax)

8. Click: **"Send the brief to my research group."**
9. Execution pauses in `WAITING_FOR_PERMISSION`. Point at the
   **PERMISSION BOUNDARY** card: agent, action, resource, reason, risk.
10. Say: *"The model asked. The policy engine said: approval required.
    The model cannot override this."*
11. Click **Approve Once** → `email.send` executes → COMPLETED.
12. Back in **Activity**: `approval_requested → approval_granted →
    email.send → COMPLETED` in the timeline and audit journal.

## Optional Act 4 — Skill Discovery (1 min)

13. Run 2–3 similar requests (e.g. *"summarize this research paper"* ×3).
14. Open **Skills**: a proposal card appears (*"AETHER noticed repeated
    workflows"*). Approve it → the skill is registered live.

## Fallbacks if the network fails

- Mock provider keeps the whole story working offline.
- Every tool card is labeled REAL / STUB / DEMO — narrate honestly.
- `pytest tests/ -q` (31 tests) passes with no credentials.
