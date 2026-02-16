"""
Interactive CLI prompts.

Provides user input utilities for interactive commands.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()

T = TypeVar("T")


def prompt_user(
    message: str,
    default: str | None = None,
    show_default: bool = True,
) -> str:
    """Prompt user for text input.

    Args:
        message: Prompt message
        default: Default value if user presses Enter
        show_default: Show default value in prompt

    Returns:
        User input or default
    """
    result = Prompt.ask(message, default=default, show_default=show_default)
    return result if result is not None else ""


def confirm(
    message: str,
    default: bool = False,
    auto_yes: bool = False,
) -> bool:
    """Ask for yes/no confirmation.

    Args:
        message: Question to ask
        default: Default value if user presses Enter
        auto_yes: If True, automatically return True without prompting

    Returns:
        True if confirmed, False otherwise
    """
    if auto_yes:
        console.print(f"{message} [auto-yes]")
        return True

    return bool(Confirm.ask(message, default=default))


def select_from_list(
    items: Sequence[T],
    message: str = "Select an option",
    display_func: Callable[[T], str] = str,
    allow_cancel: bool = True,
) -> T | None:
    """Present a numbered list and let user select an item.

    Args:
        items: List of items to choose from
        message: Prompt message
        display_func: Function to convert item to display string
        allow_cancel: Allow user to cancel selection

    Returns:
        Selected item or None if cancelled
    """
    if not items:
        console.print("[yellow]No items to select from[/yellow]")
        return None

    console.print(f"\n{message}:")
    for i, item in enumerate(items, 1):
        console.print(f"  {i}. {display_func(item)}")

    if allow_cancel:
        console.print("  q. Cancel")

    while True:
        choice = Prompt.ask("Enter number").strip().lower()

        if allow_cancel and choice == "q":
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
            console.print(f"[red]Please enter a number between 1 and {len(items)}[/red]")
        except ValueError:
            console.print("[red]Invalid input. Enter a number or 'q' to cancel.[/red]")


def progress_message(message: str, done: bool = False) -> None:
    """Print a progress message.

    Args:
        message: Message to display
        done: If True, show as completed (green checkmark)
    """
    if done:
        console.print(f"  [green]✓[/green] {message}")
    else:
        console.print(f"  [blue]•[/blue] {message}")


def error_message(message: str) -> None:
    """Print an error message.

    Args:
        message: Error message to display
    """
    console.print(f"[red]ERROR:[/red] {message}")


def warning_message(message: str) -> None:
    """Print a warning message.

    Args:
        message: Warning message to display
    """
    console.print(f"[yellow]WARNING:[/yellow] {message}")


def info_message(message: str) -> None:
    """Print an info message.

    Args:
        message: Info message to display
    """
    console.print(f"[blue]INFO:[/blue] {message}")
