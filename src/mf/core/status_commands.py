"""CLI for `mf status` (render-drift dashboard)."""

import click
from rich.console import Console

console = Console()


@click.command(name="status")
@click.option("-v", "--verbose", is_flag=True, help="List the drifted pages per module")
def status(verbose: bool) -> None:
    """Show render drift across all projection modules (read-only).

    Aggregates `mf papers/projects/packages/pubs diff` into one dashboard:
    how many pages are current vs would be created/updated by generate.

    \b
    Examples:
        mf status
        mf status --verbose
    """
    from mf.core.status import collect_status, print_status

    results = collect_status()
    print_status(results, console=console, verbose=verbose)
