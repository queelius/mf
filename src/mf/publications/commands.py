"""CLI commands for publications management.

Publications = officially published works with venues (journals, conferences).
Use `mf papers` for all papers including preprints and drafts.
"""

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def is_publication(entry) -> bool:
    """Check if a paper entry qualifies as a publication.

    A publication is a paper that has been officially published:
    - Has status="published", OR
    - Has a venue (journal, conference, etc.), OR
    - Has a DOI (excluding arxiv DOIs)
    """
    if entry.data.get("status") == "published":
        return True
    if entry.data.get("venue"):
        return True
    # DOI indicates formal publication (but not arxiv preprint DOIs)
    doi = entry.data.get("doi", "")
    return bool(doi and "arxiv" not in doi.lower())


def is_preprint(entry) -> bool:
    """Check if a paper is a preprint (arXiv, etc.)."""
    return bool(entry.data.get("arxiv_id"))


@click.group(name="pubs")
def pubs() -> None:
    """Manage publications (officially published works).

    Publications are papers with venues (journals, conferences).
    Use `mf papers` for all papers including preprints and drafts.
    """
    pass


@pubs.command()
@click.pass_obj
def sync(ctx) -> None:
    """Sync publications to paper database.

    Reads frontmatter from content/publications/ and updates paper_db.json.
    """
    from mf.publications.sync import sync_publications

    dry_run = ctx.dry_run if ctx else False
    sync_publications(dry_run=dry_run)


@pubs.command()
@click.option("--slug", help="Generate only a specific publication (by paper slug)")
@click.option("--force", is_flag=True, help="Overwrite existing files completely")
@click.pass_obj
def generate(ctx, slug: str | None, force: bool) -> None:
    """Generate publication content from paper database.

    Creates/updates content/publications/ markdown files from paper_db.json
    entries that qualify as publications (have venue, status=published, or DOI).

    By default, updates existing files by merging pdf/html/cite fields without
    overwriting other manual edits. Use --force to completely regenerate.

    \b
    Examples:
        mf pubs generate                           # Update all publications
        mf pubs generate --slug cognitive-mri-ai-conversations
        mf pubs generate --force                   # Regenerate all from scratch
        mf pubs generate --dry-run                 # Preview changes
    """
    from mf.publications.generate import generate_publications

    dry_run = ctx.dry_run if ctx else False
    generate_publications(slug=slug, dry_run=dry_run, force=force)


@pubs.command(name="list")
@click.option("-q", "--query", help="Search in title/abstract")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("-c", "--category", help="Filter by category")
@click.option("--venue", help="Filter by venue")
@click.option("--all", "show_all", is_flag=True, help="Include non-published papers")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_pubs(
    query: str | None,
    tag: tuple[str, ...],
    category: str | None,
    venue: str | None,
    show_all: bool,
    as_json: bool,
) -> None:
    """List publications (officially published papers).

    By default only shows papers with a venue or status="published".
    Use --all to include preprints and drafts.

    \b
    Examples:
        mf pubs list                    # Published only
        mf pubs list --all              # All papers
        mf pubs list --venue "IEEE"
        mf pubs list --tag "encrypted search"
    """
    import json as json_module

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    # Get all papers and filter
    results = []
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue

        # By default, only show publications (has venue or status=published)
        if not show_all and not is_publication(entry):
            continue

        # Text search
        if query:
            query_lower = query.lower()
            title = entry.data.get("title", slug).lower()
            abstract = entry.data.get("abstract", "").lower()
            if query_lower not in title and query_lower not in abstract:
                continue

        # Tags filter
        if tag:
            entry_tags = entry.data.get("tags", [])
            if not any(t in entry_tags for t in tag):
                continue

        # Category filter
        if category and entry.data.get("category") != category:
            continue

        # Venue filter
        if venue:
            entry_venue = entry.data.get("venue", "").lower()
            if venue.lower() not in entry_venue:
                continue

        results.append(entry)

    if as_json:
        output = [
            {
                "slug": entry.slug,
                "title": entry.title,
                "date": entry.date,
                "category": entry.data.get("category"),
                "status": entry.data.get("status"),
                "venue": entry.data.get("venue"),
                "tags": entry.data.get("tags", []),
            }
            for entry in results
        ]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No publications found matching criteria[/yellow]")
        return

    table = Table(title=f"Publications ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Category", style="green")
    table.add_column("Status", style="blue")
    table.add_column("Venue", style="dim")

    for entry in sorted(results, key=lambda e: e.date or "", reverse=True):
        title = entry.title
        table.add_row(
            entry.slug,
            title[:45] + "..." if len(title) > 45 else title,
            entry.data.get("category", ""),
            entry.data.get("status", ""),
            (entry.data.get("venue", "")[:20] + "..."
             if len(entry.data.get("venue", "")) > 20
             else entry.data.get("venue", "")),
        )

    console.print(table)


@pubs.command()
@click.argument("slug")
def show(slug: str) -> None:
    """Show details for a specific publication.

    \b
    Examples:
        mf pubs show 2016-ieee-int-8-ccts
        mf pubs show reliability-estimation-in-series-systems
    """
    import json as json_module

    from rich.syntax import Syntax

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    entry = db.get(slug)

    if not entry:
        console.print(f"[red]Publication not found: {slug}[/red]")
        return

    # Display as formatted JSON
    json_str = json_module.dumps(entry.data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Publication: {slug}"))


@pubs.command()
def stats() -> None:
    """Show publication statistics.

    Only counts papers that qualify as publications (have venue or status=published).
    Use `mf papers stats` for all papers.
    """
    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    # Count publications vs all papers
    total_papers = 0
    publications = 0
    venue_counts: dict[str, int] = {}

    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue

        total_papers += 1

        if is_publication(entry):
            publications += 1
            venue = entry.data.get("venue")
            if venue:
                venue_counts[venue] = venue_counts.get(venue, 0) + 1

    unpublished = total_papers - publications

    content = f"""[cyan]Publications:[/cyan] {publications}
[cyan]Unpublished papers:[/cyan] {unpublished}
[cyan]Total in database:[/cyan] {total_papers}"""

    if venue_counts:
        content += "\n\n[bold]By venue:[/bold]"
        for venue, count in sorted(venue_counts.items(), key=lambda x: -x[1]):
            venue_display = venue[:50] + "..." if len(venue) > 50 else venue
            content += f"\n  {venue_display}: {count}"

    console.print(Panel(content, title="Publication Statistics"))


@pubs.command(name="categories")
@click.option("--all", "show_all", is_flag=True, help="Include unpublished papers")
def list_categories(show_all: bool) -> None:
    """List publication categories."""
    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    # Count by category (publications only by default)
    category_counts: dict[str, int] = {}
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue
        if not show_all and not is_publication(entry):
            continue
        cat = entry.data.get("category", "uncategorized")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if not category_counts:
        console.print("[yellow]No categories found[/yellow]")
        return

    title = "All Paper Categories" if show_all else "Publication Categories"
    console.print(f"[bold]{title}:[/bold]")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        console.print(f"  {cat}: {count}")


@pubs.command(name="tags")
@click.option("--all", "show_all", is_flag=True, help="Include unpublished papers")
def list_tags(show_all: bool) -> None:
    """List publication tags."""
    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    # Count tags (publications only by default)
    tag_counts: dict[str, int] = {}
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue
        if not show_all and not is_publication(entry):
            continue
        for tag in entry.data.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    if not tag_counts:
        console.print("[yellow]No tags found[/yellow]")
        return

    title = "All Paper Tags" if show_all else "Publication Tags"
    console.print(f"[bold]{title}:[/bold]")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:30]:
        console.print(f"  {tag}: {count}")

    if len(tag_counts) > 30:
        console.print(f"  [dim]... and {len(tag_counts) - 30} more[/dim]")


@pubs.command(name="preprints")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_preprints(as_json: bool) -> None:
    """List preprints (arXiv papers)."""
    import json as json_module

    from mf.core.database import PaperDatabase

    db = PaperDatabase()
    db.load()

    results = []
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue
        if is_preprint(entry):
            results.append(entry)

    if as_json:
        output = [
            {
                "slug": entry.slug,
                "title": entry.title,
                "arxiv_id": entry.data.get("arxiv_id"),
                "date": entry.date,
            }
            for entry in results
        ]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No preprints found[/yellow]")
        return

    table = Table(title=f"Preprints ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("arXiv ID", style="green")
    table.add_column("Date", style="dim")

    for entry in sorted(results, key=lambda e: e.date or "", reverse=True):
        table.add_row(
            entry.slug,
            entry.title[:45] + "..." if len(entry.title) > 45 else entry.title,
            entry.data.get("arxiv_id", ""),
            entry.date or "",
        )

    console.print(table)
