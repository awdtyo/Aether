# Architecture

`USER → AETHER CORE → MODEL ROUTER + ORCHESTRATOR → agents → skills → policy → tools → audit → memory`

- `backend/main.py` — FastAPI app, `/api/*` routes, CORS, lifespan DB init.
- `backend/api/` — thin routes; all logic lives in runtime/services.
- `backend/runtime/` — `ExecutionStore` (states + approvals) and `Orchestrator`
  (intent → agent → skill → gated tools → verify → memory).
- `backend/agents/` — Personal, Research, Developer, Planning. Services injected; no DB access.
- `backend/skills/` — file-based `skills/*/skill.yaml` + registry matcher.
- `backend/tools/` — registry dispatches only after policy verdict; filesystem
  sandboxed to workspace, git allowlisted, no shell.
- `backend/policies/` — deterministic rule engine (ALLOW/DENY/APPROVAL_REQUIRED), fail-closed.
- `backend/memory/` — typed CRUD + hashed-embedding cosine search + persist gate.
- `backend/audit/` — every significant event; secrets redacted.
- `backend/models/` — provider abstraction (`mock`, `openai_compatible` incl. Nebius) + tier router.
- `backend/database/` — SQLAlchemy models; SQLite locally, Postgres+pgvector via `DATABASE_URL`.
