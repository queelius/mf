"""
Main CLI dispatcher for mf.

Usage:
    mf init                              # Initialize .mf/ directory
    mf papers [process|sync|generate]
    mf projects [import|refresh|clean]
    mf pubs sync
"""

import click
from rich.console import Console

from mf import __version__

console = Console()


class Context:
    """Shared context for all commands."""

    def __init__(self, verbose: bool = False, dry_run: bool = False):
        self.verbose = verbose
        self.dry_run = dry_run
        self.console = console


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.version_option(version=__version__, prog_name="mf")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("-n", "--dry-run", is_flag=True, help="Preview without making changes")
@click.pass_context
def main(ctx: click.Context, verbose: bool, dry_run: bool) -> None:
    """Metafunctor site management tools.

    Manage papers, projects, and publications for the Hugo static site.
    """
    ctx.ensure_object(dict)
    ctx.obj = Context(verbose=verbose, dry_run=dry_run)

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")


@main.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing .mf/ directory")
@click.pass_obj
def init(ctx, force: bool) -> None:
    """Initialize .mf/ directory structure.

    Creates the .mf/ directory with proper structure for mf data.
    """
    from mf.core.config import get_site_root

    dry_run = ctx.dry_run if ctx else False

    try:
        site_root = get_site_root()
    except FileNotFoundError:
        # For init, use cwd as the site root since .mf/ doesn't exist yet
        from pathlib import Path
        site_root = Path.cwd()

    mf_dir = site_root / ".mf"

    if mf_dir.exists() and not force:
        console.print(f"[yellow].mf/ directory already exists at {mf_dir}[/yellow]")
        console.print("[dim]Use --force to reinitialize.[/dim]")
        return

    console.print(f"[cyan]Initializing .mf/ directory at {site_root}[/cyan]")

    # Create directory structure
    dirs_to_create = [
        mf_dir,
        mf_dir / "cache",
        mf_dir / "backups" / "papers",
        mf_dir / "backups" / "projects",
        mf_dir / "backups" / "series",
    ]

    for dir_path in dirs_to_create:
        if not dry_run:
            dir_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]Created[/green] {dir_path.relative_to(site_root)}")

    # Update .gitignore
    gitignore_path = site_root / ".gitignore"
    gitignore_entry = ".mf/cache/"

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if gitignore_entry not in content:
            if not dry_run:
                with open(gitignore_path, "a") as f:
                    f.write(f"\n# mf cache\n{gitignore_entry}\n")
            console.print(f"  [green]Updated[/green] .gitignore with {gitignore_entry}")

    console.print()
    if dry_run:
        console.print("[yellow]DRY RUN - no changes made[/yellow]")
    else:
        console.print("[green]Done![/green] .mf/ directory initialized.")


# Import and register command groups (imports after main definition intentional)
from mf.analytics.commands import analytics  # noqa: E402
from mf.backup.commands import backup  # noqa: E402
from mf.claude.commands import claude  # noqa: E402
from mf.config.commands import config  # noqa: E402
from mf.content.commands import content  # noqa: E402
from mf.core.integrity_commands import integrity  # noqa: E402
from mf.papers.commands import papers  # noqa: E402
from mf.projects.commands import projects  # noqa: E402
from mf.publications.commands import pubs  # noqa: E402
from mf.posts.commands import posts  # noqa: E402
from mf.series.commands import series  # noqa: E402
from mf.taxonomy.commands import taxonomy  # noqa: E402
from mf.health.commands import health  # noqa: E402

main.add_command(papers)
main.add_command(posts)
main.add_command(projects)
main.add_command(pubs)
main.add_command(backup)
main.add_command(config)
main.add_command(content)
main.add_command(claude)
main.add_command(series)
main.add_command(analytics)
main.add_command(integrity)
main.add_command(taxonomy)
main.add_command(health)


if __name__ == "__main__":
    main()
