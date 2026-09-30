# AETHER — Personal AI Operating System

> Your memory. Your skills. Your agents. Your rules.

AETHER is not a generic chatbot. It is a personal AI OS with structured memory,
reusable skills, specialized agents, policy-gated tools, model routing, and a
complete audit trail — behind a command-center UI.

## Quickstart (local, zero credentials)

```bash
cp .env.example .env
pip install -r backend/requirements.txt
cd backend && python -m uvicorn main:app --port 8000 &
cd ../frontend && npm install && npm run dev
```

Open http://localhost:5173. The backend runs on :8000 with a local mock model,
SQLite storage, and in-workspace sandboxed tools. No API keys needed.

## NVIDIA Nemotron via OpenRouter

AETHER can run NVIDIA Nemotron through OpenRouter using its
OpenAI-compatible API.

Configure:

```env
MODEL_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=<your key>
MODEL_NAME=nvidia/nemotron-3.5-lightning
```

Any OpenRouter model id works (e.g. `MODEL_NAME=nvidia/nemotron-3-ultra-550b-a55b`)
with no code changes. `OPENROUTER_API_KEY` is accepted as an alias when
`OPENAI_API_KEY` is empty. Optional `OPENROUTER_HTTP_REFERER` /
`OPENROUTER_X_TITLE` headers are sent only when set.

The application also supports the local/mock provider (`MODEL_PROVIDER=mock`,
the default) for offline development and tests. The Tools page shows
provider, model, and connection status — never API keys.

## Production (Postgres + pgvector + Nebius)

```bash
cp .env.example .env   # set DATABASE_URL, MODEL_PROVIDER=openai_compatible, OPENAI_* keys
docker compose up --build
```

## Primary demo

1. "Prepare my research meeting for tomorrow." → meeting-preparation skill →
   Planning/Research agents → memory + calendar → brief. All steps audited.
2. "Send the brief to my research group." → `email.send` is APPROVAL_REQUIRED →
   UI shows PERMISSION REQUEST → Approve Once → execution resumes, timeline updates.

## Architecture

```
USER → AETHER CORE (runtime/orchestrator) → MODEL ROUTER + agents →
SKILL ENGINE → POLICY ENGINE → TOOL LAYER → AUDIT JOURNAL → MEMORY
```

Dependency direction: `API → Runtime → Agents → Skills → Services → Tools`;
cross-cutting: Memory, Policy, Audit, Model Router. Agents never touch the DB;
tools never bypass policy. See `docs/`.

## Layout

- `backend/` FastAPI app (`main.py`, `api/`, `core/`, `agents/`, `memory/`,
  `skills/`, `tools/`, `policies/`, `runtime/`, `models/`, `database/`)
- `frontend/` React+TS+Vite command-center OS
- `skills/` file-based skill definitions (`skill.yaml`)
- `tests/` policy, memory, runtime, tools, orchestrator
- `docs/` architecture, memory, skills, agents, security

## Tests

```bash
python -m pytest tests/ -q
```
