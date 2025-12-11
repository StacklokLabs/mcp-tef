"""Test run management commands for mcp-tef CLI."""

import asyncio
import json
import os

import click
from rich.console import Console
from rich.table import Table

from mcp_tef_cli.client import ClientConfig, TefClient
from mcp_tef_cli.constants import (
    DEFAULT_CONTAINER_NAME,
    EXIT_INVALID_ARGUMENTS,
    EXIT_SUCCESS,
)
from mcp_tef_cli.models import PaginatedTestRunResponse, TestRunResponse
from mcp_tef_cli.output import print_error, print_info, print_success, print_warning
from mcp_tef_cli.utils import handle_api_errors, resolve_tef_url

console = Console()

DEFAULT_TIMEOUT = 120
DEFAULT_POLL_INTERVAL = 2


def resolve_api_key(cli_key: str | None) -> str | None:
    """Resolve API key from CLI argument or environment variable.

    Args:
        cli_key: API key from CLI argument (takes precedence)

    Returns:
        Resolved API key or None if not set
    """
    if cli_key:
        return cli_key
    return os.environ.get("TEF_API_KEY")


def format_classification(classification: str | None) -> str:
    """Format classification with description.

    Args:
        classification: Classification code (TP, FP, TN, FN)

    Returns:
        Formatted string with description
    """
    descriptions = {
        "TP": "True Positive",
        "FP": "False Positive",
        "TN": "True Negative",
        "FN": "False Negative",
    }
    if not classification:
        return "-"
    desc = descriptions.get(classification, "")
    return f"{classification} ({desc})" if desc else classification


def format_test_run_table(tr: TestRunResponse, show_pending_hint: bool = False) -> None:
    """Format test run as table output.

    Args:
        tr: Test run response
        show_pending_hint: Show hint for checking pending runs
    """
    console.print()
    title = "Test Run Created" if tr.status == "pending" else "Test Run Results"
    console.print(f"[bold]{title}[/bold]")
    console.print("=" * 65)
    console.print()
    console.print(f"Test Run ID:      {tr.id}")
    console.print(f"Test Case:        {tr.test_case_id}")
    console.print(f"Status:           {tr.status}")

    if tr.status == "completed":
        console.print(f"Classification:   {format_classification(tr.classification)}")
        console.print()

        # Expected
        if tr.expected_tool:
            console.print("[bold]Expected:[/bold]")
            console.print(f"  Server:         {tr.expected_tool.mcp_server_url}")
            console.print(f"  Tool:           {tr.expected_tool.name}")
            if tr.expected_tool.parameters:
                console.print(f"  Parameters:     {json.dumps(tr.expected_tool.parameters)}")
        else:
            console.print("[bold]Expected:[/bold]  (no tool expected - negative test)")

        console.print()

        # Selected
        if tr.selected_tool:
            console.print("[bold]Selected (LLM):[/bold]")
            console.print(f"  Server:         {tr.selected_tool.mcp_server_url}")
            console.print(f"  Tool:           {tr.selected_tool.name}")
            if tr.selected_tool.parameters:
                console.print(f"  Parameters:     {json.dumps(tr.selected_tool.parameters)}")
        else:
            console.print("[bold]Selected (LLM):[/bold]  (none)")

        console.print()

        # Evaluation metrics
        console.print("[bold]Evaluation:[/bold]")
        tool_match = (
            tr.classification == "TP" or tr.classification == "TN" if tr.classification else None
        )
        if tool_match is True:
            console.print("  Tool Match:     [green]Correct[/green]")
        elif tool_match is False:
            console.print("  Tool Match:     [red]Incorrect[/red]")
        else:
            console.print("  Tool Match:     -")

        if tr.llm_confidence:
            console.print(f"  Confidence:     {tr.llm_confidence} ({tr.confidence_score or '-'})")
        if tr.parameter_correctness is not None:
            console.print(f"  Param Score:    {tr.parameter_correctness}/10")

        console.print()

        # Timing
        console.print("[bold]Timing:[/bold]")
        if tr.execution_time_ms:
            console.print(f"  Execution:      {tr.execution_time_ms:,} ms")
        console.print(f"  Created:        {tr.created_at}")
        if tr.completed_at:
            console.print(f"  Completed:      {tr.completed_at}")

    elif tr.status == "failed":
        console.print()
        console.print(f"[red]Error: {tr.error_message or 'Unknown error'}[/red]")
        console.print(f"Created:          {tr.created_at}")

    else:  # pending or running
        console.print(f"Created:          {tr.created_at}")

    # Model settings
    if tr.model_settings:
        console.print()
        model_str = f"{tr.model_settings.provider}/{tr.model_settings.model}"
        temp_str = f"temp={tr.model_settings.temperature}"
        console.print(f"Model: {model_str} ({temp_str})")

    if show_pending_hint and tr.status in ("pending", "running"):
        console.print()
        print_info(f"Test run submitted. Use 'mcp-tef-cli test-run get {tr.id}' to check status.")


def format_test_run_json(tr: TestRunResponse) -> None:
    """Format test run as JSON output.

    Args:
        tr: Test run response
    """
    click.echo(json.dumps(tr.model_dump(mode="json"), indent=2, default=str))


def format_test_run_list_table(response: PaginatedTestRunResponse) -> None:
    """Format test run list as table output.

    Args:
        response: Paginated test run response
    """
    console.print()
    console.print(f"[bold]Test Runs ({response.total} total)[/bold]")
    console.print("=" * 65)

    if not response.items:
        console.print("[yellow]No test runs found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Status")
    table.add_column("Classification")
    table.add_column("Selected Tool")
    table.add_column("Confidence")
    table.add_column("Time (ms)", justify="right")

    for tr in response.items:
        status_style = {
            "completed": "green",
            "failed": "red",
            "pending": "yellow",
            "running": "blue",
        }.get(tr.status, "")

        table.add_row(
            tr.id,
            f"[{status_style}]{tr.status}[/{status_style}]" if status_style else tr.status,
            tr.classification or "-",
            tr.selected_tool.name if tr.selected_tool else "(none)",
            tr.confidence_score or "-",
            f"{tr.execution_time_ms:,}" if tr.execution_time_ms else "-",
        )

    console.print()
    console.print(table)

    # Pagination info
    start = response.offset + 1
    end = response.offset + len(response.items)
    console.print()
    console.print(f"Showing {start}-{end} of {response.total} test runs")


def format_test_run_list_json(response: PaginatedTestRunResponse) -> None:
    """Format test run list as JSON output.

    Args:
        response: Paginated test run response
    """
    click.echo(json.dumps(response.model_dump(mode="json"), indent=2, default=str))


# =============================================================================
# CLI Command Group
# =============================================================================


@click.group(name="test-run")
def test_run() -> None:
    """Manage test runs for query-tool alignment evaluation.

    Test runs execute a test case with a specific LLM configuration and
    record the results. Use these commands to execute test cases, view
    results, and list past test runs.
    """
    pass


# =============================================================================
# Execute Subcommand
# =============================================================================


@test_run.command(name="execute")
@click.argument("test_case_id")
@click.option(
    "--model-provider",
    required=True,
    help="LLM provider (e.g., anthropic, openai, openrouter, ollama)",
)
@click.option(
    "--model-name",
    required=True,
    help="Model identifier (e.g., claude-sonnet-4-5-20250929)",
)
@click.option(
    "--api-key",
    default=None,
    help="API key for the model provider (or set TEF_API_KEY env var)",
)
@click.option(
    "--base-url",
    default=None,
    help="Custom base URL (for ollama, openrouter, etc.)",
)
@click.option(
    "--temperature",
    type=float,
    default=0.4,
    help="Model temperature (0.0-2.0, default: 0.4)",
)
@click.option(
    "--timeout",
    "model_timeout",
    type=int,
    default=30,
    help="Model timeout in seconds (1-300, default: 30)",
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    help="Maximum retries on failure (0-10, default: 3)",
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
    "--no-wait",
    is_flag=True,
    help="Return immediately without waiting for completion",
)
@click.option(
    "--poll-interval",
    type=int,
    default=DEFAULT_POLL_INTERVAL,
    help=f"Seconds between status checks when waiting (default: {DEFAULT_POLL_INTERVAL})",
)
@click.option(
    "--request-timeout",
    type=int,
    default=DEFAULT_TIMEOUT,
    help=f"HTTP request timeout in seconds (default: {DEFAULT_TIMEOUT})",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def execute(
    test_case_id: str,
    model_provider: str,
    model_name: str,
    api_key: str | None,
    base_url: str | None,
    temperature: float,
    model_timeout: int,
    max_retries: int,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    no_wait: bool,
    poll_interval: int,
    request_timeout: int,
    insecure: bool,
) -> None:
    """Execute a test case with specified LLM configuration.

    Examples:

      \b
      # Execute test case with OpenRouter
      mcp-tef-cli test-run execute a1b2c3d4-... \\
        --model-provider openrouter \\
        --model-name anthropic/claude-sonnet-4-5-20250929 \\
        --api-key sk-xxx

      \b
      # Execute with local Ollama (no API key required)
      mcp-tef-cli test-run execute a1b2c3d4-... \\
        --model-provider ollama \\
        --model-name llama3.2 \\
        --base-url http://localhost:11434

      \b
      # Don't wait for completion
      mcp-tef-cli test-run execute a1b2c3d4-... \\
        --model-provider openrouter \\
        --model-name anthropic/claude-sonnet-4-5-20250929 \\
        --no-wait
    """
    # Validate temperature
    if not 0.0 <= temperature <= 2.0:
        print_error("Invalid temperature", "Must be between 0.0 and 2.0")
        raise SystemExit(EXIT_INVALID_ARGUMENTS)

    # Validate model timeout
    if not 1 <= model_timeout <= 300:
        print_error("Invalid model timeout", "Must be between 1 and 300 seconds")
        raise SystemExit(EXIT_INVALID_ARGUMENTS)

    # Validate max retries
    if not 0 <= max_retries <= 10:
        print_error("Invalid max retries", "Must be between 0 and 10")
        raise SystemExit(EXIT_INVALID_ARGUMENTS)

    # Resolve URL and API key
    url = resolve_tef_url(tef_url, container_name, output_format)
    resolved_api_key = resolve_api_key(api_key)

    async def _execute() -> TestRunResponse:
        config = ClientConfig(
            base_url=url,
            timeout=float(request_timeout),
            verify_ssl=not insecure,
            api_key=resolved_api_key,
        )
        client = TefClient(config)
        try:
            # Execute the test run
            result = await client.execute_test_run(
                test_case_id=test_case_id,
                model_provider=model_provider,
                model_name=model_name,
                temperature=temperature,
                timeout=model_timeout,
                max_retries=max_retries,
                base_url=base_url,
            )

            # Wait for completion unless --no-wait
            if not no_wait and result.status in ("pending", "running"):
                result = await client.poll_test_run_completion(
                    test_run_id=result.id,
                    poll_interval=float(poll_interval),
                    timeout=float(request_timeout),
                )

            return result
        finally:
            await client.close()

    with handle_api_errors(url, resource_type="Test case", resource_id=test_case_id):
        result = asyncio.run(_execute())

        if output_format == "json":
            format_test_run_json(result)
        else:
            format_test_run_table(result, show_pending_hint=no_wait)

            if result.status == "completed":
                console.print()
                if result.classification in ("TP", "TN"):
                    print_success("Test run completed successfully")
                else:
                    print_warning(
                        f"Test run completed with classification: {result.classification}"
                    )
            elif result.status == "failed":
                console.print()
                print_error("Test run failed", result.error_message or "Unknown error")

        # Exit codes: 0 for completed runs (any classification), 2 for system failures
        if result.status == "failed":
            raise SystemExit(2)
        else:
            raise SystemExit(EXIT_SUCCESS)


# =============================================================================
# List Subcommand
# =============================================================================


@test_run.command(name="list")
@click.option(
    "--test-case-id",
    default=None,
    help="Filter by test case ID",
)
@click.option(
    "--server-url",
    default=None,
    help="Filter by MCP server URL",
)
@click.option(
    "--tool-name",
    default=None,
    help="Filter by selected tool name",
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
    "--offset",
    type=int,
    default=0,
    help="Number of records to skip (default: 0)",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    help="Maximum records to return (default: 100, max: 1000)",
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
    test_case_id: str | None,
    server_url: str | None,
    tool_name: str | None,
    tef_url: str | None,
    container_name: str | None,
    offset: int,
    limit: int,
    output_format: str,
    insecure: bool,
) -> None:
    """List test runs with optional filters.

    Examples:

      \b
      # List all test runs
      mcp-tef-cli test-run list

      \b
      # Filter by test case
      mcp-tef-cli test-run list --test-case-id a1b2c3d4-...

      \b
      # Filter by tool name
      mcp-tef-cli test-run list --tool-name get_weather

      \b
      # Output as JSON
      mcp-tef-cli test-run list --format json
    """
    url = resolve_tef_url(tef_url, container_name, output_format)

    async def _list() -> PaginatedTestRunResponse:
        config = ClientConfig(
            base_url=url,
            timeout=60.0,
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            return await client.list_test_runs(
                test_case_id=test_case_id,
                mcp_server_url=server_url,
                tool_name=tool_name,
                offset=offset,
                limit=limit,
            )
        finally:
            await client.close()

    with handle_api_errors(url):
        result = asyncio.run(_list())

        if output_format == "json":
            format_test_run_list_json(result)
        else:
            format_test_run_list_table(result)

        raise SystemExit(EXIT_SUCCESS)


# =============================================================================
# Get Subcommand
# =============================================================================


@test_run.command(name="get")
@click.argument("test_run_id")
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
    help="Show raw LLM response and all tools",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def get(
    test_run_id: str,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    verbose: bool,
    insecure: bool,
) -> None:
    """Get detailed information about a specific test run.

    Examples:

      \b
      # Get test run by ID
      mcp-tef-cli test-run get b2c3d4e5-f6a7-8901-bcde-f23456789012

      \b
      # Show raw LLM response
      mcp-tef-cli test-run get b2c3d4e5-... --verbose

      \b
      # Output as JSON
      mcp-tef-cli test-run get b2c3d4e5-... --format json
    """
    url = resolve_tef_url(tef_url, container_name, output_format)

    async def _get() -> TestRunResponse:
        config = ClientConfig(
            base_url=url,
            timeout=60.0,
            verify_ssl=not insecure,
        )
        client = TefClient(config)
        try:
            return await client.get_test_run(test_run_id)
        finally:
            await client.close()

    with handle_api_errors(url, resource_type="Test run", resource_id=test_run_id):
        result = asyncio.run(_get())

        if output_format == "json":
            format_test_run_json(result)
        else:
            format_test_run_table(result)

            # Verbose output - show raw LLM response
            if verbose and result.llm_response_raw:
                console.print()
                console.print("[bold]Raw LLM Response:[/bold]")
                console.print(result.llm_response_raw)

        raise SystemExit(EXIT_SUCCESS)
