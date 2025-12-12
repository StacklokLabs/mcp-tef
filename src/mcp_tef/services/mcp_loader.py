"""MCP server tool loading service."""

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import ListToolsResult

from mcp_tef.api.errors import LLMProviderError
from mcp_tef.models.schemas import ToolDefinition
from mcp_tef.services.json_schema_utils import extract_parameter_descriptions

logger = structlog.get_logger(__name__)


class MCPLoaderService:
    """Service for loading tool definitions from MCP servers using MCP SDK."""

    def __init__(self, timeout: int = 30):
        """Initialize MCP loader service.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    async def load_tools_from_server(self, url: str, transport: str) -> list[ToolDefinition]:
        """Load tool definitions from MCP server as ToolDefinition objects.

        Args:
            url: MCP server URL
            transport: Transport protocol ('sse' or 'streamable_http')

        Returns:
            List of ToolDefinition objects with full input_schema and extracted parameters

        Raises:
            LLMProviderError: If connection fails or SDK operation fails
        """
        logger.info("Loading tools from MCP server", url=url, transport=transport)
        try:
            # Select appropriate client based on transport
            if transport == "sse":
                async with sse_client(url) as (read, write):
                    raw_tools = await self._handle_session(read, write)
            else:  # transport == "streamable_http"
                async with streamablehttp_client(url) as (read, write, _):
                    raw_tools = await self._handle_session(read, write)

            logger.info("Loaded tools from MCP server", url=url, tool_count=len(raw_tools))
        except Exception as e:
            logger.exception("Failed to load tools from MCP server", url=url, error=str(e))

            # Provide more helpful error messages for common cases
            error_msg = self._format_connection_error(url, e)

            raise LLMProviderError(
                "MCP Server",
                error_msg,
                e,
            ) from e

        tools = []
        for tool in raw_tools:
            input_schema = tool.get("input_schema", {})

            # Extract parameter descriptions from schema (handles $ref)
            parameters = extract_parameter_descriptions(input_schema) if input_schema else {}

            tools.append(
                ToolDefinition(
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=input_schema,
                    parameters=parameters,
                )
            )

        return tools

    def _format_connection_error(self, url: str, error: Exception) -> str:
        """Format connection errors with helpful context.

        Args:
            url: The URL that failed to connect
            error: The original exception

        Returns:
            A user-friendly error message
        """
        error_str = str(error).lower()

        # Check for common connection issues
        if "connection refused" in error_str or "cannot connect" in error_str:
            return f"Cannot connect to MCP server at {url}. Is the server running?"
        if "timeout" in error_str or "timed out" in error_str:
            return f"Connection to MCP server at {url} timed out. The server may be unresponsive."
        if (
            "name or service not known" in error_str
            or "nodename nor servname provided" in error_str
        ):
            return f"Cannot resolve hostname for {url}. Please check the URL."
        if "taskgroup" in error_str or "sub-exception" in error_str:
            # Generic async error - try to extract root cause
            return (
                f"Failed to connect to MCP server at {url}. "
                "The server may not be running or is unreachable."
            )
        # Fall back to original error for unexpected cases
        return f"Failed to connect or load tools from {url}: {str(error)}"

    async def _handle_session(self, read, write) -> list[dict]:
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # List available tools using MCP protocol
            list_tools_result: ListToolsResult = await session.list_tools()

            # Convert MCP tool format to our internal format
            tools = []
            for mcp_tool in list_tools_result.tools:
                # MCP SDK returns Tool objects with name, description, inputSchema, outputSchema
                tool_dict = {
                    "name": mcp_tool.name,
                    "description": mcp_tool.description or "",
                    "input_schema": mcp_tool.inputSchema or {},
                    "output_schema": mcp_tool.outputSchema or {},
                }
                tools.append(tool_dict)
            return tools
