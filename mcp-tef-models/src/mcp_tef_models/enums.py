"""Enums for mcp-tef models."""

from enum import StrEnum


class MCPServerStatus(StrEnum):
    """MCP server connection status."""

    ACTIVE = "active"
    FAILED = "failed"


class TestRunStatus(StrEnum):
    """Test run execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Classification(StrEnum):
    """Test result classification."""

    TRUE_POSITIVE = "TP"
    FALSE_POSITIVE = "FP"
    TRUE_NEGATIVE = "TN"
    FALSE_NEGATIVE = "FN"


class ConfidenceCategory(StrEnum):
    """Confidence level categories."""

    ROBUST = "robust"
    NEEDS_CLARITY = "needs_clarity"
    MISLEADING = "misleading"


class SimilarityMethod(StrEnum):
    """Similarity analysis methods."""

    EMBEDDING = "embedding"
    DESCRIPTION_OVERLAP = "description_overlap"


class EmbeddingModelType(StrEnum):
    """Embedding model provider types."""

    FASTEMBED = "fastembed"
    OPENAI = "openai"
    CUSTOM = "custom"


class ModelClass(StrEnum):
    """Model classification by capability."""

    SMALL = "small"  # For simple language processing tasks (tool selection, pattern matching)
    FRONTIER = "frontier"  # For complex reasoning tasks (recommendations, generation)
    EMBEDDING = "embedding"  # For embedding models (semantic similarity)
