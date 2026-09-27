"""App factory + entrypoint.

``uvicorn app.main:app`` (or ``python -m app.main``) serves the bot on
``0.0.0.0:$PORT`` (default 8080), matching the harness's ``/v1/*`` expectation.
"""
from __future__ import annotations

import os

from fastapi import FastAPI

from .api.routes import router
from .engine.service import VeraEngine


def create_app() -> FastAPI:
    app = FastAPI(title="Vera Message Engine", version="1.0.0")
    app.state.engine = VeraEngine()
    app.include_router(router)

    @app.get("/")
    async def root():
        return {"service": "vera-message-engine", "endpoints":
                ["/v1/healthz", "/v1/metadata", "/v1/context", "/v1/tick", "/v1/reply"]}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8080")), reload=False)
