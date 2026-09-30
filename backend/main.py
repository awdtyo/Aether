"""AETHER backend entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from core.logging import setup_logging
from core.config import get_settings

log = setup_logging(get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    for problem in s.validate_model_config():
        log.warning("model config: %s", problem)
    if s.model_provider == "mock":
        log.info("model provider: local mock (set MODEL_PROVIDER=openai_compatible for Nebius/OpenRouter)")
    else:
        log.info("model provider: %s endpoint=%s model=%s",
                 s.model_provider, s.openai_base_url, s.model_name)
    try:
        from database.db import init_db
        await init_db()
        log.info("database initialized")
    except Exception as e:
        log.warning("db init skipped (%s); using in-memory fallback", e)
    if s.demo_mode:
        try:
            from api.deps import memory as _mem
            from demo.seed_data import DEMO_EVENTS, DEMO_MEMORIES, DEMO_NOTES, DEMO_SOURCE
            from memory.schemas import MemoryCreate, MemoryType
            from tools import stubs
            have = {m.content for m in await _mem.list(limit=500)}
            added = 0
            for mtype, content, conf in DEMO_MEMORIES:
                if content not in have:
                    await _mem.create(MemoryCreate(type=MemoryType(mtype), content=content,
                                                   source=DEMO_SOURCE, confidence=conf))
                    added += 1
            cal = stubs.ensure_demo(DEMO_EVENTS, DEMO_NOTES)
            log.info("demo mode: seeded %s memories, %s", added, cal)
        except Exception as e:
            log.warning("demo seeding skipped (%s)", e)
    yield


app = FastAPI(title="AETHER", description="Personal AI Operating System",
              version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "AETHER"}


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.backend_host, port=s.backend_port, reload=True)
