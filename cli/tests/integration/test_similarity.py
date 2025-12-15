"""Integration tests for similarity CLI commands."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from mcp_tef_cli.commands.similarity import similarity
from mcp_tef_cli.constants import (
    EXIT_INVALID_ARGUMENTS,
    EXIT_REQUEST_TIMEOUT,
    EXIT_SUCCESS,
    EXIT_TEF_SERVER_UNREACHABLE,
)

pytestmark = [pytest.mark.integration]


def mock_matrix_response():
    """Return a mock SimilarityMatrixResponse JSON."""
    return {
        "tool_ids": ["tool-1", "tool-2", "tool-3"],
        "matrix": [
            [1.0, 0.85, 0.45],
            [0.85, 1.0, 0.32],
            [0.45, 0.32, 1.0],
        ],
        "threshold": 0.85,
        "flagged_pairs": [
            {
                "tool_a_id": "tool-1",
                "tool_b_id": "tool-2",
                "similarity_score": 0.85,
            }
        ],
        "generated_at": "2025-01-15T10:30:00Z",
    }


def mock_analysis_response():
    """Return a mock SimilarityAnalysisResponse JSON."""
    response = mock_matrix_response()
    response["recommendations"] = None
    return response


def mock_analysis_response_with_recommendations():
    """Return a mock SimilarityAnalysisResponse with recommendations."""
    response = mock_matrix_response()
    response["recommendations"] = [
        {
            "tool_pair": ["tool-1", "tool-2"],
            "similarity_score": 0.85,
            "issues": [
                {
                    "issue_type": "naming_clarity",
                    "description": "Both tools use similar naming",
                    "tool_a_id": "tool-1",
                    "tool_b_id": "tool-2",
                    "evidence": {"common_terms": ["weather"]},
                }
            ],
            "recommendations": [
                {
                    "issue": "naming_clarity",
                    "tool_id": "tool-1",
                    "recommendation": "Rename to clarify scope",
                    "rationale": "Distinguishes from similar tools",
                    "priority": "high",
                    "revised_description": "Get current weather",
                    "apply_commands": None,
                }
            ],
        }
    ]
    return response


def mock_overlap_response():
    """Return a mock OverlapMatrixResponse JSON."""
    return {
        "tool_ids": ["tool-1", "tool-2"],
        "matrix": [
            [1.0, 0.75],
            [0.75, 1.0],
        ],
        "dimensions": {
            "semantic": 0.50,
            "description": 0.30,
            "parameters": 0.20,
        },
        "generated_at": "2025-01-15T10:30:00Z",
    }


def mock_recommendations_response():
    """Return a mock DifferentiationRecommendationResponse JSON."""
    return {
        "tool_pair": ["tool-1", "tool-2"],
        "similarity_score": 0.94,
        "issues": [
            {
                "issue_type": "naming_clarity",
                "description": "Both tools use weather-related naming",
                "tool_a_id": "tool-1",
                "tool_b_id": "tool-2",
                "evidence": {"common_terms": ["weather", "location"]},
            }
        ],
        "recommendations": [
            {
                "issue": "naming_clarity",
                "tool_id": "tool-1",
                "recommendation": "Rename to 'get_current_weather'",
                "rationale": "Distinguishes from forecast tools",
                "priority": "high",
                "revised_description": "Get current real-time weather conditions",
                "apply_commands": None,
            },
            {
                "issue": "naming_clarity",
                "tool_id": "tool-2",
                "recommendation": "Add use-case examples to description",
                "rationale": "Clarifies bulk/batch use case",
                "priority": "medium",
                "revised_description": None,
                "apply_commands": None,
            },
        ],
        "generated_at": "2025-01-15T10:30:00Z",
    }


class TestSimilarityAnalyzeCommand:
    """Test similarity analyze CLI command."""

    @respx.mock
    def test_analyze_success(self):
        """Successful analysis displays results table."""
        respx.post("http://localhost:8000/similarity/analyze").mock(
            return_value=httpx.Response(200, json=mock_analysis_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Similarity Analysis Results" in result.output
        assert "tool-1" in result.output or "T1" in result.output

    @respx.mock
    def test_analyze_with_recommendations(self):
        """Analysis with recommendations flag shows recommendations."""
        respx.post("http://localhost:8000/similarity/analyze").mock(
            return_value=httpx.Response(200, json=mock_analysis_response_with_recommendations())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--include-recommendations",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Recommendations" in result.output
        assert "naming_clarity" in result.output

    @respx.mock
    def test_analyze_json_output(self):
        """JSON format outputs valid JSON."""
        respx.post("http://localhost:8000/similarity/analyze").mock(
            return_value=httpx.Response(200, json=mock_analysis_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "tool_ids" in data
        assert "matrix" in data
        assert "flagged_pairs" in data

    @respx.mock
    def test_analyze_verbose_output(self):
        """Verbose flag shows detailed output."""
        respx.post("http://localhost:8000/similarity/analyze").mock(
            return_value=httpx.Response(200, json=mock_analysis_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--verbose",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_analyze_with_custom_threshold(self):
        """Custom threshold is sent in request."""
        route = respx.post("http://localhost:8000/similarity/analyze").mock(
            return_value=httpx.Response(200, json=mock_analysis_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--threshold",
                "0.90",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["similarity_threshold"] == 0.90

    def test_analyze_invalid_threshold(self):
        """Invalid threshold shows error."""
        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--threshold",
                "1.5",
            ],
        )

        assert result.exit_code == EXIT_INVALID_ARGUMENTS

    @respx.mock
    def test_analyze_timeout(self):
        """Timeout error shows helpful message."""
        respx.post("http://localhost:8000/similarity/analyze").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "analyze",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_REQUEST_TIMEOUT
        assert "Request timed out" in result.output


class TestSimilarityMatrixCommand:
    """Test similarity matrix CLI command."""

    @respx.mock
    def test_matrix_success(self):
        """Successful matrix generation displays table."""
        respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Similarity Matrix" in result.output

    @respx.mock
    def test_matrix_json_output(self):
        """JSON format outputs valid JSON."""
        respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "tool_ids" in data
        assert "matrix" in data
        assert len(data["tool_ids"]) == 3
        assert len(data["matrix"]) == 3

    @respx.mock
    def test_matrix_with_threshold(self):
        """Custom threshold is applied."""
        route = respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--threshold",
                "0.75",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["similarity_threshold"] == 0.75

    @respx.mock
    def test_matrix_http_error(self):
        """HTTP error is handled gracefully."""
        respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_TEF_SERVER_UNREACHABLE


class TestSimilarityOverlapCommand:
    """Test similarity overlap CLI command."""

    @respx.mock
    def test_overlap_success(self):
        """Successful overlap matrix displays table."""
        respx.post("http://localhost:8000/similarity/overlap-matrix").mock(
            return_value=httpx.Response(200, json=mock_overlap_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "overlap",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Capability Overlap Matrix" in result.output
        assert "Dimension Weights" in result.output

    @respx.mock
    def test_overlap_json_output(self):
        """JSON format outputs valid JSON with dimensions."""
        respx.post("http://localhost:8000/similarity/overlap-matrix").mock(
            return_value=httpx.Response(200, json=mock_overlap_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "overlap",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "tool_ids" in data
        assert "matrix" in data
        assert "dimensions" in data
        assert "semantic" in data["dimensions"]


class TestSimilarityRecommendCommand:
    """Test similarity recommend CLI command."""

    @respx.mock
    def test_recommend_success(self):
        """Successful recommendations display table."""
        respx.post("http://localhost:8000/similarity/recommendations").mock(
            return_value=httpx.Response(200, json=mock_recommendations_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "recommend",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Differentiation Recommendations" in result.output
        assert "tool-1" in result.output
        assert "tool-2" in result.output

    @respx.mock
    def test_recommend_json_output(self):
        """JSON format outputs valid JSON."""
        respx.post("http://localhost:8000/similarity/recommendations").mock(
            return_value=httpx.Response(200, json=mock_recommendations_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "recommend",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        data = json.loads(result.output)
        assert "tool_pair" in data
        assert "similarity_score" in data
        assert "issues" in data
        assert "recommendations" in data

    @respx.mock
    def test_recommend_displays_issues(self):
        """Issues are displayed in output."""
        respx.post("http://localhost:8000/similarity/recommendations").mock(
            return_value=httpx.Response(200, json=mock_recommendations_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "recommend",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Issues Identified" in result.output
        assert "naming_clarity" in result.output

    @respx.mock
    def test_recommend_displays_priorities(self):
        """Recommendation priorities are displayed."""
        respx.post("http://localhost:8000/similarity/recommendations").mock(
            return_value=httpx.Response(200, json=mock_recommendations_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "recommend",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "HIGH" in result.output
        assert "MEDIUM" in result.output


class TestCommonOptions:
    """Test common options across all similarity commands."""

    @respx.mock
    def test_insecure_flag(self):
        """--insecure flag is accepted."""
        respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--insecure",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_custom_timeout(self):
        """--timeout option is accepted."""
        respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse",
                "--timeout",
                "120",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS

    @respx.mock
    def test_multiple_server_urls(self):
        """Multiple server URLs are parsed correctly."""
        route = respx.post("http://localhost:8000/similarity/matrix").mock(
            return_value=httpx.Response(200, json=mock_matrix_response())
        )

        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
                "--server-urls",
                "http://localhost:3000/sse,http://localhost:3001/mcp",
            ],
        )

        assert result.exit_code == EXIT_SUCCESS
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert "mcp_servers" in request_body
        assert len(request_body["mcp_servers"]) == 2
        # Verify each server config has url and transport
        for server_config in request_body["mcp_servers"]:
            assert "url" in server_config
            assert "transport" in server_config
            assert server_config["transport"] in ("sse", "streamable-http")

    def test_missing_server_urls(self):
        """Missing --server-urls shows error."""
        runner = CliRunner()
        result = runner.invoke(
            similarity,
            [
                "matrix",
                "--url",
                "http://localhost:8000",
            ],
        )

        assert result.exit_code != EXIT_SUCCESS
        assert "server-urls" in result.output.lower() or "missing" in result.output.lower()
