"""Output formatting utilities for mcp-tef CLI."""

import json
import sys

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

__all__ = [
    "format_json",
    "print_json",
    "format_table",
    "print_table",
    "print_error",
    "print_success",
    "print_info",
    "print_warning",
]

console = Console()
console_stderr = Console(stderr=True)


def format_json(data: dict | list | BaseModel, pretty: bool = True) -> str:
    """Format data as JSON.

    Args:
        data: Data to format (dict, list, or Pydantic model)
        pretty: Whether to pretty-print with indentation

    Returns:
        JSON string
    """
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")

    if pretty:
        return json.dumps(data, indent=2, default=str)
    else:
        return json.dumps(data, default=str)


def print_json(data: dict | list | BaseModel, pretty: bool = True, file=sys.stdout) -> None:
    """Print JSON to stdout (pipeable).

    Args:
        data: Data to print
        pretty: Whether to pretty-print
        file: Output file stream
    """
    print(format_json(data, pretty), file=file)


def format_table(data: BaseModel | dict, title: str | None = None) -> Table:
    """Format data as Rich table.

    Args:
        data: Data to format (dict or Pydantic model)
        title: Optional table title

    Returns:
        Rich Table object
    """
    table = Table(title=title, show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    if isinstance(data, BaseModel):
        data = data.model_dump()

    for key, value in data.items():
        table.add_row(str(key), str(value))

    return table


def print_table(data: BaseModel | dict, title: str | None = None) -> None:
    """Print table to stdout.

    Args:
        data: Data to print
        title: Optional table title
    """
    console.print(format_table(data, title))


def print_error(message: str, details: str | None = None) -> None:
    """Print error message to stderr.

    Args:
        message: Error message
        details: Optional detailed error information
    """
    console_stderr.print(f"[bold red]✗ {message}[/bold red]")
    if details:
        console_stderr.print(f"  {details}")


def print_success(message: str) -> None:
    """Print success message.

    Args:
        message: Success message
    """
    console.print(f"[bold green]✓ {message}[/bold green]")


def print_info(message: str) -> None:
    """Print informational message.

    Args:
        message: Info message
    """
    console.print(f"[bold blue]ℹ {message}[/bold blue]")


def print_warning(message: str) -> None:
    """Print warning message.

    Args:
        message: Warning message
    """
    console.print(f"[bold yellow]⚠ {message}[/bold yellow]")
