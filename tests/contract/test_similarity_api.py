"""Contract tests for similarity API endpoints."""

from typing import Literal, cast
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from mcp_tef_models.schemas import ToolDefinition

from mcp_tef.api.app import app
from mcp_tef.config.settings import Settings
from mcp_tef.services.embedding_service import EmbeddingService


@pytest.fixture(scope="module")
def shared_embedding_service():
    """Create a shared embedding service for all tests in this module.

    This prevents rate limiting issues from HuggingFace by reusing
    the same fastembed model instance across all tests.
    """
    return EmbeddingService(
        model_type=cast(Literal["fastembed", "openai", "custom"], "fastembed"),
        model_name="BAAI/bge-small-en-v1.5",
        api_key="",
        custom_api_url="",
        timeout=30,
    )


@pytest.fixture
def sample_url_list():
    """Create sample URL list for testing."""
    return [
        "http://example.com/mcp1",
        "http://example.com/mcp2",
    ]


@pytest.fixture
def mock_mcp_loader():
    """Mock MCP loader service to return sample tools."""
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        mock_loader = AsyncMock()
        mock_loader_class.return_value = mock_loader

        # Return different tools for each URL
        async def load_tools_from_server(
            url: str, transport: str = "streamable-http"
        ) -> list[ToolDefinition]:
            if "mcp1" in url:
                return [
                    ToolDefinition(
                        name="search_documents",
                        description="Search through user documents",
                        parameters={"query": "Search query string"},
                    ),
                ]
            return [
                ToolDefinition(
                    name="find_files",
                    description="Find files in the system",
                    parameters={"pattern": "File name pattern"},
                ),
            ]

        mock_loader.load_tools_from_server = AsyncMock(side_effect=load_tools_from_server)
        yield mock_loader


@pytest.fixture
async def client(test_db, shared_embedding_service, mock_mcp_loader):
    """Create test client with embedding settings."""
    settings = Settings(
        embedding_model_type="fastembed",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        openrouter_api_key="test-api-key",
        database_url="sqlite:///:memory:",
        log_level="DEBUG",
        port=8000,
    )
    # Override settings and db for testing
    app.state.settings = settings
    app.state.db = test_db

    # Cache the shared embedding service to avoid re-initialization
    app.state.embedding_service = shared_embedding_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_analyze_similarity_contract(client, sample_url_list):
    """Test POST /similarity/analyze contract."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "compute_full_similarity": False,
            "include_confusion_testing": False,
            "include_recommendations": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Required fields
    assert "tool_ids" in data
    assert "matrix" in data
    assert "threshold" in data
    assert "flagged_pairs" in data
    assert "generated_at" in data

    # Optional fields
    assert "recommendations" in data or "recommendations" not in data

    # Type validation
    assert isinstance(data["tool_ids"], list)
    assert all(isinstance(tool_id, str) for tool_id in data["tool_ids"])

    assert isinstance(data["matrix"], list)
    assert all(isinstance(row, list) for row in data["matrix"])
    assert all(isinstance(val, (int, float)) for row in data["matrix"] for val in row)

    assert isinstance(data["threshold"], (int, float))
    assert 0.0 <= data["threshold"] <= 1.0

    assert isinstance(data["flagged_pairs"], list)
    for pair in data["flagged_pairs"]:
        assert "tool_a_id" in pair
        assert "tool_b_id" in pair
        assert "similarity_score" in pair
        assert isinstance(pair["tool_a_id"], str)
        assert isinstance(pair["tool_b_id"], str)
        assert isinstance(pair["similarity_score"], (int, float))

    assert isinstance(data["generated_at"], str)


@pytest.mark.asyncio
async def test_generate_overlap_matrix_contract(client, sample_url_list):
    """Test POST /similarity/overlap-matrix contract."""
    response = await client.post(
        "/similarity/overlap-matrix",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Required fields per OpenAPI spec
    required_fields = ["tool_ids", "matrix", "dimensions", "generated_at"]
    for field in required_fields:
        assert field in data

    # Type validation
    assert isinstance(data["tool_ids"], list)
    assert isinstance(data["matrix"], list)
    assert isinstance(data["dimensions"], dict)
    assert isinstance(data["generated_at"], str)

    # Dimensions structure
    dimensions = data["dimensions"]
    assert "semantic" in dimensions
    assert "parameters" in dimensions
    assert "description" in dimensions
    assert all(isinstance(v, (int, float)) for v in dimensions.values())


@pytest.mark.asyncio
async def test_analyze_similarity_request_validation(client):
    """Test request validation for /similarity/analyze."""
    # Missing required fields
    response = await client.post(
        "/similarity/analyze",
        json={},
    )

    # Should fail validation (no mcp_server_urls provided)
    assert response.status_code == 422

    # Invalid threshold
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_server_urls": ["http://example.com/mcp1", "http://example.com/mcp2"],
            "similarity_threshold": 1.5,  # > 1.0
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_overlap_matrix_request_validation(client):
    """Test request validation for /similarity/overlap-matrix."""
    # No mcp_server_urls provided
    response = await client.post(
        "/similarity/overlap-matrix",
        json={},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_similarity_with_embedding_method(client, sample_url_list):
    """Test analysis_methods with embedding method."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "analysis_methods": ["embedding"],
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "matrix" in data
    assert "tool_ids" in data
    assert "flagged_pairs" in data


@pytest.mark.asyncio
async def test_analyze_similarity_with_description_overlap_method(client, sample_url_list):
    """Test analysis_methods with description_overlap method."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "analysis_methods": ["description_overlap"],
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "matrix" in data
    assert "tool_ids" in data
    assert "flagged_pairs" in data


@pytest.mark.asyncio
async def test_analyze_similarity_with_unsupported_method(client, sample_url_list):
    """Test that unsupported analysis methods are rejected."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "analysis_methods": ["llm_similarity"],  # Not implemented yet
        },
    )

    assert response.status_code == 422  # Validation error
    data = response.json()
    # Check error message in either detail or message field
    error_text = str(data)
    assert "Unsupported analysis method" in error_text


@pytest.mark.asyncio
async def test_analyze_similarity_with_custom_embedding_model(client, sample_url_list):
    """Test embedding_model override with custom model."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "embedding_model": "BAAI/bge-base-en-v1.5",  # Different fastembed model
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "matrix" in data
    assert "tool_ids" in data
    assert "flagged_pairs" in data


@pytest.mark.asyncio
async def test_analyze_similarity_with_model_type_prefix(client, sample_url_list):
    """Test embedding_model with type:model format."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
            "embedding_model": "fastembed:BAAI/bge-small-en-v1.5",  # Explicit type prefix
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "matrix" in data
    assert "tool_ids" in data
    assert "flagged_pairs" in data
