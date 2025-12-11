"""mcp-tef CLI - Command-line interface for deploying and managing mcp-tef.

This package provides a CLI tool for:
- Deploying mcp-tef Docker containers from GHCR
- Managing mcp-tef server instances
- Managing test cases and test runs for query-tool alignment evaluation
"""

import click

from mcp_tef_cli.commands.deploy import deploy
from mcp_tef_cli.commands.similarity import similarity
from mcp_tef_cli.commands.stop import stop
from mcp_tef_cli.commands.test_case import test_case
from mcp_tef_cli.commands.test_run import test_run
from mcp_tef_cli.commands.tool_quality import tool_quality

__version__ = "0.1.0"


@click.group()
@click.version_option(version=__version__, prog_name="mtef")
def cli() -> None:
    """mcp-tef CLI - MCP Tool Evaluation System.

    Deploy and manage mcp-tef containers for evaluating MCP tool selection.
    """
    pass


# Register commands
cli.add_command(deploy)
cli.add_command(similarity)
cli.add_command(stop)
cli.add_command(tool_quality)
cli.add_command(test_case)
cli.add_command(test_run)


def main() -> None:
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
