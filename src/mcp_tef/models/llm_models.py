"""Internal models for LLM responses and tool selection."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """LLM confidence level for tool selection."""

    HIGH = "high"
    LOW = "low"


class LLMToolCall(BaseModel):
    """Model for an LLM tool call."""

    name: str = Field(..., description="Tool name")
    server_name: str | None = Field(None, description="MCP server name hosting the tool")
    parameters: dict[str, Any] = Field(..., description="Parameters extracted by LLM")
    response: dict[str, Any] | None = Field(None, description="Response from the tool if available")


class LLMResponse(BaseModel):
    """Model for structured LLM response."""

    tool_calls: list[LLMToolCall] = Field([], description="Tool calls if LLM selected a tool")
    confidence_level: ConfidenceLevel | None = Field(
        None, description="LLM confidence level for tool selection (high or low)"
    )
    raw_response: str = Field(..., description="Raw response from LLM")
