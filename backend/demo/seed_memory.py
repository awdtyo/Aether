"""Import a private personal-memory YAML file into AETHER's memory service.

Usage:
    python -m backend.demo.seed_memory --file ~/.aether/personal_memory.yaml

Uses the project's MemoryService (never raw SQL). Idempotent: memories whose
normalized content already exists are skipped. Reports counts per outcome.
Only counts and types are printed — never full memory contents.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Make backend/ importable regardless of the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field, ValidationError

VALID_TYPES = {"FACT", "PREFERENCE", "PROJECT", "GOAL", "DECISION",
               "EXPERIENCE", "SKILL", "WORKFLOW"}


class ExplicitMemory(BaseModel):
    type: str
    content: str = Field(min_length=1, max_length=8000)
    source: str = "user_input"
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class Project(BaseModel):
    name: str
    description: str = ""


class PersonalMemoryFile(BaseModel):
    user: dict = Field(default_factory=dict)
    interests: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    projects: list[Project] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    memories: list[ExplicitMemory] = Field(default_factory=list)


def normalize(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


def load_personal_memory_file(path: str | Path) -> PersonalMemoryFile:
    import yaml
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"memory file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except Exception as e:
        raise ValueError(f"malformed YAML in {p}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"top level of {p} must be a mapping")
    try:
        doc = PersonalMemoryFile.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"invalid personal memory schema in {p}:\n{e}") from e
    known = set(PersonalMemoryFile.model_fields)
    ignored = sorted(set(data) - known)
    if ignored:
        # Never silently drop user data:_extra sections are schema-valid but
        # the importer only maps known sections (see to_entries).
        print(f"warning: ignoring unknown top-level sections: {', '.join(ignored)} "
              f"(keys only — restructure them into known sections to import)",
              file=sys.stderr)
    return doc


def to_entries(doc: PersonalMemoryFile) -> list[tuple[str, str, str, float]]:
    """Flatten to (type, content, source, confidence) tuples. No I/O."""
    entries: list[tuple[str, str, str, float]] = []
    user = doc.user or {}
    if user.get("name"):
        entries.append(("FACT", f"User's name is {user['name']}.", "user_profile", 0.95))
    if user.get("role"):
        entries.append(("FACT", f"User's role: {user['role']}.", "user_profile", 0.9))
    for v in doc.interests:
        entries.append(("FACT", f"User is interested in {v}.", "user_profile", 0.85))
    for k, v in (doc.preferences or {}).items():
        entries.append(("PREFERENCE", f"User prefers {k}: {v}.", "user_preference", 0.85))
    for proj in doc.projects:
        body = f"Project {proj.name}." + (f" {proj.description}" if proj.description else "")
        entries.append(("PROJECT", body.strip(), "project_context", 0.9))
    for g in doc.goals:
        entries.append(("GOAL", g if g.endswith(".") else g + ".", "user_input", 0.9))
    for d in doc.decisions:
        entries.append(("DECISION", d if d.endswith(".") else d + ".", "user_input", 0.85))
    for w in doc.workflows:
        entries.append(("WORKFLOW", w if w.endswith(".") else w + ".", "workflow", 0.8))
    for m in doc.memories:
        mtype = m.type.upper()
        if mtype not in VALID_TYPES:
            raise ValueError(f"invalid memory type: {m.type!r} (expected one of {sorted(VALID_TYPES)})")
        entries.append((mtype, m.content, m.source, m.confidence))
    return entries


async def import_memories(memory_service, entries) -> dict[str, int]:
    from memory.schemas import MemoryCreate, MemoryType
    existing = {normalize(m.content) for m in await memory_service.list(limit=5000)}
    added = skipped = 0
    for mtype, content, source, confidence in entries:
        if normalize(content) in existing:
            skipped += 1
            continue
        await memory_service.create(MemoryCreate(type=MemoryType(mtype), content=content,
                                                 source=source, confidence=confidence))
        existing.add(normalize(content))
        added += 1
    return {"added": added, "skipped": skipped}


async def run_import(memory_service, path: str | Path) -> dict[str, int]:
    doc = load_personal_memory_file(path)
    return await import_memories(memory_service, to_entries(doc))


def build_service():
    """MemoryService wired to the configured database (data dir by default)."""
    from core.config import get_settings
    from database.db import get_session_factory, init_db
    from memory.service import MemoryService
    get_settings().data_dir()  # ensure private dirs exist
    return MemoryService(session_factory=get_session_factory()), init_db()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import private personal memory YAML into AETHER.")
    parser.add_argument("--file", default="~/.aether/personal_memory.yaml")
    args = parser.parse_args(argv)
    try:
        service, init = build_service()
        result = asyncio.run(_run(service, init, args.file))
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"import done: added={result['added']} skipped={result['skipped']}")
    return 0


async def _run(service, init_coro, path):
    await init_coro
    return await run_import(service, path)


if __name__ == "__main__":
    raise SystemExit(main())
