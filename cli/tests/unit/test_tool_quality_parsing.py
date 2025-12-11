"""Unit tests for tool-quality command parsing and formatting functions."""

import pytest

from mcp_tef_cli.commands.tool_quality import (
    parse_server_urls,
    resolve_api_key,
)
from mcp_tef_cli.models import (
    EvaluationDimensionResult,
    EvaluationResult,
    ToolQualityResult,
)


class TestServerUrlParsing:
    """Test server URL parsing from comma-separated string."""

    def test_parse_single_url(self):
        """Single URL returns list with one item."""
        urls = parse_server_urls("http://localhost:3000/sse")
        assert urls == ["http://localhost:3000/sse"]

    def test_parse_multiple_urls(self):
        """Comma-separated URLs are split correctly."""
        urls = parse_server_urls("http://localhost:3000/sse,http://localhost:3001/mcp")
        assert urls == ["http://localhost:3000/sse", "http://localhost:3001/mcp"]

    def test_parse_urls_with_whitespace(self):
        """Whitespace around URLs is trimmed."""
        urls = parse_server_urls("http://localhost:3000/sse , http://localhost:3001/mcp")
        assert urls == ["http://localhost:3000/sse", "http://localhost:3001/mcp"]

    def test_parse_empty_string_raises(self):
        """Empty string raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="At least one server URL"):
            parse_server_urls("")

    def test_parse_only_whitespace_raises(self):
        """String with only whitespace raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="At least one server URL"):
            parse_server_urls("   ")

    def test_parse_only_commas_raises(self):
        """String with only commas raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="At least one server URL"):
            parse_server_urls(",,,")


class TestApiKeyResolution:
    """Test API key resolution from CLI args and environment."""

    def test_cli_arg_takes_precedence(self, monkeypatch):
        """CLI --api-key overrides environment variable."""
        monkeypatch.setenv("TEF_API_KEY", "env-key")
        key = resolve_api_key(cli_key="cli-key")
        assert key == "cli-key"

    def test_falls_back_to_env_var(self, monkeypatch):
        """Uses TEF_API_KEY when no CLI arg provided."""
        monkeypatch.setenv("TEF_API_KEY", "env-key")
        key = resolve_api_key(cli_key=None)
        assert key == "env-key"

    def test_returns_none_when_not_set(self, monkeypatch):
        """Returns None when neither CLI nor env is set."""
        monkeypatch.delenv("TEF_API_KEY", raising=False)
        key = resolve_api_key(cli_key=None)
        assert key is None

    def test_empty_cli_key_uses_env(self, monkeypatch):
        """Empty string CLI key still uses env variable."""
        monkeypatch.setenv("TEF_API_KEY", "env-key")
        # Empty string is falsy, so should fall back to env
        key = resolve_api_key(cli_key="")
        assert key == "env-key"


class TestToolQualityModels:
    """Test Pydantic model validation."""

    def test_evaluation_dimension_result_valid(self):
        """Valid dimension result parses correctly."""
        result = EvaluationDimensionResult(score=8, explanation="Clear description")
        assert result.score == 8
        assert result.explanation == "Clear description"

    def test_evaluation_result_valid(self):
        """Valid evaluation result parses correctly."""
        result = EvaluationResult(
            clarity=EvaluationDimensionResult(score=8, explanation="Clear"),
            completeness=EvaluationDimensionResult(score=7, explanation="Good"),
            conciseness=EvaluationDimensionResult(score=9, explanation="Concise"),
            suggested_description="Improved description",
        )
        assert result.clarity.score == 8
        assert result.completeness.score == 7
        assert result.conciseness.score == 9
        assert result.suggested_description == "Improved description"

    def test_evaluation_result_optional_suggestion(self):
        """Evaluation result with no suggested description."""
        result = EvaluationResult(
            clarity=EvaluationDimensionResult(score=8, explanation="Clear"),
            completeness=EvaluationDimensionResult(score=7, explanation="Good"),
            conciseness=EvaluationDimensionResult(score=9, explanation="Concise"),
        )
        assert result.suggested_description is None

    def test_tool_quality_result_valid(self):
        """Valid tool quality result parses correctly."""
        result = ToolQualityResult(
            tool_name="get_weather",
            tool_description="Get current weather",
            evaluation_result=EvaluationResult(
                clarity=EvaluationDimensionResult(score=8, explanation="Clear"),
                completeness=EvaluationDimensionResult(score=7, explanation="Good"),
                conciseness=EvaluationDimensionResult(score=9, explanation="Concise"),
            ),
        )
        assert result.tool_name == "get_weather"
        assert result.tool_description == "Get current weather"
        assert result.evaluation_result.clarity.score == 8
