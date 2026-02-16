"""CLI commands for paper management."""

from __future__ import annotations

import contextlib
import json as json_module
from typing import TYPE_CHECKING, Any

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mf.core.field_ops import ChangeResult

if TYPE_CHECKING:
    from mf.papers.zenodo import ZenodoClient

console = Console()


@click.group()
def papers() -> None:
    """Manage research papers.

    Process LaTeX papers, generate Hugo content, and sync changes.
    """
    pass


@papers.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--slug", help="Override slug for the paper")
@click.option("-y", "--yes", is_flag=True, help="Auto-answer yes to prompts")
@click.pass_obj
def process(ctx, source: str, slug: str | None, yes: bool) -> None:
    """Process a LaTeX paper into Hugo content.

    SOURCE is a path to a .tex file or directory containing .tex files.
    """
    from mf.papers.processor import process_paper

    dry_run = ctx.dry_run if ctx else False
    process_paper(source, slug=slug, auto_yes=yes, dry_run=dry_run)


@papers.command()
@click.option("--slug", help="Sync only a specific paper by slug")
@click.option("-y", "--yes", is_flag=True, help="Auto-regenerate stale papers")
@click.option(
    "-w", "--workers",
    default=1,
    type=click.IntRange(1, 16),
    help="Number of parallel workers for processing (default: 1)",
)
@click.option(
    "-t", "--timeout",
    default=300,
    type=click.IntRange(30, 1800),
    help="Timeout per paper in seconds (default: 300 = 5 min)",
)
@click.pass_obj
def sync(ctx, slug: str | None, yes: bool, workers: int, timeout: int) -> None:
    """Check for stale papers and regenerate.

    Compares source file hashes with stored hashes to detect changes.

    Use --workers to process multiple papers in parallel (e.g., -w 4).
    This can significantly speed up syncing when many papers are stale.

    Use --timeout to set max time per paper (default: 5 minutes).
    Papers that exceed the timeout will be reported as failed.
    """
    from mf.papers.sync import sync_papers

    dry_run = ctx.dry_run if ctx else False
    sync_papers(slug=slug, auto_yes=yes, dry_run=dry_run, workers=workers, timeout=timeout)


@papers.command()
@click.option("--slug", help="Generate only a specific paper")
@click.option("--no-image-cache", is_flag=True, help="Force regenerate thumbnails")
@click.pass_obj
def generate(ctx, slug: str | None, no_image_cache: bool) -> None:
    """Generate Hugo content from /static/latex/.

    Reads paper metadata and generates content/papers/ markdown files.
    """
    from mf.papers.generator import generate_papers

    dry_run = ctx.dry_run if ctx else False
    generate_papers(slug=slug, use_image_cache=not no_image_cache, dry_run=dry_run)


@papers.command(name="list")
@click.option("-q", "--query", help="Search in title/abstract")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("-c", "--category", help="Filter by category")
@click.option("--with-source", is_flag=True, help="Only papers with source tracking")
@click.option("--featured", is_flag=True, help="Only featured papers")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_papers(
    query: str | None,
    tag: tuple[str, ...],
    category: str | None,
    with_source: bool,
    featured: bool,
    as_json: bool,
) -> None:
    """List papers in the database."""
    import json as json_module

    from rich.table import Table

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    results = db.search(
        query=query,
        tags=list(tag) if tag else None,
        category=category,
        has_source=True if with_source else None,
        featured=True if featured else None,
    )

    if as_json:
        output = [{"slug": e.slug, **e.data} for e in results]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No papers found matching criteria[/yellow]")
        return

    table = Table(title=f"Papers ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Category", style="green")
    table.add_column("Source", style="blue")

    for entry in results:
        source = "✓" if entry.source_path else ""
        table.add_row(
            entry.slug,
            entry.title[:50] + "..." if len(entry.title) > 50 else entry.title,
            str(entry.data.get("category", "")),
            source,
        )

    console.print(table)


@papers.command()
def stats() -> None:
    """Show paper database statistics."""
    from rich.panel import Panel

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    s = db.stats()

    content = f"""[cyan]Total papers:[/cyan] {s['total']}
[cyan]With source tracking:[/cyan] {s['with_source']}
[cyan]Featured:[/cyan] {s['featured']}
[cyan]Categories:[/cyan] {', '.join(s['categories']) or 'none'}"""

    console.print(Panel(content, title="Paper Database Stats"))


@papers.command()
@click.argument("slug")
def show(slug: str) -> None:
    """Show details for a specific paper."""
    from rich.syntax import Syntax

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Paper not found: {slug}[/red]")
        return

    # Pretty print as JSON
    json_str = json_module.dumps(entry.data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Paper: {slug}"))


# -----------------------------------------------------------------------------
# Field override commands
# -----------------------------------------------------------------------------


def _regenerate_paper(slug: str, dry_run: bool) -> None:
    """Run paper content generation for a single slug."""
    from mf.papers.generator import generate_papers

    generate_papers(slug=slug, dry_run=dry_run)
    console.print(f"[green]\u2713[/green] Regenerated content for {slug}")


def _print_change(result: ChangeResult) -> None:
    """Print a ChangeResult as a formatted diff."""
    console.print(f"[cyan]{result.slug}[/cyan]: {result.field}")
    if result.old_value is not None:
        console.print(f"  old: {result.old_value}")
    if result.new_value is not None:
        console.print(f"  new: {result.new_value}")
    elif result.action == "unset":
        console.print("  [dim](removed)[/dim]")


@papers.command(name="fields")
def fields_cmd() -> None:
    """List all valid paper fields and their types."""
    from mf.papers.field_ops import PAPERS_SCHEMA

    table = Table(title="Paper Fields")
    table.add_column("Field", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description")
    table.add_column("Constraints", style="yellow")

    for name, fdef in sorted(PAPERS_SCHEMA.items()):
        constraints = []
        if fdef.choices:
            constraints.append(f"choices: {', '.join(fdef.choices)}")
        if fdef.min_val is not None:
            constraints.append(f"min: {fdef.min_val}")
        if fdef.max_val is not None:
            constraints.append(f"max: {fdef.max_val}")
        table.add_row(name, fdef.field_type.value, fdef.description, "; ".join(constraints) or "-")

    console.print(table)


@papers.command(name="set")
@click.argument("slug")
@click.argument("field")
@click.argument("value")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def set_field_cmd(ctx, slug: str, field: str, value: str, regenerate: bool) -> None:
    """Set a paper field value.

    \\b
    Examples:
        mf papers set my-paper stars 5
        mf papers set my-paper status published
        mf papers set my-paper tags "stats,ml"
        mf papers set my-paper venue "NeurIPS 2024"
    """
    from mf.core.database import PaperDatabase
    from mf.core.field_ops import coerce_value, parse_field_path
    from mf.papers.field_ops import PAPERS_SCHEMA, set_paper_field, validate_paper_field

    dry_run = ctx.dry_run if ctx else False

    top, sub = parse_field_path(field)
    schema = PAPERS_SCHEMA.get(top)
    if schema is None:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf papers fields' to see valid fields.[/dim]")
        return

    # Coerce value
    try:
        coerced = value if sub is not None else coerce_value(value, schema)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Validate
    errors = validate_paper_field(field, coerced)
    if errors:
        for err in errors:
            console.print(f"[red]{err}[/red]")
        return

    db = PaperDatabase()
    db.load()

    result = set_paper_field(db, slug, field, coerced)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to paper_db.json[/green]")

    if regenerate:
        _regenerate_paper(slug, dry_run)


@papers.command(name="unset")
@click.argument("slug")
@click.argument("field")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def unset_field_cmd(ctx, slug: str, field: str, regenerate: bool) -> None:
    """Remove a paper field override.

    \\b
    Examples:
        mf papers unset my-paper stars
        mf papers unset my-paper venue
    """
    from mf.core.database import PaperDatabase
    from mf.core.field_ops import parse_field_path
    from mf.papers.field_ops import PAPERS_SCHEMA, unset_paper_field

    dry_run = ctx.dry_run if ctx else False

    top, _sub = parse_field_path(field)
    if top not in PAPERS_SCHEMA:
        console.print(f"[red]Unknown field: {top!r}[/red]")
        console.print("[dim]Run 'mf papers fields' to see valid fields.[/dim]")
        return

    db = PaperDatabase()
    db.load()

    try:
        result = unset_paper_field(db, slug, field)
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
    console.print("[green]Saved to paper_db.json[/green]")

    if regenerate:
        _regenerate_paper(slug, dry_run)


@papers.command(name="feature")
@click.argument("slug")
@click.option("--off", is_flag=True, help="Remove from featured")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def feature(ctx, slug: str, off: bool, regenerate: bool) -> None:
    """Toggle a paper's featured status.

    \\b
    Examples:
        mf papers feature my-paper
        mf papers feature my-paper --off
    """
    from mf.core.database import PaperDatabase
    from mf.papers.field_ops import set_paper_field

    dry_run = ctx.dry_run if ctx else False

    db = PaperDatabase()
    db.load()

    value = not off
    result = set_paper_field(db, slug, "featured", value)
    _print_change(result)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    db.save()
    console.print("[green]Saved to paper_db.json[/green]")

    if regenerate:
        _regenerate_paper(slug, dry_run)


@papers.command(name="tag")
@click.argument("slug")
@click.option("--add", "add_tags", multiple=True, help="Tags to add")
@click.option("--remove", "remove_tags", multiple=True, help="Tags to remove")
@click.option("--set", "set_tags", help="Replace all tags (comma-separated)")
@click.option("--regenerate", is_flag=True, help="Regenerate Hugo content after change")
@click.pass_obj
def tag(ctx, slug: str, add_tags: tuple[str, ...], remove_tags: tuple[str, ...], set_tags: str | None, regenerate: bool) -> None:
    """Manage paper tags.

    \\b
    Examples:
        mf papers tag my-paper --add statistics --add ml
        mf papers tag my-paper --remove old-tag
        mf papers tag my-paper --set "statistics,ml,optimization"
    """
    from mf.core.database import PaperDatabase
    from mf.papers.field_ops import modify_paper_list_field

    dry_run = ctx.dry_run if ctx else False

    if not add_tags and not remove_tags and set_tags is None:
        console.print("[red]Specify --add, --remove, or --set[/red]")
        return

    db = PaperDatabase()
    db.load()

    replace = None
    if set_tags is not None:
        replace = [t.strip() for t in set_tags.split(",") if t.strip()]

    result = modify_paper_list_field(
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
    console.print("[green]Saved to paper_db.json[/green]")

    if regenerate:
        _regenerate_paper(slug, dry_run)


# -----------------------------------------------------------------------------
# Zenodo subcommand group
# -----------------------------------------------------------------------------


@papers.group()
def zenodo() -> None:
    """Manage Zenodo DOI registration for papers.

    Zenodo is a research data repository that provides DOIs for research outputs.
    Use these commands to register papers and get permanent DOIs.

    \b
    Setup:
    1. Get API token from https://zenodo.org/account/settings/applications/
    2. Add to .mf/config.yaml:
       zenodo:
         api_token: "your-token-here"
         sandbox: false  # Use true for testing
    """
    pass


def _load_zenodo_config() -> dict[str, Any]:
    """Load Zenodo config from .mf/config.yaml."""
    from mf.core.config import get_paths

    config_path = get_paths().config_file
    if not config_path.exists():
        return {}

    try:
        with open(config_path) as f:
            content = f.read()
            # Handle both YAML and JSON
            if content.strip().startswith("{"):
                loaded = json_module.loads(content)
                return loaded if isinstance(loaded, dict) else {}
            loaded = yaml.safe_load(content)
            return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _get_zenodo_client() -> tuple[ZenodoClient, bool]:
    """Get configured Zenodo client or raise error."""
    from mf.papers.zenodo import ZenodoClient

    config = _load_zenodo_config()
    zenodo_config: dict[str, Any] = config.get("zenodo", {})
    api_token = zenodo_config.get("api_token")

    if not api_token:
        console.print("[red]Zenodo API token not configured![/red]")
        console.print()
        console.print("To configure:")
        console.print("1. Get API token from https://zenodo.org/account/settings/applications/")
        console.print("2. Add to .mf/config.yaml:")
        console.print()
        console.print("   zenodo:")
        console.print('     api_token: "your-token-here"')
        console.print("     sandbox: false  # Use true for testing")
        raise SystemExit(1)

    sandbox = bool(zenodo_config.get("sandbox", False))
    return ZenodoClient(api_token=str(api_token), sandbox=sandbox), sandbox


@zenodo.command(name="list")
@click.option("--min-stars", default=3, help="Minimum star rating for eligibility")
@click.option("--all", "show_all", is_flag=True, help="Show all papers, not just eligible")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def zenodo_list(min_stars: int, show_all: bool, as_json: bool) -> None:
    """List papers eligible for Zenodo registration.

    By default, shows papers with 3+ stars that don't have a Zenodo DOI.
    """
    from mf.core.database import PaperDatabase
    from mf.papers.zenodo import is_eligible_for_zenodo

    db = PaperDatabase()
    db.load()

    results = []
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue

        eligible = is_eligible_for_zenodo(entry, min_stars)

        if show_all or eligible:
            results.append({
                "slug": slug,
                "title": entry.title[:60] + "..." if len(entry.title) > 60 else entry.title,
                "stars": entry.stars,
                "category": entry.data.get("category", ""),
                "doi": entry.doi,
                "zenodo_doi": entry.zenodo_doi,
                "eligible": eligible,
            })

    # Sort by stars descending, then by slug
    results.sort(key=lambda x: (-x["stars"], x["slug"]))

    if as_json:
        console.print(json_module.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No papers found matching criteria[/yellow]")
        return

    # Summary
    eligible_count = sum(1 for r in results if r["eligible"])
    registered_count = sum(1 for r in results if r["zenodo_doi"])

    table = Table(title=f"Papers for Zenodo ({eligible_count} eligible, {registered_count} registered)")
    table.add_column("Slug", style="cyan")
    table.add_column("Stars", justify="center")
    table.add_column("Category", style="green")
    table.add_column("Status")

    for r in results:
        if r["zenodo_doi"]:
            status = f"[green]✓[/green] {r['zenodo_doi']}"
        elif r["doi"]:
            status = f"[blue]Has DOI[/blue] {r['doi'][:30]}..."
        elif r["eligible"]:
            status = "[yellow]Eligible[/yellow]"
        else:
            status = f"[dim]< {min_stars} stars[/dim]"

        table.add_row(
            r["slug"],
            "⭐" * r["stars"] if r["stars"] <= 5 else str(r["stars"]),
            r["category"][:20],
            status,
        )

    console.print(table)
    console.print()
    console.print("[dim]Use --all to show all papers, --min-stars N to change threshold[/dim]")


@zenodo.command()
@click.argument("slug", required=False)
@click.option("--all", "register_all", is_flag=True, help="Register all eligible papers")
@click.option("--force", is_flag=True, help="Register even if < min stars")
@click.option("--publish", is_flag=True, help="Actually publish (get DOI). Without this, dry-run.")
@click.option("--min-stars", default=3, help="Minimum star rating for eligibility")
@click.pass_obj
def register(ctx, slug: str | None, register_all: bool, force: bool, publish: bool, min_stars: int) -> None:
    """Register a paper on Zenodo to get a DOI.

    \b
    By default, runs in dry-run mode showing what would be uploaded.
    Use --publish to actually create the DOI (irreversible).

    \b
    Examples:
        mf papers zenodo register my-paper          # Dry run
        mf papers zenodo register my-paper --publish  # Actually publish
        mf papers zenodo register --all --publish   # Register all eligible
        mf papers zenodo register my-paper --force  # Even if < 3 stars
    """
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.zenodo import (
        find_paper_pdf,
        is_eligible_for_zenodo,
        map_paper_to_zenodo_metadata,
    )

    if not slug and not register_all:
        console.print("[red]Specify a paper slug or use --all[/red]")
        raise SystemExit(1)

    dry_run = ctx.dry_run if ctx else False

    # Load database
    db = PaperDatabase()
    db.load()

    paths = get_paths()

    # Get papers to register
    papers_to_register = []

    if register_all:
        for paper_slug in db:
            entry = db.get(paper_slug)
            if entry and (is_eligible_for_zenodo(entry, min_stars) or force) and not entry.has_zenodo():
                    papers_to_register.append(entry)
    else:
        assert slug is not None  # guarded above
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            raise SystemExit(1)

        if entry.has_zenodo():
            console.print(f"[yellow]Paper already registered on Zenodo: {entry.zenodo_doi}[/yellow]")
            console.print(f"URL: {entry.zenodo_url}")
            return

        if not is_eligible_for_zenodo(entry, min_stars) and not force:
            console.print(f"[yellow]Paper has {entry.stars} stars (< {min_stars})[/yellow]")
            console.print("Use --force to register anyway.")
            raise SystemExit(1)

        papers_to_register.append(entry)

    if not papers_to_register:
        console.print("[yellow]No papers to register[/yellow]")
        return

    console.print(f"[cyan]Found {len(papers_to_register)} paper(s) to register[/cyan]")
    console.print()

    if not publish:
        console.print("[yellow]DRY RUN - Use --publish to actually create DOIs[/yellow]")
        console.print()

    # Get client only if publishing
    client = None
    sandbox = False
    if publish and not dry_run:
        client, sandbox = _get_zenodo_client()
        if sandbox:
            console.print("[yellow]Using Zenodo SANDBOX (testing mode)[/yellow]")
            console.print()

        # Test connection
        if not client.test_connection():
            console.print("[red]Failed to connect to Zenodo API[/red]")
            raise SystemExit(1)

    # Process each paper
    registered = []
    failed = []

    for entry in papers_to_register:
        paper_slug = entry.slug
        console.print(f"[bold]{paper_slug}[/bold]: {entry.title[:50]}...")

        # Find PDF
        pdf_path = find_paper_pdf(entry, paths.static)
        if not pdf_path:
            console.print("  [red]✗ No PDF found[/red]")
            failed.append((paper_slug, "No PDF found"))
            continue

        console.print(f"  [dim]PDF: {pdf_path.relative_to(paths.root)}[/dim]")

        # Generate metadata
        metadata = map_paper_to_zenodo_metadata(entry, paper_slug)

        console.print(f"  [dim]Upload type: {metadata['upload_type']}[/dim]")
        console.print(f"  [dim]Creators: {', '.join(c['name'] for c in metadata['creators'])}[/dim]")

        if not publish or dry_run:
            console.print("  [yellow]Would upload to Zenodo[/yellow]")
            continue

        # Actually register
        assert client is not None  # guarded by publish and not dry_run checks above
        try:
            # Create deposit
            deposit = client.create_deposit()
            console.print(f"  Created deposit: {deposit.id}")

            # Upload metadata
            deposit = client.update_metadata(deposit.id, metadata)
            console.print("  Uploaded metadata")

            # Upload PDF
            client.upload_file(deposit.id, pdf_path)
            console.print("  Uploaded PDF")

            # Publish
            published = client.publish(deposit.id)
            console.print("  [green]✓ Published![/green]")
            console.print(f"  Version DOI: [cyan]{published.doi}[/cyan]")
            if published.conceptdoi:
                console.print(f"  Concept DOI: [cyan]{published.conceptdoi}[/cyan] (always points to latest)")
            console.print(f"  URL: {published.doi_url}")

            # Update database
            entry.set_zenodo_registration(
                deposit_id=published.id,
                doi=published.doi or f"10.5281/zenodo.{published.id}",
                url=published.doi_url or f"https://zenodo.org/record/{published.id}",
                concept_doi=published.conceptdoi,
                version=1,
            )
            registered.append((paper_slug, published.doi))

        except Exception as e:
            console.print(f"  [red]✗ Error: {e}[/red]")
            failed.append((paper_slug, str(e)))
            continue

    # Save database if we registered anything
    if registered and not dry_run:
        db.save()
        console.print()
        console.print(f"[green]Registered {len(registered)} paper(s)[/green]")
        for paper_slug, doi in registered:
            console.print(f"  {paper_slug}: {doi}")

    if failed:
        console.print()
        console.print(f"[red]Failed to register {len(failed)} paper(s)[/red]")
        for paper_slug, error in failed:
            console.print(f"  {paper_slug}: {error}")


@zenodo.command()
@click.argument("slug")
@click.option("--publish", is_flag=True, help="Actually publish the new version")
@click.pass_obj
def update(ctx, slug: str, publish: bool) -> None:
    """Create a new version of a paper already on Zenodo.

    \b
    Use this when you've updated a paper and want a new DOI for the new version.
    The concept DOI will continue to point to the latest version.

    \b
    Examples:
        mf papers zenodo update my-paper           # Dry run
        mf papers zenodo update my-paper --publish # Actually publish new version
    """
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.zenodo import find_paper_pdf, map_paper_to_zenodo_metadata

    dry_run = ctx.dry_run if ctx else False

    db = PaperDatabase()
    db.load()

    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Paper not found: {slug}[/red]")
        raise SystemExit(1)

    if not entry.has_zenodo():
        console.print("[red]Paper not registered on Zenodo. Use 'register' first.[/red]")
        raise SystemExit(1)

    console.print(f"[bold]{slug}[/bold]: {entry.title[:50]}...")
    console.print(f"  Current version: {entry.zenodo_version}")
    console.print(f"  Current DOI: {entry.zenodo_doi}")
    if entry.zenodo_concept_doi:
        console.print(f"  Concept DOI: {entry.zenodo_concept_doi}")

    paths = get_paths()

    # Find PDF
    pdf_path = find_paper_pdf(entry, paths.static)
    if not pdf_path:
        console.print("  [red]✗ No PDF found[/red]")
        raise SystemExit(1)

    console.print(f"  [dim]PDF: {pdf_path.relative_to(paths.root)}[/dim]")

    if not publish or dry_run:
        console.print()
        console.print("[yellow]DRY RUN - Would create new version on Zenodo[/yellow]")
        console.print(f"  New version: {entry.zenodo_version + 1}")
        return

    # Get client
    try:
        client, sandbox = _get_zenodo_client()
    except SystemExit:
        return

    if sandbox:
        console.print("[yellow]Using Zenodo SANDBOX[/yellow]")

    try:
        # Create new version
        console.print()
        console.print("[cyan]Creating new version...[/cyan]")
        if entry.zenodo_deposit_id is None:
            console.print("[red]No Zenodo deposit ID found[/red]")
            raise SystemExit(1)
        new_draft = client.new_version(entry.zenodo_deposit_id)
        console.print(f"  Created draft: {new_draft.id}")

        # Update metadata
        metadata = map_paper_to_zenodo_metadata(entry, slug)
        metadata["version"] = str(entry.zenodo_version + 1)
        new_draft = client.update_metadata(new_draft.id, metadata)
        console.print("  Updated metadata")

        # Delete old files and upload new PDF
        existing_files = client.list_files(new_draft.id)
        for f in existing_files:
            file_id = f.get("id") or f.get("key")
            if file_id:
                with contextlib.suppress(Exception):
                    client.delete_file(new_draft.id, str(file_id))

        client.upload_file(new_draft.id, pdf_path)
        console.print("  Uploaded new PDF")

        # Publish
        published = client.publish(new_draft.id)
        console.print()
        console.print("[green]✓ New version published![/green]")
        console.print(f"  Version: {entry.zenodo_version + 1}")
        console.print(f"  Version DOI: [cyan]{published.doi}[/cyan]")
        console.print(f"  Concept DOI: [cyan]{published.conceptdoi}[/cyan] (still points to latest)")
        console.print(f"  URL: {published.doi_url}")

        # Update database
        entry.set_zenodo_registration(
            deposit_id=published.id,
            doi=published.doi or f"10.5281/zenodo.{published.id}",
            url=published.doi_url or f"https://zenodo.org/record/{published.id}",
            concept_doi=published.conceptdoi,
            version=entry.zenodo_version + 1,
        )
        db.save()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise SystemExit(1) from e


@zenodo.command(name="import")
@click.argument("slug", required=False)
@click.option("--all", "import_all", is_flag=True, help="Search all unregistered papers")
@click.option(
    "--min-score",
    default=0.8,
    type=float,
    help="Minimum match confidence (0.0-1.0, default: 0.8)",
)
@click.option("-i", "--interactive", is_flag=True, help="Confirm each match interactively")
@click.option("--json", "as_json", is_flag=True, help="Output matches as JSON without importing")
@click.pass_obj
def zenodo_import(
    ctx,
    slug: str | None,
    import_all: bool,
    min_score: float,
    interactive: bool,
    as_json: bool,
) -> None:
    """Import existing Zenodo records for papers.

    Searches the Zenodo public records API for records matching papers in
    paper_db.json and populates their zenodo_* fields.

    \b
    Examples:
        mf papers zenodo import expo-masked-fim             # Import one paper
        mf papers zenodo import --all                       # Search all unregistered
        mf papers zenodo import --all --json                # Show matches as JSON
        mf papers zenodo import --all -i                    # Confirm each match
        mf --dry-run papers zenodo import expo-masked-fim   # Dry run
    """
    import time

    from rich.progress import Progress

    from mf.core.database import PaperDatabase
    from mf.papers.zenodo import ZenodoRecord, compute_match_score

    if not slug and not import_all:
        console.print("[red]Specify a paper slug or use --all[/red]")
        raise SystemExit(1)

    dry_run = ctx.dry_run if ctx else False

    db = PaperDatabase()
    db.load()

    # Identify target papers (those without zenodo_doi)
    targets = []
    if import_all:
        for paper_slug in db:
            entry = db.get(paper_slug)
            if entry and not entry.has_zenodo():
                targets.append(entry)
    else:
        assert slug is not None  # guarded above
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            raise SystemExit(1)
        if entry.has_zenodo():
            console.print(f"[yellow]Paper already registered: {entry.zenodo_doi}[/yellow]")
            console.print(f"  URL: {entry.zenodo_url}")
            return
        targets.append(entry)

    if not targets:
        console.print("[yellow]No unregistered papers to search[/yellow]")
        return

    # Get Zenodo client
    try:
        client, sandbox = _get_zenodo_client()
    except SystemExit:
        return

    if sandbox:
        console.print("[yellow]Using Zenodo SANDBOX[/yellow]")

    console.print(f"[cyan]Searching Zenodo for {len(targets)} paper(s)...[/cyan]")
    console.print()

    # Collect results for JSON output or summary
    all_matches = []
    imported = []
    no_match = []

    use_progress = len(targets) > 1 and not as_json
    progress_ctx = Progress(disable=not use_progress)

    with progress_ctx as progress:
        task = progress.add_task("Searching...", total=len(targets)) if use_progress else None

        for idx, entry in enumerate(targets):
            paper_slug = entry.slug

            if not as_json:
                console.print(f"[bold]{paper_slug}[/bold]: {entry.title[:60]}")

            # Build search queries
            candidates = []

            # Query 1: DOI search (if paper has one)
            if entry.doi:
                try:
                    hits = client.search_records(f'doi:"{entry.doi}"', size=5)
                    for hit in hits:
                        rec = ZenodoRecord.from_search_hit(hit)
                        score = compute_match_score(
                            entry.title, entry.authors, rec.title, rec.creators,
                        )
                        candidates.append((rec, score))
                except Exception:
                    pass  # Fall through to title search

            # Query 2: Title + author search
            if not candidates:
                title = entry.title[:100]
                author_last = ""
                if entry.authors:
                    first_author = entry.authors[0]
                    if isinstance(first_author, dict):
                        name = first_author.get("name", "")
                    else:
                        name = str(first_author)
                    parts = name.strip().split()
                    author_last = parts[-1] if parts else ""

                query = f'title:"{title}"'
                if author_last:
                    query += f" AND creators.name:{author_last}"

                try:
                    hits = client.search_records(query, size=10)
                    for hit in hits:
                        rec = ZenodoRecord.from_search_hit(hit)
                        score = compute_match_score(
                            entry.title, entry.authors, rec.title, rec.creators,
                        )
                        candidates.append((rec, score))
                except Exception as e:
                    if not as_json:
                        console.print(f"  [red]Search error: {e}[/red]")

            # Deduplicate by record ID, keeping highest score
            seen_ids: dict[int, tuple[ZenodoRecord, float]] = {}
            for rec, score in candidates:
                if rec.id not in seen_ids or score > seen_ids[rec.id][1]:
                    seen_ids[rec.id] = (rec, score)
            candidates = sorted(seen_ids.values(), key=lambda x: -x[1])

            # Filter by min_score
            good_matches = [(rec, score) for rec, score in candidates if score >= min_score]

            # Collect for JSON output
            if as_json:
                match_data = {
                    "slug": paper_slug,
                    "title": entry.title,
                    "candidates": [
                        {
                            "record_id": rec.id,
                            "doi": rec.doi,
                            "doi_url": rec.doi_url,
                            "title": rec.title,
                            "creators": rec.creators,
                            "record_url": rec.record_url,
                            "score": round(score, 3),
                        }
                        for rec, score in candidates[:5]
                    ],
                }
                all_matches.append(match_data)
                if task is not None:
                    progress.advance(task)
                if idx < len(targets) - 1:
                    time.sleep(1)
                continue

            # Handle results
            if not good_matches:
                console.print("  [dim]No match found[/dim]")
                no_match.append(paper_slug)
            elif len(good_matches) == 1 or not interactive:
                # Auto-import best match
                best_rec, best_score = good_matches[0]
                console.print(f"  [green]Match[/green] (score={best_score:.2f}): {best_rec.title[:50]}")
                console.print(f"  DOI: {best_rec.doi}")
                console.print(f"  URL: {best_rec.record_url}")

                accept = True
                if interactive:
                    accept = click.confirm("  Import this record?", default=True)

                if accept:
                    entry.set_zenodo_registration(
                        deposit_id=best_rec.id,
                        doi=best_rec.doi or "",
                        url=best_rec.record_url or f"https://zenodo.org/record/{best_rec.id}",
                        concept_doi=best_rec.conceptdoi,
                    )
                    imported.append((paper_slug, best_rec.doi))
                    console.print("  [green]Imported[/green]")
                else:
                    console.print("  [yellow]Skipped[/yellow]")
            else:
                # Multiple matches + interactive
                console.print(f"  Found {len(good_matches)} candidates:")
                for i, (rec, score) in enumerate(good_matches[:5], 1):
                    console.print(f"    [{i}] (score={score:.2f}) {rec.title[:50]}")
                    console.print(f"        DOI: {rec.doi}")

                choice = click.prompt(
                    "  Select record (number or 'skip')",
                    default="1",
                    show_default=True,
                )
                if choice.lower() == "skip":
                    console.print("  [yellow]Skipped[/yellow]")
                else:
                    try:
                        idx_choice = int(choice) - 1
                        if 0 <= idx_choice < len(good_matches):
                            chosen_rec, chosen_score = good_matches[idx_choice]
                            entry.set_zenodo_registration(
                                deposit_id=chosen_rec.id,
                                doi=chosen_rec.doi or "",
                                url=chosen_rec.record_url or f"https://zenodo.org/record/{chosen_rec.id}",
                                concept_doi=chosen_rec.conceptdoi,
                            )
                            imported.append((paper_slug, chosen_rec.doi))
                            console.print("  [green]Imported[/green]")
                        else:
                            console.print("  [yellow]Invalid choice, skipped[/yellow]")
                    except ValueError:
                        console.print("  [yellow]Invalid input, skipped[/yellow]")

            if task is not None:
                progress.advance(task)

            # Rate limiting: Zenodo allows 30 req/min; each paper may use
            # up to 2 requests (DOI + title search), so 2.5s keeps us safe.
            if idx < len(targets) - 1:
                time.sleep(2.5)

    # JSON output
    if as_json:
        console.print(json_module.dumps(all_matches, indent=2))
        return

    # Save database
    if imported and not dry_run:
        db.save()
        console.print()
        console.print(f"[green]Imported {len(imported)} record(s)[/green]")
        for paper_slug, doi in imported:
            console.print(f"  {paper_slug}: {doi}")
    elif imported and dry_run:
        console.print()
        console.print(f"[yellow]Dry run — would import {len(imported)} record(s)[/yellow]")
        for paper_slug, doi in imported:
            console.print(f"  {paper_slug}: {doi}")

    if no_match:
        console.print()
        console.print(f"[dim]No match for {len(no_match)} paper(s): {', '.join(no_match)}[/dim]")


@zenodo.command()
@click.pass_obj
def test(ctx) -> None:
    """Test Zenodo API connection.

    Verifies that the API token is valid and can access Zenodo.
    """
    console.print("[cyan]Testing Zenodo API connection...[/cyan]")
    console.print()

    try:
        client, sandbox = _get_zenodo_client()
    except SystemExit:
        return

    if sandbox:
        console.print("[yellow]Using Zenodo SANDBOX (sandbox.zenodo.org)[/yellow]")
    else:
        console.print("[green]Using Zenodo PRODUCTION (zenodo.org)[/green]")
    console.print()

    if client.test_connection():
        console.print("[green]✓ Connection successful![/green]")

        # List recent deposits
        deposits = client.list_deposits(size=5)
        if deposits:
            console.print()
            console.print(f"[dim]Recent deposits ({len(deposits)}):[/dim]")
            for d in deposits[:5]:
                status = "published" if d.submitted else "draft"
                title = d.metadata.get("title", "Untitled")[:40]
                console.print(f"  [{status}] {d.id}: {title}")
    else:
        console.print("[red]✗ Connection failed - check your API token[/red]")


# -----------------------------------------------------------------------------
# CITATION.cff subcommand group
# -----------------------------------------------------------------------------


def _parse_github_url(github_url: str) -> tuple[str, str] | None:
    """Parse owner and repo from a GitHub URL.

    Args:
        github_url: URL like "https://github.com/owner/repo"

    Returns:
        Tuple of (owner, repo) or None if invalid
    """
    import re

    patterns = [
        r"github\.com[/:]([^/]+)/([^/.]+)",  # https://github.com/owner/repo or git@github.com:owner/repo
    ]

    for pattern in patterns:
        match = re.search(pattern, github_url)
        if match:
            return match.group(1), match.group(2)
    return None


def _fetch_citation_cff(github_url: str) -> str | None:
    """Fetch CITATION.cff content from a GitHub repo.

    Args:
        github_url: GitHub repository URL

    Returns:
        CITATION.cff content as string, or None if not found/error
    """
    import urllib.error
    import urllib.request

    parsed = _parse_github_url(github_url)
    if not parsed:
        return None

    owner, repo = parsed

    # Try main branch first, then master
    branches = ["main", "master"]
    for branch in branches:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/CITATION.cff"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                content: str = response.read().decode("utf-8")
                return content
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # Try next branch
            return None
        except Exception:
            return None

    return None


@papers.command("cff-status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cff_status(as_json: bool) -> None:
    """Show which papers have CITATION.cff in their GitHub repos.

    Checks each paper with a github_url to see if it has a CITATION.cff file.
    """
    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    results = []

    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue

        github_url = entry.data.get("github_url")
        if not github_url:
            continue

        # Check if CFF exists
        cff_content = _fetch_citation_cff(github_url)
        has_cff = cff_content is not None

        results.append({
            "slug": slug,
            "github_url": github_url,
            "has_cff": has_cff,
        })

    if as_json:
        console.print(json_module.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No papers with github_url found[/yellow]")
        return

    # Summary
    total = len(results)
    with_cff = sum(1 for r in results if r["has_cff"])

    table = Table(title=f"CITATION.cff Status ({with_cff}/{total} have CFF)")
    table.add_column("Slug", style="cyan")
    table.add_column("Has CFF", justify="center")
    table.add_column("GitHub URL", style="dim")

    for r in results:
        status = "[green]✓[/green]" if r["has_cff"] else "[dim]-[/dim]"
        # Truncate URL for display
        url = r["github_url"]
        if len(url) > 45:
            url = url[:42] + "..."
        table.add_row(r["slug"], status, url)

    console.print(table)


@papers.command("fetch-cff")
@click.option("--slug", help="Fetch for specific paper")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch for all papers with github_url")
@click.option("--force", is_flag=True, help="Overwrite existing fields (default: only fill empty)")
@click.pass_obj
def fetch_cff(ctx, slug: str | None, fetch_all: bool, force: bool) -> None:
    """Fetch CITATION.cff from GitHub repos and merge into paper_db.

    By default, only fills empty fields in paper_db (manual entries preserved).
    Use --force to overwrite all fields from CFF.

    \b
    Examples:
        mf papers fetch-cff --slug my-paper       # Fetch for one paper
        mf papers fetch-cff --all                 # Fetch for all papers
        mf papers fetch-cff --slug my-paper --force  # Overwrite existing
    """
    from mf.core.database import PaperDatabase
    from mf.papers.citation import cff_to_paper_fields, parse_cff

    if not slug and not fetch_all:
        console.print("[red]Specify --slug or use --all[/red]")
        raise SystemExit(1)

    dry_run = ctx.dry_run if ctx else False

    db = PaperDatabase()
    db.load()

    # Collect papers to process
    papers_to_process = []

    if fetch_all:
        for paper_slug in db:
            entry = db.get(paper_slug)
            if entry and entry.data.get("github_url"):
                papers_to_process.append(entry)
    else:
        assert slug is not None  # guarded above
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            raise SystemExit(1)
        if not entry.data.get("github_url"):
            console.print(f"[red]Paper has no github_url: {slug}[/red]")
            raise SystemExit(1)
        papers_to_process.append(entry)

    if not papers_to_process:
        console.print("[yellow]No papers with github_url to process[/yellow]")
        return

    console.print(f"[cyan]Processing {len(papers_to_process)} paper(s)...[/cyan]")
    console.print()

    updated = 0
    skipped = 0
    no_cff = 0

    for entry in papers_to_process:
        paper_slug = entry.slug
        github_url = str(entry.data.get("github_url", ""))

        console.print(f"[bold]{paper_slug}[/bold]")

        # Fetch CFF
        cff_content = _fetch_citation_cff(github_url)
        if not cff_content:
            console.print("  [dim]No CITATION.cff found[/dim]")
            no_cff += 1
            continue

        # Parse and convert
        cff = parse_cff(cff_content)
        cff_fields = cff_to_paper_fields(cff)

        if not cff_fields:
            console.print("  [dim]CITATION.cff has no usable fields[/dim]")
            skipped += 1
            continue

        # Determine what to merge
        fields_to_update = {}

        for field, value in cff_fields.items():
            existing = entry.data.get(field)
            if force or not existing:
                fields_to_update[field] = value
                action = "overwrite" if existing else "fill"
                console.print(f"  [green]•[/green] {field}: {action}")
            else:
                console.print(f"  [dim]• {field}: skip (has value)[/dim]")

        if not fields_to_update:
            console.print("  [dim]Nothing to update[/dim]")
            skipped += 1
            continue

        if dry_run:
            console.print("  [yellow]Would update (dry-run)[/yellow]")
        else:
            entry.update(**fields_to_update)
            console.print("  [green]Updated[/green]")

        updated += 1

    # Save if we updated anything
    if updated > 0 and not dry_run:
        db.save()

    # Summary
    console.print()
    console.print(f"[cyan]Summary:[/cyan] {updated} updated, {skipped} skipped, {no_cff} no CFF")
    if dry_run:
        console.print("[yellow]Dry-run mode - no changes saved[/yellow]")
