"""Integration tests for test-case CLI command."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from mcp_tef_cli.commands.test_case import test_case
from mcp_tef_cli.constants import (
    EXIT_INVALID_ARGUMENTS,
    EXIT_REQUEST_TIMEOUT,
    EXIT_RESOURCE_NOT_FOUND,
    EXIT_SUCCESS,
    EXIT_TEF_SERVER_UNREACHABLE,
)

pytestmark = [pytest.mark.integration]


def mock_test_case_response(
    test_case_id: str = "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    name: str = "Weather test",
    query: str = "What is the weather in San Francisco?",
    expected_tool_calls: list[dict] | None = None,
    order_dependent_matching: bool = False,
) -> dict:
    """Generate mock test case response."""
    # Default: single tool call
    if expected_tool_calls is None:
        expected_tool_calls = [
            {
                "mcp_server_url": "http://localhost:3000/sse",
                "tool_name": "get_weather",
                "parameters": None,
            }
        ]

    return {
        "id": test_case_id,
        "name": name,
        "query": query,
        "expected_tool_calls": expected_tool_calls,
        "order_dependent_matching": order_dependent_matching,
        "available_mcp_servers": ["http://localhost:3000/sse"],
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-15T10:30:00Z",
    }


def mock_paginated_test_case_response(count: int = 3) -> dict:
    """Generate mock paginated test case response."""
    items = [
        mock_test_case_response(
            test_case_id=f"test-case-{i}",
            name=f"Test Case {i}",
            query=f"Query {i}",
        )
        for i in range(count)
    ]
    return {
        "items": items,
        "total": count,
        "offset": 0,
        "limit": 50,
    }


class TestTestCaseCreateCommand:
    """Test test-case create CLI command."""

    @respx.mock
    def test_create_test_case_success(self):
        """Successful creation displays results."""
        respx.post("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(201, json=mock_test_case_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "Weather test",
                "--query",
                "What is the weather in San Francisco?",
                "--expected-tool-calls",
                '[{"mcp_server_url":"http://localhost:3000/sse","tool_name":"get_weather"}]',
                "--servers",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Weather test" in result.output
        assert "created successfully" in result.output.lower()

    @respx.mock
    def test_create_negative_test_case(self):
        """Test case without expected tool (negative test) succeeds."""
        respx.post("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(
                201,
                json=mock_test_case_response(
                    expected_tool_calls=None,
                ),
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "No tool test",
                "--query",
                "What is 2+2?",
                "--servers",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    def test_create_validation_error_server_not_in_servers(self):
        """Error when expected tool call server not in servers list."""
        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "Invalid test",
                "--query",
                "Test query",
                "--expected-tool-calls",
                (
                    '[{"mcp_server_url":"http://localhost:9999/sse",'
                    '"tool_name":"get_weather"}]'  # Not in servers
                ),
                "--servers",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_INVALID_ARGUMENTS
        assert "must be in" in result.output.lower()

    @respx.mock
    def test_create_json_output(self):
        """JSON output format returns valid JSON."""
        respx.post("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(201, json=mock_test_case_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "Weather test",
                "--query",
                "What is the weather?",
                "--expected-tool-calls",
                '[{"mcp_server_url":"http://localhost:3000/sse","tool_name":"get_weather"}]',
                "--servers",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "id" in data
        assert data["name"] == "Weather test"

    @respx.mock
    def test_create_with_expected_params(self):
        """Creation with expected parameters succeeds."""
        expected_tool_calls = [
            {
                "mcp_server_url": "http://localhost:3000/sse",
                "tool_name": "get_weather",
                "parameters": {"location": "San Francisco"},
            }
        ]
        respx.post("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(
                201,
                json=mock_test_case_response(expected_tool_calls=expected_tool_calls),
            )
        )

        runner = CliRunner()
        expected_tool_calls_json = (
            '[{"mcp_server_url":"http://localhost:3000/sse",'
            '"tool_name":"get_weather","parameters":{"location":"San Francisco"}}]'
        )
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "Weather test",
                "--query",
                "What is the weather?",
                "--expected-tool-calls",
                expected_tool_calls_json,
                "--servers",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_create_timeout_error(self):
        """Timeout error is handled gracefully."""
        respx.post("http://localhost:8000/test-cases").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "create",
                "--url",
                "http://localhost:8000",
                "--name",
                "Weather test",
                "--query",
                "What is the weather?",
                "--servers",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_REQUEST_TIMEOUT


class TestTestCaseListCommand:
    """Test test-case list CLI command."""

    @respx.mock
    def test_list_test_cases_success(self):
        """Successful listing displays test cases."""
        respx.get("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_case_response(3))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "list",
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "3 total" in result.output
        assert "Test Case 0" in result.output

    @respx.mock
    def test_list_test_cases_empty(self):
        """Empty list is handled gracefully."""
        respx.get("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_case_response(0))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "list",
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "0 total" in result.output or "No test cases" in result.output

    @respx.mock
    def test_list_json_output(self):
        """JSON output format returns valid JSON."""
        respx.get("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_case_response(2))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
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

    @respx.mock
    def test_list_with_pagination(self):
        """Pagination parameters are passed correctly."""
        route = respx.get("http://localhost:8000/test-cases").mock(
            return_value=httpx.Response(200, json=mock_paginated_test_case_response(1))
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "list",
                "--url",
                "http://localhost:8000",
                "--offset",
                "10",
                "--limit",
                "25",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert route.called
        request = route.calls[0].request
        assert "offset=10" in str(request.url)
        assert "limit=25" in str(request.url)


class TestTestCaseGetCommand:
    """Test test-case get CLI command."""

    @respx.mock
    def test_get_test_case_success(self):
        """Successful get displays test case details."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        respx.get(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            return_value=httpx.Response(200, json=mock_test_case_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "get",
                test_case_id,
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Weather test" in result.output
        assert test_case_id in result.output

    @respx.mock
    def test_get_test_case_not_found(self):
        """404 error returns appropriate exit code."""
        test_case_id = "nonexistent-id"
        respx.get(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            return_value=httpx.Response(404, text="Not found")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "get",
                test_case_id,
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code == EXIT_RESOURCE_NOT_FOUND
        assert "not found" in result.output.lower()

    @respx.mock
    def test_get_json_output(self):
        """JSON output format returns valid JSON."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        respx.get(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            return_value=httpx.Response(200, json=mock_test_case_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "get",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert data["id"] == test_case_id


class TestTestCaseDeleteCommand:
    """Test test-case delete CLI command."""

    @respx.mock
    def test_delete_test_case_success(self):
        """Successful deletion with --yes flag."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        respx.delete(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            return_value=httpx.Response(204)
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "delete",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--yes",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "deleted successfully" in result.output.lower()

    @respx.mock
    def test_delete_test_case_not_found(self):
        """404 error returns appropriate exit code."""
        test_case_id = "nonexistent-id"
        respx.delete(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            return_value=httpx.Response(404, text="Not found")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "delete",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--yes",
            ],
        )

        assert result.exit_code == EXIT_RESOURCE_NOT_FOUND
        assert "not found" in result.output.lower()

    def test_delete_aborted_without_yes(self):
        """Deletion aborted when user declines confirmation."""
        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "delete",
                "some-id",
                "--url",
                "http://localhost:8000",
            ],
            input="n\n",  # Decline confirmation
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "aborted" in result.output.lower()

    @respx.mock
    def test_delete_connection_error(self):
        """Connection error is handled gracefully."""
        test_case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        respx.delete(f"http://localhost:8000/test-cases/{test_case_id}").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        runner = CliRunner()
        result = runner.invoke(
            test_case,
            [
                "delete",
                test_case_id,
                "--url",
                "http://localhost:8000",
                "--yes",
            ],
        )

        assert result.exit_code == EXIT_TEF_SERVER_UNREACHABLE
