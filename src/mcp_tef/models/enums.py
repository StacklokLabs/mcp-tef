"""Enums for mcp-tef models.

This module re-exports enums from mcp_tef_models for backward compatibility.
New code should import directly from mcp_tef_models.
"""

# Re-export all enums from mcp_tef_models for backward compatibility
from mcp_tef_models.enums import (  # noqa: F401
    Classification,
    ConfidenceCategory,
    EmbeddingModelType,
    MCPServerStatus,
    ModelClass,
    SimilarityMethod,
    TestRunStatus,
)

__all__ = [
    "Classification",
    "ConfidenceCategory",
    "EmbeddingModelType",
    "MCPServerStatus",
    "ModelClass",
    "SimilarityMethod",
    "TestRunStatus",
]
