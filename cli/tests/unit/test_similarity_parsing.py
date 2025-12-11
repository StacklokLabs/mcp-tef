"""Unit tests for similarity command parsing utilities."""

import pytest

from mcp_tef_cli.commands.similarity import parse_server_urls, validate_threshold


class TestServerUrlParsing:
    """Test server URL parsing from comma-separated string."""

    def test_parse_single_url(self):
        """Single URL is parsed correctly."""
        urls = parse_server_urls("http://localhost:3000/sse")
        assert urls == ["http://localhost:3000/sse"]

    def test_parse_multiple_urls(self):
        """Multiple URLs are parsed correctly."""
        urls = parse_server_urls("http://localhost:3000/sse,http://localhost:3001/mcp")
        assert urls == ["http://localhost:3000/sse", "http://localhost:3001/mcp"]

    def test_parse_urls_with_whitespace(self):
        """URLs with surrounding whitespace are trimmed."""
        urls = parse_server_urls("  http://localhost:3000/sse , http://localhost:3001/mcp  ")
        assert urls == ["http://localhost:3000/sse", "http://localhost:3001/mcp"]

    def test_parse_empty_string_raises(self):
        """Empty string raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            parse_server_urls("")

    def test_parse_whitespace_only_raises(self):
        """Whitespace-only string raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            parse_server_urls("   ")

    def test_parse_none_raises(self):
        """None value raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            parse_server_urls(None)

    def test_parse_empty_segments_filtered(self):
        """Empty segments from double commas are filtered out."""
        urls = parse_server_urls("http://localhost:3000/sse,,http://localhost:3001/mcp")
        assert urls == ["http://localhost:3000/sse", "http://localhost:3001/mcp"]


class TestThresholdValidation:
    """Test threshold value validation."""

    def test_valid_threshold(self):
        """Valid threshold in range passes."""
        result = validate_threshold(0.85)
        assert result == 0.85

    def test_threshold_at_lower_bound(self):
        """Threshold at 0.0 is valid."""
        result = validate_threshold(0.0)
        assert result == 0.0

    def test_threshold_at_upper_bound(self):
        """Threshold at 1.0 is valid."""
        result = validate_threshold(1.0)
        assert result == 1.0

    def test_threshold_below_range_raises(self):
        """Threshold below 0.0 raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            validate_threshold(-0.1)

    def test_threshold_above_range_raises(self):
        """Threshold above 1.0 raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            validate_threshold(1.5)

    def test_threshold_way_out_of_range_raises(self):
        """Threshold way out of range raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            validate_threshold(100.0)
