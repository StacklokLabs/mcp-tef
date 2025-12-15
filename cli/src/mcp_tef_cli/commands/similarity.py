"""Similarity analysis commands for mcp-tef CLI."""

import asyncio
import json

import click
from rich.console import Console
from rich.table import Table

from mcp_tef_cli.client import ClientConfig, TefClient
from mcp_tef_cli.constants import (
    DEFAULT_CONTAINER_NAME,
    EXIT_INVALID_ARGUMENTS,
    EXIT_SUCCESS,
)
from mcp_tef_cli.models import (
    DifferentiationRecommendation,
    DifferentiationRecommendationResponse,
    OverlapMatrixResponse,
    SimilarityAnalysisResponse,
    SimilarityMatrixResponse,
)
from mcp_tef_cli.output import print_error, print_success
from mcp_tef_cli.utils import handle_api_errors, resolve_tef_url

console = Console()

# Default timeouts
DEFAULT_TIMEOUT = 60
DEFAULT_TIMEOUT_WITH_RECOMMENDATIONS = 120

# Table layout constants
MIN_COLUMN_WIDTH = 6
ROW_LABEL_WIDTH = 25
TABLE_BORDER_OVERHEAD = 10
DEFAULT_CONSOLE_WIDTH = 80


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


def validate_threshold(value: float) -> float:
    """Validate threshold is in valid range.

    Args:
        value: Threshold value

    Returns:
        Validated threshold value

    Raises:
        click.BadParameter: If threshold is out of range
    """
    if value < 0.0 or value > 1.0:
        raise click.BadParameter("Threshold must be between 0.0 and 1.0")
    return value


def calculate_column_limits(console: Console, total_tools: int) -> tuple[int, int]:
    """Calculate how many columns can fit in console width.

    Args:
        console: Rich Console instance
        total_tools: Total number of tools (columns) to display

    Returns:
        Tuple of (columns_to_show, columns_truncated)
    """
    console_width = (
        console.width if hasattr(console, "width") and console.width else DEFAULT_CONSOLE_WIDTH
    )
    available_width = console_width - ROW_LABEL_WIDTH - TABLE_BORDER_OVERHEAD
    max_columns = max(1, available_width // MIN_COLUMN_WIDTH)
    columns_to_show = min(total_tools, max_columns)
    columns_truncated = total_tools - columns_to_show
    return columns_to_show, columns_truncated


def format_matrix_table(
    response: SimilarityMatrixResponse,
    threshold: float,
) -> None:
    """Format and print similarity matrix as a table.

    Args:
        response: Similarity matrix response
        threshold: Threshold for highlighting
    """
    console.print()
    console.print("[bold]Similarity Matrix[/bold]")
    console.print("=" * 60)
    console.print()
    console.print(f"Tools: {len(response.tool_ids)}")
    console.print(f"Threshold: {threshold}")
    console.print(f"Generated: {response.generated_at}")
    console.print()

    if not response.tool_ids:
        console.print("[yellow]No tools to analyze.[/yellow]")
        return

    # Calculate console layout constraints
    total_tools = len(response.tool_ids)
    columns_to_show, columns_truncated = calculate_column_limits(console, total_tools)
    console_width = (
        console.width if hasattr(console, "width") and console.width else DEFAULT_CONSOLE_WIDTH
    )

    # Create abbreviated labels for columns
    labels = [f"T{i + 1}" for i in range(columns_to_show)]

    # Build table
    table = Table(show_header=True, header_style="bold")
    table.add_column("", style="cyan", width=ROW_LABEL_WIDTH, no_wrap=True)  # Row label column

    for label in labels:
        table.add_column(
            label, justify="center", min_width=MIN_COLUMN_WIDTH, width=MIN_COLUMN_WIDTH
        )

    # Add rows
    for i, tool_id in enumerate(response.tool_ids):
        row_label = f"T{i + 1}: {tool_id[:20]}..." if len(tool_id) > 20 else f"T{i + 1}: {tool_id}"
        row_values = []

        # Only show values for columns that fit
        for j in range(columns_to_show):
            score = response.matrix[i][j]
            # Highlight values above threshold (excluding diagonal)
            if i != j and score >= threshold:
                row_values.append(f"[bold yellow]*{score:.2f}*[/bold yellow]")
            else:
                row_values.append(f"{score:.2f}")

        table.add_row(row_label, *row_values)

    console.print(table)
    console.print()

    if columns_truncated > 0:
        console.print(
            f"[yellow]Note: {columns_truncated} column(s) truncated "
            f"(console width: {console_width}, "
            f"showing {columns_to_show}/{total_tools} columns)[/yellow]"
        )
        console.print()

    console.print(f"[dim]*Highlighted* values exceed threshold ({threshold})[/dim]")
    console.print()
    console.print(f"Flagged Pairs: {len(response.flagged_pairs)}")


def format_analyze_table(
    response: SimilarityAnalysisResponse,
    verbose: bool = False,
) -> None:
    """Format and print similarity analysis results as a table.

    Args:
        response: Similarity analysis response
        verbose: Whether to show detailed output
    """
    console.print()
    console.print("[bold]Similarity Analysis Results[/bold]")
    console.print("=" * 60)
    console.print()
    console.print(f"Analyzed {len(response.tool_ids)} tools")
    console.print(f"Threshold: {response.threshold}")
    console.print()

    if verbose and response.matrix:
        # Show full matrix in verbose mode
        format_matrix_table(response, response.threshold)
        console.print()

    # Show flagged pairs
    if response.flagged_pairs:
        console.print(
            f"[bold]Flagged Pairs ({len(response.flagged_pairs)} above threshold):[/bold]"
        )

        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool A", style="cyan")
        table.add_column("Tool B", style="cyan")
        table.add_column("Similarity", justify="center")
        table.add_column("Flagged", justify="center")

        for pair in response.flagged_pairs:
            table.add_row(
                pair.tool_a_id[:30] + "..." if len(pair.tool_a_id) > 30 else pair.tool_a_id,
                pair.tool_b_id[:30] + "..." if len(pair.tool_b_id) > 30 else pair.tool_b_id,
                f"{pair.similarity_score:.2f}",
                "[green]✓[/green]",
            )

        console.print(table)
    else:
        console.print("[green]No pairs above threshold.[/green]")

    # Show recommendations if present
    if response.recommendations:
        format_recommendations(response.recommendations)


def format_recommendations(recommendations: list[DifferentiationRecommendation]) -> None:
    """Format and print differentiation recommendations.

    Args:
        recommendations: List of recommendations
    """
    console.print()
    console.print("[bold]Recommendations:[/bold]")
    console.print("-" * 60)

    for rec in recommendations:
        console.print()
        tool_a = rec.tool_pair[0] if len(rec.tool_pair) > 0 else "unknown"
        tool_b = rec.tool_pair[1] if len(rec.tool_pair) > 1 else "unknown"
        console.print(
            f"[bold cyan]Pair: {tool_a} ↔ {tool_b}[/bold cyan] "
            f"(similarity: {rec.similarity_score:.2f})"
        )

        if rec.issues:
            console.print()
            console.print("[bold]Issues Identified:[/bold]")
            for issue in rec.issues:
                console.print(f"  • \\[{issue.issue_type}] {issue.description}")

        if rec.recommendations:
            console.print()
            console.print("[bold]Recommendations:[/bold]")
            for item in rec.recommendations:
                priority_color = {
                    "high": "red",
                    "medium": "yellow",
                    "low": "blue",
                }.get(item.priority.lower(), "white")

                console.print(
                    f"  [{priority_color}][{item.priority.upper()}][/{priority_color}] "
                    f"{item.recommendation}"
                )
                if item.tool_id:
                    console.print(f"    Tool: {item.tool_id}")
                console.print(f"    Rationale: {item.rationale}")
                if item.revised_description:
                    console.print(f'    Revised Description: "{item.revised_description}"')

        console.print("-" * 60)


def format_overlap_table(response: OverlapMatrixResponse) -> None:
    """Format and print overlap matrix as a table.

    Args:
        response: Overlap matrix response
    """
    console.print()
    console.print("[bold]Capability Overlap Matrix[/bold]")
    console.print("=" * 60)
    console.print()
    console.print(f"Tools: {len(response.tool_ids)}")
    console.print(f"Generated: {response.generated_at}")
    console.print()

    # Show dimension weights
    console.print("[bold]Dimension Weights:[/bold]")
    for dim, weight in response.dimensions.items():
        console.print(f"  • {dim.capitalize()}: {weight:.2f}")
    console.print()

    if not response.tool_ids:
        console.print("[yellow]No tools to analyze.[/yellow]")
        return

    # Calculate console layout constraints
    total_tools = len(response.tool_ids)
    columns_to_show, columns_truncated = calculate_column_limits(console, total_tools)
    console_width = (
        console.width if hasattr(console, "width") and console.width else DEFAULT_CONSOLE_WIDTH
    )

    # Create abbreviated labels for columns
    labels = [f"T{i + 1}" for i in range(columns_to_show)]

    # Build table
    table = Table(show_header=True, header_style="bold")
    table.add_column("", style="cyan", width=ROW_LABEL_WIDTH, no_wrap=True)

    for label in labels:
        table.add_column(
            label, justify="center", min_width=MIN_COLUMN_WIDTH, width=MIN_COLUMN_WIDTH
        )

    # Add rows
    for i, tool_id in enumerate(response.tool_ids):
        row_label = f"T{i + 1}: {tool_id[:20]}..." if len(tool_id) > 20 else f"T{i + 1}: {tool_id}"
        row_values = []
        # Only show values for columns that fit
        for j in range(columns_to_show):
            row_values.append(f"{response.matrix[i][j]:.2f}")
        table.add_row(row_label, *row_values)

    console.print(table)

    if columns_truncated > 0:
        console.print()
        console.print(
            f"[yellow]Note: {columns_truncated} column(s) truncated "
            f"(console width: {console_width}, "
            f"showing {columns_to_show}/{total_tools} columns)[/yellow]"
        )


def format_recommend_table(response: DifferentiationRecommendationResponse) -> None:
    """Format and print recommendations as a table.

    Args:
        response: Recommendations response
    """
    console.print()
    console.print("[bold]Differentiation Recommendations[/bold]")
    console.print("=" * 60)
    console.print()

    tool_a = response.tool_pair[0] if len(response.tool_pair) > 0 else "unknown"
    tool_b = response.tool_pair[1] if len(response.tool_pair) > 1 else "unknown"

    console.print(f"Tool Pair: {tool_a} ↔ {tool_b}")
    console.print(f"Similarity Score: {response.similarity_score:.2f}")
    console.print(f"Generated: {response.generated_at}")
    console.print()

    # Issues
    if response.issues:
        console.print("[bold]Issues Identified:[/bold]")
        console.print("-" * 60)
        for i, issue in enumerate(response.issues, 1):
            console.print()
            console.print(f"{i}. \\[{issue.issue_type}] {issue.description}")
            if issue.evidence:
                console.print(f"   Evidence: {issue.evidence}")
            console.print(f"   Affects: {issue.tool_a_id}, {issue.tool_b_id}")
        console.print()

    # Recommendations
    if response.recommendations:
        console.print("[bold]Recommendations:[/bold]")
        console.print("-" * 60)
        for item in response.recommendations:
            priority_color = {
                "high": "red",
                "medium": "yellow",
                "low": "blue",
            }.get(item.priority.lower(), "white")

            console.print()
            console.print(
                f"[{priority_color}][{item.priority.upper()} PRIORITY][/{priority_color}] "
                f"{item.recommendation}"
            )
            if item.tool_id:
                console.print(f"  Tool: {item.tool_id}")
            console.print(f"  Rationale: {item.rationale}")
            if item.revised_description:
                console.print(f'  Revised Description: "{item.revised_description}"')

        console.print()
        print_success(f"{len(response.recommendations)} recommendations generated")


@click.group(name="similarity")
def similarity():
    """Analyze tool description similarity across MCP servers."""
    pass


@similarity.command(name="analyze")
@click.option(
    "--server-urls",
    required=True,
    help="Comma-separated MCP server URLs to analyze",
)
@click.option(
    "--threshold",
    type=float,
    default=0.85,
    help="Similarity threshold for flagging pairs (0.0-1.0)",
)
@click.option(
    "--method",
    type=click.Choice(["embedding", "description_overlap"]),
    default="embedding",
    help="Analysis method",
)
@click.option(
    "--embedding-model",
    default=None,
    help="Embedding model (e.g., openai:text-embedding-3-small)",
)
@click.option(
    "--full-similarity",
    is_flag=True,
    help="Include parameter similarity in analysis",
)
@click.option(
    "--include-recommendations",
    is_flag=True,
    help="Generate AI recommendations for flagged pairs",
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
    help="Show detailed similarity scores and tool info",
)
@click.option(
    "--timeout",
    type=int,
    default=None,
    help="Request timeout in seconds (default: 60, or 120 with recommendations)",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def analyze(
    server_urls: str,
    threshold: float,
    method: str,
    embedding_model: str | None,
    full_similarity: bool,
    include_recommendations: bool,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    verbose: bool,
    timeout: int | None,
    insecure: bool,
) -> None:
    """Run full similarity analysis with optional recommendations.

    Analyze tool similarity across MCP servers with configurable thresholds
    and optional AI-powered recommendations for differentiating similar tools.

    Examples:

      \b
      # Basic similarity analysis
      mtef similarity analyze \\
        --server-urls http://localhost:3000/sse

      \b
      # With custom threshold and recommendations
      mtef similarity analyze \\
        --server-urls http://localhost:3000/sse \\
        --threshold 0.90 --include-recommendations

      \b
      # Output as JSON
      mtef similarity analyze \\
        --server-urls http://localhost:3000/sse --format json
    """
    # Validate threshold
    try:
        validate_threshold(threshold)
    except click.BadParameter as e:
        print_error("Invalid threshold", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Parse server URLs
    try:
        parsed_urls = parse_server_urls(server_urls)
    except click.BadParameter as e:
        print_error("Invalid server URLs", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Determine timeout
    if timeout is None:
        timeout = (
            DEFAULT_TIMEOUT_WITH_RECOMMENDATIONS if include_recommendations else DEFAULT_TIMEOUT
        )

    # Resolve mcp-tef URL
    url = resolve_tef_url(tef_url, container_name, output_format)

    # Make API call
    config = ClientConfig(
        base_url=url,
        timeout=float(timeout),
        verify_ssl=not insecure,
    )

    async def _run():
        client = TefClient(config)
        try:
            return await client.analyze_similarity(
                server_urls=parsed_urls,
                threshold=threshold,
                method=method,
                embedding_model=embedding_model,
                compute_full_similarity=full_similarity,
                include_recommendations=include_recommendations,
            )
        finally:
            await client.close()

    with handle_api_errors(url):
        response = asyncio.run(_run())

        # Output results
        if output_format == "json":
            data = response.model_dump(mode="json")
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            format_analyze_table(response, verbose=verbose)
            console.print()
            print_success(
                f"Analysis complete: {len(response.flagged_pairs)} pairs "
                f"flagged above {threshold} threshold"
            )

        raise SystemExit(EXIT_SUCCESS)


@similarity.command(name="matrix")
@click.option(
    "--server-urls",
    required=True,
    help="Comma-separated MCP server URLs",
)
@click.option(
    "--threshold",
    type=float,
    default=0.85,
    help="Threshold for flagging similar pairs (0.0-1.0)",
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
def matrix(
    server_urls: str,
    threshold: float,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    timeout: int,
    insecure: bool,
) -> None:
    """Generate similarity matrix for tool pairs.

    Generate a complete similarity matrix showing pairwise similarity
    scores between all tools from the specified MCP servers.

    Examples:

      \b
      # Generate similarity matrix
      mtef similarity matrix \\
        --server-urls http://localhost:3000/sse

      \b
      # With custom threshold
      mtef similarity matrix \\
        --server-urls http://localhost:3000/sse --threshold 0.90

      \b
      # Output as JSON
      mtef similarity matrix \\
        --server-urls http://localhost:3000/sse --format json
    """
    # Validate threshold
    try:
        validate_threshold(threshold)
    except click.BadParameter as e:
        print_error("Invalid threshold", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Parse server URLs
    try:
        parsed_urls = parse_server_urls(server_urls)
    except click.BadParameter as e:
        print_error("Invalid server URLs", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Resolve mcp-tef URL
    url = resolve_tef_url(tef_url, container_name, output_format)

    # Make API call
    config = ClientConfig(
        base_url=url,
        timeout=float(timeout),
        verify_ssl=not insecure,
    )

    async def _run():
        client = TefClient(config)
        try:
            return await client.get_similarity_matrix(
                server_urls=parsed_urls,
                threshold=threshold,
            )
        finally:
            await client.close()

    with handle_api_errors(url):
        response = asyncio.run(_run())

        # Output results
        if output_format == "json":
            data = response.model_dump(mode="json")
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            format_matrix_table(response, threshold)
            console.print()
            print_success(f"Matrix generated for {len(response.tool_ids)} tools")

        raise SystemExit(EXIT_SUCCESS)


@similarity.command(name="overlap")
@click.option(
    "--server-urls",
    required=True,
    help="Comma-separated MCP server URLs",
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
def overlap(
    server_urls: str,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    timeout: int,
    insecure: bool,
) -> None:
    """Generate capability overlap matrix with dimension breakdown.

    Generate a capability overlap matrix showing functional overlap
    across multiple dimensions (semantic, description, parameters).

    Examples:

      \b
      # Generate overlap matrix
      mtef similarity overlap \\
        --server-urls http://localhost:3000/sse

      \b
      # Output as JSON
      mtef similarity overlap \\
        --server-urls http://localhost:3000/sse --format json
    """
    # Parse server URLs
    try:
        parsed_urls = parse_server_urls(server_urls)
    except click.BadParameter as e:
        print_error("Invalid server URLs", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Resolve mcp-tef URL
    url = resolve_tef_url(tef_url, container_name, output_format)

    # Make API call
    config = ClientConfig(
        base_url=url,
        timeout=float(timeout),
        verify_ssl=not insecure,
    )

    async def _run():
        client = TefClient(config)
        try:
            return await client.get_overlap_matrix(
                server_urls=parsed_urls,
            )
        finally:
            await client.close()

    with handle_api_errors(url):
        response = asyncio.run(_run())

        # Output results
        if output_format == "json":
            data = response.model_dump(mode="json")
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            format_overlap_table(response)
            console.print()
            print_success(f"Overlap matrix generated for {len(response.tool_ids)} tools")

        raise SystemExit(EXIT_SUCCESS)


@similarity.command(name="recommend")
@click.option(
    "--server-urls",
    required=True,
    help="Comma-separated MCP server URLs (must resolve to exactly 2 tools)",
)
@click.option(
    "--tool-names",
    default=None,
    help="Comma-separated tool names to filter (useful when server has many tools)",
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
    "--timeout",
    type=int,
    default=DEFAULT_TIMEOUT_WITH_RECOMMENDATIONS,
    help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT_WITH_RECOMMENDATIONS})",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification",
)
def recommend(
    server_urls: str,
    tool_names: str | None,
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
    timeout: int,
    insecure: bool,
) -> None:
    """Get differentiation recommendations for exactly 2 tools.

    Generate detailed AI-powered recommendations for differentiating
    two similar tools. The MCP servers must expose exactly 2 tools total.

    Examples:

      \b
      # Get recommendations for two tools from a server
      mtef similarity recommend \\
        --server-urls http://localhost:3000/sse

      \b
      # Filter specific tools from a server with many tools
      mtef similarity recommend \\
        --server-urls http://localhost:3000/sse \\
        --tool-names search_issues,search_pull_requests

      \b
      # Output as JSON
      mtef similarity recommend \\
        --server-urls http://localhost:3000/sse --format json
    """
    # Parse server URLs
    try:
        parsed_urls = parse_server_urls(server_urls)
    except click.BadParameter as e:
        print_error("Invalid server URLs", str(e))
        raise SystemExit(EXIT_INVALID_ARGUMENTS) from e

    # Parse tool names if provided
    parsed_tool_names = None
    if tool_names:
        parsed_tool_names = [name.strip() for name in tool_names.split(",") if name.strip()]
        if not parsed_tool_names:
            print_error("Invalid tool names", "At least one tool name is required")
            raise SystemExit(EXIT_INVALID_ARGUMENTS)

    # Resolve mcp-tef URL
    url = resolve_tef_url(tef_url, container_name, output_format)

    # Make API call
    config = ClientConfig(
        base_url=url,
        timeout=float(timeout),
        verify_ssl=not insecure,
    )

    async def _run():
        client = TefClient(config)
        try:
            return await client.get_recommendations(
                server_urls=parsed_urls,
                tool_names=parsed_tool_names,
            )
        finally:
            await client.close()

    with handle_api_errors(url):
        response = asyncio.run(_run())

        # Output results
        if output_format == "json":
            data = response.model_dump(mode="json")
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            format_recommend_table(response)

        raise SystemExit(EXIT_SUCCESS)
