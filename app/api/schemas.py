"""Request/response models for the 5 endpoints.

Shapes follow challenge-testing-brief.md §2-3 exactly. Requests use
``extra="allow"`` so a judge that adds fields mid-test never triggers a 422 —
the engine simply ignores what it doesn't use.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    delivered_at: Optional[str] = None


class TickRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    now: Optional[str] = None
    available_triggers: list[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str = ""
    received_at: Optional[str] = None
    turn_number: Optional[int] = None
