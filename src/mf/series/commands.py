"""CLI commands for series management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from mf.core.field_ops import ChangeResult
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group(name="series")
def series() -> None:
    """Manage content series.

    Series are thematic collections of posts (e.g., "Stepanov", "The Long Echo").
    """
    pass


@series.command(name="list")
@click.option("-q", "--query", help="Search in title/description")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("-s", "--status", help="Filter by status (active, completed, archived)")
@click.option("--featured", is_flag=True, help="Only featured series")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_series(
    query: str | None,
    tag: tuple[str, ...],
    status: str | None,
    featured: bool,
    as_json: bool,
) -> None:
    """List all series in the database."""
    import json as json_module

    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    results = db.search(
        query=query,
        tags=list(tag) if tag else None,
        status=status,
        featured=True if featured else None,
    )

    # Get post counts for each series
    post_counts = _get_series_post_counts()

    if as_json:
        output = []
        for entry in results:
            data = dict(entry.data)
            data["slug"] = entry.slug
            data["post_count"] = post_counts.get(entry.slug, 0)
            output.append(data)
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No series found matching criteria[/yellow]")
        return

    table = Table(title=f"Series ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Posts", style="green", justify="right")
    table.add_column("Status", style="blue")
    table.add_column("Flags")

    for entry in sorted(results, key=lambda e: e.title):
        flags = ""
        if entry.featured:
            flags += "F "

        table.add_row(
            entry.slug,
            entry.title[:40] + "..." if len(entry.title) > 40 else entry.title,
            str(post_counts.get(entry.slug, 0)),
            entry.status,
            flags.strip(),
        )

    console.print(table)
    console.print("\n[dim]F = Featured[/dim]")


@series.command()
@click.argument("slug")
@click.option("--landing", is_flag=True, help="Show landing page content")
def show(slug: str, landing: bool) -> None:
    """Show details for a specific series."""
    import json as json_module

    from rich.markdown import Markdown
    from rich.syntax import Syntax

    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    entry = db.get(slug)

    if not entry:
        console.print(f"[red]Series not found: {slug}[/red]")
        console.print("[dim]Use 'mf series list' to see available series[/dim]")
        return

    # If --landing flag is set, show landing page content and exit
    if landing:
        landing_path = None
        source_label = None
        strip_frontmatter = False

        # Try external source first
        if entry.source_dir and entry.landing_page:
            candidate = entry.source_dir / entry.landing_page
            if candidate.exists():
                landing_path = candidate
                source_label = str(candidate)

        # Fallback to local Hugo content
        if landing_path is None:
            from mf.core.config import get_paths
            local_path = get_paths().content / "series" / slug / "_index.md"
            if local_path.exists():
                landing_path = local_path
                source_label = f"content/series/{slug}/_index.md (local)"
                strip_frontmatter = True

        if landing_path is None:
            console.print("[yellow]No landing page found[/yellow]")
            console.print("[dim]No source_dir configured and no local _index.md found[/dim]")
            return

        content = landing_path.read_text(encoding="utf-8")
        # Strip YAML front matter for local Hugo files
        if strip_frontmatter and content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        console.print(Panel(
            Markdown(content),
            title=f"Landing: {entry.title or slug}",
            subtitle=f"Source: {source_label}"
        ))
        return

    # Get posts in this series
    posts = _get_posts_in_series(slug)

    # Build display data
    display_data: dict[str, Any] = {
        "title": entry.title,
        "description": entry.description,
        "status": entry.status,
        "featured": entry.featured,
        "tags": entry.tags,
        "color": entry.color,
        "icon": entry.icon,
        "created_date": entry.created_date,
        "related_projects": entry.related_projects,
        "post_count": len(posts),
    }

    # Add source sync info if configured
    if entry.has_source():
        display_data["source_dir"] = str(entry.source_dir)
        display_data["posts_subdir"] = entry.posts_subdir
        display_data["landing_page"] = entry.landing_page

    # Add associations if present
    if entry.associations:
        display_data["associations"] = entry.associations

    # Remove None values for cleaner display
    display_data = {k: v for k, v in display_data.items() if v is not None and v != []}

    json_str = json_module.dumps(display_data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Series: {slug}"))

    if posts:
        console.print(f"\n[cyan]Posts in this series ({len(posts)}):[/cyan]")
        for post in posts:
            console.print(f"  - {post['title']}")
            console.print(f"    [dim]{post['path']}[/dim]")

    # Show associations
    if entry.related_papers:
        console.print("\n[cyan]Related papers:[/cyan]")
        for paper in entry.related_papers:
            console.print(f"  - {paper}")

    if entry.related_media:
        console.print("\n[cyan]Related media:[/cyan]")
        for media in entry.related_media:
            console.print(f"  - {media}")

    if entry.external_links:
        console.print("\n[cyan]External links:[/cyan]")
        for link in entry.external_links:
            console.print(f"  - [{link.get('name', 'Link')}]({link.get('url', '')})")


@series.command()
@click.option("--include-orphans", is_flag=True, help="Show posts with series not in DB")
def scan(include_orphans: bool) -> None:
    """Scan content for series usage and report statistics.

    Shows which series are used in content and identifies any orphaned
    series references (series used in content but not defined in the database).
    """

    import frontmatter

    from mf.core.config import get_paths
    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    paths = get_paths()
    content_dir = paths.content

    # Scan all posts for series usage
    series_usage: dict[str, list[dict]] = {}
    all_posts = list((content_dir / "post").rglob("*.md"))

    for post_path in all_posts:
        try:
            post = frontmatter.load(post_path)
            series_list = post.get("series", [])

            # Handle both string and list
            if isinstance(series_list, str):
                series_list = [series_list]

            for series_slug in series_list:
                if series_slug not in series_usage:
                    series_usage[series_slug] = []
                series_usage[series_slug].append({
                    "title": post.get("title", post_path.stem),
                    "path": str(post_path.relative_to(paths.root)),
                    "date": str(post.get("date", "")),
                })
        except Exception as e:
            click.echo(f"Warning: skipping {post_path}: {e}", err=True)
            continue

    # Get series in DB
    db_series = set(db)

    # Get series found in content
    content_series = set(series_usage.keys())

    # Orphaned series (in content but not in DB)
    orphaned = content_series - db_series

    # Unused series (in DB but not in content)
    unused = db_series - content_series

    # Stats panel
    console.print(Panel(
        f"[cyan]Total series in DB:[/cyan] {len(db)}\n"
        f"[cyan]Series used in content:[/cyan] {len(content_series)}\n"
        f"[cyan]Total posts with series:[/cyan] {sum(len(p) for p in series_usage.values())}\n"
        f"[yellow]Orphaned (in content, not in DB):[/yellow] {len(orphaned)}\n"
        f"[yellow]Unused (in DB, not in content):[/yellow] {len(unused)}",
        title="Series Scan Results"
    ))

    # Show series usage table
    table = Table(title="Series Usage")
    table.add_column("Series", style="cyan")
    table.add_column("Posts", style="green", justify="right")
    table.add_column("In DB", style="blue")
    table.add_column("Featured", style="yellow")

    for series_slug in sorted(content_series | db_series):
        post_count = len(series_usage.get(series_slug, []))
        in_db = "Yes" if series_slug in db_series else "[red]No[/red]"

        entry = db.get(series_slug)
        featured = "Yes" if entry and entry.featured else "-"

        table.add_row(
            series_slug,
            str(post_count) if post_count else "-",
            in_db,
            featured,
        )

    console.print(table)

    # Report orphaned series
    if orphaned:
        console.print("\n[yellow]Orphaned series (used in content but not in DB):[/yellow]")
        for slug in sorted(orphaned):
            console.print(f"  - [cyan]{slug}[/cyan] ({len(series_usage[slug])} posts)")
            console.print("    [dim]Consider adding to series_db.json[/dim]")

    # Report unused series
    if unused:
        console.print("\n[yellow]Unused series (in DB but no content):[/yellow]")
        for slug in sorted(unused):
            entry = db.get(slug)
            console.print(f"  - [cyan]{slug}[/cyan]: {entry.title if entry else slug}")


@series.command()
def stats() -> None:
    """Show series database statistics."""
    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    s: dict[str, Any] = db.stats()
    post_counts = _get_series_post_counts()
    total_posts = sum(post_counts.values())

    statuses_list: list[str] = list(s.get("statuses", []))
    content = f"""[cyan]Total series:[/cyan] {s.get('total', 0)}
[cyan]Featured:[/cyan] {s.get('featured', 0)}
[cyan]Active:[/cyan] {s.get('active', 0)}
[cyan]Total posts in series:[/cyan] {total_posts}
[cyan]Statuses:[/cyan] {', '.join(statuses_list) or 'none'}"""

    console.print(Panel(content, title="Series Database Stats"))


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


@series.command(name="fields")
def fields_cmd() -> None:
    """List all valid series fields and their types."""
    from mf.series.field_ops import SERIES_SCHEMA

    table = Table(title="Series Fields")
    table.add_column("Field", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description")
    table.add_column("Constraints", style="yellow")

    for name, fdef in sorted(SERIES_SCHEMA.items()):
        constraints = []
        if fdef.choices:
            constraints.append(f"choices: {', '.join(fdef.choices)}")
        if fdef.min_val is not None:
            constraints.append(f"min: {fdef.min_val}")
        if fdef.max_val is not None:
            constraints.append(f"max: {fdef.max_val}")
        table.add_row(name, fdef.field_type.value, fdef.description, "; ".join(constraints) or "-")

    console.print(table)


@series.command(name="set")
@click.argument("slug")
@click.argument("field")
@click.argument("value")
@click.pass_obj
def set_field_cmd(ctx, slug: str, field: str, value: str) -> None:
    """Set a series field value.

    \\b
    Examples:
        mf series set my-series status completed
        mf series set my-series color "#ff6b6b"
        mf series set my-series tags "math,computing"
    """
    from mf.core.database import SeriesDatabase
    from mf.core.field_ops import coerce_value, parse_field_path
    from mf.series.field_ops import SERIES_SCHEMA, set_series_field, validate_series_field

    dry_run = ctx.dry_run if ctx else False

    top, sub = parse_field_path(field)
    schema = SERIES_SCHEMA.get(top)
    if schema is None:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf series fields' to see valid fields.[/dim]")
        return

    # Coerce value
    try:
        coerced = value if sub is not None else coerce_value(value, schema)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Validate
    errors = validate_series_field(field, coerced)
    if errors:
        for err in errors:
            console.print(f"[red]{err}[/red]")
        return

    db = SeriesDatabase()
    db.load()

    result = set_series_field(db, slug, field, coerced)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to series_db.json[/green]")


@series.command(name="unset")
@click.argument("slug")
@click.argument("field")
@click.pass_obj
def unset_field_cmd(ctx, slug: str, field: str) -> None:
    """Remove a series field override.

    \\b
    Examples:
        mf series unset my-series color
        mf series unset my-series icon
    """
    from mf.core.database import SeriesDatabase
    from mf.core.field_ops import parse_field_path
    from mf.series.field_ops import SERIES_SCHEMA, unset_series_field

    dry_run = ctx.dry_run if ctx else False

    top, _sub = parse_field_path(field)
    if top not in SERIES_SCHEMA:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf series fields' to see valid fields.[/dim]")
        return

    db = SeriesDatabase()
    db.load()

    try:
        result = unset_series_field(db, slug, field)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        return

    _print_change(result)

    if result.old_value is None:
        console.print(f"[yellow]Field {field!r} was not set on {slug}.[/yellow]")
        return

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to series_db.json[/green]")


@series.command(name="feature")
@click.argument("slug")
@click.option("--off", is_flag=True, help="Remove from featured")
@click.pass_obj
def feature(ctx, slug: str, off: bool) -> None:
    """Toggle a series' featured status.

    \\b
    Examples:
        mf series feature my-series
        mf series feature my-series --off
    """
    from mf.core.database import SeriesDatabase
    from mf.series.field_ops import set_series_field

    dry_run = ctx.dry_run if ctx else False

    db = SeriesDatabase()
    db.load()

    value = not off
    result = set_series_field(db, slug, "featured", value)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to series_db.json[/green]")


@series.command(name="tag")
@click.argument("slug")
@click.option("--add", "add_tags", multiple=True, help="Tags to add")
@click.option("--remove", "remove_tags", multiple=True, help="Tags to remove")
@click.option("--set", "set_tags", help="Replace all tags (comma-separated)")
@click.pass_obj
def tag(ctx, slug: str, add_tags: tuple[str, ...], remove_tags: tuple[str, ...], set_tags: str | None) -> None:
    """Manage series tags.

    \\b
    Examples:
        mf series tag my-series --add math --add computing
        mf series tag my-series --remove old-tag
        mf series tag my-series --set "math,computing,philosophy"
    """
    from mf.core.database import SeriesDatabase
    from mf.series.field_ops import modify_series_list_field

    dry_run = ctx.dry_run if ctx else False

    if not add_tags and not remove_tags and set_tags is None:
        console.print("[red]Specify --add, --remove, or --set[/red]")
        return

    db = SeriesDatabase()
    db.load()

    replace = None
    if set_tags is not None:
        replace = [t.strip() for t in set_tags.split(",") if t.strip()]

    result = modify_series_list_field(
        db,
        slug,
        "tags",
        add=list(add_tags) if add_tags else None,
        remove=list(remove_tags) if remove_tags else None,
        replace=replace,
    )
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to series_db.json[/green]")


# -----------------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------------


def _get_series_post_counts() -> dict[str, int]:
    """Get post count for each series by scanning content."""

    from mf.core.config import get_paths

    try:
        import frontmatter
    except ImportError:
        return {}

    paths = get_paths()
    content_dir = paths.content

    counts: dict[str, int] = {}

    try:
        for post_path in (content_dir / "post").rglob("*.md"):
            try:
                post = frontmatter.load(post_path)
                series_list = post.get("series", [])

                if isinstance(series_list, str):
                    series_list = [series_list]

                for series_slug in series_list:
                    counts[series_slug] = counts.get(series_slug, 0) + 1
            except Exception as e:
                click.echo(f"Warning: skipping {post_path}: {e}", err=True)
                continue
    except Exception as e:
        click.echo(f"Warning: error scanning posts: {e}", err=True)

    return counts


def _get_posts_in_series(slug: str) -> list[dict]:
    """Get all posts in a specific series."""

    from mf.core.config import get_paths

    try:
        import frontmatter
    except ImportError:
        return []

    paths = get_paths()
    content_dir = paths.content

    posts = []

    try:
        for post_path in (content_dir / "post").rglob("*.md"):
            try:
                post = frontmatter.load(post_path)
                series_list = post.get("series", [])

                if isinstance(series_list, str):
                    series_list = [series_list]

                if slug in series_list:
                    posts.append({
                        "title": post.get("title", post_path.stem),
                        "path": str(post_path.relative_to(paths.root)),
                        "date": str(post.get("date", "")),
                    })
            except Exception as e:
                click.echo(f"Warning: skipping {post_path}: {e}", err=True)
                continue
    except Exception as e:
        click.echo(f"Warning: error scanning posts: {e}", err=True)

    # Sort by date
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)

    return posts


@series.command()
@click.argument("slug", required=False)
@click.option("--all", "sync_all", is_flag=True, help="Sync all series with source_dir")
@click.option("--push", is_flag=True, help="Push metafunctor → source (default is pull)")
@click.option("--posts-only", is_flag=True, help="Skip landing page sync")
@click.option("--landing-only", is_flag=True, help="Skip posts sync")
@click.option("--delete", is_flag=True, help="Delete posts removed from source")
@click.option("--dry-run", is_flag=True, help="Preview changes without syncing")
@click.option("-v", "--verbose", is_flag=True, help="Show all posts, not just changes")
@click.option("--diff", "show_diff", is_flag=True, help="Show diff for conflicted posts")
@click.option("--ours", "resolve_ours", is_flag=True, help="Resolve conflicts by keeping metafunctor version")
@click.option("--theirs", "resolve_theirs", is_flag=True, help="Resolve conflicts by taking source version")
@click.option("--interactive", "interactive", is_flag=True, help="Prompt for each conflict")
@click.option("--add-mkdocs", is_flag=True, help="Update MkDocs site in source repo (push only)")
def sync(
    slug: str | None,
    sync_all: bool,
    push: bool,
    posts_only: bool,
    landing_only: bool,
    delete: bool,
    dry_run: bool,
    verbose: bool,
    show_diff: bool,
    resolve_ours: bool,
    resolve_theirs: bool,
    interactive: bool,
    add_mkdocs: bool,
) -> None:
    """Sync series posts from external source repository.

    Pull posts from source repo to metafunctor (default), or push
    with --push flag.

    \b
    Conflict Resolution:
        By default, conflicted posts (changed in both source and metafunctor)
        are skipped. Use resolution flags to handle conflicts:

        --ours     Keep metafunctor version (overwrite source on push)
        --theirs   Take source version (overwrite metafunctor on pull)
        --diff     Show unified diff for conflicted posts
        --interactive  Prompt for each conflict

    \b
    Examples:
        mf series sync stepanov           # Pull stepanov posts
        mf series sync stepanov --dry-run # Preview changes
        mf series sync stepanov --dry-run --diff  # Preview with diffs
        mf series sync stepanov --push    # Push to source repo
        mf series sync stepanov --theirs  # Pull, taking source for conflicts
        mf series sync --all              # Sync all configured series
    """
    from mf.core.database import SeriesDatabase
    from mf.series.syncer import (
        ConflictResolution,
        execute_sync,
        list_syncable_series,
        plan_pull_sync,
        plan_push_sync,
        print_sync_plan,
    )

    # Validate --add-mkdocs requires --push
    if add_mkdocs and not push:
        console.print("[red]--add-mkdocs can only be used with --push[/red]")
        return

    # Validate conflict resolution flags
    if sum([resolve_ours, resolve_theirs, interactive]) > 1:
        console.print("[red]Cannot use multiple conflict resolution flags together[/red]")
        return

    # Determine conflict resolution strategy
    if resolve_ours:
        conflict_resolution = ConflictResolution.OURS
    elif resolve_theirs:
        conflict_resolution = ConflictResolution.THEIRS
    else:
        conflict_resolution = ConflictResolution.SKIP

    db = SeriesDatabase()
    db.load()

    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]\n")

    # Determine which series to sync
    if sync_all:
        entries = list_syncable_series(db)
        if not entries:
            console.print("[yellow]No series have source_dir configured[/yellow]")
            return
        console.print(f"Syncing {len(entries)} series with source configuration\n")
    elif slug:
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Series not found: {slug}[/red]")
            return
        if not entry.has_source():
            console.print(f"[yellow]Series '{slug}' has no source_dir configured[/yellow]")
            return
        entries = [entry]
    else:
        console.print("[red]Specify a series slug or use --all[/red]")
        console.print("\n[dim]Series with source_dir configured:[/dim]")
        for entry in list_syncable_series(db):
            console.print(f"  - {entry.slug}")
        return

    include_posts = not landing_only
    include_landing = not posts_only

    total_success = 0
    total_failures = 0
    total_conflicts = 0

    for entry in entries:
        console.print(f"\n[cyan]{'='*60}[/cyan]")
        console.print(f"[cyan]Series: {entry.slug}[/cyan]")
        console.print(f"[cyan]{'='*60}[/cyan]")

        # Plan the sync
        if push:
            plan = plan_push_sync(entry, include_landing, include_posts)
        else:
            plan = plan_pull_sync(entry, include_landing, include_posts)

        # Print plan
        print_sync_plan(plan, verbose, show_diff=show_diff)

        if plan.errors:
            continue

        if not plan.has_changes:
            console.print("[green]Already up to date[/green]")
        else:
            # Handle interactive mode for conflicts
            effective_resolution = conflict_resolution
            if interactive and plan.conflict_count > 0:
                effective_resolution = _prompt_conflict_resolution(plan, push)

            # Execute sync
            console.print("\n[cyan]Executing sync...[/cyan]")
            success, failures, skipped = execute_sync(
                plan, db,
                delete=delete,
                dry_run=dry_run,
                conflict_resolution=effective_resolution,
            )
            total_success += success
            total_failures += failures
            total_conflicts += skipped

        # MkDocs sync (runs even when no post changes — associations may differ)
        if add_mkdocs and entry.source_dir:
            from mf.core.database import PaperDatabase, ProjectsDatabase
            from mf.series.mkdocs import execute_mkdocs_sync

            paper_db = PaperDatabase()
            paper_db.load()
            proj_db = ProjectsDatabase()
            proj_db.load()

            execute_mkdocs_sync(
                entry,
                entry.source_dir,
                paper_db=paper_db,
                projects_db=proj_db,
                dry_run=dry_run,
            )

    # Summary
    if len(entries) > 1 or total_conflicts > 0:
        console.print(f"\n[cyan]{'='*60}[/cyan]")
        console.print("[cyan]Summary[/cyan]")
        console.print(f"[cyan]{'='*60}[/cyan]")
        console.print(f"[green]Success:[/green] {total_success}")
        console.print(f"[red]Failures:[/red] {total_failures}")
        if total_conflicts > 0:
            console.print(f"[magenta]Conflicts skipped:[/magenta] {total_conflicts}")
            console.print("[dim]Use --ours, --theirs, or --interactive to resolve conflicts[/dim]")


def _prompt_conflict_resolution(plan: Any, push: bool) -> Any:
    """Prompt user for conflict resolution in interactive mode.

    Args:
        plan: The sync plan with conflicts
        push: Whether this is a push operation

    Returns:
        ConflictResolution to use
    """
    from mf.series.syncer import ConflictResolution, print_conflict_diff

    console.print(f"\n[magenta bold]Found {plan.conflict_count} conflict(s)[/magenta bold]")

    for item in plan.conflicts:
        print_conflict_diff(item)

    console.print("\n[cyan]How do you want to resolve these conflicts?[/cyan]")
    if push:
        console.print("  [1] Skip conflicts (keep both versions unchanged)")
        console.print("  [2] Use metafunctor version (--ours)")
        console.print("  [3] Cancel")
    else:
        console.print("  [1] Skip conflicts (keep both versions unchanged)")
        console.print("  [2] Use source version (--theirs)")
        console.print("  [3] Cancel")

    choice: int = click.prompt("Choice", type=click.IntRange(1, 3), default=1)  # type: ignore[arg-type]

    if choice == 1:
        return ConflictResolution.SKIP
    elif choice == 2:
        return ConflictResolution.OURS if push else ConflictResolution.THEIRS
    else:
        raise click.Abort()


@series.command()
@click.argument("series_slug")
@click.argument("content_path")
def add(series_slug: str, content_path: str) -> None:
    """Add a post or content file to a series.

    Updates the frontmatter of the target file to include
    the series in its 'series' field.

    \b
    Examples:
        mf series add stepanov content/post/2024-01-01-my-post/index.md
        mf series add the-long-echo content/post/2024-02-15-legacy/
    """
    from pathlib import Path

    import frontmatter

    from mf.core.config import get_paths
    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    # Verify series exists
    entry = db.get(series_slug)
    if not entry:
        console.print(f"[red]Series not found: {series_slug}[/red]")
        console.print("[dim]Use 'mf series list' to see available series[/dim]")
        return

    # Resolve content path
    paths = get_paths()
    content_file = Path(content_path)

    # Handle directory paths (look for index.md)
    if content_file.is_dir():
        content_file = content_file / "index.md"

    # Make path absolute if relative
    if not content_file.is_absolute():
        content_file = paths.root / content_file

    if not content_file.exists():
        console.print(f"[red]File not found: {content_file}[/red]")
        return

    try:
        post = frontmatter.load(content_file)

        # Get current series list
        series_list = post.get("series", [])
        if isinstance(series_list, str):
            series_list = [series_list]

        # Check if already in series
        if series_slug in series_list:
            console.print(f"[yellow]Already in series '{series_slug}': {content_file.name}[/yellow]")
            return

        # Add to series
        series_list.append(series_slug)
        post["series"] = series_list

        # Write back
        with open(content_file, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        console.print(f"[green]Added to series '{series_slug}':[/green] {content_file.relative_to(paths.root)}")

    except Exception as e:
        console.print(f"[red]Error updating file: {e}[/red]")


@series.command()
@click.argument("series_slug")
@click.argument("content_path")
def remove(series_slug: str, content_path: str) -> None:
    """Remove a post or content file from a series.

    Updates the frontmatter of the target file to remove
    the series from its 'series' field.

    \b
    Examples:
        mf series remove stepanov content/post/2024-01-01-my-post/index.md
        mf series remove the-long-echo content/post/2024-02-15-legacy/
    """
    from pathlib import Path

    import frontmatter

    from mf.core.config import get_paths
    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    # Verify series exists
    entry = db.get(series_slug)
    if not entry:
        console.print(f"[red]Series not found: {series_slug}[/red]")
        console.print("[dim]Use 'mf series list' to see available series[/dim]")
        return

    # Resolve content path
    paths = get_paths()
    content_file = Path(content_path)

    # Handle directory paths (look for index.md)
    if content_file.is_dir():
        content_file = content_file / "index.md"

    # Make path absolute if relative
    if not content_file.is_absolute():
        content_file = paths.root / content_file

    if not content_file.exists():
        console.print(f"[red]File not found: {content_file}[/red]")
        return

    try:
        post = frontmatter.load(content_file)

        # Get current series list
        series_list = post.get("series", [])
        if isinstance(series_list, str):
            series_list = [series_list]

        # Check if in series
        if series_slug not in series_list:
            console.print(f"[yellow]Not in series '{series_slug}': {content_file.name}[/yellow]")
            return

        # Remove from series
        series_list.remove(series_slug)

        # Update or remove the field
        if series_list:
            post["series"] = series_list
        else:
            del post["series"]

        # Write back
        with open(content_file, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        console.print(f"[green]Removed from series '{series_slug}':[/green] {content_file.relative_to(paths.root)}")

    except Exception as e:
        console.print(f"[red]Error updating file: {e}[/red]")


@series.command()
@click.argument("slug")
@click.option("--title", help="Series title (default: slug titlecased)")
@click.option("--description", help="Short description for cards")
@click.option("--source", "source_dir", type=click.Path(), help="External source directory (enables sync)")
@click.option("--init-source", is_flag=True, help="Create source directory structure if --source given")
@click.option("--tags", help="Comma-separated tags")
@click.option("--color", default="#667eea", help="Hex color for UI")
@click.option("--featured", is_flag=True, help="Mark as featured")
@click.option("--status", default="active", type=click.Choice(["active", "completed", "archived"]), help="Series status")
def create(
    slug: str,
    title: str | None,
    description: str | None,
    source_dir: str | None,
    init_source: bool,
    tags: str | None,
    color: str,
    featured: bool,
    status: str,
) -> None:
    """Create a new series in the database.

    Creates an entry in series_db.json. If --source is provided,
    configures sync to an external repository. Use --init-source
    to also scaffold the source directory structure.

    \b
    Examples:
        # Create inline series (no external source)
        mf series create my-new-series --title "My New Series"

        # Create series with external source
        mf series create my-series --title "My Series" \\
            --source ~/github/alpha/my-series

        # Create and initialize source structure
        mf series create my-series --title "My Series" \\
            --source ~/github/alpha/my-series --init-source
    """
    from datetime import datetime
    from pathlib import Path

    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    # Check if series already exists
    if slug in db:
        console.print(f"[red]Series already exists: {slug}[/red]")
        console.print("[dim]Use 'mf series show' to view existing series[/dim]")
        return

    # Build series data
    series_data = {
        "title": title or slug.replace("-", " ").title(),
        "status": status,
        "featured": featured,
        "color": color,
        "created_date": datetime.now().strftime("%Y-%m-%d"),
    }

    if description:
        series_data["description"] = description

    if tags:
        series_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    # Handle source configuration
    if source_dir:
        source_path = Path(source_dir).expanduser().resolve()
        series_data["source_dir"] = str(source_path)
        series_data["posts_subdir"] = "post"
        series_data["landing_page"] = "docs/index.md"

        if init_source:
            _init_source_structure(source_path, str(series_data["title"]), slug)

    # Save to database
    db.set(slug, series_data)
    db.save()

    console.print(f"[green]Created series:[/green] {slug}")
    console.print(f"  [cyan]Title:[/cyan] {series_data['title']}")
    console.print(f"  [cyan]Status:[/cyan] {series_data['status']}")

    if source_dir:
        console.print(f"  [cyan]Source:[/cyan] {source_dir}")
        if init_source:
            console.print("  [cyan]Initialized source structure[/cyan]")

    console.print("\n[dim]Use 'mf series add' to add posts to this series[/dim]")
    if source_dir:
        console.print("[dim]Use 'mf series sync' to sync with source repository[/dim]")


def _init_source_structure(source_path: Path, title: str, slug: str) -> None:
    """Initialize the source directory structure for a series.

    Args:
        source_path: Path to create the source structure
        title: Series title
        slug: Series slug
    """
    from datetime import datetime

    # Create directories
    (source_path / "post").mkdir(parents=True, exist_ok=True)
    (source_path / "docs").mkdir(parents=True, exist_ok=True)

    # Create README.md
    readme_content = f"""# {title}

This repository contains the source content for the {title} series on metafunctor.com.

## Structure

- `post/` - Individual posts in the series
- `docs/` - Landing page and documentation

## Syncing

Use `mf series sync {slug}` to sync content to metafunctor.com.

## Created

{datetime.now().strftime('%Y-%m-%d')}
"""
    readme_path = source_path / "README.md"
    if not readme_path.exists():
        readme_path.write_text(readme_content, encoding="utf-8")
        console.print(f"  Created: {readme_path}")

    # Create landing page template
    landing_content = f"""---
title: "{title}"
description: "A series about..."
---

## About This Series

Welcome to the {title} series. This series explores...

## Posts

Posts will be listed automatically when synced to metafunctor.
"""
    landing_path = source_path / "docs" / "index.md"
    if not landing_path.exists():
        landing_path.write_text(landing_content, encoding="utf-8")
        console.print(f"  Created: {landing_path}")


@series.command(name="delete")
@click.argument("slug")
@click.option("--purge", is_flag=True, help="Remove all traces: database entry, content directory, and series references from posts")
@click.option("--dry-run", is_flag=True, help="Preview what would be deleted without making changes")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
def delete_series(slug: str, purge: bool, dry_run: bool, yes: bool) -> None:
    """Delete a series from the database.

    By default, removes only the series entry from series_db.json.

    With --purge, removes all traces: the database entry, the local
    content directory (content/series/{slug}/), and strips the series
    reference from any posts that mention it.

    \b
    Examples:
        mf series delete my-series --dry-run     # Preview
        mf series delete my-series -y             # DB entry only
        mf series delete my-series --purge -y     # Remove all traces
    """
    import shutil

    import frontmatter

    from mf.core.config import get_paths
    from mf.core.database import SeriesDatabase

    db = SeriesDatabase()
    db.load()

    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Series not found: {slug}[/red]")
        console.print("[dim]Use 'mf series list' to see available series[/dim]")
        return

    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]\n")

    # Gather state
    posts = _get_posts_in_series(slug)
    paths = get_paths()
    content_dir = paths.content / "series" / slug

    # Show what will happen
    console.print(f"[cyan]Series:[/cyan] {entry.title} ({slug})")
    console.print(f"[cyan]Status:[/cyan] {entry.status}")
    console.print("[cyan]Database:[/cyan] series_db.json [red](will be removed)[/red]")

    if content_dir.exists():
        if purge:
            console.print(f"[cyan]Content dir:[/cyan] {content_dir.relative_to(paths.root)} [red](will be deleted)[/red]")
        else:
            console.print(f"[cyan]Content dir:[/cyan] {content_dir.relative_to(paths.root)} (will be kept)")

    if posts:
        if purge:
            console.print(f"[cyan]Posts:[/cyan] {len(posts)} post(s) [red](series reference will be stripped)[/red]")
            for post in posts[:5]:
                console.print(f"  - {post['title']} [dim]({post['path']})[/dim]")
            if len(posts) > 5:
                console.print(f"  ... and {len(posts) - 5} more")
        else:
            console.print(f"[yellow]Warning:[/yellow] {len(posts)} post(s) reference this series (use --purge to strip)")

    if dry_run:
        console.print("\n[yellow]DRY RUN - nothing was deleted[/yellow]")
        return

    # Confirm
    if not yes:
        click.confirm("\nDelete this series?", abort=True)

    # 1. Delete from database
    if db.delete(slug):
        db.save()
        console.print(f"[green]Deleted from series_db.json:[/green] {slug}")
    else:
        console.print("[red]Failed to delete from database[/red]")
        return

    if purge:
        # 2. Delete content directory
        if content_dir.exists():
            shutil.rmtree(content_dir)
            console.print(f"[green]Deleted content directory:[/green] {content_dir.relative_to(paths.root)}")

        # 3. Strip series references from posts
        if posts:
            stripped = 0
            for post_info in posts:
                post_path = paths.root / post_info["path"]
                try:
                    post = frontmatter.load(post_path)
                    series_list = post.get("series", [])
                    if isinstance(series_list, str):
                        series_list = [series_list]

                    if slug in series_list:
                        series_list.remove(slug)
                        if series_list:
                            post["series"] = series_list
                        else:
                            del post["series"]

                        with open(post_path, "w", encoding="utf-8") as f:
                            f.write(frontmatter.dumps(post))
                        stripped += 1
                except Exception as e:
                    console.print(f"[red]Failed to update {post_info['path']}: {e}[/red]")

            console.print(f"[green]Stripped series reference from {stripped} post(s)[/green]")
    elif posts:
        console.print(f"\n[yellow]Note:[/yellow] {len(posts)} post(s) still reference series '{slug}'")
        console.print("[dim]Use --purge to remove all traces, or 'mf series scan' to find orphans[/dim]")


def _load_series_frontmatter(series_slug: str) -> tuple[Path, dict, str]:
    """Load frontmatter from a series _index.md file.

    Args:
        series_slug: The series slug

    Returns:
        Tuple of (file_path, frontmatter_dict, content_body)

    Raises:
        FileNotFoundError: If series content file doesn't exist
    """
    import frontmatter

    from mf.core.config import get_paths

    paths = get_paths()
    series_file = paths.content / "series" / series_slug / "_index.md"

    if not series_file.exists():
        raise FileNotFoundError(f"Series content file not found: {series_file}")

    post = frontmatter.load(series_file)
    return series_file, dict(post.metadata), post.content


def _save_series_frontmatter(file_path: Path, metadata: dict, content: str) -> None:
    """Save frontmatter and content to a series _index.md file.

    Args:
        file_path: Path to the series _index.md file
        metadata: Frontmatter dictionary
        content: Body content
    """
    import frontmatter

    post = frontmatter.Post(content, **metadata)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))


def _ensure_associations(metadata: dict[str, Any]) -> dict[str, Any]:
    """Ensure the associations structure exists in metadata.

    Args:
        metadata: Frontmatter dictionary

    Returns:
        The associations dict (possibly newly created)
    """
    if "associations" not in metadata:
        metadata["associations"] = {}
    assoc: dict[str, Any] = metadata["associations"]

    # Ensure all sub-structures exist
    if "featured" not in assoc:
        assoc["featured"] = []
    if "projects" not in assoc:
        assoc["projects"] = []
    if "papers" not in assoc:
        assoc["papers"] = []
    if "writing" not in assoc:
        assoc["writing"] = []
    if "links" not in assoc:
        assoc["links"] = []

    return assoc


@series.command(name="add-featured")
@click.argument("series_slug")
@click.argument("artifact")
def add_featured(series_slug: str, artifact: str) -> None:
    """Add a featured artifact (centerpiece) to a series.

    The artifact argument should be in the format type:slug, where type
    is one of: project, paper, writing.

    \b
    Examples:
        mf series add-featured the-long-echo project:longecho
        mf series add-featured minds-and-machines writing:the-policy
        mf series add-featured oblivious-computing paper:bernoulli-sets
    """
    # Parse type:slug
    if ":" not in artifact:
        console.print(f"[red]Invalid artifact format: {artifact}[/red]")
        console.print("[dim]Expected format: type:slug (e.g., project:longecho)[/dim]")
        return

    artifact_type, artifact_slug = artifact.split(":", 1)

    valid_types = ["project", "paper", "writing"]
    if artifact_type not in valid_types:
        console.print(f"[red]Invalid artifact type: {artifact_type}[/red]")
        console.print(f"[dim]Valid types: {', '.join(valid_types)}[/dim]")
        return

    try:
        file_path, metadata, content = _load_series_frontmatter(series_slug)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    assoc = _ensure_associations(metadata)

    # Check if already featured
    for feat in assoc["featured"]:
        if feat.get("type") == artifact_type and feat.get("slug") == artifact_slug:
            console.print(f"[yellow]Already featured: {artifact_type}:{artifact_slug}[/yellow]")
            return

    # Add the featured artifact
    assoc["featured"].append({
        "type": artifact_type,
        "slug": artifact_slug
    })

    _save_series_frontmatter(file_path, metadata, content)
    console.print(f"[green]Added featured artifact:[/green] {artifact_type}:{artifact_slug}")
    console.print(f"[dim]Updated: {file_path}[/dim]")


@series.command(name="add-related")
@click.argument("series_slug")
@click.option("--paper", "papers", multiple=True, help="Paper slug to add")
@click.option("--project", "projects", multiple=True, help="Project slug to add")
@click.option("--writing", "writings", multiple=True, help="Writing slug to add")
def add_related(
    series_slug: str,
    papers: tuple[str, ...],
    projects: tuple[str, ...],
    writings: tuple[str, ...],
) -> None:
    """Add related content to a series.

    Related content appears in the series page but is not the centerpiece.

    \b
    Examples:
        mf series add-related the-long-echo --project ctk --project btk
        mf series add-related oblivious-computing --paper crypto-perf-hash
        mf series add-related minds-and-machines --writing echoes-sublime
    """
    if not papers and not projects and not writings:
        console.print("[yellow]No content specified. Use --paper, --project, or --writing.[/yellow]")
        return

    try:
        file_path, metadata, content = _load_series_frontmatter(series_slug)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    assoc = _ensure_associations(metadata)

    added_count = 0

    # Add papers
    for paper in papers:
        if paper not in assoc["papers"]:
            assoc["papers"].append(paper)
            console.print(f"[green]Added paper:[/green] {paper}")
            added_count += 1
        else:
            console.print(f"[yellow]Paper already added:[/yellow] {paper}")

    # Add projects
    for project in projects:
        if project not in assoc["projects"]:
            assoc["projects"].append(project)
            console.print(f"[green]Added project:[/green] {project}")
            added_count += 1
        else:
            console.print(f"[yellow]Project already added:[/yellow] {project}")

    # Add writings
    for writing in writings:
        if writing not in assoc["writing"]:
            assoc["writing"].append(writing)
            console.print(f"[green]Added writing:[/green] {writing}")
            added_count += 1
        else:
            console.print(f"[yellow]Writing already added:[/yellow] {writing}")

    if added_count > 0:
        _save_series_frontmatter(file_path, metadata, content)
        console.print(f"\n[dim]Updated: {file_path}[/dim]")
    else:
        console.print("\n[dim]No changes made[/dim]")


@series.command(name="add-link")
@click.argument("series_slug")
@click.argument("name")
@click.argument("url")
def add_link(series_slug: str, name: str, url: str) -> None:
    """Add an external link to a series.

    External links appear in a links section on the series page.

    \b
    Examples:
        mf series add-link the-long-echo "GitHub Organization" "https://github.com/long-echo"
        mf series add-link stepanov "Stepanov Papers" "http://stepanovpapers.com"
    """
    try:
        file_path, metadata, content = _load_series_frontmatter(series_slug)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    assoc = _ensure_associations(metadata)

    # Check if link already exists
    for link in assoc["links"]:
        if link.get("url") == url:
            console.print(f"[yellow]Link already exists:[/yellow] {url}")
            return

    # Add the link
    assoc["links"].append({
        "name": name,
        "url": url
    })

    _save_series_frontmatter(file_path, metadata, content)
    console.print(f"[green]Added link:[/green] {name} → {url}")
    console.print(f"[dim]Updated: {file_path}[/dim]")


@series.command(name="artifacts")
@click.argument("series_slug")
def artifacts(series_slug: str) -> None:
    """List all artifacts and content in a series.

    Shows featured items, related papers, projects, writing, links, and posts.

    \b
    Examples:
        mf series artifacts the-long-echo
        mf series artifacts stepanov
    """
    try:
        file_path, metadata, content = _load_series_frontmatter(series_slug)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    assoc = metadata.get("associations", {})

    # Get posts in this series
    posts = _get_posts_in_series(series_slug)

    # Create display panel
    console.print(Panel(
        f"[cyan]Title:[/cyan] {metadata.get('title', series_slug)}\n"
        f"[cyan]Description:[/cyan] {metadata.get('description', 'No description')[:80]}...",
        title=f"Series: {series_slug}"
    ))

    # Featured artifacts
    featured = assoc.get("featured", [])
    if featured:
        console.print("\n[bold cyan]Featured Artifacts (Centerpieces)[/bold cyan]")
        for feat in featured:
            artifact_type = feat.get('type', 'unknown')
            artifact_slug = feat.get('slug', 'unknown')
            console.print(f"  ⭐ [cyan]({artifact_type})[/cyan] {artifact_slug}")
    else:
        console.print("\n[dim]No featured artifacts[/dim]")

    # Related projects
    projects = assoc.get("projects", [])
    if projects:
        console.print("\n[bold cyan]Related Projects[/bold cyan]")
        for proj in projects:
            console.print(f"  📦 {proj}")

    # Related papers
    papers = assoc.get("papers", [])
    if papers:
        console.print("\n[bold cyan]Related Papers[/bold cyan]")
        for paper in papers:
            console.print(f"  📄 {paper}")

    # Related writing
    writings = assoc.get("writing", [])
    if writings:
        console.print("\n[bold cyan]Related Writing[/bold cyan]")
        for writing in writings:
            console.print(f"  ✍️  {writing}")

    # External links
    links = assoc.get("links", [])
    if links:
        console.print("\n[bold cyan]External Links[/bold cyan]")
        for link in links:
            console.print(f"  🔗 {link.get('name', 'Link')}: {link.get('url', '')}")

    # Posts
    if posts:
        console.print(f"\n[bold cyan]Posts ({len(posts)})[/bold cyan]")
        for post in posts[:10]:  # Show first 10
            console.print(f"  📝 {post['title']}")
        if len(posts) > 10:
            console.print(f"  [dim]... and {len(posts) - 10} more posts[/dim]")
    else:
        console.print("\n[dim]No posts in this series[/dim]")

    # Summary
    total = len(featured) + len(projects) + len(papers) + len(writings) + len(links) + len(posts)
    console.print(f"\n[cyan]Total artifacts:[/cyan] {total}")
