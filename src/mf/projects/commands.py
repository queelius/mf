"""CLI commands for GitHub projects management."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console

console = Console()


def _get_dry_run(ctx: Any) -> bool:
    """Extract the dry_run flag from the Click context object."""
    return ctx.dry_run if ctx else False


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if it exceeds max_len."""
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _save_and_regenerate(
    db: Any,
    slug: str,
    dry_run: bool,
    regenerate: bool,
) -> None:
    """Save database changes and optionally regenerate Hugo content.

    Shared tail logic for field override commands (set, unset, feature, hide, tag).
    """
    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to projects_db.json[/green]")

    if regenerate:
        _regenerate_project(slug, dry_run)


@click.group(name="projects")
def projects() -> None:
    """Manage GitHub projects.

    Import repositories, refresh metadata, and clean stale projects.
    """
    pass


@projects.command(name="import")
@click.option("--user", required=True, help="GitHub username to import from")
@click.option("--exclude-forks", is_flag=True, help="Exclude forked repositories")
@click.option("--exclude-archived", is_flag=True, help="Exclude archived repositories")
@click.option("--min-stars", type=int, help="Minimum number of stars")
@click.option("--has-description", is_flag=True, help="Only repos with descriptions")
@click.option("--language", multiple=True, help="Filter by language(s)")
@click.option("--topics", multiple=True, help="Filter by topic(s)")
@click.option("--include-private", is_flag=True, help="Include private repositories")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("-f", "--force", is_flag=True, help="Force overwrite existing projects")
@click.pass_obj
def import_repos(
    ctx,
    user: str,
    exclude_forks: bool,
    exclude_archived: bool,
    min_stars: int | None,
    has_description: bool,
    language: tuple[str, ...],
    topics: tuple[str, ...],
    include_private: bool,
    token: str | None,
    force: bool,
) -> None:
    """Import all repositories from a GitHub user."""
    from mf.projects.importer import import_user_repos

    import_user_repos(
        username=user,
        token=token,
        exclude_forks=exclude_forks,
        exclude_archived=exclude_archived,
        min_stars=min_stars,
        has_description=has_description,
        languages=list(language),
        topics=list(topics),
        include_private=include_private,
        force=force,
        dry_run=_get_dry_run(ctx),
    )


@projects.command()
@click.option("--slug", help="Refresh only a specific project")
@click.option("--older-than", type=float, help="Only refresh if not synced in N hours")
@click.option("--newer-than", type=float, help="Only refresh if synced within N hours")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("-f", "--force", is_flag=True, help="Force refresh even if unchanged")
@click.pass_obj
def refresh(
    ctx,
    slug: str | None,
    older_than: float | None,
    newer_than: float | None,
    token: str | None,
    force: bool,
) -> None:
    """Refresh project data from GitHub."""
    from mf.projects.importer import refresh_projects

    refresh_projects(
        slug=slug,
        token=token,
        older_than=older_than,
        newer_than=newer_than,
        force=force,
        dry_run=_get_dry_run(ctx),
    )


def _resolve_user(user: str | None) -> str | None:
    """Resolve GitHub username from argument or config, printing an error if missing."""
    if user:
        return user

    from mf.config.commands import get_config_value

    resolved: str | None = get_config_value("github.default_user")
    if not resolved:
        console.print("[red]No user specified. Use --user or set github.default_user in config.[/red]")
    return resolved


@projects.command()
@click.option("--user", help="GitHub username (uses config default if not set)")
@click.option("--include-private", is_flag=True, help="Include private repositories")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompts")
@click.option("--prune", is_flag=True, help="Also remove orphaned overrides from projects_db.json")
@click.pass_obj
def clean(ctx, user: str | None, include_private: bool, token: str | None, yes: bool, prune: bool) -> None:
    """Remove projects that no longer exist on GitHub."""
    from mf.projects.importer import clean_stale_projects

    user = _resolve_user(user)
    if not user:
        return

    clean_stale_projects(
        username=user,
        token=token,
        include_private=include_private,
        auto_confirm=yes,
        prune_overrides=prune,
        dry_run=_get_dry_run(ctx),
    )


@projects.command()
@click.option("--slug", help="Sync only a specific project (refresh only, skips clean/import)")
@click.option("--user", help="GitHub username (uses config default if not set)")
@click.option("--exclude-forks", is_flag=True, default=True, help="Exclude forked repositories")
@click.option("--include-private", is_flag=True, help="Include private repositories")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompts")
@click.option("--prune", is_flag=True, help="Also remove orphaned overrides from projects_db.json")
@click.pass_obj
def sync(ctx, slug: str | None, user: str | None, exclude_forks: bool, include_private: bool, token: str | None, yes: bool, prune: bool) -> None:
    """Full sync: clean stale, import new, refresh all.

    Combines clean, import, and refresh into one command.
    Honors manual overrides in projects_db.json.

    With --slug, only refreshes that specific project (skips clean/import).
    """
    from mf.projects.importer import (
        clean_stale_projects,
        import_user_repos,
        refresh_projects,
    )

    dry_run = _get_dry_run(ctx)

    if slug:
        console.print(f"[cyan]Syncing single project: {slug}[/cyan]")
        refresh_projects(slug=slug, token=token, force=True, dry_run=dry_run)
        return

    user = _resolve_user(user)
    if not user:
        return

    console.print("[bold cyan]Step 1/3: Cleaning stale projects...[/bold cyan]")
    clean_stale_projects(
        username=user,
        token=token,
        include_private=include_private,
        auto_confirm=yes,
        prune_overrides=prune,
        dry_run=dry_run,
    )

    console.print()
    console.print("[bold cyan]Step 2/3: Importing new repositories...[/bold cyan]")
    import_user_repos(
        username=user,
        token=token,
        exclude_forks=exclude_forks,
        include_private=include_private,
        dry_run=dry_run,
    )

    console.print()
    console.print("[bold cyan]Step 3/3: Refreshing all projects...[/bold cyan]")
    refresh_projects(token=token, force=True, dry_run=dry_run)

    console.print()
    console.print("[bold green]Sync complete![/bold green]")


@projects.command(name="rate-limit")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
def rate_limit(token: str | None) -> None:
    """Check GitHub API rate limit status."""
    from mf.projects.github import check_rate_limit

    check_rate_limit(token)


@projects.command(name="list")
@click.option("-q", "--query", help="Search in title/abstract")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("-c", "--category", help="Filter by category")
@click.option("--featured", is_flag=True, help="Only featured projects")
@click.option("--hidden", is_flag=True, help="Only hidden projects")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_projects(
    query: str | None,
    tag: tuple[str, ...],
    category: str | None,
    featured: bool,
    hidden: bool,
    as_json: bool,
) -> None:
    """List projects in the database."""
    import json as json_module

    from rich.table import Table

    from mf.core.database import ProjectsDatabase

    db = ProjectsDatabase()
    db.load()

    results = db.search(
        query=query,
        tags=list(tag) if tag else None,
        category=category,
        featured=featured or None,
        hidden=hidden or None,
    )

    if as_json:
        output = [{"slug": slug, **data} for slug, data in results]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No projects found matching criteria[/yellow]")
        return

    table = Table(title=f"Projects ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Category", style="green")
    table.add_column("Stars", style="yellow")
    table.add_column("Status", style="blue")

    for slug, data in results:
        title = data.get("title", slug)
        status = ""
        if data.get("featured"):
            status += "* "
        if data.get("hide"):
            status += "(hidden)"
        table.add_row(
            slug,
            _truncate(title, 40),
            data.get("category", ""),
            str(data.get("stars", "")),
            status,
        )

    console.print(table)


@projects.command()
def stats() -> None:
    """Show project database statistics."""
    from rich.panel import Panel

    from mf.core.database import ProjectsDatabase

    db = ProjectsDatabase()
    db.load()

    s = db.stats()

    content = f"""[cyan]Total projects:[/cyan] {s['total']}
[cyan]Featured:[/cyan] {s['featured']}
[cyan]Hidden:[/cyan] {s['hidden']}
[cyan]Visible:[/cyan] {s['visible']}
[cyan]Categories:[/cyan] {', '.join(s['categories']) or 'none'}"""

    console.print(Panel(content, title="Project Database Stats"))


@projects.command()
@click.argument("slug")
def show(slug: str) -> None:
    """Show details for a specific project."""
    import json as json_module

    from rich.panel import Panel
    from rich.syntax import Syntax

    from mf.core.database import ProjectsCache, ProjectsDatabase

    db = ProjectsDatabase()
    db.load()

    cache = ProjectsCache()
    cache.load()

    overrides = db.get(slug)
    cached = cache.get(slug)

    if not overrides and not cached:
        console.print(f"[red]Project not found: {slug}[/red]")
        return

    cached_summary = None
    if cached:
        cached_summary = {
            key: cached.get(key)
            for key in ("name", "description", "stargazers_count", "language", "topics", "_last_synced")
        }

    combined = {
        "overrides": overrides or {},
        "cached_github": cached_summary,
    }

    json_str = json_module.dumps(combined, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Project: {slug}"))


def _print_generation_summary(success: int, failed: int, label: str = "projects") -> None:
    """Print the success/failure summary after content generation."""
    console.print(f"\n[green]Generated {success} {label}[/green]")
    if failed:
        console.print(f"[yellow]Failed: {failed}[/yellow]")


@projects.command(name="generate")
@click.option("--slug", help="Generate only a specific project")
@click.option("--rich-only", is_flag=True, help="Only generate rich projects")
@click.pass_obj
def generate(ctx, slug: str | None, rich_only: bool) -> None:
    """Generate Hugo content for projects.

    Creates content/projects/{slug}/index.md (or _index.md for rich projects)
    from GitHub cache and manual overrides.
    """
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import (
        generate_all_projects,
        generate_project_content,
        merge_project_data,
    )

    dry_run = _get_dry_run(ctx)

    db = ProjectsDatabase()
    db.load()

    cache = ProjectsCache()
    cache.load()

    if slug:
        github_data = cache.get(slug)
        if not github_data:
            console.print(f"[red]Project not in cache: {slug}[/red]")
            console.print("[dim]Run 'mf projects import' or 'mf projects refresh' first[/dim]")
            return

        overrides = db.get(slug) or {}
        if rich_only and not overrides.get("rich_project"):
            console.print(f"[yellow]{slug} is not a rich project[/yellow]")
            return

        merged = merge_project_data(slug, github_data, overrides)
        generate_project_content(slug, merged, dry_run)
        return

    if rich_only:
        success = 0
        failed = 0
        for proj_slug in db.list_rich_projects():
            github_data = cache.get(proj_slug)
            if not github_data:
                console.print(f"  [yellow]No cache for: {proj_slug}[/yellow]")
                failed += 1
                continue
            overrides = db.get(proj_slug) or {}
            merged = merge_project_data(proj_slug, github_data, overrides)
            if generate_project_content(proj_slug, merged, dry_run):
                success += 1
            else:
                failed += 1
        _print_generation_summary(success, failed, "rich projects")
    else:
        success, failed = generate_all_projects(cache, db, dry_run)
        _print_generation_summary(success, failed)


@projects.command(name="list-rich")
def list_rich() -> None:
    """List projects configured as rich (branch bundles)."""
    from rich.table import Table

    from mf.core.database import ProjectsDatabase

    db = ProjectsDatabase()
    db.load()

    rich_projects = db.list_rich_projects()

    if not rich_projects:
        console.print("[yellow]No rich projects configured[/yellow]")
        console.print(
            "[dim]Set 'rich_project: true' in projects_db.json to enable[/dim]"
        )
        return

    table = Table(title=f"Rich Projects ({len(rich_projects)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Sections", style="green")
    table.add_column("External Docs", style="blue")

    for slug in rich_projects:
        data = db.get(slug) or {}
        title = data.get("title", slug)
        sections = data.get("content_sections", [])
        external = data.get("external_docs", {})

        table.add_row(
            slug,
            _truncate(title, 35),
            ", ".join(sections) if sections else "-",
            ", ".join(external.keys()) if external else "-",
        )

    console.print(table)


@projects.command(name="make-rich")
@click.argument("slug")
@click.option("--sections", multiple=True, default=["docs"],
              help="Content sections to create (default: docs)")
@click.pass_obj
def make_rich(ctx, slug: str, sections: tuple[str, ...]) -> None:
    """Configure a project as a rich project (branch bundle).

    This updates projects_db.json to mark the project as rich and
    specifies which content sections to create.

    \\b
    Examples:
        mf projects make-rich my-project
        mf projects make-rich my-project --sections docs --sections tutorials
    """
    from mf.core.database import ProjectsDatabase

    dry_run = _get_dry_run(ctx)

    db = ProjectsDatabase()
    db.load()

    current = db.get(slug) or {}

    if current.get("rich_project"):
        console.print(f"[yellow]{slug} is already a rich project[/yellow]")
        console.print(f"[dim]Current sections: {current.get('content_sections', [])}[/dim]")
        return

    db.update(slug, rich_project=True, content_sections=list(sections))

    if dry_run:
        console.print(f"[dim]Would mark {slug} as rich with sections: {list(sections)}[/dim]")
        return

    db.save()
    console.print(f"[green]Marked {slug} as rich project[/green]")
    console.print(f"[dim]Sections: {list(sections)}[/dim]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print(f"  1. Run: mf projects generate --slug {slug}")
    console.print(f"  2. Edit content/projects/{slug}/_index.md")
    console.print("  3. Add content to section pages")


# -- Field override commands ---------------------------------------------------


def _regenerate_project(slug: str, dry_run: bool) -> None:
    """Run project content generation for a single slug."""
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import generate_project_content, merge_project_data

    cache = ProjectsCache()
    cache.load()
    github_data = cache.get(slug)
    if not github_data:
        console.print(f"[dim]Tip: Run 'mf projects generate --slug {slug}' to update Hugo content[/dim]")
        return

    db = ProjectsDatabase()
    db.load()
    overrides = db.get(slug) or {}
    merged = merge_project_data(slug, github_data, overrides)
    generate_project_content(slug, merged, dry_run)
    console.print(f"[green]Regenerated content for {slug}[/green]")


def _print_change(result: Any) -> None:
    """Print a ChangeResult as a formatted diff."""
    console.print(f"[cyan]{result.slug}[/cyan]: {result.field}")
    if result.old_value is not None:
        console.print(f"  old: {result.old_value}")
    if result.new_value is not None:
        console.print(f"  new: {result.new_value}")
    elif result.action == "unset":
        console.print("  [dim](removed)[/dim]")


def _validate_field_name(field: str) -> bool:
    """Validate that the top-level field name is in the schema.

    Prints an error and returns False if the field is unknown.
    """
    from mf.projects.field_ops import FIELD_SCHEMA, parse_field_path

    top, _sub = parse_field_path(field)
    if top not in FIELD_SCHEMA:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf projects fields' to see valid fields.[/dim]")
        return False
    return True


@projects.command(name="fields")
def fields_cmd() -> None:
    """List all valid project fields and their types."""
    from rich.table import Table

    from mf.projects.field_ops import FIELD_SCHEMA

    table = Table(title="Project Fields")
    table.add_column("Field", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description")
    table.add_column("Constraints", style="yellow")

    for name, fdef in sorted(FIELD_SCHEMA.items()):
        constraints = []
        if fdef.choices:
            constraints.append(f"choices: {', '.join(fdef.choices)}")
        if fdef.min_val is not None:
            constraints.append(f"min: {fdef.min_val}")
        if fdef.max_val is not None:
            constraints.append(f"max: {fdef.max_val}")
        table.add_row(name, fdef.field_type.value, fdef.description, "; ".join(constraints) or "-")

    console.print(table)
    console.print("\n[dim]Use dot notation for dict sub-keys: packages.pypi, external_docs.mkdocs[/dim]")


@projects.command(name="set")
@click.argument("slug")
@click.argument("field")
@click.argument("value")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def set_field(ctx, slug: str, field: str, value: str, regenerate: bool) -> None:
    """Set a project field value.

    Supports dot notation for nested dicts (e.g. packages.pypi).

    \\b
    Examples:
        mf projects set my-project stars 5
        mf projects set my-project category library
        mf projects set my-project tags "python,stats"
        mf projects set my-project packages.pypi my-package
    """
    from mf.core.database import ProjectsDatabase
    from mf.projects.field_ops import (
        FIELD_SCHEMA,
        coerce_value,
        parse_field_path,
        set_project_field,
        validate_field,
    )

    dry_run = _get_dry_run(ctx)

    top, sub = parse_field_path(field)
    schema = FIELD_SCHEMA.get(top)
    if schema is None:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf projects fields' to see valid fields.[/dim]")
        return

    # For dot-notation on dict fields, the value is always a string
    try:
        coerced = value if sub is not None else coerce_value(value, schema)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    errors = validate_field(field, coerced)
    if errors:
        for err in errors:
            console.print(f"[red]{err}[/red]")
        return

    db = ProjectsDatabase()
    db.load()

    result = set_project_field(db, slug, field, coerced)
    _print_change(result)

    _save_and_regenerate(db, slug, dry_run, regenerate)


@projects.command(name="unset")
@click.argument("slug")
@click.argument("field")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def unset_field(ctx, slug: str, field: str, regenerate: bool) -> None:
    """Remove a project field override.

    \\b
    Examples:
        mf projects unset my-project stars
        mf projects unset my-project packages.pypi
    """
    from mf.projects.field_ops import unset_project_field

    dry_run = _get_dry_run(ctx)

    if not _validate_field_name(field):
        return

    from mf.core.database import ProjectsDatabase

    db = ProjectsDatabase()
    db.load()

    try:
        result = unset_project_field(db, slug, field)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        return

    _print_change(result)

    if result.old_value is None:
        console.print(f"[yellow]Field {field!r} was not set on {slug}.[/yellow]")
        return

    _save_and_regenerate(db, slug, dry_run, regenerate)


@projects.command(name="feature")
@click.argument("slug")
@click.option("--off", is_flag=True, help="Remove from featured")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def feature(ctx, slug: str, off: bool, regenerate: bool) -> None:
    """Toggle a project's featured status.

    \\b
    Examples:
        mf projects feature my-project
        mf projects feature my-project --off
    """
    from mf.core.database import ProjectsDatabase
    from mf.projects.field_ops import set_project_field

    dry_run = _get_dry_run(ctx)

    db = ProjectsDatabase()
    db.load()

    result = set_project_field(db, slug, "featured", not off)
    _print_change(result)

    _save_and_regenerate(db, slug, dry_run, regenerate)


@projects.command(name="hide")
@click.argument("slug")
@click.option("--off", is_flag=True, help="Unhide the project")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def hide(ctx, slug: str, off: bool, regenerate: bool) -> None:
    """Toggle a project's hidden status.

    \\b
    Examples:
        mf projects hide my-project
        mf projects hide my-project --off
    """
    from mf.core.database import ProjectsDatabase
    from mf.projects.field_ops import set_project_field

    dry_run = _get_dry_run(ctx)

    db = ProjectsDatabase()
    db.load()

    result = set_project_field(db, slug, "hide", not off)
    _print_change(result)

    _save_and_regenerate(db, slug, dry_run, regenerate)


@projects.command(name="tag")
@click.argument("slug")
@click.option("--add", "add_tags", multiple=True, help="Tags to add")
@click.option("--remove", "remove_tags", multiple=True, help="Tags to remove")
@click.option("--set", "set_tags", help="Replace all tags (comma-separated)")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def tag(ctx, slug: str, add_tags: tuple[str, ...], remove_tags: tuple[str, ...], set_tags: str | None, regenerate: bool) -> None:
    """Manage project tags.

    \\b
    Examples:
        mf projects tag my-project --add python --add stats
        mf projects tag my-project --remove old-tag
        mf projects tag my-project --set "python,stats,ml"
    """
    from mf.core.database import ProjectsDatabase
    from mf.projects.field_ops import modify_list_field

    dry_run = _get_dry_run(ctx)

    if not add_tags and not remove_tags and set_tags is None:
        console.print("[red]Specify --add, --remove, or --set[/red]")
        return

    db = ProjectsDatabase()
    db.load()

    replace = None
    if set_tags is not None:
        replace = [t.strip() for t in set_tags.split(",") if t.strip()]

    result = modify_list_field(
        db,
        slug,
        "tags",
        add=list(add_tags) if add_tags else None,
        remove=list(remove_tags) if remove_tags else None,
        replace=replace,
    )
    _print_change(result)

    _save_and_regenerate(db, slug, dry_run, regenerate)


@projects.command(name="codemeta-status")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
def codemeta_status(token: str | None) -> None:
    """Show which projects have codemeta.json in their GitHub repos.

    Checks each project's GitHub repository for a codemeta.json file.
    """
    import requests
    from rich.table import Table

    from mf.core.database import ProjectsCache

    cache = ProjectsCache()
    cache.load()

    table = Table(title="CodeMeta Status")
    table.add_column("Project", style="cyan")
    table.add_column("GitHub URL")
    table.add_column("Has codemeta.json", style="green")

    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    checked = 0
    has_codemeta = 0

    for slug in cache:
        entry = cache.get(slug)
        if not entry:
            continue

        github_url = entry.get("html_url") or entry.get("github")
        if not github_url:
            continue

        owner_repo = _parse_github_url(github_url)
        if not owner_repo:
            continue

        owner, repo = owner_repo
        checked += 1

        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/codemeta.json"
        try:
            resp = requests.get(api_url, headers=headers, timeout=10)
            has_file = resp.status_code == 200
            if has_file:
                has_codemeta += 1
        except requests.RequestException:
            has_file = False

        table.add_row(
            slug,
            _truncate(github_url, 40),
            "yes" if has_file else "-",
        )

    console.print(table)
    console.print(f"\n[dim]Checked {checked} projects, {has_codemeta} have codemeta.json[/dim]")


@projects.command(name="fetch-codemeta")
@click.option("--slug", help="Fetch for specific project")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch for all projects with github URL")
@click.option("--force", is_flag=True, help="Overwrite existing fields (default: only fill empty)")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.pass_obj
def fetch_codemeta(ctx, slug: str | None, fetch_all: bool, force: bool, token: str | None) -> None:
    """Fetch codemeta.json from GitHub repos and merge into projects.

    By default, only fills empty fields in the project data. Use --force
    to overwrite all fields from codemeta.json.

    \\b
    Examples:
        mf projects fetch-codemeta --slug my-project
        mf projects fetch-codemeta --all
        mf projects fetch-codemeta --all --force  # Overwrite existing
    """
    import requests

    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.codemeta import codemeta_to_project_fields, parse_codemeta

    dry_run = _get_dry_run(ctx)

    if not slug and not fetch_all:
        console.print("[red]Specify --slug or --all[/red]")
        return

    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()

    headers: dict[str, str] = {"Accept": "application/vnd.github.v3.raw"}
    if token:
        headers["Authorization"] = f"token {token}"

    fetched = 0
    skipped = 0
    errors = 0

    slugs_to_check = [slug] if slug else list(cache)

    for proj_slug in slugs_to_check:
        entry = cache.get(proj_slug)
        if not entry:
            if slug:
                console.print(f"[red]Project not found in cache: {proj_slug}[/red]")
            continue

        github_url = entry.get("html_url") or entry.get("github")
        if not github_url:
            skipped += 1
            continue

        owner_repo = _parse_github_url(github_url)
        if not owner_repo:
            skipped += 1
            continue

        owner, repo = owner_repo

        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/codemeta.json"
        try:
            resp = requests.get(raw_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                if slug:
                    console.print(f"[yellow]{proj_slug}: No codemeta.json found[/yellow]")
                skipped += 1
                continue

            content = resp.text
        except requests.RequestException as e:
            console.print(f"[red]{proj_slug}: Error fetching: {e}[/red]")
            errors += 1
            continue

        cm = parse_codemeta(content)
        fields = codemeta_to_project_fields(cm)

        if not fields:
            if slug:
                console.print(f"[yellow]{proj_slug}: codemeta.json has no usable fields[/yellow]")
            skipped += 1
            continue

        current = db.get(proj_slug) or {}

        if force:
            updated = {**current, **fields}
        else:
            updated = current.copy()
            for key, field_value in fields.items():
                if key not in updated or not updated[key]:
                    updated[key] = field_value

        if dry_run:
            console.print(f"[cyan]{proj_slug}[/cyan]: Would update with {list(fields.keys())}")
        else:
            db.set(proj_slug, updated)
            console.print(f"[green]{proj_slug}: Updated with {list(fields.keys())}[/green]")

        fetched += 1

    if not dry_run and fetched > 0:
        db.save()

    console.print(f"\n[green]Fetched:[/green] {fetched}")
    if skipped:
        console.print(f"[dim]Skipped (no codemeta.json):[/dim] {skipped}")
    if errors:
        console.print(f"[red]Errors:[/red] {errors}")


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Parse owner and repo from GitHub URL.

    Args:
        url: GitHub URL like https://github.com/owner/repo

    Returns:
        Tuple of (owner, repo) or None if not a valid GitHub URL
    """
    if not url:
        return None

    url = url.rstrip("/")

    if "github.com/" in url:
        parts = url.split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return (parts[0], parts[1])

    return None
