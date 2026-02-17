"""CLI commands for package management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from mf.core.field_ops import ChangeResult
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group(name="packages")
def packages() -> None:
    """Manage packages from PyPI, CRAN, and other registries.

    Track external packages, sync metadata from registries, and generate
    Hugo content for package pages.
    """
    pass


@packages.command(name="list")
@click.option("-q", "--query", help="Search in name/description")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("--registry", help="Filter by registry (pypi, cran)")
@click.option("--featured", is_flag=True, help="Only featured packages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_packages(
    query: str | None,
    tag: tuple[str, ...],
    registry: str | None,
    featured: bool,
    as_json: bool,
) -> None:
    """List all packages in the database."""
    import json as json_module

    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()

    results = db.search(
        query=query,
        tags=list(tag) if tag else None,
        registry=registry,
        featured=True if featured else None,
    )

    if as_json:
        output = []
        for entry in results:
            data = dict(entry.data)
            data["slug"] = entry.slug
            output.append(data)
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No packages found matching criteria[/yellow]")
        return

    table = Table(title=f"Packages ({len(results)} found)")
    table.add_column("Name", style="cyan")
    table.add_column("Registry")
    table.add_column("Version")
    table.add_column("Flags")
    table.add_column("Tags")

    for entry in sorted(results, key=lambda e: e.name):
        flags = ""
        if entry.featured:
            flags += "F "

        table.add_row(
            entry.name,
            entry.registry or "-",
            entry.latest_version or "-",
            flags.strip(),
            ", ".join(entry.tags) if entry.tags else "-",
        )

    console.print(table)
    console.print("\n[dim]F = Featured[/dim]")


@packages.command()
@click.argument("name")
def show(name: str) -> None:
    """Show details for a specific package."""
    import json as json_module

    from rich.syntax import Syntax

    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()

    entry = db.get(name)

    if not entry:
        console.print(f"[red]Package not found: {name}[/red]")
        console.print("[dim]Use 'mf packages list' to see available packages[/dim]")
        return

    display_data: dict[str, Any] = {
        "name": entry.name,
        "registry": entry.registry,
        "description": entry.description,
        "latest_version": entry.latest_version,
        "featured": entry.featured,
        "tags": entry.tags,
        "project": entry.project,
        "install_command": entry.install_command,
        "registry_url": entry.registry_url,
        "license": entry.license,
        "downloads": entry.downloads,
        "last_synced": entry.last_synced,
    }

    # Remove None values for cleaner display
    display_data = {k: v for k, v in display_data.items() if v is not None and v != []}

    json_str = json_module.dumps(display_data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Package: {name}"))


@packages.command()
@click.argument("name")
@click.option("--registry", required=True, type=click.Choice(["pypi", "cran"]),
              help="Package registry")
@click.option("--project", help="Link to an mf project slug")
@click.option("--no-sync", is_flag=True, help="Skip registry metadata fetch")
@click.pass_obj
def add(ctx: Any, name: str, registry: str, project: str | None, no_sync: bool) -> None:
    """Add a new package to the database.

    \\b
    Examples:
        mf packages add requests --registry pypi
        mf packages add ReliabilityTheory --registry cran --project reliabilitytheory
        mf packages add my-pkg --registry pypi --no-sync
    """
    from mf.packages.database import PackageDatabase

    dry_run = ctx.dry_run if ctx else False

    db = PackageDatabase()
    db.load()

    if name in db:
        console.print(f"[red]Package already exists: {name}[/red]")
        console.print("[dim]Use 'mf packages show' to view existing package[/dim]")
        return

    # Build initial entry data
    entry_data: dict[str, Any] = {
        "name": name,
        "registry": registry,
    }
    if project:
        entry_data["project"] = project

    # Sync from registry unless --no-sync
    if not no_sync:
        from mf.packages.registries import discover_registries

        adapters = discover_registries()
        adapter = adapters.get(registry)
        if adapter:
            console.print(f"[cyan]Fetching metadata from {registry}...[/cyan]")
            try:
                metadata = adapter.fetch_metadata(name)
                if metadata:
                    # Merge registry metadata into entry
                    entry_data["description"] = metadata.description
                    entry_data["latest_version"] = metadata.latest_version
                    if metadata.install_command:
                        entry_data["install_command"] = metadata.install_command
                    if metadata.registry_url:
                        entry_data["registry_url"] = metadata.registry_url
                    if metadata.license:
                        entry_data["license"] = metadata.license
                    if metadata.downloads is not None:
                        entry_data["downloads"] = metadata.downloads

                    from datetime import datetime
                    entry_data["last_synced"] = datetime.now().isoformat(timespec="seconds")
                    console.print(f"[green]Fetched metadata for {name}[/green]")
                else:
                    console.print(f"[yellow]Package not found on {registry}: {name}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Warning: could not fetch metadata: {e}[/yellow]")
        else:
            console.print(f"[yellow]No adapter available for registry: {registry}[/yellow]")

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.set(name, entry_data)
    db.save()
    console.print(f"[green]Added package:[/green] {name} ({registry})")


@packages.command()
@click.argument("name")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@click.pass_obj
def remove(ctx: Any, name: str, yes: bool) -> None:
    """Remove a package from the database.

    \\b
    Examples:
        mf packages remove my-pkg
        mf packages remove my-pkg -y
    """
    from mf.packages.database import PackageDatabase

    dry_run = ctx.dry_run if ctx else False

    db = PackageDatabase()
    db.load()

    entry = db.get(name)
    if not entry:
        console.print(f"[red]Package not found: {name}[/red]")
        return

    if not yes:
        click.confirm(f"Remove package '{name}'?", abort=True)

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.delete(name)
    db.save()
    console.print(f"[green]Removed package:[/green] {name}")


@packages.command()
@click.argument("name", required=False)
@click.pass_obj
def sync(ctx: Any, name: str | None) -> None:
    """Sync package metadata from registries.

    If NAME is given, sync that single package. Otherwise, sync all packages.

    \\b
    Examples:
        mf packages sync requests
        mf packages sync
    """
    from datetime import datetime

    from mf.packages.database import PackageDatabase
    from mf.packages.registries import discover_registries

    dry_run = ctx.dry_run if ctx else False

    db = PackageDatabase()
    db.load()

    adapters = discover_registries()

    if name:
        entry = db.get(name)
        if not entry:
            console.print(f"[red]Package not found: {name}[/red]")
            return
        entries = [(name, entry)]
    else:
        entries = list(db.items())

    if not entries:
        console.print("[yellow]No packages to sync[/yellow]")
        return

    synced = 0
    failed = 0

    for slug, entry in entries:
        reg = entry.registry
        if not reg:
            console.print(f"  [yellow]{slug}: no registry set, skipping[/yellow]")
            failed += 1
            continue

        adapter = adapters.get(reg)
        if not adapter:
            console.print(f"  [yellow]{slug}: no adapter for registry '{reg}', skipping[/yellow]")
            failed += 1
            continue

        console.print(f"  [cyan]Syncing {slug} from {reg}...[/cyan]")
        try:
            metadata = adapter.fetch_metadata(entry.name)
            if metadata:
                old_version = entry.latest_version
                entry.update(
                    description=metadata.description,
                    latest_version=metadata.latest_version,
                )
                if metadata.install_command:
                    entry.update(install_command=metadata.install_command)
                if metadata.registry_url:
                    entry.update(registry_url=metadata.registry_url)
                if metadata.license:
                    entry.update(license=metadata.license)
                if metadata.downloads is not None:
                    entry.update(downloads=metadata.downloads)
                entry.update(last_synced=datetime.now().isoformat(timespec="seconds"))

                if old_version != metadata.latest_version:
                    console.print(
                        f"    [green]Updated:[/green] {old_version} -> {metadata.latest_version}"
                    )
                else:
                    console.print(f"    [dim]No version change ({metadata.latest_version})[/dim]")
                synced += 1
            else:
                console.print(f"    [yellow]Not found on {reg}[/yellow]")
                failed += 1
        except Exception as e:
            console.print(f"    [red]Error: {e}[/red]")
            failed += 1

    if dry_run:
        console.print(f"\n[yellow]Dry run -- no changes saved. ({synced} synced, {failed} failed)[/yellow]")
        return

    db.save()
    console.print(f"\n[green]Sync complete:[/green] {synced} synced, {failed} failed")


@packages.command()
@click.argument("name", required=False)
@click.pass_obj
def generate(ctx: Any, name: str | None) -> None:
    """Generate Hugo content for packages.

    If NAME is given, generate for that single package. Otherwise, generate
    for all packages.

    \\b
    Examples:
        mf packages generate requests
        mf packages generate
    """
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import generate_all_packages, generate_package_content

    dry_run = ctx.dry_run if ctx else False

    db = PackageDatabase()
    db.load()

    if name:
        entry = db.get(name)
        if not entry:
            console.print(f"[red]Package not found: {name}[/red]")
            return

        console.print(f"[cyan]Generating content for {name}...[/cyan]")
        generate_package_content(name, entry, dry_run=dry_run)
    else:
        console.print("[cyan]Generating content for all packages...[/cyan]")
        success, failed = generate_all_packages(db, dry_run=dry_run)
        console.print(f"\n[green]Generated:[/green] {success} success, {failed} failed")


# -----------------------------------------------------------------------------
# Field override commands
# -----------------------------------------------------------------------------


def _print_change(result: ChangeResult) -> None:
    """Print a ChangeResult as a formatted diff."""
    console.print(f"[cyan]{result.slug}[/cyan]: {result.field}")
    if result.old_value is not None:
        console.print(f"  old: {result.old_value}")
    if result.new_value is not None:
        console.print(f"  new: {result.new_value}")
    elif result.action == "unset":
        console.print("  [dim](removed)[/dim]")


@packages.command(name="fields")
def fields_cmd() -> None:
    """List all valid package fields and their types."""
    from mf.packages.field_ops import PACKAGES_SCHEMA

    table = Table(title="Package Fields")
    table.add_column("Field", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description")
    table.add_column("Constraints", style="yellow")

    for name, fdef in sorted(PACKAGES_SCHEMA.items()):
        constraints = []
        if fdef.choices:
            constraints.append(f"choices: {', '.join(fdef.choices)}")
        if fdef.min_val is not None:
            constraints.append(f"min: {fdef.min_val}")
        if fdef.max_val is not None:
            constraints.append(f"max: {fdef.max_val}")
        table.add_row(name, fdef.field_type.value, fdef.description, "; ".join(constraints) or "-")

    console.print(table)


@packages.command(name="set")
@click.argument("name")
@click.argument("field")
@click.argument("value")
@click.pass_obj
def set_field_cmd(ctx: Any, name: str, field: str, value: str) -> None:
    """Set a package field value.

    \\b
    Examples:
        mf packages set requests description "HTTP for Humans"
        mf packages set my-pkg tags "python,http"
        mf packages set my-pkg featured true
    """
    from mf.core.field_ops import coerce_value, parse_field_path
    from mf.packages.database import PackageDatabase
    from mf.packages.field_ops import PACKAGES_SCHEMA, set_package_field, validate_package_field

    dry_run = ctx.dry_run if ctx else False

    top, sub = parse_field_path(field)
    schema = PACKAGES_SCHEMA.get(top)
    if schema is None:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf packages fields' to see valid fields.[/dim]")
        return

    # Coerce value
    try:
        coerced = value if sub is not None else coerce_value(value, schema)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Validate
    errors = validate_package_field(field, coerced)
    if errors:
        for err in errors:
            console.print(f"[red]{err}[/red]")
        return

    db = PackageDatabase()
    db.load()

    result = set_package_field(db, name, field, coerced)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to packages_db.json[/green]")


@packages.command(name="unset")
@click.argument("name")
@click.argument("field")
@click.pass_obj
def unset_field_cmd(ctx: Any, name: str, field: str) -> None:
    """Remove a package field override.

    \\b
    Examples:
        mf packages unset my-pkg description
        mf packages unset my-pkg license
    """
    from mf.core.field_ops import parse_field_path
    from mf.packages.database import PackageDatabase
    from mf.packages.field_ops import PACKAGES_SCHEMA, unset_package_field

    dry_run = ctx.dry_run if ctx else False

    top, _sub = parse_field_path(field)
    if top not in PACKAGES_SCHEMA:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf packages fields' to see valid fields.[/dim]")
        return

    db = PackageDatabase()
    db.load()

    try:
        result = unset_package_field(db, name, field)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        return

    _print_change(result)

    if result.old_value is None:
        console.print(f"[yellow]Field {field!r} was not set on {name}.[/yellow]")
        return

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to packages_db.json[/green]")


@packages.command(name="feature")
@click.argument("name")
@click.option("--off", is_flag=True, help="Remove from featured")
@click.pass_obj
def feature(ctx: Any, name: str, off: bool) -> None:
    """Toggle a package's featured status.

    \\b
    Examples:
        mf packages feature requests
        mf packages feature requests --off
    """
    from mf.packages.database import PackageDatabase
    from mf.packages.field_ops import set_package_field

    dry_run = ctx.dry_run if ctx else False

    db = PackageDatabase()
    db.load()

    value = not off
    result = set_package_field(db, name, "featured", value)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to packages_db.json[/green]")


@packages.command(name="tag")
@click.argument("name")
@click.option("--add", "add_tags", multiple=True, help="Tags to add")
@click.option("--remove", "remove_tags", multiple=True, help="Tags to remove")
@click.option("--set", "set_tags", help="Replace all tags (comma-separated)")
@click.pass_obj
def tag(ctx: Any, name: str, add_tags: tuple[str, ...], remove_tags: tuple[str, ...], set_tags: str | None) -> None:
    """Manage package tags.

    \\b
    Examples:
        mf packages tag requests --add http --add networking
        mf packages tag my-pkg --remove old-tag
        mf packages tag my-pkg --set "python,utility,http"
    """
    from mf.packages.database import PackageDatabase
    from mf.packages.field_ops import modify_package_list_field

    dry_run = ctx.dry_run if ctx else False

    if not add_tags and not remove_tags and set_tags is None:
        console.print("[red]Specify --add, --remove, or --set[/red]")
        return

    db = PackageDatabase()
    db.load()

    replace = None
    if set_tags is not None:
        replace = [t.strip() for t in set_tags.split(",") if t.strip()]

    result = modify_package_list_field(
        db,
        name,
        "tags",
        add=list(add_tags) if add_tags else None,
        remove=list(remove_tags) if remove_tags else None,
        replace=replace,
    )
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run -- no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to packages_db.json[/green]")


@packages.command()
def stats() -> None:
    """Show package database statistics."""
    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()

    s: dict[str, Any] = db.stats()

    registries_list: list[str] = list(s.get("registries", []))
    content = f"""[cyan]Total packages:[/cyan] {s.get('total', 0)}
[cyan]Featured:[/cyan] {s.get('featured', 0)}
[cyan]Registries:[/cyan] {', '.join(registries_list) or 'none'}"""

    console.print(Panel(content, title="Package Database Stats"))
