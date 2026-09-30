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
    try:
        from database.db import init_db
        await init_db()
        log.info("database initialized")
    except Exception as e:
        log.warning("db init skipped (%s); using in-memory fallback", e)
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
