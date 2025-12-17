"""HTTP client for mcp-tef API communication."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from mcp_tef_models.schemas import (
    DifferentiationRecommendationResponse,
    ExpectedToolCall,
    MCPServerConfig,
    ModelSettingsCreate,
    OverlapMatrixResponse,
    PaginatedTestCaseResponse,
    PaginatedTestRunResponse,
    SimilarityAnalysisResponse,
    TestCaseCreate,
    TestCaseResponse,
    TestRunExecuteRequest,
    TestRunResponse,
)
from pydantic import BaseModel, Field

from mcp_tef_cli.models import (
    HealthResponse,
    ServerInfo,
    ToolQualityResponse,
)

__all__ = [
    "ClientConfig",
    "TefClient",
]


class ClientConfig(BaseModel):
    """Configuration for mcp-tef HTTP client."""

    base_url: str = Field(
        default="https://localhost:8000", description="Base URL for mcp-tef server"
    )
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds")
    verify_ssl: bool = Field(
        default=False, description="Verify SSL certificates (disable for self-signed certs)"
    )
    api_key: str | None = Field(default=None, description="API key for authentication")
    api_key_header: str = Field(default="X-Model-API-Key", description="Header name for API key")


class TefClient:
    """HTTP client for mcp-tef API.

    This client provides async methods for interacting with the mcp-tef REST API.
    It handles connection management, request/response serialization, and error handling.

    Example:
        ```python
        config = ClientConfig(base_url="https://localhost:8000")
        client = TefClient(config)

        try:
            health = await client.health()
            print(f"Server status: {health.status}")
        finally:
            await client.close()
        ```
    """

    def __init__(self, config: ClientConfig | None = None):
        """Initialize HTTP client.

        Args:
            config: Client configuration. If None, uses defaults.
        """
        self.config = config or ClientConfig()
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def _get_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Get or create HTTP client (thread-safe).

        Yields:
            Configured httpx AsyncClient instance
        """
        async with self._lock:
            if self._client is None:
                headers = {}
                if self.config.api_key:
                    headers[self.config.api_key_header] = self.config.api_key

                self._client = httpx.AsyncClient(
                    base_url=str(self.config.base_url),
                    timeout=self.config.timeout,
                    verify=self.config.verify_ssl,
                    headers=headers,
                )

        try:
            yield self._client
        finally:
            pass

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        async with self._lock:
            if self._client:
                await self._client.aclose()
                self._client = None

    async def health(self) -> HealthResponse:
        """Get server health status.

        Returns:
            HealthResponse with server health status

        Raises:
            httpx.HTTPError: If request fails
        """
        async with self._get_client() as client:
            response = await client.get("/health")
            response.raise_for_status()
            return HealthResponse.model_validate(response.json())

    async def info(self) -> ServerInfo:
        """Get server information.

        Returns:
            ServerInfo with server name, version, and status

        Raises:
            httpx.HTTPError: If request fails
        """
        async with self._get_client() as client:
            response = await client.get("/")
            response.raise_for_status()
            return ServerInfo.model_validate(response.json())

    async def evaluate_tool_quality(
        self,
        server_urls: list[str],
        model_provider: str,
        model_name: str,
    ) -> ToolQualityResponse:
        """Evaluate tool description quality for MCP servers.

        Args:
            server_urls: List of MCP server URLs to evaluate
            model_provider: LLM provider name (e.g., 'anthropic', 'openai', 'openrouter')
            model_name: Model identifier (e.g., 'claude-sonnet-4-5-20250929')

        Returns:
            ToolQualityResponse with evaluation results and any errors

        Raises:
            httpx.HTTPError: If request fails
            httpx.TimeoutException: If request times out
        """
        async with self._get_client() as client:
            response = await client.get(
                "/mcp-servers/tools/quality",
                params={
                    "server_urls": ",".join(server_urls),
                    "model_provider": model_provider,
                    "model_name": model_name,
                },
            )
            response.raise_for_status()
            return ToolQualityResponse.model_validate(response.json())

    # =========================================================================
    # Test Case Methods
    # =========================================================================

    async def create_test_case(
        self,
        name: str,
        query: str,
        available_mcp_servers: list[MCPServerConfig],
        expected_tool_calls: list[ExpectedToolCall] | None = None,
        order_dependent_matching: bool = False,
    ) -> TestCaseResponse:
        """Create a new test case.

        Args:
            name: Descriptive name for the test case
            query: User query to evaluate
            available_mcp_servers: List of MCPServerConfig objects
            expected_tool_calls: List of expected tool calls (null/empty for negative tests)
            order_dependent_matching: Whether tool calls must match in exact order

        Returns:
            TestCaseResponse with created test case

        Raises:
            httpx.HTTPError: If request fails
        """
        payload = TestCaseCreate(
            name=name,
            query=query,
            available_mcp_servers=available_mcp_servers,
            expected_tool_calls=expected_tool_calls,
            order_dependent_matching=order_dependent_matching,
        )

        async with self._get_client() as client:
            response = await client.post(
                "/test-cases",
                json=payload.model_dump(mode="json", exclude_none=True),
            )
            response.raise_for_status()
            return TestCaseResponse.model_validate(response.json())

    async def list_test_cases(
        self,
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedTestCaseResponse:
        """List all test cases with pagination.

        Args:
            offset: Number of records to skip
            limit: Maximum records to return

        Returns:
            PaginatedTestCaseResponse with test cases

        Raises:
            httpx.HTTPError: If request fails
        """
        async with self._get_client() as client:
            response = await client.get(
                "/test-cases",
                params={"offset": offset, "limit": limit},
            )
            response.raise_for_status()
            return PaginatedTestCaseResponse.model_validate(response.json())

    async def get_test_case(
        self,
        test_case_id: str,
    ) -> TestCaseResponse:
        """Get a specific test case by ID.

        Args:
            test_case_id: Test case UUID

        Returns:
            TestCaseResponse with test case details

        Raises:
            httpx.HTTPError: If request fails (404 if not found)
        """
        async with self._get_client() as client:
            response = await client.get(f"/test-cases/{test_case_id}")
            response.raise_for_status()
            return TestCaseResponse.model_validate(response.json())

    async def delete_test_case(
        self,
        test_case_id: str,
    ) -> None:
        """Delete a test case.

        Args:
            test_case_id: Test case UUID

        Raises:
            httpx.HTTPError: If request fails (404 if not found)
        """
        async with self._get_client() as client:
            response = await client.delete(f"/test-cases/{test_case_id}")
            response.raise_for_status()

    # =========================================================================
    # Test Run Methods
    # =========================================================================

    async def execute_test_run(
        self,
        test_case_id: str,
        model_provider: str,
        model_name: str,
        temperature: float = 0.4,
        timeout: int = 30,
        max_retries: int = 3,
        base_url: str | None = None,
    ) -> TestRunResponse:
        """Execute a test case and create a test run.

        Args:
            test_case_id: Test case UUID to execute
            model_provider: LLM provider name
            model_name: Model identifier
            temperature: Model temperature (0.0-2.0)
            timeout: Model timeout in seconds
            max_retries: Maximum retries on failure
            base_url: Custom base URL for provider

        Returns:
            TestRunResponse with test run details

        Raises:
            httpx.HTTPError: If request fails
        """
        payload = TestRunExecuteRequest(
            model_settings=ModelSettingsCreate(
                provider=model_provider,
                model=model_name,
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
                base_url=base_url,
            )
        )

        async with self._get_client() as client:
            response = await client.post(
                f"/test-cases/{test_case_id}/run",
                json=payload.model_dump(mode="json", exclude_none=True),
            )
            response.raise_for_status()
            return TestRunResponse.model_validate(response.json())

    async def list_test_runs(
        self,
        test_case_id: str | None = None,
        mcp_server_url: str | None = None,
        tool_name: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> PaginatedTestRunResponse:
        """List test runs with optional filters.

        Args:
            test_case_id: Filter by test case ID
            mcp_server_url: Filter by MCP server URL
            tool_name: Filter by selected tool name
            offset: Number of records to skip
            limit: Maximum records to return

        Returns:
            PaginatedTestRunResponse with test runs

        Raises:
            httpx.HTTPError: If request fails
        """
        params: dict = {"offset": offset, "limit": limit}
        if test_case_id:
            params["test_case_id"] = test_case_id
        if mcp_server_url:
            params["mcp_server_url"] = mcp_server_url
        if tool_name:
            params["tool_name"] = tool_name

        async with self._get_client() as client:
            response = await client.get("/test-runs", params=params)
            response.raise_for_status()
            return PaginatedTestRunResponse.model_validate(response.json())

    async def get_test_run(
        self,
        test_run_id: str,
    ) -> TestRunResponse:
        """Get a specific test run by ID.

        Args:
            test_run_id: Test run UUID

        Returns:
            TestRunResponse with test run details

        Raises:
            httpx.HTTPError: If request fails (404 if not found)
        """
        async with self._get_client() as client:
            response = await client.get(f"/test-runs/{test_run_id}")
            response.raise_for_status()
            return TestRunResponse.model_validate(response.json())

    async def poll_test_run_completion(
        self,
        test_run_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> TestRunResponse:
        """Poll for test run completion.

        Args:
            test_run_id: Test run UUID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait for completion

        Returns:
            TestRunResponse with completed test run

        Raises:
            httpx.HTTPError: If request fails
            TimeoutError: If timeout exceeded
        """
        start_time = time.monotonic()
        while (time.monotonic() - start_time) < timeout:
            result = await self.get_test_run(test_run_id)
            if result.status in ("completed", "failed"):
                return result
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Test run {test_run_id} did not complete within {timeout}s")

    # =========================================================================
    # Similarity Methods
    # =========================================================================

    def _convert_urls_to_server_configs(self, server_urls: list[str]) -> list[MCPServerConfig]:
        """Convert list of URLs to MCPServerConfig objects.

        Supports two formats:
        - URL only: "http://localhost:3000/sse" (uses default transport)
        - URL with transport: "http://localhost:3000/sse:sse"

        Args:
            server_urls: List of MCP server URLs (optionally with transport)

        Returns:
            List of MCPServerConfig objects
        """
        configs = []
        for url in server_urls:
            # Check if transport is specified (format: url:transport)
            # Use rsplit to handle URLs with ports (e.g., http://localhost:8080)
            parts = url.rsplit(":", 1)

            if len(parts) == 2:
                url_part, potential_transport = parts
                # Valid transports are 'sse' or 'streamable-http'
                if potential_transport in ("sse", "streamable-http"):
                    # Verify the URL part is still valid (starts with http:// or https://)
                    if url_part.startswith(("http://", "https://")):
                        configs.append(MCPServerConfig(url=url_part, transport=potential_transport))
                        continue

            # No valid transport found, treat entire string as URL with default transport
            configs.append(MCPServerConfig(url=url))

        return configs

    async def analyze_similarity(
        self,
        server_urls: list[str],
        threshold: float = 0.85,
        method: str = "embedding",
        embedding_model: str | None = None,
        compute_full_similarity: bool = False,
        include_recommendations: bool = False,
    ) -> SimilarityAnalysisResponse:
        """Analyze tool similarity across MCP servers.

        Args:
            server_urls: List of MCP server URLs
            threshold: Similarity threshold for flagging (0.0-1.0)
            method: Analysis method (embedding, description_overlap)
            embedding_model: Optional embedding model override
            compute_full_similarity: Include parameter similarity
            include_recommendations: Generate AI recommendations

        Returns:
            SimilarityAnalysisResponse with matrix and optional recommendations

        Raises:
            httpx.HTTPError: If request fails
        """
        mcp_servers = self._convert_urls_to_server_configs(server_urls)
        payload: dict = {
            "mcp_servers": [config.model_dump() for config in mcp_servers],
            "similarity_threshold": threshold,
            "compute_full_similarity": compute_full_similarity,
            "include_recommendations": include_recommendations,
        }

        # Only include optional fields if they differ from defaults
        if method != "embedding":
            payload["analysis_methods"] = [method]

        if embedding_model:
            payload["embedding_model"] = embedding_model

        async with self._get_client() as client:
            response = await client.post("/similarity/analyze", json=payload)
            response.raise_for_status()
            return SimilarityAnalysisResponse.model_validate(response.json())

    async def get_overlap_matrix(
        self,
        server_urls: list[str],
    ) -> OverlapMatrixResponse:
        """Generate capability overlap matrix with dimension breakdown.

        Args:
            server_urls: List of MCP server URLs

        Returns:
            OverlapMatrixResponse with weighted dimensions

        Raises:
            httpx.HTTPError: If request fails
        """
        mcp_servers = self._convert_urls_to_server_configs(server_urls)
        payload = {
            "mcp_servers": [config.model_dump() for config in mcp_servers],
        }

        async with self._get_client() as client:
            response = await client.post("/similarity/overlap-matrix", json=payload)
            response.raise_for_status()
            return OverlapMatrixResponse.model_validate(response.json())

    async def get_recommendations(
        self,
        server_urls: list[str],
        tool_names: list[str] | None = None,
    ) -> DifferentiationRecommendationResponse:
        """Get differentiation recommendations for exactly 2 tools.

        Args:
            server_urls: List of MCP server URLs (must yield exactly 2 tools)
            tool_names: Optional list of tool names to filter

        Returns:
            DifferentiationRecommendationResponse with recommendations

        Raises:
            httpx.HTTPError: If request fails
            ValueError: If not exactly 2 tools
        """
        mcp_servers = self._convert_urls_to_server_configs(server_urls)
        payload = {
            "mcp_servers": [config.model_dump() for config in mcp_servers],
        }
        if tool_names:
            payload["tool_names"] = tool_names

        async with self._get_client() as client:
            response = await client.post("/similarity/recommendations", json=payload)
            response.raise_for_status()
            return DifferentiationRecommendationResponse.model_validate(response.json())
