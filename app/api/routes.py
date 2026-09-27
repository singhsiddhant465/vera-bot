"""HTTP surface: the 5 endpoints the judge calls (+ optional teardown).

The route layer is deliberately thin — validate/shape only, delegate all logic
to ``VeraEngine``. The engine instance is attached to ``app.state`` in main.py
so tests can inject a fresh one.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..config import VALID_SCOPES
from .schemas import ContextRequest, ReplyRequest, TickRequest

router = APIRouter(prefix="/v1")


def _engine(request: Request):
    return request.app.state.engine


@router.get("/healthz")
async def healthz(request: Request):
    return _engine(request).healthz()


@router.get("/metadata")
async def metadata(request: Request):
    return _engine(request).metadata()


@router.post("/context")
async def push_context(body: ContextRequest, request: Request, response: Response):
    if body.scope not in VALID_SCOPES:
        response.status_code = 400
        return {"accepted": False, "reason": "invalid_scope",
                "details": f"scope must be one of {list(VALID_SCOPES)}"}
    result = _engine(request).push_context(
        body.scope, body.context_id, body.version, body.payload, body.delivered_at)
    if not result.get("accepted") and result.get("reason") == "stale_version":
        response.status_code = 409
    return result


@router.post("/tick")
async def tick(body: TickRequest, request: Request):
    return _engine(request).tick(body.now or "", body.available_triggers)


@router.post("/reply")
async def reply(body: ReplyRequest, request: Request):
    return _engine(request).reply(
        body.conversation_id, body.merchant_id, body.from_role, body.message)


@router.post("/teardown")
async def teardown(request: Request):
    return _engine(request).teardown()
