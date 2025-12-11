"""Integration tests for tool-quality CLI command."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from mcp_tef_cli.commands.tool_quality import tool_quality
from mcp_tef_cli.constants import (
    EXIT_REQUEST_TIMEOUT,
    EXIT_SUCCESS,
    EXIT_TEF_SERVER_UNREACHABLE,
)

pytestmark = [pytest.mark.integration]


def mock_quality_response():
    """Return a mock ToolQualityResponse JSON."""
    return {"results": [mock_tool_result()], "errors": None}


def mock_tool_result():
    """Return a mock ToolQualityResult."""
    return {
        "tool_name": "get_weather",
        "tool_description": "Get current weather",
        "evaluation_result": {
            "clarity": {"score": 8, "explanation": "Clear description"},
            "completeness": {"score": 7, "explanation": "Good coverage"},
            "conciseness": {"score": 9, "explanation": "Concise"},
            "suggested_description": "Retrieve weather data for a location",
        },
    }


class TestToolQualityCommand:
    """Test tool-quality CLI command."""

    @respx.mock
    def test_successful_evaluation(self):
        """Successful evaluation displays results table."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "get_weather" in result.output
        assert "8/10" in result.output

    @respx.mock
    def test_verbose_output(self):
        """--verbose flag shows detailed explanations."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--verbose",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Clear description" in result.output
        assert "Retrieve weather data" in result.output

    @respx.mock
    def test_json_output(self):
        """--format json outputs valid JSON."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["tool_name"] == "get_weather"

    @respx.mock
    def test_partial_failure_exit_code(self):
        """Partial failure (some servers failed) returns exit code 1."""
        response_with_errors = {
            "results": [mock_tool_result()],
            "errors": ["http://localhost:3001/mcp: Connection refused"],
        }
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=response_with_errors)
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse,http://localhost:3001/mcp",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == 1
        assert "Connection refused" in result.output

    @respx.mock
    def test_complete_failure_exit_code(self):
        """Complete failure (no servers could be evaluated) returns exit code 2."""
        response_all_errors = {
            "results": [],
            "errors": ["http://localhost:3000/sse: Connection refused"],
        }
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=response_all_errors)
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == 2
        assert "Connection refused" in result.output

    @respx.mock
    def test_timeout_error_shows_help(self):
        """Timeout error mentions --timeout option."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == EXIT_REQUEST_TIMEOUT
        assert "--timeout" in result.output

    def test_missing_required_args(self):
        """Missing required arguments shows error."""
        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--server-urls",
                "http://localhost:3000/sse",
                # Missing --model-provider and --model-name
            ],
        )

        assert result.exit_code != 0
        # Click shows "Missing option" error
        assert "missing" in result.output.lower() or "required" in result.output.lower()

    @respx.mock
    def test_insecure_flag_works(self):
        """--insecure flag is accepted."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--insecure",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_custom_timeout(self):
        """--timeout option is accepted."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--timeout",
                "120",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_custom_tef_url(self):
        """--url option changes the mcp-tef server URL."""
        respx.get("https://mcp-tef.example.com:8080/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "https://mcp-tef.example.com:8080",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--insecure",  # For self-signed certs
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_http_error_handling(self):
        """HTTP errors are handled gracefully."""
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == EXIT_TEF_SERVER_UNREACHABLE
        assert "500" in result.output or "error" in result.output.lower()

    @respx.mock
    def test_api_key_via_cli(self):
        """API key can be provided via --api-key."""
        route = respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "anthropic",
                "--model-name",
                "claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-ant-test-key",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        # Verify the API key was sent in the header
        assert route.called
        request = route.calls[0].request
        assert request.headers.get("X-Model-API-Key") == "sk-ant-test-key"

    @respx.mock
    def test_api_key_via_env(self, monkeypatch):
        """API key can be provided via TEF_API_KEY environment variable."""
        monkeypatch.setenv("TEF_API_KEY", "sk-env-test-key")

        route = respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=mock_quality_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "anthropic",
                "--model-name",
                "claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        # Verify the API key was sent in the header
        assert route.called
        request = route.calls[0].request
        assert request.headers.get("X-Model-API-Key") == "sk-env-test-key"

    @respx.mock
    def test_multiple_tools_in_response(self):
        """Multiple tools in response are displayed correctly."""
        response = {
            "results": [
                mock_tool_result(),
                {
                    "tool_name": "search_database",
                    "tool_description": "Search the database",
                    "evaluation_result": {
                        "clarity": {"score": 6, "explanation": "Too vague"},
                        "completeness": {"score": 5, "explanation": "Missing details"},
                        "conciseness": {"score": 8, "explanation": "Brief"},
                        "suggested_description": None,
                    },
                },
            ],
            "errors": None,
        }
        respx.get("http://localhost:8000/mcp-servers/tools/quality").mock(
            return_value=httpx.Response(200, json=response)
        )

        runner = CliRunner()
        result = runner.invoke(
            tool_quality,
            [
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "get_weather" in result.output
        assert "search_database" in result.output
        assert "8/10" in result.output
        assert "6/10" in result.output
        assert "Evaluated 2 tool(s)" in result.output
