"""Integration tests for similarity analysis endpoints."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_tef.api.app import app
from mcp_tef.config.settings import Settings


@pytest.fixture
def test_data_dir():
    """Get test data directory path."""
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def sample_server_list(test_data_dir):
    """Load sample server list from test data."""
    with open(test_data_dir / "mcp_tools_5.json") as f:
        return json.load(f)


@pytest.fixture
def sample_url_list():
    """Create sample MCP server config list for testing."""
    from mcp_tef.models.schemas import MCPServerConfig

    return [
        MCPServerConfig(url="http://example.com/mcp1", transport="streamable-http"),
        MCPServerConfig(url="http://example.com/mcp2", transport="streamable-http"),
        MCPServerConfig(url="http://example.com/mcp3", transport="streamable-http"),
    ]


@pytest.fixture
def mock_mcp_loader_with_tools():
    """Mock MCP loader service to return sample tools."""
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        from mcp_tef.models.schemas import ToolDefinition

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
                        description="Search through user documents using semantic search",
                        parameters={
                            "query": "Search query string",
                            "max_results": "Maximum number of results to return",
                        },
                    ),
                ]
            if "mcp2" in url:
                return [
                    ToolDefinition(
                        name="find_files",
                        description="Find files in the system by name or pattern",
                        parameters={
                            "pattern": "File name pattern to search for",
                            "directory": "Directory to search in",
                        },
                    ),
                ]
            # mcp3
            return [
                ToolDefinition(
                    name="get_weather",
                    description="Get current weather information for a location",
                    parameters={
                        "location": "City or location name",
                        "units": "Temperature units (celsius or fahrenheit)",
                    },
                ),
            ]

        mock_loader.load_tools_from_server = AsyncMock(side_effect=load_tools_from_server)
        yield mock_loader


@pytest.fixture
def mock_embedding_service():
    """Mock the EmbeddingService to avoid actual model initialization."""
    with patch("mcp_tef.api.similarity.EmbeddingService") as mock_service_class:
        # Create mock instance
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        # Mock generate_embeddings_batch to return deterministic embeddings
        # Each text gets a unique but deterministic embedding
        async def mock_generate_embeddings_batch(texts):
            import hashlib

            embeddings = []
            for text in texts:
                # Generate deterministic embedding based on text hash
                hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
                # Create a 384-dimensional embedding (typical for small models)
                base_val = (hash_val % 1000) / 1000.0
                embedding = [base_val + (i * 0.001) for i in range(384)]
                embeddings.append(embedding)
            return embeddings

        mock_service.generate_embeddings_batch = AsyncMock(
            side_effect=mock_generate_embeddings_batch
        )

        yield mock_service


@pytest.fixture
async def client(test_db, mock_embedding_service, mock_mcp_loader_with_tools):
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_analyze_similarity_with_url_list(client, sample_url_list):
    """Test similarity analysis with mcp_server_urls format."""
    response = await client.post(
        "/similarity/analyze",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.80,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "tool_ids" in data
    assert "matrix" in data
    assert "flagged_pairs" in data

    # Verify we have the right number of tools (3 URLs, 1 tool each)
    assert len(data["tool_ids"]) == 3

    # Verify matrix properties
    assert isinstance(data["tool_ids"], list)
    assert isinstance(data["matrix"], list)
    assert len(data["matrix"]) == len(data["tool_ids"])

    # Verify matrix is symmetric
    matrix = data["matrix"]
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            assert matrix[i][j] == matrix[j][i]

    # Verify diagonal is 1.0
    for i in range(len(matrix)):
        assert matrix[i][i] == 1.0


@pytest.mark.asyncio
async def test_analyze_similarity_with_compute_full(client, sample_url_list):
    """Test similarity analysis with full similarity computation."""
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
            "compute_full_similarity": True,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Full similarity should be computed but not exposed in matrix response
    # (it would be in detailed pair responses if we added that endpoint)
    assert "matrix" in data


@pytest.mark.asyncio
async def test_generate_similarity_matrix(client, sample_url_list):
    """Test similarity matrix generation endpoint."""
    response = await client.post(
        "/similarity/matrix",
        json={
            "mcp_servers": [
                {"url": s.url, "transport": s.transport}
                if hasattr(s, "url")
                else {"url": s, "transport": "streamable-http"}
                for s in sample_url_list
            ],
            "similarity_threshold": 0.85,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "tool_ids" in data
    assert "matrix" in data
    assert "threshold" in data
    assert "flagged_pairs" in data
    assert "generated_at" in data

    # Verify threshold is correct
    assert data["threshold"] == 0.85
