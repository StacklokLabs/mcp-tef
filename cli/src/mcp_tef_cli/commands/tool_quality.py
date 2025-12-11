"""Tool quality evaluation command for mcp-tef CLI."""

import asyncio
import json
import os

import click
import httpx
from rich.console import Console
from rich.table import Table

from mcp_tef_cli.client import ClientConfig, TefClient
from mcp_tef_cli.constants import (
    DEFAULT_CONTAINER_NAME,
    EXIT_INVALID_ARGUMENTS,
    EXIT_REQUEST_TIMEOUT,
    EXIT_SUCCESS,
    EXIT_TEF_SERVER_UNREACHABLE,
)
from mcp_tef_cli.docker_client import discover_tef_url
from mcp_tef_cli.models import ToolQualityResponse, ToolQualityResult
from mcp_tef_cli.output import print_error, print_info, print_success

console = Console()

# Default timeout for LLM evaluations (can be slow)
DEFAULT_TIMEOUT = 60


def parse_server_urls(value: str) -> list[str]:
    """Parse comma-separated server URLs.

    Args:
        value: Comma-separated string of server URLs

    Returns:
        List of trimmed server URLs

    Raises:
        click.BadParameter: If no valid URLs provided
    """
    if not value or not value.strip():
        raise click.BadParameter("At least one server URL is required")

    urls = [url.strip() for url in value.split(",") if url.strip()]
    if not urls:
        raise click.BadParameter("At least one server URL is required")

    return urls


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


def format_results_table(
    results: list[ToolQualityResult],
    verbose: bool = False,
) -> None:
    """Format and print results as a table.

    Args:
        results: List of tool quality results
        verbose: Whether to show detailed explanations
    """
    if not results:
        console.print("[yellow]No tools evaluated.[/yellow]")
        return

    console.print()
    console.print("[bold]Tool Quality Evaluation Results[/bold]")
    console.print("=" * 60)

    if verbose:
        # Verbose output - show full details for each tool
        for result in results:
            console.print()
            console.print(f"[bold cyan]Tool: {result.tool_name}[/bold cyan]")
            console.print(f'  Description: "{result.tool_description}"')

            eval_result = result.evaluation_result
            console.print(
                f"  Clarity:      {eval_result.clarity.score}/10 - "
                f"{eval_result.clarity.explanation}"
            )
            console.print(
                f"  Completeness: {eval_result.completeness.score}/10 - "
                f"{eval_result.completeness.explanation}"
            )
            console.print(
                f"  Conciseness:  {eval_result.conciseness.score}/10 - "
                f"{eval_result.conciseness.explanation}"
            )
            if eval_result.suggested_description:
                console.print(f'  Suggested:    "{eval_result.suggested_description}"')
    else:
        # Table output - scores only
        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool Name", style="cyan")
        table.add_column("Clarity", justify="center")
        table.add_column("Completeness", justify="center")
        table.add_column("Conciseness", justify="center")

        for result in results:
            eval_result = result.evaluation_result
            table.add_row(
                result.tool_name,
                f"{eval_result.clarity.score}/10",
                f"{eval_result.completeness.score}/10",
                f"{eval_result.conciseness.score}/10",
            )

        console.print()
        console.print(table)


def format_results_json(response: ToolQualityResponse) -> None:
    """Format and print results as JSON.

    Args:
        response: Tool quality response
    """
    data = response.model_dump(mode="json")
    click.echo(json.dumps(data, indent=2, default=str))


async def evaluate_tool_quality_async(
    base_url: str,
    server_urls: list[str],
    model_provider: str,
    model_name: str,
    api_key: str | None,
    timeout: float,
    verify_ssl: bool,
) -> ToolQualityResponse:
    """Call the mcp-tef tool quality evaluation endpoint.

    Args:
        base_url: mcp-tef server URL
        server_urls: List of MCP server URLs to evaluate
        model_provider: LLM provider name
        model_name: Model identifier
        api_key: Optional API key for the model provider
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates

    Returns:
        ToolQualityResponse with results and any errors
    """
    config = ClientConfig(
        base_url=base_url,
        timeout=timeout,
        verify_ssl=verify_ssl,
        api_key=api_key,
    )
    client = TefClient(config)

    try:
        return await client.evaluate_tool_quality(
            server_urls=server_urls,
            model_provider=model_provider,
            model_name=model_name,
        )
    finally:
        await client.close()


@click.command(name="tool-quality")
@click.option(
    "--server-urls",
    required=True,
    help="Comma-separated MCP server URLs to evaluate",
)
@click.option(
    "--model-provider",
    required=True,
    help="LLM provider (e.g., anthropic, openai, openrouter)",
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
    "--url",
    "tef_url",
    default=None,
    help="mcp-tef server URL (bypasses Docker container discovery)",
)
@click.option(
    "--container-name",
    default=None,
    help=f"Docker container name for mcp-tef URL discovery (default: {DEFAULT_CONTAINER_NAME})",
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
    help="Show detailed explanations and suggested descriptions",
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
def tool_quality(
    server_urls: str,
    model_provider: str,
    model_name: str,
    api_key: str | None,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    verbose: bool,
    timeout: int,
    insecure: bool,
) -> None:
    """Evaluate tool description quality for MCP servers.

    This command connects to MCP servers, retrieves tool definitions, and uses
    an LLM to assess each tool's description quality across three dimensions:
    clarity, completeness, and conciseness.

    The mcp-tef server URL is automatically discovered from the running Docker
    container (deployed via 'mcp-tef-cli deploy').

    Examples:

      \b
      # Evaluate tools from a single MCP server
      mcp-tef-cli tool-quality --server-urls http://localhost:3000/sse \\
        --model-provider openrouter --model-name anthropic/claude-sonnet-4-5-20250929

      \b
      # Evaluate multiple servers with verbose output
      mcp-tef-cli tool-quality \\
        --server-urls http://localhost:3000/sse,http://localhost:3001/mcp \\
        --model-provider anthropic --model-name claude-sonnet-4-5-20250929 \\
        --verbose

      \b
      # Output as JSON for scripting
      mcp-tef-cli tool-quality --server-urls http://localhost:3000/sse \\
        --model-provider openrouter --model-name anthropic/claude-sonnet-4-5-20250929 \\
        --format json
    """
    # Determine mcp-tef URL: use --url if provided, otherwise discover from Docker
    if tef_url:
        url = tef_url
        if output_format != "json":
            print_info(f"Using mcp-tef at {url}")
    else:
        url = discover_tef_url(container_name or DEFAULT_CONTAINER_NAME)
        # Only print info message if not outputting JSON (for clean machine-readable output)
        if output_format != "json":
            print_info(f"Discovered mcp-tef at {url}")

    # Parse and validate server URLs
    try:
        parsed_urls = parse_server_urls(server_urls)
    except click.BadParameter as e:
        print_error("Invalid server URLs", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Resolve API key
    resolved_api_key = resolve_api_key(api_key)

    try:
        response = asyncio.run(
            evaluate_tool_quality_async(
                base_url=url,
                server_urls=parsed_urls,
                model_provider=model_provider,
                model_name=model_name,
                api_key=resolved_api_key,
                timeout=float(timeout),
                verify_ssl=not insecure,
            )
        )

        # Determine exit code based on results
        has_results = bool(response.results)
        has_errors = bool(response.errors)

        if output_format == "json":
            format_results_json(response)
        else:
            format_results_table(response.results, verbose=verbose)

            # Print summary
            console.print()
            if has_results:
                print_success(f"Evaluated {len(response.results)} tool(s)")

            # Print errors if any
            if has_errors and response.errors:
                console.print()
                console.print("[bold yellow]Errors:[/bold yellow]")
                for error in response.errors:
                    console.print(f"  - {error}")

        # Exit codes per spec
        if has_errors and not has_results:
            # Complete failure - no servers could be evaluated
            raise SystemExit(2)
        elif has_errors:
            # Partial success - some servers failed
            raise SystemExit(1)
        else:
            # Success - all servers evaluated
            raise SystemExit(EXIT_SUCCESS)

    except httpx.TimeoutException as e:
        print_error("Request timed out")
        console.print(
            "  The LLM evaluation may take longer for servers with many tools.",
            style="yellow",
        )
        console.print(
            "  Try increasing the timeout with --timeout (e.g., --timeout 120)",
            style="yellow",
        )
        raise SystemExit(EXIT_REQUEST_TIMEOUT) from e

    except httpx.ConnectError as e:
        print_error("Cannot connect to mcp-tef server", f"URL: {url}")
        console.print("  Is the mcp-tef server running?", style="yellow")
        raise SystemExit(EXIT_TEF_SERVER_UNREACHABLE) from e

    except httpx.HTTPStatusError as e:
        print_error(
            "HTTP error from mcp-tef server",
            f"Status: {e.response.status_code} - {e.response.text}",
        )
        raise SystemExit(EXIT_TEF_SERVER_UNREACHABLE) from e

    except httpx.HTTPError as e:
        print_error("HTTP error", str(e))
        raise SystemExit(EXIT_TEF_SERVER_UNREACHABLE) from e
