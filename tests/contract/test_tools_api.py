"""Contract tests for tool retrieval via MCP server URLs.

Note: Tools are no longer persisted. Instead, they are retrieved directly from MCP server URLs.
The /tools endpoint and POST /tools endpoint have been removed.
Tools are now queried via /mcp-servers/tools?server_url=<url>
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from mcp_tef.models.schemas import ToolDefinition


@pytest.mark.asyncio
async def test_get_mcp_server_tools_direct_fetch(client: AsyncClient):
    """Test GET /mcp-servers/tools endpoint fetches tools directly from MCP server URL."""
    test_server_url = "http://localhost:3001"

    # Mock MCPLoaderService to return tools
    with patch("mcp_tef.api.mcp_servers.MCPLoaderService") as mock_loader:
        mock_instance = mock_loader.return_value
        mock_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        response = await client.get(f"/mcp-servers/tools?server_url={test_server_url}")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "count" in data
        assert len(data["tools"]) == 1
        assert data["count"] == 1
        assert data["tools"][0]["name"] == "test_tool"

        # Verify the service was called with correct URL and transport
        mock_instance.load_tools_from_server.assert_called_once_with(
            test_server_url, "streamable-http"
        )


@pytest.mark.asyncio
async def test_get_mcp_server_tools_pagination(client: AsyncClient):
    """Test GET /mcp-servers/tools with pagination parameters."""
    test_server_url = "http://localhost:3001"

    # Create 5 mock tools
    mock_tools = [
        ToolDefinition(
            name=f"tool_{i}",
            description=f"Tool {i}",
            input_schema={"type": "object"},
        )
        for i in range(5)
    ]

    with patch("mcp_tef.api.mcp_servers.MCPLoaderService") as mock_loader:
        mock_instance = mock_loader.return_value
        mock_instance.load_tools_from_server = AsyncMock(return_value=mock_tools)

        # Test limit
        response = await client.get(f"/mcp-servers/tools?server_url={test_server_url}&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 2
        assert data["count"] == 2

        # Test offset
        response = await client.get(
            f"/mcp-servers/tools?server_url={test_server_url}&offset=2&limit=2"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 2
        assert data["count"] == 2


@pytest.mark.asyncio
async def test_get_mcp_server_tools_missing_url(client: AsyncClient):
    """Test GET /mcp-servers/tools returns 422 when server_url is missing."""
    response = await client.get("/mcp-servers/tools")

    assert response.status_code == 422  # FastAPI returns 422 for missing required query parameters
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_mcp_server_tools_empty(client: AsyncClient):
    """Test GET /mcp-servers/tools returns empty list when server has no tools."""
    test_server_url = "http://localhost:3001"

    with patch("mcp_tef.api.mcp_servers.MCPLoaderService") as mock_loader:
        mock_instance = mock_loader.return_value
        mock_instance.load_tools_from_server = AsyncMock(return_value=[])

        response = await client.get(f"/mcp-servers/tools?server_url={test_server_url}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 0
        assert data["count"] == 0
