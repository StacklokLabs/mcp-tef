"""Integration tests for test-run CLI command."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from mcp_tef_cli.commands.test_run import test_run
from mcp_tef_cli.constants import (
    EXIT_INVALID_ARGUMENTS,
    EXIT_REQUEST_TIMEOUT,
    EXIT_RESOURCE_NOT_FOUND,
    EXIT_SUCCESS,
    EXIT_TEF_SERVER_UNREACHABLE,
)

pytestmark = [pytest.mark.integration]


def mock_test_run_response(
    test_run_id: str = "b2c3d4e5-f6a7-8901-bcde-f23456789012",
    test_case_id: str = "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    status: str = "completed",
    classification: str | None = "TP",
    selected_tool_name: str | None = "get_weather",
) -> dict:
    """Generate mock test run response."""
    selected_tool = None
    if selected_tool_name:
        selected_tool = {
            "id": "tool-123",
            "name": selected_tool_name,
            "mcp_server_url": "http://localhost:3000/sse",
            "parameters": {"location": "San Francisco"},
        }

    expected_tool = {
        "id": "tool-123",
        "name": "get_weather",
        "mcp_server_url": "http://localhost:3000/sse",
        "parameters": {"location": "San Francisco"},
    }

    return {
        "id": test_run_id,
        "test_case_id": test_case_id,
        "model_settings": {
            "created_at": "2024-01-01T00:00:00Z",
            "id": "settings-123",
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "temperature": 0.4,
            "timeout": 30,
            "max_retries": 3,
            "base_url": None,
        },
        "status": status,
        "llm_response_raw": '{"tool": "get_weather"}',
        "selected_tool": selected_tool,
        "expected_tool": expected_tool,
        "extracted_parameters": {"location": "San Francisco"},
        "parameter_correctness": 9.5,
        "llm_confidence": "high",
        "confidence_score": "robust",
        "classification": classification,
        "execution_time_ms": 1234,
        "error_message": None,
        "created_at": "2025-01-15T10:30:00Z",
        "completed_at": "2025-01-15T10:30:01Z" if status == "completed" else None,
    }


def mock_paginated_test_run_response(count: int = 3) -> dict:
    """Generate mock paginated test run response."""
    items = [mock_test_run_response(test_run_id=f"test-run-{i}") for i in range(count)]
    return {
        "items": items,
        "total": count,
        "offset": 0,
        "limit": 100,
    }


class TestTestRunExecuteCommand:
    """Test test-run execute CLI command."""

    @respx.mock
    def test_execute_success_with_wait(self):
        """Successful execution with wait displays results."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        test_run_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"

        # First request returns pending
        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(
                201,
                json=mock_test_run_response(
                    test_run_id=test_run_id,
                    status="pending",
                    classification=None,
                ),
            )
        )

        # Poll returns completed
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            return_value=httpx.Response(
                200,
                json=mock_test_run_response(
                    test_run_id=test_run_id,
                    status="completed",
                    classification="TP",
                ),
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "completed" in result.output.lower()
        assert "TP" in result.output

    @respx.mock
    def test_execute_no_wait(self):
        """Execution with --no-wait returns immediately."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(
                201,
                json=mock_test_run_response(status="pending", classification=None),
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
                "--no-wait",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "pending" in result.output.lower()
        assert "test-run get" in result.output

    @respx.mock
    def test_execute_json_output(self):
        """JSON output format returns valid JSON."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(201, json=mock_test_run_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
                "--format",
                "json",
                "--no-wait",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "id" in data
        assert "status" in data

    @respx.mock
    def test_execute_fp_exit_code(self):
        """False Positive classification returns exit code 0 (completed successfully)."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(
                201,
                json=mock_test_run_response(
                    status="completed",
                    classification="FP",
                ),
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
                "--no-wait",
            ],
        )

        # FP/FN are valid test outcomes, not errors - exit 0 per Unix convention
        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_execute_failed_exit_code(self):
        """Failed test run returns exit code 2."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        failed_response = mock_test_run_response(status="failed", classification=None)
        failed_response["error_message"] = "LLM request failed"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(201, json=failed_response)
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
                "--no-wait",
            ],
        )

        assert result.exit_code == 2

    def test_execute_invalid_temperature(self):
        """Invalid temperature returns error."""
        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                "some-id",
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--temperature",
                "5.0",  # Invalid
            ],
        )

        assert result.exit_code == EXIT_INVALID_ARGUMENTS
        assert "temperature" in result.output.lower()

    @respx.mock
    def test_execute_test_case_not_found(self):
        """404 error returns appropriate exit code."""
        test_case_id = "nonexistent-id"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(404, text="Not found")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
            ],
        )

        assert result.exit_code == EXIT_RESOURCE_NOT_FOUND
        assert "not found" in result.output.lower()

    @respx.mock
    def test_execute_api_key_via_env(self, monkeypatch):
        """API key can be provided via TEF_API_KEY environment variable."""
        monkeypatch.setenv("TEF_API_KEY", "sk-env-test-key")

        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        route = respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            return_value=httpx.Response(201, json=mock_test_run_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--no-wait",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        # Verify the API key was sent in the header
        assert route.called
        request = route.calls[0].request
        assert request.headers.get("X-Model-API-Key") == "sk-env-test-key"

    @respx.mock
    def test_execute_timeout_error(self):
        """Timeout error is handled gracefully."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        respx.post(f"http://localhost:8000/test-cases/{test_case_id}/run").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "execute",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--model-provider",
                "openrouter",
                "--model-name",
                "anthropic/claude-sonnet-4-5-20250929",
                "--api-key",
                "sk-xxx",
            ],
        )

        assert result.exit_code == EXIT_REQUEST_TIMEOUT


class TestTestRunListCommand:
    """Test test-run list CLI command."""

    @respx.mock
    def test_list_test_runs_success(self):
        """Successful listing displays test runs."""
        respx.get("http://localhost:8000/test-runs").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_run_response(3))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "list",
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "3 total" in result.output
        assert "1-3 of 3 test runs" in result.output

    @respx.mock
    def test_list_test_runs_empty(self):
        """Empty list is handled gracefully."""
        respx.get("http://localhost:8000/test-runs").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_run_response(0))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "list",
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "0 results" in result.output or "No test runs" in result.output

    @respx.mock
    def test_list_with_filters(self):
        """Filter parameters are passed correctly."""
        route = respx.get("http://localhost:8000/test-runs").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_run_response(1))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "list",
                "--url",
                "http://localhost:8000",
                "--test-case-id",
                "abc123",
                "--tool-name",
                "get_weather",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert route.called
        request = route.calls[0].request
        assert "test_case_id=abc123" in str(request.url)
        assert "tool_name=get_weather" in str(request.url)

    @respx.mock
    def test_list_json_output(self):
        """JSON output format returns valid JSON."""
        respx.get("http://localhost:8000/test-runs").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_run_response(2))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "list",
                "--url",
                "http://localhost:8000",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "items" in data
        assert len(data["items"]) == 2


class TestTestRunGetCommand:
    """Test test-run get CLI command."""

    @respx.mock
    def test_get_test_run_success(self):
        """Successful get displays test run details."""
        test_run_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            return_value=httpx.Response(200, json=mock_test_run_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "get",
                test_run_id,
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert test_run_id in result.output
        assert "completed" in result.output.lower()

    @respx.mock
    def test_get_test_run_not_found(self):
        """404 error returns appropriate exit code."""
        test_run_id = "nonexistent-id"
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            return_value=httpx.Response(404, text="Not found")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "get",
                test_run_id,
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_RESOURCE_NOT_FOUND
        assert "not found" in result.output.lower()

    @respx.mock
    def test_get_json_output(self):
        """JSON output format returns valid JSON."""
        test_run_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            return_value=httpx.Response(200, json=mock_test_run_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "get",
                test_run_id,
                "--url",
                "http://localhost:8000",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert data["id"] == test_run_id

    @respx.mock
    def test_get_verbose_output(self):
        """Verbose output includes raw LLM response."""
        test_run_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            return_value=httpx.Response(200, json=mock_test_run_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "get",
                test_run_id,
                "--url",
                "http://localhost:8000",
                "--verbose",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Raw LLM Response" in result.output

    @respx.mock
    def test_get_connection_error(self):
        """Connection error is handled gracefully."""
        test_run_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
        respx.get(f"http://localhost:8000/test-runs/{test_run_id}").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_run,
            [
                "get",
                test_run_id,
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_TEF_SERVER_UNREACHABLE
