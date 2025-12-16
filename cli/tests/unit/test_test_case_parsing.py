"""Unit tests for test case command parsing utilities."""

import pytest
from click import BadParameter
from mcp_tef_models.schemas import TestCaseCreate
from pydantic import ValidationError

from mcp_tef_cli.commands.test_case import (
    load_test_cases_from_file,
    parse_json_params,
    parse_set_option,
    substitute_env_vars,
)


class TestCaseCreateValidation:
    """Test validation via TestCaseCreate Pydantic model."""

    def test_valid_test_case_with_expected_tool(self):
        """Valid test case with expected tool passes validation."""
        tc = TestCaseCreate(
            name="Test",
            query="What is the weather?",
            available_mcp_servers=["http://localhost:3000/sse"],
            expected_mcp_server_url="http://localhost:3000/sse",
            expected_tool_name="get_weather",
        )
        assert tc.name == "Test"
        assert tc.expected_tool_name == "get_weather"

    def test_valid_negative_test_case(self):
        """Valid negative test case (no expected tool) passes validation."""
        tc = TestCaseCreate(
            name="Negative test",
            query="What is 2 + 2?",
            available_mcp_servers=["http://localhost:3000/sse"],
        )
        assert tc.expected_tool_name is None
        assert tc.expected_mcp_server_url is None

    def test_only_server_provided_raises(self):
        """Only server without tool raises ValidationError."""
        with pytest.raises(ValidationError, match="both be provided or both omitted"):
            TestCaseCreate(
                name="Test",
                query="Query",
                available_mcp_servers=["http://localhost:3000/sse"],
                expected_mcp_server_url="http://localhost:3000/sse",
            )

    def test_only_tool_provided_raises(self):
        """Only tool without server raises ValidationError."""
        with pytest.raises(ValidationError, match="both be provided or both omitted"):
            TestCaseCreate(
                name="Test",
                query="Query",
                available_mcp_servers=["http://localhost:3000/sse"],
                expected_tool_name="get_weather",
            )

    def test_expected_server_not_in_available_servers_raises(self):
        """Expected server not in available servers raises ValidationError."""
        with pytest.raises(ValidationError, match="must be in available_mcp_servers"):
            TestCaseCreate(
                name="Test",
                query="Query",
                available_mcp_servers=["http://localhost:3000/sse"],
                expected_mcp_server_url="http://other-server:3000/sse",
                expected_tool_name="get_weather",
            )

    def test_expected_params_without_tool_raises(self):
        """Expected parameters without tool raises ValidationError."""
        with pytest.raises(
            ValidationError, match="expected_parameters requires expected_tool_name"
        ):
            TestCaseCreate(
                name="Test",
                query="Query",
                available_mcp_servers=["http://localhost:3000/sse"],
                expected_parameters={"location": "SF"},
            )

    def test_empty_servers_list_raises(self):
        """Empty available servers list raises ValidationError."""
        with pytest.raises(ValidationError):
            TestCaseCreate(
                name="Test",
                query="Query",
                available_mcp_servers=[],
            )


class TestJsonParameterParsing:
    """Test JSON parameter parsing."""

    def test_parse_valid_json_simple(self):
        """Simple valid JSON is parsed correctly."""
        params = parse_json_params('{"location": "SF"}')
        assert params == {"location": "SF"}

    def test_parse_valid_json_complex(self):
        """Complex valid JSON is parsed correctly."""
        params = parse_json_params('{"location": "San Francisco", "units": "fahrenheit"}')
        assert params == {"location": "San Francisco", "units": "fahrenheit"}

    def test_parse_valid_json_nested(self):
        """Nested valid JSON is parsed correctly."""
        params = parse_json_params('{"query": {"city": "NYC", "country": "USA"}}')
        assert params == {"query": {"city": "NYC", "country": "USA"}}

    def test_parse_valid_json_array(self):
        """JSON with array values is parsed correctly."""
        params = parse_json_params('{"cities": ["NYC", "LA", "SF"]}')
        assert params == {"cities": ["NYC", "LA", "SF"]}

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises BadParameter."""
        with pytest.raises(BadParameter, match="Invalid JSON"):
            parse_json_params("not json")

    def test_parse_incomplete_json_raises(self):
        """Incomplete JSON raises BadParameter."""
        with pytest.raises(BadParameter, match="Invalid JSON"):
            parse_json_params('{"location": ')

    def test_parse_none_returns_none(self):
        """None input returns None."""
        assert parse_json_params(None) is None

    def test_parse_empty_object(self):
        """Empty JSON object is parsed correctly."""
        params = parse_json_params("{}")
        assert params == {}


class TestLoadTestCasesFromFile:
    """Test loading test cases from JSON file."""

    def test_load_single_test_case(self, tmp_path):
        """Load single test case from JSON file."""
        file_path = tmp_path / "test_case.json"
        file_path.write_text(
            """{
            "name": "Weather test",
            "query": "What is the weather?",
            "available_mcp_servers": ["http://localhost:3000/sse"],
            "expected_mcp_server_url": "http://localhost:3000/sse",
            "expected_tool_name": "get_weather"
        }"""
        )

        test_cases = load_test_cases_from_file(str(file_path))

        assert len(test_cases) == 1
        assert test_cases[0].name == "Weather test"
        assert test_cases[0].expected_tool_name == "get_weather"

    def test_load_multiple_test_cases(self, tmp_path):
        """Load multiple test cases from JSON array."""
        file_path = tmp_path / "test_cases.json"
        file_path.write_text(
            """[
            {
                "name": "Test 1",
                "query": "Query 1",
                "available_mcp_servers": ["http://localhost:3000/sse"]
            },
            {
                "name": "Test 2",
                "query": "Query 2",
                "available_mcp_servers": ["http://localhost:3001/sse"]
            }
        ]"""
        )

        test_cases = load_test_cases_from_file(str(file_path))

        assert len(test_cases) == 2
        assert test_cases[0].name == "Test 1"
        assert test_cases[1].name == "Test 2"

    def test_load_file_not_found_raises(self):
        """Loading non-existent file raises BadParameter."""
        with pytest.raises(BadParameter, match="File not found"):
            load_test_cases_from_file("/nonexistent/path/file.json")

    def test_load_invalid_json_raises(self, tmp_path):
        """Loading file with invalid JSON raises BadParameter."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json")

        with pytest.raises(BadParameter, match="Invalid JSON"):
            load_test_cases_from_file(str(file_path))

    def test_load_empty_array_raises(self, tmp_path):
        """Loading file with empty array raises BadParameter."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("[]")

        with pytest.raises(BadParameter, match="empty array"):
            load_test_cases_from_file(str(file_path))

    def test_load_invalid_test_case_raises(self, tmp_path):
        """Loading file with invalid test case raises BadParameter."""
        file_path = tmp_path / "invalid_test_case.json"
        file_path.write_text(
            """{
            "name": "Missing required fields"
        }"""
        )

        with pytest.raises(BadParameter):
            load_test_cases_from_file(str(file_path))

    def test_load_validation_error_in_batch(self, tmp_path):
        """Loading batch with one invalid test case shows index in error."""
        file_path = tmp_path / "batch.json"
        file_path.write_text(
            """[
            {
                "name": "Valid",
                "query": "Query",
                "available_mcp_servers": ["http://localhost:3000/sse"]
            },
            {
                "name": "Invalid - missing query",
                "available_mcp_servers": ["http://localhost:3000/sse"]
            }
        ]"""
        )

        with pytest.raises(BadParameter, match=r"Test case \[1\]"):
            load_test_cases_from_file(str(file_path))

    def test_load_directory_raises(self, tmp_path):
        """Loading a directory instead of file raises BadParameter."""
        with pytest.raises(BadParameter, match="Not a file"):
            load_test_cases_from_file(str(tmp_path))


class TestSubstituteEnvVars:
    """Test environment variable substitution."""

    def test_substitute_single_var(self):
        """Single variable is substituted correctly."""
        content = '{"url": "${MY_VAR}"}'
        result = substitute_env_vars(content, {"MY_VAR": "http://localhost"})
        assert result == '{"url": "http://localhost"}'

    def test_substitute_multiple_vars(self):
        """Multiple variables are substituted correctly."""
        content = '{"server": "${SERVER}", "port": "${PORT}"}'
        result = substitute_env_vars(content, {"SERVER": "localhost", "PORT": "8080"})
        assert result == '{"server": "localhost", "port": "8080"}'

    def test_substitute_same_var_multiple_times(self):
        """Same variable appearing multiple times is substituted everywhere."""
        content = '["${URL}", "${URL}"]'
        result = substitute_env_vars(content, {"URL": "http://example.com"})
        assert result == '["http://example.com", "http://example.com"]'

    def test_substitute_from_os_environ(self, monkeypatch):
        """Variables are resolved from OS environment when not in env_vars."""
        monkeypatch.setenv("TEST_ENV_VAR", "from_os")
        content = '{"value": "${TEST_ENV_VAR}"}'
        result = substitute_env_vars(content, {})
        assert result == '{"value": "from_os"}'

    def test_explicit_env_vars_override_os(self, monkeypatch):
        """Explicit env_vars take precedence over OS environment."""
        monkeypatch.setenv("MY_VAR", "from_os")
        content = '{"value": "${MY_VAR}"}'
        result = substitute_env_vars(content, {"MY_VAR": "from_explicit"})
        assert result == '{"value": "from_explicit"}'

    def test_unresolved_var_kept_as_is(self):
        """Unresolved variables are left unchanged."""
        content = '{"value": "${UNDEFINED_VAR}"}'
        result = substitute_env_vars(content, {})
        assert result == '{"value": "${UNDEFINED_VAR}"}'

    def test_no_vars_returns_unchanged(self):
        """Content without variables is returned unchanged."""
        content = '{"name": "test", "value": 123}'
        result = substitute_env_vars(content, {"UNUSED": "value"})
        assert result == content

    def test_none_env_vars_uses_os_only(self, monkeypatch):
        """None env_vars still substitutes from OS environment."""
        monkeypatch.setenv("OS_VAR", "os_value")
        content = '{"value": "${OS_VAR}"}'
        result = substitute_env_vars(content, None)
        assert result == '{"value": "os_value"}'

    def test_var_with_numbers(self):
        """Variable names with numbers are supported."""
        content = '{"value": "${VAR_123}"}'
        result = substitute_env_vars(content, {"VAR_123": "numbered"})
        assert result == '{"value": "numbered"}'

    def test_var_starting_with_underscore(self):
        """Variable names starting with underscore are supported."""
        content = '{"value": "${_PRIVATE}"}'
        result = substitute_env_vars(content, {"_PRIVATE": "private_value"})
        assert result == '{"value": "private_value"}'

    def test_invalid_var_syntax_ignored(self):
        """Invalid variable syntax is not substituted."""
        content = '{"a": "$VAR", "b": "${}", "c": "${123}"}'
        result = substitute_env_vars(content, {"VAR": "value"})
        # None of these should be substituted
        assert result == content


class TestParseSetOption:
    """Test --set option parsing."""

    def test_parse_single_set(self):
        """Single KEY=VALUE is parsed correctly."""
        result = parse_set_option(("MY_VAR=value",))
        assert result == {"MY_VAR": "value"}

    def test_parse_multiple_sets(self):
        """Multiple KEY=VALUE pairs are parsed correctly."""
        result = parse_set_option(("VAR1=value1", "VAR2=value2"))
        assert result == {"VAR1": "value1", "VAR2": "value2"}

    def test_parse_value_with_equals(self):
        """Value containing '=' is parsed correctly."""
        result = parse_set_option(("URL=http://host?foo=bar",))
        assert result == {"URL": "http://host?foo=bar"}

    def test_parse_empty_value(self):
        """Empty value is allowed."""
        result = parse_set_option(("VAR=",))
        assert result == {"VAR": ""}

    def test_parse_empty_tuple(self):
        """Empty tuple returns empty dict."""
        result = parse_set_option(())
        assert result == {}

    def test_parse_missing_equals_raises(self):
        """Missing '=' raises BadParameter."""
        with pytest.raises(BadParameter, match="Expected KEY=VALUE"):
            parse_set_option(("INVALID",))

    def test_parse_empty_key_raises(self):
        """Empty key raises BadParameter."""
        with pytest.raises(BadParameter, match="Key cannot be empty"):
            parse_set_option(("=value",))

    def test_later_set_overrides_earlier(self):
        """Later --set for same key overrides earlier value."""
        result = parse_set_option(("VAR=first", "VAR=second"))
        assert result == {"VAR": "second"}


class TestLoadTestCasesWithEnvVars:
    """Test loading test cases with environment variable substitution."""

    def test_load_with_env_var_substitution(self, tmp_path):
        """Environment variables in file are substituted."""
        file_path = tmp_path / "test_case.json"
        file_path.write_text(
            """{
            "name": "Test",
            "query": "Query",
            "available_mcp_servers": ["${SERVER_URL}"],
            "expected_mcp_server_url": "${SERVER_URL}",
            "expected_tool_name": "tool"
        }"""
        )

        test_cases = load_test_cases_from_file(
            str(file_path), env_vars={"SERVER_URL": "http://localhost:3000/sse"}
        )

        assert len(test_cases) == 1
        assert len(test_cases[0].available_mcp_servers) == 1
        assert test_cases[0].available_mcp_servers[0].url == "http://localhost:3000/sse"
        assert test_cases[0].expected_mcp_server_url == "http://localhost:3000/sse"

    def test_load_multiple_with_env_vars(self, tmp_path):
        """Multiple test cases with same variable are all substituted."""
        file_path = tmp_path / "test_cases.json"
        file_path.write_text(
            """[
            {
                "name": "Test 1",
                "query": "Query 1",
                "available_mcp_servers": ["${URL}"]
            },
            {
                "name": "Test 2",
                "query": "Query 2",
                "available_mcp_servers": ["${URL}"]
            }
        ]"""
        )

        test_cases = load_test_cases_from_file(
            str(file_path), env_vars={"URL": "http://server:8000"}
        )

        assert len(test_cases) == 2
        assert len(test_cases[0].available_mcp_servers) == 1
        assert test_cases[0].available_mcp_servers[0].url == "http://server:8000"
        assert len(test_cases[1].available_mcp_servers) == 1
        assert test_cases[1].available_mcp_servers[0].url == "http://server:8000"

    def test_load_with_unresolved_var_fails_validation(self, tmp_path):
        """Unresolved variable that results in invalid URL fails validation."""
        file_path = tmp_path / "test_case.json"
        file_path.write_text(
            """{
            "name": "Test",
            "query": "Query",
            "available_mcp_servers": ["${UNDEFINED}"]
        }"""
        )

        # The unresolved ${UNDEFINED} is kept as-is, which is a valid string
        # but may not be a valid URL depending on use case
        # This should fail validation because ${UNDEFINED} doesn't match the URL pattern
        with pytest.raises(BadParameter):
            load_test_cases_from_file(str(file_path), env_vars={})

    def test_load_from_os_env(self, tmp_path, monkeypatch):
        """Variables are resolved from OS environment."""
        monkeypatch.setenv("MCP_TEST_SERVER", "http://from-os:9000")
        file_path = tmp_path / "test_case.json"
        file_path.write_text(
            """{
            "name": "Test",
            "query": "Query",
            "available_mcp_servers": ["${MCP_TEST_SERVER}"]
        }"""
        )

        test_cases = load_test_cases_from_file(str(file_path))

        assert len(test_cases[0].available_mcp_servers) == 1
        assert test_cases[0].available_mcp_servers[0].url == "http://from-os:9000"
