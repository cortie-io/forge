from typing import Any, Dict

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    action: str = Field(min_length=1, max_length=60)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    ok: bool
    message: str
    result: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
