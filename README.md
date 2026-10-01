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
- `tests/` policy, memory, runtime, tools, orchestrator, intent, discovery, timeline, demo, privacy (44 tests, offline)
- `docs/` architecture, memory, skills, agents, security

## Tests

```bash
python -m pytest tests/ -q
```

## Technical Deep Dive

This section documents exact runtime behavior. All flowcharts mirror the
implementation (`backend/runtime/`, `backend/policies/`, `backend/tools/`,
`backend/memory/`, `backend/models/`, `backend/api/`).

### 1. End-to-end request lifecycle

```text
USER  (Command Center input / POST /api/command {"message": ...})
  │
  ▼
API LAYER  (backend/api/routes.py — thin; no business logic)
  │  creates nothing, decides nothing; delegates to Orchestrator
  ▼
RUNTIME  (Orchestrator.handle)
  │  1. intent classification  (LLM structured → validated, else rules)
  │  2. agent + skill selection (validated against live registries)
  │  3. memory retrieval  (semantic search, top 8)
  │  4. sensitive-action pre-check  (policy BEFORE any execution)
  │  5. agent execution  (agent calls policy-gated tools only)
  │  6. verification + durable-fact persistence (gated, never raw chat)
  ▼
MODEL ROUTER ──► ModelProvider ──► OpenRouter / Nebius / mock
  │  (agents never instantiate model clients)
  ▼
AUDIT JOURNAL  (every step recorded; UI timeline + inspector)
```

Dependency direction is one-way, enforced by imports:

```text
API → Runtime → Agents → Skills → Services → Tools
         ↘ Memory · Policy · Audit · Model Router (cross-cutting)
```

Agents never touch the database (they receive injected services).
Tools never bypass the policy engine (`ToolRegistry.run` always checks first).
The LLM never authorizes anything (it only *requests*; the engine decides).

### 2. Execution state machine

States (`backend/runtime/schemas.py`):

```text
                          ┌─────────────────────────┐
                          │   WAITING_FOR_PERMISSION│◄── approval needed
                          │   (paused, resumable)   │    (email.send, commit…)
                          └───────────┬─────────────┘
                                      │ approve → EXECUTING
                                      │ deny    → FAILED
                                      ▼
CREATED → PLANNING → EXECUTING → TOOL_CALL ──► VERIFYING → COMPLETED
   │          │           │            │              │
   │          │           │            │              └──► FAILED (any error)
   │          │           │            └─────────────────► FAILED
   │          │           └──────────────────────────────► FAILED
   │          └──────────────────────────────────────────► FAILED
   └───────────────────────────────────────────────────► FAILED
```

Legal transitions (`TRANSITIONS` map, enforced by `ExecutionStore.transition`;
illegal ones raise `ValueError`):

| From | To |
|---|---|
| CREATED | PLANNING, FAILED |
| PLANNING | EXECUTING, WAITING_FOR_PERMISSION, COMPLETED, FAILED |
| EXECUTING | TOOL_CALL, VERIFYING, WAITING_FOR_PERMISSION, COMPLETED, FAILED |
| TOOL_CALL | EXECUTING, WAITING_FOR_PERMISSION, VERIFYING, FAILED |
| WAITING_FOR_PERMISSION | EXECUTING, FAILED |
| VERIFYING | COMPLETED, FAILED |
| COMPLETED / FAILED | (terminal) |

Every execution carries `id` (uuid), `agent`, `skill`, `user_request`,
`result`/`error`, `pending_approval_id`, timestamps, and a `history` list of
`{state, note}` entries. Short approval ids are 8 hex chars.

### 3. Orchestrator flow (`Orchestrator.handle`)

```text
ex = store.create(text)                       # state CREATED
transition → PLANNING
decision, source = classify_intent(text)      # "llm" | "rules"  (see §4)
skill = registry lookup(decision.skill)       # None if unknown
agent = skill.agent or decision.agent
audit: intent_classified  (source, agent, confidence, plan)
transition → EXECUTING
mems = memory.search(text, limit=8)
audit: memory_read ×2  ("started", "N memories retrieved")
sensitive = detect(text)                      # email.send | git.commit |
                                              # calendar.delete patterns
if sensitive:
    verdict = policy.check(...)               # LLM output is INPUT only
    audit: <tool.action> permission=<verdict>
    if DENY:               → finish FAILED ("Blocked by policy")
    if APPROVAL_REQUIRED:  → create approval, → WAITING_FOR_PERMISSION,
                            return paused message (NOTHING executed)
agent.run(ctx)                                # TOOL_CALL → VERIFYING
if worth_persisting(text): memory.create(...) # gated durable facts only
finish → COMPLETED (result) / FAILED (error)
```

`resume_after_approval(execution_id, approved)` only fires from
`WAITING_FOR_PERMISSION` (else returns `None`): deny → audit
`approval_denied` → FAILED; approve → audit `approval_granted` → EXECUTING →
approved tool runs through the normal gated path → COMPLETED.

### 4. Intent classification (LLM proposes, runtime disposes)

```text
classify_intent(text, router, skills)
  │
  ├─► TRY LLM:  router.generate_structured(prompt, IntentDecision)
  │             IntentDecision = {agent: personal|research|developer|planning,
  │                               skill: name|null, plan: ≤6 steps,
  │                               confidence: 0..1}
  │             · temperature 0.1, tier "fast"
  │             · agent must be one of 4 literals (Pydantic-enforced)
  │             · skill must exist in the live registry, else forced to null
  │             · unknown agent name → ValueError → fall through to rules
  │             · ANY ProviderError (mock/offline/bad JSON) → fall through
  │
  └─► RULES (deterministic): skills.match keywords → skill.agent,
      else _rule_agent() (research/meeting/email heuristic → pick_agent
      keyword router).  Source recorded as "llm" | "rules" in audit.
```

The model's choice can only *name* an agent/skill — both are re-validated
against `AGENTS` and the skill registry before use. A skill id that does not
exist degrades to "no skill", never to an error or a bypass.

### 5. Policy engine (authoritative, deterministic)

`PolicyEngine.check(PolicyCheck{agent, tool, action, resource, reason})` scans
an ordered rule list — **first matching rule wins** — and returns
`ALLOW | DENY | APPROVAL_REQUIRED` with a human reason. Matching is
case-insensitive on `(tool, action-prefix, resource-substring)`.
No rule matches → `APPROVAL_REQUIRED` (fail closed).

| Tool | Action | Resource scope | Decision |
|---|---|---|---|
| filesystem | read | `/Private` | DENY |
| filesystem | write | `/Private` | DENY |
| filesystem | read | (any) | ALLOW |
| filesystem | write | `/Projects`, `/Research` | ALLOW |
| filesystem | write (elsewhere), delete | (any) | APPROVAL_REQUIRED |
| git / github | status, log, diff / read, branch | (any) | ALLOW |
| git / github | commit, push | (any) | APPROVAL_REQUIRED |
| git / github | merge | (any) | DENY |
| email | read, draft | (any) | ALLOW |
| email | send | (any) | APPROVAL_REQUIRED |
| calendar | read, create | (any) | ALLOW |
| calendar | delete | (any) | APPROVAL_REQUIRED |
| web | search | (any) | ALLOW |
| notes | read, write | (any) | ALLOW |

### 6. Tool execution (`ToolRegistry.run`)

```text
run(agent, tool, action, args, resource, reason, audit, execution_id)
  │
  ├─ verdict = policy.check(...)            # ALWAYS first
  ├─ audit: "<tool>.<action>" permission=<verdict> status=checked|denied
  │
  ├─ DENY ────────────────► return error (nothing runs; outbox untouched)
  ├─ APPROVAL_REQUIRED ───► return error (caller pauses for approval)
  └─ ALLOW ───────────────► dispatch by tool name:
         filesystem → sandboxed to workspace root (path-escape = PermissionError;
                       read ≤20k chars, write, list ≤200 entries, file delete only)
         git        → allowlisted repos only (.git must exist); status/log/diff/
                       branch/commit via argv subprocess (no shell); push/merge
                       unreachable (policy gates them first)
         github/web → honest STUBs (need GITHUB_TOKEN / SERPER_API_KEY)
         calendar/notes/email → local DEMO stores (email.send = gated outbox)
     audit: "<tool>.<action>" permission=ALLOW status=ok|error
```

Tested invariant: without an ALLOW decision, no tool side effect can occur
(`test_protected_tool_never_runs_without_policy_approval`).

Tool kinds surfaced in the UI: `real` (filesystem, git), `stub` (github,
web), `demo` (calendar, notes, email).

### 7. Approval lifecycle

```text
WAITING_FOR_PERMISSION
  │  ApprovalRequest{id (8 chars), execution_id, agent, tool, action,
  │                  resource, reason, risk, status=pending, created_at}
  │  UI: amber PERMISSION BOUNDARY card (agent · action · resource · reason · risk)
  │
  ├─ [Approve Once] → status approved → approval_granted (audit)
  │                   → EXECUTING → tool runs → COMPLETED
  └─ [Deny]         → status denied   → approval_denied  (audit) → FAILED
```

Resolution is backend-enforced (`POST /api/approvals/{id}/resolve`);
client-side clicks are display only. Stale/double resolves return `None`
(the execution is no longer waiting).

### 8. Memory subsystem

Record: `{id, type, content, source, confidence, created_at, updated_at,
last_verified, embedding}`. Types: FACT, PREFERENCE, PROJECT, GOAL, DECISION,
EXPERIENCE, SKILL, WORKFLOW. Sources (importer + runtime): `conversation`,
`user_profile`, `user_preference`, `project_context`, `workflow`,
`user_input`, `demo-seed`.

```text
write path:  user text → worth_persisting? ──no──► discarded (never stored)
                             │
                            yes (≥24 chars, non-trivial; durable keywords
                            or >120 chars) → classify type → create()
read path:   query → embed() → cosine similarity over stored embeddings
             + 0.15 × keyword-overlap boost → type/source filter → top-N
             (each hit carries `score`)
related:     search(memory.content, limit+1) excluding self
```

Embeddings are deterministic hashed bag-of-words vectors (256-dim,
L2-normalized, `memory/service.py::embed`) — zero external dependencies, so
the MVP works offline. Swap `embed()` for a real embedder (and the JSON
column for pgvector `VECTOR`) without changing callers; `DATABASE_URL` with
Postgres already initializes the `vector` extension.

### 9. Model layer (`backend/models/`)

```text
Agent ──► ModelRouter ──► ModelProvider ──► endpoint
              │                ├─ MockProvider (deterministic, offline)
              │                └─ OpenAICompatibleProvider (OpenRouter, Nebius,
              │                   NVIDIA, Ollama — any chat-completions API)
              ├─ tiers by task: fast (<200 chars) · standard ·
              │                 reasoning (>600 chars/complex) · multimodal
              ├─ MODEL_NAME = canonical default; MODEL_FAST/_STANDARD/
              │  _REASONING/_MULTIMODAL = optional per-tier overrides
              ├─ generate_structured() → Pydantic-validated JSON
              │  (json_object mode → fenced-JSON fallback → validation error)
              └─ status() → {provider, endpoint, model, state} (no secrets)
```

Error taxonomy (all messages key-free): `ProviderConfigError` (missing key/
URL/model), `ProviderAuthError` (401/403), `ProviderModelError` (404),
`ProviderRateLimitError` (429, retryable), `ProviderTimeoutError`,
`ProviderUnavailableError` (5xx/unreachable). One retry on 429/5xx and on
empty content; reasoning traces (`reasoning_content`, multipart `reasoning`
blocks) are stripped — only final message text ever surfaces. Request logs
record host, model, latency — never keys, headers, or bodies. `max_tokens`
defaults to 4096 because Nemotron reasoning tokens count against the
completion budget.

### 10. Audit journal & execution timeline

Every event: `{timestamp, execution_id, agent, action, resource, permission,
reason, status, duration_ms}` (secrets redacted; persisted to Postgres or
SQLite, in-memory fallback). Action catalog: `agent_started`,
`intent_classified`, `memory_read`, `memory_created`, `<tool>.<action>`,
`approval_requested/granted/denied`, `agent_finished`, `skill_created`,
`error`.

`GET /api/executions/{id}` returns `{execution, events, timeline}` where
`timeline` (`runtime/timeline.py`) maps events onto demo steps —
`USER REQUEST → PLANNER → MEMORY RETRIEVAL → AGENT → POLICY CHECK → TOOL →
APPROVAL → RESULT → COMPLETED/FAILED` — collapsing consecutive benign
duplicates and labeling errors `FAILED`. Metadata and reasons only; no
chain-of-thought anywhere.

### 11. Agents & skills reference

| Agent | Capabilities | Tools |
|---|---|---|
| personal | intent understanding, memory recall, direct answers, delegation | notes, calendar, web |
| research | memory search, summarization, research briefs | notes, web, email, calendar |
| developer | repo inspection, TODO scan, status summary, dev plans | filesystem, git, github |
| planning | goal review, daily plans, priorities | calendar, notes |

Agents receive `AgentContext{execution_id, user_request, memories, args}`
plus injected deps — never the database. One agent per execution (no
agent-to-agent loops). Keyword routing (`pick_agent`) backs the LLM planner
offline. Agents are grounded by prompt contract: facts cite calendar/memory
sources; anything else is phrased as a suggestion.

| Skill | Agent | Purpose |
|---|---|---|
| meeting-preparation | research | brief from memories + calendar (Objective → Next actions) |
| daily-planning | planning | priorities, time blocks, risks from goals + calendar |
| research | research | topic analysis, open questions, next experiments |
| project-status | developer | git status/log, TODOs, dev plan |

Skills are `skills/<name>/skill.yaml` (name, description, version,
instructions, inputs/outputs, required tools/permissions, agent), matched by
keyword with LLM selection on top. Discovery (`skills/discovery.py`) groups
COMPLETED executions by (agent, request signature); ≥3 repeats with no
covering skill → proposal (UI card, count, evidence). Approval writes
`~/.aether/skills/discovered-<slug>/skill.yaml` and reloads the registry —
never silently, never into Git.

### 12. API reference (all under `/api`)

| Method & path | Purpose |
|---|---|
| POST `/command` | run orchestration → `{execution_id, state, agent, skill, result, error, pending_approval_id}` |
| GET `/executions` | recent executions (limit) |
| GET `/executions/{id}` | execution + audit events + visual timeline |
| GET `/approvals/pending` | open approval requests |
| POST `/approvals/{id}/resolve` | approve/deny → resumes or fails execution |
| POST `/memory` · GET `/memory?type=&source=` · POST `/memory/search` | create / list+filter / semantic search |
| GET `/memory/{id}` · PATCH `/memory/{id}` · DELETE `/memory/{id}` | inspect / edit / delete |
| GET `/memory/{id}/related` | related memories |
| GET `/agents` | agents + capabilities + active tasks |
| GET `/skills` · POST `/skills/{name}/run` | installed skills · run manually |
| GET `/tools` · POST `/tools/{name}/call` | registry (kinds, risk, permissions) · gated manual call |
| GET `/discovery/proposals` · POST `/discovery/{id}/approve` | skill proposals · approve-to-create |
| GET `/activity` | audit journal |
| GET `/models` | provider, models, secret-free status, demo flag, storage label, db |

### 13. Configuration reference (`.env` → `Settings`)

| Variable | Default | Effect |
|---|---|---|
| `MODEL_PROVIDER` | `mock` | `mock` \| `openai_compatible` \| `nebius` (unknown → warning + mock) |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | empty | canonical secret = first set; missing key fails per-call, never at boot |
| `OPENAI_BASE_URL` | OpenRouter | any chat-completions endpoint |
| `MODEL_NAME` | `nvidia/nemotron-3.5-lightning` | canonical model id (any id, no code change) |
| `MODEL_FAST/_STANDARD/_REASONING/_MULTIMODAL` | empty | per-tier overrides, else `MODEL_NAME` |
| `OPENROUTER_HTTP_REFERER` / `OPENROUTER_X_TITLE` | empty / `AETHER` | optional headers, sent only when set |
| `MODEL_TEMPERATURE` / `MODEL_MAX_TOKENS` / `MODEL_TIMEOUT_S` | `0.3` / `4096` / `60` | generation behavior |
| `DATABASE_URL` | — | explicit winner (e.g. Postgres in Docker) |
| `AETHER_DATA_DIR` | `~/.aether` | private data root (`~` expanded, auto-created) |
| `AETHER_WORKSPACE` / `AETHER_GIT_ALLOWLIST` | `/tmp/…` | filesystem/git sandbox roots (note: `Settings` fields are `workspace_root`/`git_allowlist`) |
| `DEMO_MODE` | `false` | seeds fictional demo data at startup |
| `BACKEND_HOST/PORT`, `FRONTEND_PORT`, `LOG_LEVEL` | `0.0.0.0`/`8000`/`5173`/`INFO` | serving |

Database resolution: explicit `DATABASE_URL` → non-default config URL →
`sqlite` at `<data-dir>/memory/memory.db`. Legacy `./aether.db` /
`backend/aether.db` is copied once into the data dir (original kept).

### 14. Storage & privacy dataflow

```text
REPO (public, git)                PRIVATE (never committed)
  backend/  frontend/               ~/.aether/
  skills/   (curated)                 memory/memory.db      ← memories
  data/seed/memory.example.yaml       skills/discovered-*/  ← approvals
  docs/  tests/  *.example            config/  audit/
        ▲                                    ▲
        │  .gitignore: .aether/ data/private/ *.db *.sqlite* .env
        │  backend/.dockerignore: *.db *.sqlite* .env
        │  UI reads memory ONLY via /api/* (no static serving, no Mounts)
```

Frontend views: Command Center (chat, approvals, activity, recent memories,
suggestions), Memory (search/filter/cards/provenance/related/edit),
Agents (capabilities/tools/live tasks), Skills (+ discovery proposals),
Tools (REAL/STUB/DEMO kinds, model REAL-vs-mock status), Activity
(timeline inspector + audit journal).

### 15. Test map (44 tests, offline, hermetic `~/.aether` isolation)

| File | Covers | Count |
|---|---|---|
| `test_policy.py` | rule decisions, deny scopes, fail-closed default | 5 |
| `test_core.py` | memory CRUD/search/filter, transitions, sandbox gate, demo flows | 7 |
| `test_openrouter.py` | config load, request shape, error taxonomy, retries, JSON validation, mock intact, stubbed runtime, gating | 12 |
| `test_polish.py` | intent fallback, registry validation, policy invariant, discovery, timeline, demo markers, config validation | 9 |
| `test_privacy.py` | data-dir resolution/creation, DB location, persistence, import + idempotency, fixture hygiene, no static serving, docker config | 11 |
