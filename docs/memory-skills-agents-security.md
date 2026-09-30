# Memory

Structured types: FACT, PREFERENCE, PROJECT, GOAL, DECISION, EXPERIENCE, SKILL, WORKFLOW.

Each record: id, type, content, source, confidence, created/updated_at,
last_verified, embedding. The `worth_persisting()` gate blocks greetings and
trivial chat; durable signals (preferences, decisions, goals, projects,
long substantive content) are saved with provenance.

Search = cosine similarity over deterministic local embeddings + keyword boost
+ type filter. Swap `memory/service.py::embed()` for a real embedder (and the
JSON column for pgvector `VECTOR`) without changing callers.

# Skills

File-based: `skills/<name>/skill.yaml` (name, description, version,
instructions, inputs/outputs, required tools/permissions, agent).
`SkillRegistry.match()` routes requests; the orchestrator prefixes results
with `[skill vX]`. Skills never bypass policy — their tools go through the
same gated `ToolRegistry.run()`.

# Agents

Personal (default/intent), Research (briefs), Developer (repo status),
Planning (daily plans). `pick_agent()` is keyword-based in the MVP; agents
receive `AgentContext` (request + retrieved memories) plus injected deps.
Agent-to-agent loops are avoided: one agent per execution.

# Security

- Policy engine is authoritative; LLM output never grants permission.
- Fail-closed default (APPROVAL_REQUIRED); `/Private` denied; merges denied.
- Filesystem sandboxed to `AETHER_WORKSPACE`; git restricted to allowlist repos, no shell.
- Approvals pause execution; backend enforces, UI only displays.
- Secrets from env only; audit redacts tokens/keys; no secrets in git or logs.
