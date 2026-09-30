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

> If responses come back prefixed with `[mock:...]`, the mock provider is
> active: set `MODEL_PROVIDER=openai_compatible` in the repo-root `.env`
> (the backend loads `<repo>/.env` regardless of working directory) and
> restart the backend. "Connected" status means a key is configured; the
> first real failure surfaces per-execution (e.g. auth errors fail that
> execution cleanly without killing the API).

## Nebius configuration (Priority 1 — real model)

Same OpenAI-compatible abstraction, Nebius Token Factory endpoint:

```env
MODEL_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://api.studio.nebius.com/v1
OPENAI_API_KEY=<nebius token>
MODEL_NAME=<nvidia/nemotron model id>
```

Startup validates the config and logs problems without secrets
(`model config: …`); the API always boots — model failures surface
per-execution as clean `FAILED` states. Request logging records host,
model, and latency only — never keys, headers, or message bodies.

## Demo mode

```bash
DEMO_MODE=true          # in .env: seeds demo memories/events/notes at startup
python -m backend.demo.seed --base http://localhost:8000   # or on demand
```

All demo data is labeled `demo-seed`/`DEMO`. Full walkthrough: `docs/demo.md`.

## Production (Postgres + pgvector)

```bash
cp .env.example .env   # set DATABASE_URL, MODEL_PROVIDER=openai_compatible, OPENAI_* keys
docker compose up --build
```

## Primary demo

1. "Prepare my research meeting for tomorrow." → LLM-assisted intent
   (falls back to rules offline) → meeting-preparation skill →
   Research agent → memory + calendar → brief. All steps audited.
2. "Send the brief to my research group." → `email.send` is APPROVAL_REQUIRED →
   UI shows the PERMISSION BOUNDARY card → Approve Once → execution resumes,
   timeline updates. The model requests; the policy engine decides.

## Security model

The LLM never authorizes anything. Every tool call flows
`runtime → policy engine → ALLOW / DENY / APPROVAL_REQUIRED → tool → audit`.
Gated actions pause in `WAITING_FOR_PERMISSION` and cannot execute before
an explicit user approval. Invariant (tested): no valid policy decision,
no execution.

## Memory architecture

Typed records (FACT, PREFERENCE, PROJECT, GOAL, DECISION, EXPERIENCE,
SKILL, WORKFLOW) with content, source, confidence, timestamps,
last-verified, and embeddings. A `worth_persisting()` gate keeps raw chat
out; semantic search + type/source filters power recall, related-memory
lookup, and agent context. Provenance is visible on every memory card.

## Private Memory

AETHER separates application code from personal user data.

Public repository:

```text
GitHub
  ├── AETHER runtime
  ├── agents
  ├── skills
  ├── tools
  ├── policies
  └── memory engine
```

Private local data:

```text
~/.aether/
  ├── memory/memory.db
  ├── skills/        # your approved discoveries
  ├── config/
  └── audit/
```

Personal memory is intentionally excluded from version control
(`.gitignore` covers `.aether/`, `*.db`, `.env`). Configure the location with
`AETHER_DATA_DIR=~/.aether` (default; `~` is expanded, directories are
created automatically). Explicit `DATABASE_URL` still wins (e.g. Postgres in
Docker). With Docker, mount your host dir: the compose file maps
`${AETHER_DATA_DIR:-${HOME}/.aether}:/data/aether`, and `.dockerignore`
keeps local databases out of images.

Import your own memory (fictional template at `data/seed/memory.example.yaml`):

```bash
cp data/seed/memory.example.yaml ~/.aether/personal_memory.yaml
# edit with your own facts, then:
python -m backend.demo.seed_memory --file ~/.aether/personal_memory.yaml
```

The importer validates the YAML schema, skips entries whose content already
exists (safe to re-run), and reports `added=`/`skipped=` counts without
printing your data. Source labels used: `user_profile`, `user_preference`,
`project_context`, `workflow`, `user_input`.

## Skills & discovery

File-based `skills/*/skill.yaml` (tools, permissions, version, agent).
Experimental **Skill Discovery** proposes reusable skills from repeated
completed executions — creation happens only through explicit approval.
Approved discoveries are written to your private data dir
(`~/.aether/skills/`), never into the Git repository, and appear live in
the Skills UI.

## Agents, permissions, audit

Personal / Research / Developer / Planning agents receive injected
services (never the DB). Permissions surface as REAL / STUB / DEMO tool
kinds plus the model status (REAL vs mock) in the Tools page. The Activity
page renders each execution as a visual timeline backed by the audit
journal — concise metadata and reasons, never chain-of-thought.

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
- `tests/` policy, memory, runtime, tools, orchestrator, intent, discovery, timeline, demo (31 tests, offline)
- `docs/` architecture, memory, skills, agents, security

## Tests

```bash
python -m pytest tests/ -q
```
