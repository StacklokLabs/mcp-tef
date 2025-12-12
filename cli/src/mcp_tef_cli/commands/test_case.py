"""Test case management commands for mcp-tef CLI."""

import asyncio
import json
import os
import re
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from mcp_tef_cli.client import ClientConfig, TefClient
from mcp_tef_cli.constants import (
    DEFAULT_CONTAINER_NAME,
    EXIT_INVALID_ARGUMENTS,
    EXIT_SUCCESS,
)
from mcp_tef_cli.models import (
    MCPServerConfig,
    PaginatedTestCaseResponse,
    TestCaseCreate,
    TestCaseResponse,
)
from mcp_tef_cli.output import print_error, print_success
from mcp_tef_cli.utils import handle_api_errors, resolve_tef_url

console = Console()

DEFAULT_TIMEOUT = 60


def parse_json_params(value: str | None) -> dict | None:
    """Parse JSON parameter string.

    Args:
        value: JSON string or None

    Returns:
        Parsed dict or None

    Raises:
        click.BadParameter: If JSON is invalid
    """
    if value is None:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Invalid JSON: {e}") from e


def substitute_env_vars(content: str, env_vars: dict[str, str] | None = None) -> str:
    """Substitute environment variables in content string.

    Supports ${VAR_NAME} syntax. Variables are resolved from:
    1. Explicitly provided env_vars dict (highest priority)
    2. OS environment variables

    Unresolved variables are left as-is (no error raised).

    Args:
        content: String content with potential ${VAR} placeholders
        env_vars: Optional dict of variable name -> value overrides

    Returns:
        Content with variables substituted
    """

    # Pattern matches ${VAR_NAME} where VAR_NAME is alphanumeric + underscore
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        # Check explicit overrides first, then environment
        if env_vars and var_name in env_vars:
            return env_vars[var_name]
        return os.environ.get(var_name, match.group(0))  # Keep original if not found

    return pattern.sub(replace, content)


def load_test_cases_from_file(
    file_path: str,
    env_vars: dict[str, str] | None = None,
) -> list[TestCaseCreate]:
    """Load and validate test case definitions from a JSON file.

    The file can contain either:
    - A single test case object
    - An array of test case objects

    Environment variable placeholders (${VAR_NAME}) in the file are substituted
    before parsing. Variables are resolved from the env_vars parameter first,
    then from OS environment variables.

    Args:
        file_path: Path to the JSON file
        env_vars: Optional dict of variable overrides for substitution

    Returns:
        List of validated TestCaseCreate models

    Raises:
        click.BadParameter: If file cannot be read, parsed, or validation fails
    """
    path = Path(file_path)

    if not path.exists():
        raise click.BadParameter(f"File not found: {file_path}")

    if not path.is_file():
        raise click.BadParameter(f"Not a file: {file_path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise click.BadParameter(f"Cannot read file: {e}") from e

    # Substitute environment variables before parsing JSON
    content = substitute_env_vars(content, env_vars)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Invalid JSON in file: {e}") from e

    # Normalize to list
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        if not data:
            raise click.BadParameter("File contains empty array")
        items = data
    else:
        raise click.BadParameter("File must contain a JSON object or array of objects")

    # Validate each item using Pydantic model
    test_cases: list[TestCaseCreate] = []
    for i, item in enumerate(items):
        try:
            test_cases.append(TestCaseCreate.model_validate(item))
        except ValidationError as e:
            prefix = f"Test case [{i}]: " if len(items) > 1 else ""
            # Format validation errors nicely
            errors = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()
            )
            raise click.BadParameter(f"{prefix}{errors}") from e

    return test_cases


def format_test_case_table(tc: TestCaseResponse, title: str = "Test Case") -> None:
    """Format test case as table output.

    Args:
        tc: Test case response
        title: Table title
    """
    console.print()
    console.print(f"[bold]{title}[/bold]")
    console.print("=" * 65)
    console.print()
    console.print(f"ID:               {tc.id}")
    console.print(f"Name:             {tc.name}")
    console.print(f"Query:            {tc.query}")
    console.print(f"Expected Server:  {tc.expected_mcp_server_url or '(none)'}")
    console.print(f"Expected Tool:    {tc.expected_tool_name or '(none)'}")
    if tc.expected_parameters:
        console.print(f"Expected Params:  {json.dumps(tc.expected_parameters)}")
    console.print("Available Servers:")
    for server in tc.available_mcp_servers:
        console.print(f"  - {server.url} ({server.transport})")
    console.print(f"Created:          {tc.created_at}")
    console.print(f"Updated:          {tc.updated_at}")


def format_test_case_json(tc: TestCaseResponse) -> None:
    """Format test case as JSON output.

    Args:
        tc: Test case response
    """
    click.echo(json.dumps(tc.model_dump(mode="json"), indent=2, default=str))


def format_test_case_list_table(response: PaginatedTestCaseResponse) -> None:
    """Format test case list as table output.

    Args:
        response: Paginated test case response
    """
    console.print()
    console.print(f"[bold]Test Cases ({response.total} total)[/bold]")
    console.print("=" * 65)

    if not response.items:
        console.print("[yellow]No test cases found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Query")
    table.add_column("Expected Tool")

    for tc in response.items:
        # Truncate long query
        query = tc.query[:30] + "..." if len(tc.query) > 30 else tc.query
        table.add_row(
            tc.id,
            tc.name,
            query,
            tc.expected_tool_name or "(none)",
        )

    console.print()
    console.print(table)

    # Pagination info
    start = response.offset + 1
    end = response.offset + len(response.items)
    console.print()
    console.print(f"Showing {start}-{end} of {response.total} test cases")


def format_test_case_list_json(response: PaginatedTestCaseResponse) -> None:
    """Format test case list as JSON output.

    Args:
        response: Paginated test case response
    """
    click.echo(json.dumps(response.model_dump(mode="json"), indent=2, default=str))


# =============================================================================
# CLI Command Group
# =============================================================================


@click.group(name="test-case")
def test_case() -> None:
    """Manage test cases for query-tool alignment evaluation.

    Test cases define a user query and the expected tool that should be
    selected by an LLM. Use these commands to create, list, view, and
    delete test cases.
    """
    pass


# =============================================================================
# Create Subcommand
# =============================================================================


def parse_set_option(values: tuple[str, ...]) -> dict[str, str]:
    """Parse --set KEY=VALUE options into a dict.

    Args:
        values: Tuple of KEY=VALUE strings

    Returns:
        Dict mapping variable names to values

    Raises:
        click.BadParameter: If a value doesn't contain '='
    """
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise click.BadParameter(f"Invalid --set format: '{value}'. Expected KEY=VALUE format.")
        key, val = value.split("=", 1)
        if not key:
            raise click.BadParameter(f"Invalid --set format: '{value}'. Key cannot be empty.")
        result[key] = val
    return result


def parse_server_spec(server_spec: str) -> MCPServerConfig:
    """Parse a server specification into MCPServerConfig.

    Supports two formats:
    - URL only: "http://localhost:3000/sse" (uses default transport)
    - URL with transport: "http://localhost:3000/sse:sse"

    Args:
        server_spec: Server specification string

    Returns:
        MCPServerConfig object

    Raises:
        click.BadParameter: If format is invalid or transport is not recognized
    """
    # Validate basic format
    if not server_spec.startswith(("http://", "https://")):
        raise click.BadParameter(
            f"Invalid server URL: '{server_spec}'. Must start with http:// or https://"
        )

    # Check if transport is specified (format: url:transport)
    # Use rsplit to handle URLs with ports (e.g., http://localhost:8080)
    # We only treat it as transport if the part after the last ':' is a valid transport
    parts = server_spec.rsplit(":", 1)

    if len(parts) == 2:
        url, potential_transport = parts
        # Check if this is actually a transport spec or just part of the URL
        # Valid transports are 'sse' or 'streamable-http'
        if potential_transport in ("sse", "streamable-http"):
            # Verify the URL part is still valid (starts with http:// or https://)
            if not url.startswith(("http://", "https://")):
                raise click.BadParameter(
                    f"Invalid URL in server spec: '{url}'. Must start with http:// or https://"
                )
            return MCPServerConfig(url=url, transport=potential_transport)

    # No valid transport found, treat entire string as URL with default transport
    return MCPServerConfig(url=server_spec)


@test_case.command(name="create")
@click.option("--name", default=None, help="Descriptive name for the test case")
@click.option("--query", default=None, help="User query to evaluate")
@click.option(
    "--expected-server",
    default=None,
    help="Expected MCP server URL (null for negative tests)",
)
@click.option(
    "--expected-tool",
    default=None,
    help="Expected tool name (null for negative tests)",
)
@click.option(
    "--expected-params",
    default=None,
    help="Expected parameters as JSON object",
)
@click.option(
    "--servers",
    default=None,
    help=(
        "Comma-separated MCP server specifications. "
        "Format: 'URL' or 'URL:transport'. "
        "Transport defaults to 'streamable-http' if not specified. "
        "Examples: 'http://localhost:3000/sse:sse' or 'http://localhost:3001'"
    ),
)
@click.option(
    "--from-file",
    "from_file",
    type=click.Path(exists=False),
    default=None,
    help="JSON file containing test case definition(s). Can be a single object or array.",
)
@click.option(
    "--set",
    "set_vars",
    multiple=True,
    help="Set variable for template substitution (KEY=VALUE). Can be repeated.",
)
@click.option(
    "--url",
    "tef_url",
    default=None,
    help="mcp-tef server URL (bypasses Docker container discovery)",
)
@click.option(
    "--container-name",
    default=None,
    help=f"Docker container name for URL discovery (default: {DEFAULT_CONTAINER_NAME})",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--timeout",
    type=int,
    default=DEFAULT_TIMEOUT,
    help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def create(
    name: str | None,
    query: str | None,
    expected_server: str | None,
    expected_tool: str | None,
    expected_params: str | None,
    servers: str | None,
    from_file: str | None,
    set_vars: tuple[str, ...],
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    timeout: int,
    insecure: bool,
) -> None:
    """Create a new test case for query-tool alignment evaluation.

    Test cases can be created either via command-line options or by loading
    definitions from a JSON file. When using --from-file, the file can contain
    a single test case object or an array of test cases for batch import.

    \b
    JSON Structure (for --from-file):
      {
        "name": "Test case name",              // required
        "query": "User query to evaluate",     // required
        "available_mcp_servers": [             // required, non-empty
          {
            "url": "${MCP_SERVER_URL}",        // required, supports variable substitution
            "transport": "streamable-http"     // optional, defaults to "streamable-http"
          }
        ],
        "expected_mcp_server_url": "...",      // optional (null for negative tests)
        "expected_tool_name": "tool_name",     // optional (must pair with server)
        "expected_parameters": {"key": "val"}  // optional (requires tool)
      }

    \b
    Variable Substitution:
      JSON files support ${VAR_NAME} placeholders that are substituted before
      parsing. Variables are resolved from --set options first, then from
      environment variables.

    Examples:

      \b
      # Create test case with expected tool (SSE transport)
      mtef test-case create \\
        --name "Weather test" \\
        --query "What is the weather in San Francisco?" \\
        --expected-server "http://localhost:3000/sse" \\
        --expected-tool "get_weather" \\
        --servers "http://localhost:3000/sse:sse"

      \b
      # Create test case with multiple servers (mixed transports)
      mtef test-case create \\
        --name "Multi-server test" \\
        --query "Get my calendar events" \\
        --servers "http://localhost:3000:sse,http://localhost:3001"

      \b
      # Create negative test case (no tool should be selected)
      mtef test-case create \\
        --name "No tool needed" \\
        --query "What is 2 + 2?" \\
        --servers "http://localhost:3000/sse:sse"

      \b
      # Create from JSON file (single or multiple test cases)
      mtef test-case create --from-file test-cases.json

      \b
      # Create from JSON file with variable substitution
      mtef test-case create \\
        --from-file test-cases.json \\
        --set MCP_SERVER_URL=http://localhost:3000/sse
    """
    # Determine input mode: file-based or parameter-based
    if from_file:
        # File-based creation - load and validate from JSON file
        if any([name, query, servers, expected_server, expected_tool, expected_params]):
            print_error(
                "Cannot combine --from-file with other test case options "
                "(--name, --query, --servers, --expected-server, --expected-tool, "
                "--expected-params)"
            )
            raise SystemExit(EXIT_INVALID_ARGUMENTS)

        # Parse --set options for variable substitution
        try:
            env_vars = parse_set_option(set_vars) if set_vars else None
        except click.BadParameter as e:
            print_error("Invalid --set option", str(e))
            raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

        try:
            test_cases = load_test_cases_from_file(from_file, env_vars=env_vars)
        except click.BadParameter as e:
            print_error("File error", str(e))
            raise SystemExit(EXIT_INVALID_ARGUMENTS) from e
    else:
        # --set is only valid with --from-file
        if set_vars:
            print_error("--set can only be used with --from-file")
            raise SystemExit(EXIT_INVALID_ARGUMENTS)
        # Parameter-based creation - validate required options
        if not name:
            print_error("--name is required (or use --from-file)")
            raise SystemExit(EXIT_INVALID_ARGUMENTS)
        if not query:
            print_error("--query is required (or use --from-file)")
            raise SystemExit(EXIT_INVALID_ARGUMENTS)
        if not servers:
            print_error("--servers is required (or use --from-file)")
            raise SystemExit(EXIT_INVALID_ARGUMENTS)

        # Parse servers from comma-separated string and convert to MCPServerConfig
        server_specs = [spec.strip() for spec in servers.split(",") if spec.strip()]
        server_configs = [parse_server_spec(spec) for spec in server_specs]

        # Parse expected parameters JSON
        try:
            expected_parameters = parse_json_params(expected_params)
        except click.BadParameter as e:
            print_error("Invalid expected parameters", str(e))
            raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

        # Build TestCaseCreate model - Pydantic validates all constraints
        try:
            test_cases = [
                TestCaseCreate(
                    name=name,
                    query=query,
                    available_mcp_servers=server_configs,
                    expected_mcp_server_url=expected_server,
                    expected_tool_name=expected_tool,
                    expected_parameters=expected_parameters,
                )
            ]
        except ValidationError as e:
            errors = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()
            )
            print_error("Validation error", errors)
            raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Resolve URL
    url = resolve_tef_url(tef_url, container_name, output_format)

    async def _create_single(tc: TestCaseCreate) -> TestCaseResponse:
        config = ClientConfig(
            base_url=url,
            timeout=float(timeout),
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            return await client.create_test_case(
                name=tc.name,
                query=tc.query,
                available_mcp_servers=tc.available_mcp_servers,
                expected_mcp_server_url=tc.expected_mcp_server_url,
                expected_tool_name=tc.expected_tool_name,
                expected_parameters=tc.expected_parameters,
            )
        finally:
            await client.close()

    async def _create_all() -> list[TestCaseResponse]:
        results = []
        for tc in test_cases:
            result = await _create_single(tc)
            results.append(result)
        return results

    with handle_api_errors(url):
        results = asyncio.run(_create_all())

        if output_format == "json":
            if len(results) == 1:
                format_test_case_json(results[0])
            else:
                # Output array for batch imports
                click.echo(
                    json.dumps([r.model_dump(mode="json") for r in results], indent=2, default=str)
                )
        else:
            for i, result in enumerate(results):
                if len(results) > 1:
                    format_test_case_table(
                        result, title=f"Test Case Created ({i + 1}/{len(results)})"
                    )
                else:
                    format_test_case_table(result, title="Test Case Created")
            console.print()
            if len(results) == 1:
                print_success("Test case created successfully")
            else:
                print_success(f"{len(results)} test cases created successfully")

        raise SystemExit(EXIT_SUCCESS)


# =============================================================================
# List Subcommand
# =============================================================================


@test_case.command(name="list")
@click.option(
    "--url",
    "tef_url",
    default=None,
    help="mcp-tef server URL (bypasses Docker container discovery)",
)
@click.option(
    "--container-name",
    default=None,
    help=f"Docker container name for URL discovery (default: {DEFAULT_CONTAINER_NAME})",
)
@click.option(
    "--offset",
    type=int,
    default=0,
    help="Number of records to skip (default: 0)",
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum records to return (default: 50, max: 100)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def list_cmd(
    tef_url: str | None,
    container_name: str | None,
    offset: int,
    limit: int,
    output_format: str,
    insecure: bool,
) -> None:
    """List all test cases with pagination.

    Examples:

      \b
      # List all test cases
      mtef test-case list

      \b
      # With pagination
      mtef test-case list --offset 10 --limit 25

      \b
      # Output as JSON
      mtef test-case list --format json
    """
    url = resolve_tef_url(tef_url, container_name, output_format)

    async def _list() -> PaginatedTestCaseResponse:
        config = ClientConfig(
            base_url=url,
            timeout=60.0,
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            return await client.list_test_cases(offset=offset, limit=limit)
        finally:
            await client.close()

    with handle_api_errors(url):
        result = asyncio.run(_list())

        if output_format == "json":
            format_test_case_list_json(result)
        else:
            format_test_case_list_table(result)

        raise SystemExit(EXIT_SUCCESS)


# =============================================================================
# Get Subcommand
# =============================================================================


@test_case.command(name="get")
@click.argument("test_case_id")
@click.option(
    "--url",
    "tef_url",
    default=None,
    help="mcp-tef server URL (bypasses Docker container discovery)",
)
@click.option(
    "--container-name",
    default=None,
    help=f"Docker container name for URL discovery (default: {DEFAULT_CONTAINER_NAME})",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show available tools from MCP servers",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def get(
    test_case_id: str,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    verbose: bool,
    insecure: bool,
) -> None:
    """Get detailed information about a specific test case.

    Examples:

      \b
      # Get test case by ID
      mtef test-case get a1b2c3d4-e5f6-7890-abcd-ef1234567890

      \b
      # Output as JSON
      mtef test-case get a1b2c3d4-e5f6-7890-abcd-ef1234567890 --format json
    """
    url = resolve_tef_url(tef_url, container_name, output_format)

    async def _get() -> TestCaseResponse:
        config = ClientConfig(
            base_url=url,
            timeout=60.0,
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            return await client.get_test_case(test_case_id)
        finally:
            await client.close()

    with handle_api_errors(url, resource_type="Test case", resource_id=test_case_id):
        result = asyncio.run(_get())

        if output_format == "json":
            format_test_case_json(result)
        else:
            format_test_case_table(result, title="Test Case Details")

            # Verbose output - show available tools
            if verbose and result.available_tools:
                console.print()
                console.print("[bold]Available Tools by Server:[/bold]")
                for server_url, tools in result.available_tools.items():
                    console.print()
                    console.print(f"[cyan]Server: {server_url}[/cyan]")
                    if tools:
                        tool_table = Table(show_header=True)
                        tool_table.add_column("Tool Name", style="cyan")
                        tool_table.add_column("Description")
                        for tool in tools:
                            tool_table.add_row(tool.name, tool.description or "(no description)")
                        console.print(tool_table)
                    else:
                        console.print("  (no tools)")

        raise SystemExit(EXIT_SUCCESS)


# =============================================================================
# Delete Subcommand
# =============================================================================


@test_case.command(name="delete")
@click.argument("test_case_id")
@click.option(
    "--url",
    "tef_url",
    default=None,
    help="mcp-tef server URL (bypasses Docker container discovery)",
)
@click.option(
    "--container-name",
    default=None,
    help=f"Docker container name for URL discovery (default: {DEFAULT_CONTAINER_NAME})",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def delete(
    test_case_id: str,
    tef_url: str | None,
    container_name: str | None,
    yes: bool,
    insecure: bool,
) -> None:
    """Delete a test case.

    Examples:

      \b
      # Delete test case
      mtef test-case delete a1b2c3d4-e5f6-7890-abcd-ef1234567890

      \b
      # Skip confirmation
      mtef test-case delete a1b2c3d4-e5f6-7890-abcd-ef1234567890 --yes
    """
    # Confirm deletion
    if not yes:
        if not click.confirm(f"Delete test case {test_case_id}?"):
            console.print("[yellow]Aborted.[/yellow]")
            raise SystemExit(EXIT_SUCCESS)

    url = resolve_tef_url(tef_url, container_name, "table")

    async def _delete() -> None:
        config = ClientConfig(
            base_url=url,
            timeout=60.0,
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            await client.delete_test_case(test_case_id)
        finally:
            await client.close()

    with handle_api_errors(url, resource_type="Test case", resource_id=test_case_id):
        asyncio.run(_delete())
        print_success(f"Test case {test_case_id} deleted successfully")
        raise SystemExit(EXIT_SUCCESS)
