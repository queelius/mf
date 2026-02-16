"""CLI commands for content health checks.

Check links, descriptions, images, stale projects, and drafts.
"""

from __future__ import annotations

import json as json_module

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group(name="health")
def health() -> None:
    """Content health checks: links, descriptions, images, stale, drafts."""
    pass


@health.command(name="links")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def links_cmd(as_json: bool) -> None:
    """Find broken internal links in content."""
    from mf.health.checks import HealthChecker

    checker = HealthChecker()
    issues = checker.check_links()

    if as_json:
        click.echo(json_module.dumps(issues, indent=2))
        return

    if not issues:
        console.print("[green]No broken internal links found.[/green]")
        return

    table = Table(title=f"Broken Internal Links ({len(issues)})")
    table.add_column("Content", style="cyan", no_wrap=False)
    table.add_column("Broken Link", style="red")
    table.add_column("Type", style="dim")

    for i in issues:
        table.add_row(i["title"], i["link"], i["content_type"])

    console.print(table)


@health.command(name="descriptions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def descriptions_cmd(as_json: bool) -> None:
    """Find posts missing the description field."""
    from mf.health.checks import HealthChecker

    checker = HealthChecker()
    issues = checker.check_descriptions()

    if as_json:
        click.echo(json_module.dumps(issues, indent=2))
        return

    if not issues:
        console.print("[green]All posts have descriptions.[/green]")
        return

    table = Table(title=f"Missing Descriptions ({len(issues)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", no_wrap=False)

    for i in issues:
        table.add_row(i["slug"], i["title"])

    console.print(table)
    console.print()
    console.print(
        "[dim]Fix with: mf posts set <slug> description \"...\"[/dim]"
    )


@health.command(name="images")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def images_cmd(as_json: bool) -> None:
    """Find posts missing featured_image."""
    from mf.health.checks import HealthChecker

    checker = HealthChecker()
    issues = checker.check_images()

    if as_json:
        click.echo(json_module.dumps(issues, indent=2))
        return

    if not issues:
        console.print("[green]All posts have featured images.[/green]")
        return

    table = Table(title=f"Missing Featured Images ({len(issues)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", no_wrap=False)

    for i in issues:
        table.add_row(i["slug"], i["title"])

    console.print(table)


@health.command(name="drafts")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def drafts_cmd(as_json: bool) -> None:
    """List all drafts with age."""
    from mf.health.checks import HealthChecker

    checker = HealthChecker()
    drafts = checker.check_drafts()

    if as_json:
        click.echo(json_module.dumps(drafts, indent=2))
        return

    if not drafts:
        console.print("[green]No drafts found.[/green]")
        return

    table = Table(title=f"Drafts ({len(drafts)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", no_wrap=False)
    table.add_column("Date", style="dim")
    table.add_column("Age (days)", justify="right")
    table.add_column("Type", style="dim")

    for d in drafts:
        age = str(d["days_old"]) if d.get("days_old") is not None else "?"
        table.add_row(
            d["slug"], d["title"], d.get("date", "?"), age, d["content_type"]
        )

    console.print(table)


@health.command(name="stale")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stale_cmd(as_json: bool) -> None:
    """Find projects where content description diverged from database."""
    from mf.health.checks import HealthChecker

    checker = HealthChecker()
    issues = checker.check_stale()

    if as_json:
        click.echo(json_module.dumps(issues, indent=2))
        return

    if not issues:
        console.print("[green]No stale project descriptions found.[/green]")
        return

    table = Table(title=f"Stale Project Descriptions ({len(issues)})")
    table.add_column("Project", style="cyan")
    table.add_column("Content Desc", no_wrap=False, max_width=40)
    table.add_column("DB Desc", no_wrap=False, max_width=40)

    for i in issues:
        table.add_row(i["slug"], i["content_desc"][:40], i["db_desc"][:40])

    console.print(table)
    console.print()
    console.print("[dim]Fix with: mf projects generate --slug <slug>[/dim]")
