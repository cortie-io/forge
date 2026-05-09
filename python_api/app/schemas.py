
from typing import Any, Dict
from pydantic import BaseModel, Field

class ExecuteRequest(BaseModel):
    """
    Request schema for executing an action with a payload.
    - action: Name of the action to execute.
    - payload: Arbitrary key-value data for the action.
    """
    action: str = Field(
        ..., min_length=1, max_length=60, description="Name of the action to execute."
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key-value data for the action."
    )

class ExecuteResponse(BaseModel):
    """
    Response schema for action execution results.
    - ok: Whether the action succeeded.
    - message: Human-readable status or error message.
    - result: Arbitrary result data.
    """
    ok: bool = Field(..., description="Whether the action succeeded.")
    message: str = Field(..., description="Status or error message.")
    result: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary result data."
    )

class HealthResponse(BaseModel):
    """
    Health check response schema.
    - status: Service health status (e.g., 'ok').
    - service: Service name.
    """
    status: str = Field(..., description="Service health status (e.g., 'ok').")
    service: str = Field(..., description="Service name.")
