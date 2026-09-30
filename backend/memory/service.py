"""Memory service: CRUD + local-embedding semantic search + worth-persisting gate.

Embeddings use a deterministic hashed bag-of-words vector so the MVP works with
zero external dependencies. When pgvector + a real embedder are configured,
swap `embed()` for the provider call — the cosine-search logic is unchanged.
"""
from __future__ import annotations

import hashlib
import math
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from memory.schemas import Memory, MemoryCreate, MemoryType, MemoryUpdate

_WORD = re.compile(r"[a-z0-9]+")
_DIM = 256


def embed(text: str, dim: int = _DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in _WORD.findall(text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16) % dim
        vec[h] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


_TRIVIAL = re.compile(r"^(hi|hey|hello|thanks|thank you|ok|okay|bye)[.! ]*$", re.I)


def worth_persisting(content: str) -> bool:
    """Gate so we don't save every chat message. Returns True for durable info."""
    c = content.strip()
    if len(c) < 24 or _TRIVIAL.match(c):
        return False
    durable = ("prefer", "decided", "decision", "goal", "project", "my ", "i work",
               "remember", "always", "never", "deadline", "meeting", "uses", "using")
    return any(k in c.lower() for k in durable) or len(c) > 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryService:
    """Persistence-backed when a session factory is given, else in-memory."""

    def __init__(self, session_factory=None):
        self._factory = session_factory
        self._mem: dict[str, dict] = {}

    # -- internal helpers -------------------------------------------------
    def _to_schema(self, row: dict, score: float | None = None) -> Memory:
        return Memory(
            id=row["id"], type=row["type"], content=row["content"],
            source=row.get("source", "conversation"),
            confidence=row.get("confidence", 0.8),
            created_at=row["created_at"], updated_at=row["updated_at"],
            last_verified=row.get("last_verified"), score=score,
        )

    # -- CRUD --------------------------------------------------------------
    async def create(self, data: MemoryCreate) -> Memory:
        from database.models import MemoryRow

        record = {
            "id": str(uuid.uuid4()),
            "type": data.type, "content": data.content,
            "source": data.source, "confidence": data.confidence,
            "embedding": embed(data.content),
            "created_at": _utcnow(), "updated_at": _utcnow(), "last_verified": None,
        }
        if self._factory is None:
            self._mem[record["id"]] = record
            return self._to_schema(record)
        async with self._factory() as s:
            s.add(MemoryRow(**{k: (v.value if isinstance(v, MemoryType) else v)
                                         for k, v in record.items()}))
            await s.commit()
        return self._to_schema(record)

    async def get(self, mem_id: str) -> Memory | None:
        from database.models import MemoryRow

        if self._factory is None:
            r = self._mem.get(mem_id)
            return self._to_schema(r) if r else None
        async with self._factory() as s:
            row = (await s.execute(select(MemoryRow).where(MemoryRow.id == mem_id))).scalar_one_or_none()
            if row is None:
                return None
            return self._to_schema({"id": row.id, "type": MemoryType(row.type),
                                    "content": row.content, "source": row.source,
                                    "confidence": row.confidence, "created_at": row.created_at,
                                    "updated_at": row.updated_at, "last_verified": row.last_verified})

    async def update(self, mem_id: str, data: MemoryUpdate) -> Memory | None:
        from database.models import MemoryRow

        if self._factory is None:
            r = self._mem.get(mem_id)
            if not r:
                return None
            if data.content is not None:
                r["content"] = data.content
                r["embedding"] = embed(data.content)
            if data.confidence is not None:
                r["confidence"] = data.confidence
            if data.last_verified is not None:
                r["last_verified"] = data.last_verified
            r["updated_at"] = _utcnow()
            return self._to_schema(r)
        async with self._factory() as s:
            row = (await s.execute(select(MemoryRow).where(MemoryRow.id == mem_id))).scalar_one_or_none()
            if row is None:
                return None
            if data.content is not None:
                row.content = data.content
                row.embedding = embed(data.content)
            if data.confidence is not None:
                row.confidence = data.confidence
            if data.last_verified is not None:
                row.last_verified = data.last_verified
            row.updated_at = _utcnow()
            await s.commit()
            return await self.get(mem_id)

    async def delete(self, mem_id: str) -> bool:
        from database.models import MemoryRow

        if self._factory is None:
            return self._mem.pop(mem_id, None) is not None
        async with self._factory() as s:
            res = await s.execute(delete(MemoryRow).where(MemoryRow.id == mem_id))
            await s.commit()
            return (res.rowcount or 0) > 0

    async def list(self, types: list[MemoryType] | None = None, limit: int = 100) -> list[Memory]:
        from database.models import MemoryRow

        if self._factory is None:
            rows = list(self._mem.values())
            if types:
                rows = [r for r in rows if r["type"] in types]
            rows.sort(key=lambda r: r["created_at"], reverse=True)
            return [self._to_schema(r) for r in rows[:limit]]
        async with self._factory() as s:
            q = select(MemoryRow).order_by(MemoryRow.created_at.desc()).limit(limit)
            if types:
                q = q.where(MemoryRow.type.in_([t.value for t in types]))
            rows = (await s.execute(q)).scalars().all()
            return [self._to_schema({"id": r.id, "type": MemoryType(r.type), "content": r.content,
                                     "source": r.source, "confidence": r.confidence,
                                     "created_at": r.created_at, "updated_at": r.updated_at,
                                     "last_verified": r.last_verified}) for r in rows]

    async def search(self, query: str, types: list[MemoryType] | None = None,
                     limit: int = 8) -> list[Memory]:
        """Cosine similarity over local embeddings + metadata type filter."""
        from database.models import MemoryRow

        qv = embed(query)
        if self._factory is None:
            scored = [(cosine(qv, r["embedding"]), r) for r in self._mem.values()
                      if not types or r["type"] in types]
        else:
            async with self._factory() as s:
                q = select(MemoryRow)
                if types:
                    q = q.where(MemoryRow.type.in_([t.value for t in types]))
                dbrows = (await s.execute(q)).scalars().all()
                scored = []
                for r in dbrows:
                    emb = r.embedding or embed(r.content)
                    scored.append((cosine(qv, emb), {"id": r.id, "type": MemoryType(r.type),
                                                    "content": r.content, "source": r.source,
                                                    "confidence": r.confidence, "created_at": r.created_at,
                                                    "updated_at": r.updated_at,
                                                    "last_verified": r.last_verified}))
        # keyword boost so exact term matches rank first
        toks = set(_WORD.findall(query.lower()))
        def _score(item):
            cos, r = item
            overlap = len(toks & set(_WORD.findall(r["content"].lower())))
            return cos + 0.15 * overlap
        scored.sort(key=_score, reverse=True)
        return [self._to_schema(r, score=round(s, 4)) for s, r in scored[:limit]]
