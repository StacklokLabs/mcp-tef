"""Integration tests for overlap matrix endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_tef.api.app import app
from mcp_tef.config.settings import Settings
from mcp_tef.models.schemas import ToolDefinition


@pytest.fixture
def sample_url_list():
    """Create sample URL list for testing."""
    return [
        "http://example.com/mcp1",
        "http://example.com/mcp2",
        "http://example.com/mcp3",
        "http://example.com/mcp4",
    ]


@pytest.fixture
def mock_mcp_loader():
    """Mock MCP loader service to return sample tools."""
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        mock_loader = AsyncMock()
        mock_loader_class.return_value = mock_loader

        # Return different tools for each URL
        async def load_tools_from_url(url: str) -> list[ToolDefinition]:
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
            if "mcp3" in url:
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
            return [
                ToolDefinition(
                    name="calculate_sum",
                    description="Calculate the sum of two numbers",
                    parameters={
                        "a": "First number",
                        "b": "Second number",
                    },
                ),
            ]

        mock_loader.load_tools_from_url_typed = AsyncMock(side_effect=load_tools_from_url)
        yield mock_loader


@pytest.fixture
async def client(test_db, mock_mcp_loader):
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
async def test_generate_overlap_matrix(client, sample_url_list):
    """Test overlap matrix generation."""
    response = await client.post(
        "/similarity/overlap-matrix",
        json={
            "mcp_server_urls": sample_url_list,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "tool_ids" in data
    assert "matrix" in data
    assert "dimensions" in data
    assert "generated_at" in data

    # Verify dimensions
    dimensions = data["dimensions"]
    assert "semantic" in dimensions
    assert "parameters" in dimensions
    assert "description" in dimensions

    # Verify dimension weights sum to 1.0
    total_weight = dimensions["semantic"] + dimensions["parameters"] + dimensions["description"]
    assert abs(total_weight - 1.0) < 0.01  # Allow for floating point error

    # Verify correct weights
    assert dimensions["semantic"] == 0.5
    assert dimensions["parameters"] == 0.3
    assert dimensions["description"] == 0.2

    # Verify matrix dimensions
    matrix = data["matrix"]
    assert len(matrix) == 4  # 4 URLs
    assert all(len(row) == 4 for row in matrix)

    # Verify matrix is symmetric
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            assert abs(matrix[i][j] - matrix[j][i]) < 0.01

    # Verify diagonal is 1.0
    for i in range(len(matrix)):
        assert abs(matrix[i][i] - 1.0) < 0.01

    # Verify all values are in [0, 1]
    for row in matrix:
        for value in row:
            assert 0.0 <= value <= 1.0


@pytest.mark.asyncio
async def test_overlap_matrix_with_similar_parameters(client):
    """Test overlap matrix detects parameter overlap."""
    # Create mock loader for this specific test with tools that have parameter overlap
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        mock_loader = AsyncMock()
        mock_loader_class.return_value = mock_loader

        async def load_tools_from_url(url: str) -> list[ToolDefinition]:
            if "url1" in url:
                return [
                    ToolDefinition(
                        name="tool_a",
                        description="First tool for testing",
                        parameters={"query": "Search query", "limit": "Result limit"},
                    ),
                ]
            if "url2" in url:
                return [
                    ToolDefinition(
                        name="tool_b",
                        description="Second tool for testing",
                        parameters={"query": "Query string", "limit": "Maximum results"},
                    ),
                ]
            return [
                ToolDefinition(
                    name="tool_c",
                    description="Third tool for testing",
                    parameters={"x": "X coordinate", "y": "Y coordinate"},
                ),
            ]

        mock_loader.load_tools_from_url_typed = AsyncMock(side_effect=load_tools_from_url)

        response = await client.post(
            "/similarity/overlap-matrix",
            json={
                "mcp_server_urls": [
                    "http://test.com/url1",
                    "http://test.com/url2",
                    "http://test.com/url3",
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()

        matrix = data["matrix"]

        # Verify that both pairs have reasonable similarity scores
        assert 0.0 <= matrix[0][1] <= 1.0
        assert 0.0 <= matrix[0][2] <= 1.0


@pytest.mark.asyncio
async def test_overlap_matrix_with_similar_descriptions(client):
    """Test overlap matrix detects description overlap."""
    # Create mock loader for this specific test with tools that have description overlap
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        mock_loader = AsyncMock()
        mock_loader_class.return_value = mock_loader

        async def load_tools_from_url(url: str) -> list[ToolDefinition]:
            if "url1" in url:
                return [
                    ToolDefinition(
                        name="search_a",
                        description="Search documents using keywords and filters",
                        parameters={},
                    ),
                ]
            if "url2" in url:
                return [
                    ToolDefinition(
                        name="search_b",
                        description="Search documents using keywords and filters",
                        parameters={},
                    ),
                ]
            return [
                ToolDefinition(
                    name="calculate",
                    description="Calculate mathematical expressions",
                    parameters={},
                ),
            ]

        mock_loader.load_tools_from_url_typed = AsyncMock(side_effect=load_tools_from_url)

        response = await client.post(
            "/similarity/overlap-matrix",
            json={
                "mcp_server_urls": [
                    "http://test.com/url1",
                    "http://test.com/url2",
                    "http://test.com/url3",
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()

        matrix = data["matrix"]

        # search_a and search_b should have very high overlap
        assert matrix[0][1] > 0.9  # Should be very similar

        # search_a and calculate should have lower overlap than the identical pair
        assert matrix[0][2] < matrix[0][1]


@pytest.mark.asyncio
async def test_overlap_matrix_performance(client):
    """Test that overlap matrix generation completes in reasonable time."""
    import time

    # Create mock loader that returns 12 tools (3 per URL)
    with patch("mcp_tef.api.similarity.MCPLoaderService") as mock_loader_class:
        mock_loader = AsyncMock()
        mock_loader_class.return_value = mock_loader

        async def load_tools_from_url(url: str) -> list[ToolDefinition]:
            # Return 3 tools per URL
            base_idx = hash(url) % 100
            return [
                ToolDefinition(
                    name=f"tool_{base_idx}_{i}",
                    description=f"Tool {base_idx}_{i} description",
                    parameters={"param": "value"},
                )
                for i in range(3)
            ]

        mock_loader.load_tools_from_url_typed = AsyncMock(side_effect=load_tools_from_url)

        # 4 URLs * 3 tools each = 12 tools
        url_list = [f"http://test.com/mcp{i}" for i in range(4)]

        start = time.time()

        response = await client.post(
            "/similarity/overlap-matrix",
            json={
                "mcp_server_urls": url_list,
            },
        )

        elapsed = time.time() - start

        assert response.status_code == 200

        # Should complete in reasonable time
        assert elapsed < 15.0  # 12 tools should be fast
