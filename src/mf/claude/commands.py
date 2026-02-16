"""CLI commands for Claude skill management."""

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


@click.group(name="claude")
def claude() -> None:
    """Manage Claude Code skill for mf.

    Install, update, or remove the mf skill that teaches
    Claude Code how to use this tool effectively.
    """
    pass


@claude.command()
@click.option("-f", "--force", is_flag=True, help="Overwrite existing installation")
@click.pass_obj
def install(ctx, force: bool) -> None:
    """Install the mf skill to .claude/skills/mf/.

    The skill teaches Claude Code how to use mf commands
    effectively for managing papers, projects, and content.
    """
    from mf.claude.installer import get_skill_dir, install_skill

    dry_run = ctx.dry_run if ctx else False

    try:
        skill_dir = get_skill_dir()
    except FileNotFoundError:
        console.print("[red]Error: Not in an mf project.[/red]")
        console.print("[dim]Run 'mf init' to initialize, or run from a directory with .mf/[/dim]")
        raise click.Abort() from None

    console.print(f"[cyan]Installing mf skill to {skill_dir}[/cyan]")

    success, actions = install_skill(force=force, dry_run=dry_run)

    for action in actions:
        if success:
            console.print(f"  [green]+[/green] {action}")
        else:
            console.print(f"  [yellow]![/yellow] {action}")

    if dry_run:
        console.print("\n[yellow]DRY RUN - no changes made[/yellow]")
    elif success:
        console.print("\n[green]Skill installed successfully![/green]")
        console.print("[dim]Restart Claude Code to load the skill.[/dim]")


@claude.command()
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def uninstall(ctx, force: bool) -> None:
    """Remove the mf skill.

    Removes the skill files from .claude/skills/mf/.
    """
    from mf.claude.installer import get_skill_dir, uninstall_skill

    dry_run = ctx.dry_run if ctx else False

    try:
        skill_dir = get_skill_dir()
    except FileNotFoundError:
        console.print("[yellow]Not in an mf project.[/yellow]")
        return

    if not skill_dir.exists():
        console.print("[yellow]Skill not installed.[/yellow]")
        return

    if not force and not dry_run and not click.confirm(f"Remove skill from {skill_dir}?"):
        console.print("[yellow]Cancelled[/yellow]")
        return

    success, actions = uninstall_skill(dry_run=dry_run)

    for action in actions:
        console.print(f"  [red]-[/red] {action}")

    if dry_run:
        console.print("\n[yellow]DRY RUN - no changes made[/yellow]")
    elif success:
        console.print("\n[green]Skill uninstalled.[/green]")


@claude.command()
def status() -> None:
    """Check skill installation status.

    Shows whether the skill is installed and if updates are available.
    """
    from mf.claude.installer import check_status, get_skill_dir

    try:
        get_skill_dir()
    except FileNotFoundError:
        console.print("[red]Error: Not in an mf project.[/red]")
        console.print("[dim]Run 'mf init' to initialize, or run from a directory with .mf/[/dim]")
        raise click.Abort() from None

    status = check_status()

    if status.installed:
        if status.files_outdated:
            status_text = "[yellow]Installed (updates available)[/yellow]"
        else:
            status_text = "[green]Installed[/green]"
    elif status.files_present:
        status_text = "[yellow]Partially installed[/yellow]"
    else:
        status_text = "[red]Not installed[/red]"

    content = f"[bold]Status:[/bold] {status_text}\n"
    content += f"[bold]Location:[/bold] {status.skill_dir}\n"

    if status.files_present:
        content += "\n[bold]Files:[/bold]\n"
        for f in sorted(status.files_present):
            if f in status.files_outdated:
                content += f"  [yellow]{f}[/yellow] (outdated)\n"
            else:
                content += f"  [green]{f}[/green]\n"
        for f in sorted(status.files_missing):
            content += f"  [red]{f}[/red] (missing)\n"

    if status.files_outdated:
        content += "\n[dim]Run 'mf claude install --force' to update[/dim]"
    elif not status.installed:
        content += "\n[dim]Run 'mf claude install' to install[/dim]"

    console.print(Panel(content, title="mf Skill Status"))
