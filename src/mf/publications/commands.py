"""CLI commands for publications management.

Uses PubsDatabase (pubs_db.json) for all operations. Decoupled from PaperDatabase.
"""

import json as json_module
from datetime import date

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from mf.core.config import get_paths
from mf.publications.database import VALID_STATUSES, VALID_TYPES, PubEntry, PubsDatabase

console = Console()


def _load_db() -> PubsDatabase:
    """Create, load, and return a PubsDatabase."""
    db = PubsDatabase()
    db.load()
    return db


@click.group(name="pubs")
def pubs() -> None:
    """Manage publications lifecycle (pubs_db.json).

    Full lifecycle tracking: draft → submitted → accepted → published.
    Use `mf pubs list`, `mf pubs add`, `mf pubs update`, `mf pubs log`.
    """


@pubs.command(name="list")
@click.option("--status", help="Filter by status")
@click.option("--type", "pub_type", help="Filter by type")
@click.option("--tag", multiple=True, help="Filter by tag(s) (can be repeated)")
@click.option("--venue", help="Filter by venue (substring match)")
@click.option("-q", help="Text search in title/abstract")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def list_pubs(
    ctx,
    status: str | None,
    pub_type: str | None,
    tag: tuple[str, ...],
    venue: str | None,
    q: str | None,
    as_json: bool,
) -> None:
    """List publications with optional filters.

    \b
    Examples:
        mf pubs list
        mf pubs list --status published
        mf pubs list --type "conference paper"
        mf pubs list --tag "encrypted search" --tag "privacy"
        mf pubs list --venue "IEEE"
        mf pubs list -q "series systems"
        mf pubs list --json
    """
    db = _load_db()

    results: list[PubEntry] = []
    for slug in db:
        entry = db.get(slug)
        if entry is None:
            continue

        if status and entry.status != status:
            continue
        if pub_type and entry.type != pub_type:
            continue
        if tag and not any(t in entry.tags for t in tag):
            continue
        if venue:
            entry_venue = (entry.venue or "").lower()
            if venue.lower() not in entry_venue:
                continue
        if q:
            q_lower = q.lower()
            title = entry.title.lower()
            abstract = (entry.abstract or "").lower()
            if q_lower not in title and q_lower not in abstract:
                continue

        results.append(entry)

    if as_json:
        output = [
            {
                "slug": e.slug,
                "title": e.title,
                "date": e.date,
                "status": e.status,
                "type": e.type,
                "venue": e.venue,
                "tags": e.tags,
            }
            for e in results
        ]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No publications found matching criteria[/yellow]")
        return

    table = Table(title=f"Publications ({len(results)} found)")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Type", style="green")
    table.add_column("Status", style="blue")
    table.add_column("Venue", style="dim")

    for e in sorted(results, key=lambda x: x.date or "", reverse=True):
        title = e.title
        venue_str = e.venue or ""
        table.add_row(
            e.slug,
            title[:45] + "..." if len(title) > 45 else title,
            e.type,
            e.status,
            venue_str[:20] + "..." if len(venue_str) > 20 else venue_str,
        )

    console.print(table)


@pubs.command()
@click.argument("slug")
@click.pass_obj
def show(ctx, slug: str) -> None:
    """Show full details for a publication.

    \b
    Examples:
        mf pubs show my-paper-slug
    """
    db = _load_db()
    entry = db.get(slug)
    if entry is None:
        console.print(f"[red]Publication not found: {slug}[/red]")
        raise SystemExit(1)

    data = {"slug": entry.slug, **entry.to_dict()}
    json_str = json_module.dumps(data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Publication: {slug}"))


@pubs.command()
@click.argument("slug")
@click.option("--title", required=True, help="Publication title")
@click.option("--type", "pub_type", required=True, help=f"Type: {', '.join(sorted(VALID_TYPES))}")
@click.option("--status", default="draft", show_default=True,
              help=f"Status: {', '.join(sorted(VALID_STATUSES))}")
@click.option("--venue", help="Venue name (journal, conference, etc.)")
@click.option("--doi", help="DOI")
@click.option("--arxiv", "arxiv_id", help="arXiv ID (e.g. 2301.12345)")
@click.option("--pdf", help="PDF artifact URL/path")
@click.option("--html", help="HTML artifact URL/path")
@click.option("--code", help="Code artifact URL/path")
@click.option("--source-repo", help="Source repository path")
@click.pass_obj
def add(
    ctx,
    slug: str,
    title: str,
    pub_type: str,
    status: str,
    venue: str | None,
    doi: str | None,
    arxiv_id: str | None,
    pdf: str | None,
    html: str | None,
    code: str | None,
    source_repo: str | None,
) -> None:
    """Add a new publication entry.

    \b
    Examples:
        mf pubs add my-new-paper --title "My Paper" --type "conference paper"
        mf pubs add preprint-2025 --title "A Preprint" --type preprint --arxiv 2501.00001
    """
    dry_run = ctx.dry_run if ctx else False

    if status not in VALID_STATUSES:
        console.print(f"[red]Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}[/red]")
        raise SystemExit(1)
    if pub_type not in VALID_TYPES:
        console.print(f"[red]Invalid type '{pub_type}'. Valid: {sorted(VALID_TYPES)}[/red]")
        raise SystemExit(1)

    db = _load_db()

    if slug in db:
        console.print(f"[red]Publication already exists: {slug}[/red]")
        raise SystemExit(1)

    artifacts: dict[str, str | None] = {}
    if pdf:
        artifacts["pdf"] = pdf
    if html:
        artifacts["html"] = html
    if code:
        artifacts["code"] = code

    entry = PubEntry(
        slug=slug,
        title=title,
        status=status,
        type=pub_type,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        artifacts=artifacts,
        source_repo=source_repo,
        timeline=[{"event": "created", "date": str(date.today())}],
    )

    if dry_run:
        console.print(f"[dim][dry-run] Would add: {slug}[/dim]")
        console.print(json_module.dumps({"slug": slug, **entry.to_dict()}, indent=2))
        return

    db.set(entry)
    db.save()
    console.print(f"[green]Added publication: {slug}[/green]")


@pubs.command()
@click.argument("slug")
@click.option("--title", help="Update title")
@click.option("--status", help=f"Update status: {', '.join(sorted(VALID_STATUSES))}")
@click.option("--type", "pub_type", help=f"Update type: {', '.join(sorted(VALID_TYPES))}")
@click.option("--venue", help="Update venue")
@click.option("--doi", help="Update DOI")
@click.option("--arxiv", "arxiv_id", help="Update arXiv ID")
@click.option("--pdf", help="Update PDF artifact")
@click.option("--html", help="Update HTML artifact")
@click.option("--slides", help="Update slides artifact")
@click.option("--poster", help="Update poster artifact")
@click.option("--video", help="Update video artifact")
@click.option("--photos", help="Update photos artifact")
@click.option("--code", help="Update code artifact")
@click.option("--bibtex", help="Update BibTeX artifact")
@click.pass_obj
def update(
    ctx,
    slug: str,
    title: str | None,
    status: str | None,
    pub_type: str | None,
    venue: str | None,
    doi: str | None,
    arxiv_id: str | None,
    pdf: str | None,
    html: str | None,
    slides: str | None,
    poster: str | None,
    video: str | None,
    photos: str | None,
    code: str | None,
    bibtex: str | None,
) -> None:
    """Update fields on an existing publication.

    \b
    Examples:
        mf pubs update my-paper --status accepted
        mf pubs update my-paper --pdf https://example.com/paper.pdf
        mf pubs update my-paper --doi 10.1234/example
    """
    dry_run = ctx.dry_run if ctx else False

    if status is not None and status not in VALID_STATUSES:
        console.print(f"[red]Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}[/red]")
        raise SystemExit(1)
    if pub_type is not None and pub_type not in VALID_TYPES:
        console.print(f"[red]Invalid type '{pub_type}'. Valid: {sorted(VALID_TYPES)}[/red]")
        raise SystemExit(1)

    db = _load_db()
    entry = db.get(slug)
    if entry is None:
        console.print(f"[red]Publication not found: {slug}[/red]")
        raise SystemExit(1)

    if title is not None:
        entry.title = title
    if status is not None:
        entry.status = status
    if pub_type is not None:
        entry.type = pub_type
    if venue is not None:
        entry.venue = venue
    if doi is not None:
        entry.doi = doi
    if arxiv_id is not None:
        entry.arxiv_id = arxiv_id

    # Artifact updates
    artifact_map = {
        "pdf": pdf,
        "html": html,
        "slides": slides,
        "poster": poster,
        "video": video,
        "photos": photos,
        "code": code,
        "bibtex": bibtex,
    }
    for key, val in artifact_map.items():
        if val is not None:
            entry.artifacts[key] = val

    if dry_run:
        console.print(f"[dim][dry-run] Would update: {slug}[/dim]")
        console.print(json_module.dumps({"slug": slug, **entry.to_dict()}, indent=2))
        return

    db.set(entry)
    db.save()
    console.print(f"[green]Updated publication: {slug}[/green]")


@pubs.command()
@click.argument("slug")
@click.option("--event", required=True, help="Event label (e.g. 'submitted', 'revision-requested')")
@click.option("--note", help="Optional note for this event")
@click.option("--date", "event_date", default=None,
              help="Event date (YYYY-MM-DD, defaults to today)")
@click.pass_obj
def log(ctx, slug: str, event: str, note: str | None, event_date: str | None) -> None:
    """Append a timeline event to a publication.

    \b
    Examples:
        mf pubs log my-paper --event submitted
        mf pubs log my-paper --event "revision-requested" --note "Reviewer 2 wants more experiments"
        mf pubs log my-paper --event accepted --date 2025-03-15
    """
    dry_run = ctx.dry_run if ctx else False

    db = _load_db()
    entry = db.get(slug)
    if entry is None:
        console.print(f"[red]Publication not found: {slug}[/red]")
        raise SystemExit(1)

    timeline_entry: dict = {
        "event": event,
        "date": event_date or str(date.today()),
    }
    if note:
        timeline_entry["note"] = note

    if dry_run:
        console.print(f"[dim][dry-run] Would append timeline event to {slug}: {timeline_entry}[/dim]")
        return

    entry.timeline.append(timeline_entry)
    db.set(entry)
    db.save()
    console.print(f"[green]Logged event '{event}' on {slug}[/green]")


@pubs.command()
@click.option("--slug", help="Generate only a specific publication (by slug)")
@click.option("--force", is_flag=True, help="Overwrite existing files completely")
@click.pass_obj
def generate(ctx, slug: str | None, force: bool) -> None:
    """Generate publication content from pubs_db.

    Creates/updates content/publications/ markdown files.

    \b
    Examples:
        mf pubs generate
        mf pubs generate --slug my-paper
        mf pubs generate --force
    """
    from mf.publications.generate import generate_publications

    dry_run = ctx.dry_run if ctx else False
    generate_publications(slug=slug, dry_run=dry_run, force=force)


@pubs.command()
@click.pass_obj
def migrate(ctx) -> None:
    """Migrate legacy paper_db.json entries into pubs_db.json.

    Reads from PaperDatabase and populates PubsDatabase.
    Will not overwrite entries that already exist in pubs_db.json.
    """
    db = _load_db()
    if len(db) > 0:
        console.print(
            f"[yellow]pubs_db already contains {len(db)} entries. "
            "Run `mf pubs migrate` only on an empty database.[/yellow]"
        )
        console.print("To proceed, back up and delete pubs_db.json first.")
        raise SystemExit(1)

    try:
        from mf.publications.migrate import migrate_paper_db
    except ImportError:
        console.print("[red]migrate module not available (mf.publications.migrate not found)[/red]")
        raise SystemExit(1)

    paths = get_paths()
    migrate_paper_db(paper_db_path=paths.paper_db, pubs_db_path=paths.pubs_db)


@pubs.command()
@click.option("--slug", help="Pull artifacts for a specific publication only")
@click.option("--type", "artifact_type", help="Pull only this artifact type (e.g. pdf, html, slides)")
@click.pass_obj
def pull(ctx, slug: str | None, artifact_type: str | None) -> None:
    """Pull artifacts from source repos into static/.

    Copies files (PDFs, etc.) from source_repo locations to their
    target paths in static/. Requires artifacts_source mapping in
    pubs_db to know where source files live.

    \b
    Examples:
        mf pubs pull                    # Pull all artifacts
        mf pubs pull --type pdf         # Pull only PDFs
        mf pubs pull --slug my-paper    # Pull artifacts for one pub
    """
    from mf.publications.pull import pull_artifacts

    dry_run = ctx.dry_run if ctx else False
    pull_artifacts(slug=slug, artifact_type=artifact_type, dry_run=dry_run)


@pubs.command()
@click.option("--slug", help="Check a specific publication only")
@click.option("--type", "artifact_type", help="Check only this artifact type")
@click.pass_obj
def check(ctx, slug: str | None, artifact_type: str | None) -> None:
    """Check which artifacts are present or missing.

    Shows a table of all artifacts with their status in static/ and
    whether the source file exists.

    \b
    Examples:
        mf pubs check
        mf pubs check --type pdf
        mf pubs check --slug my-paper
    """
    from mf.publications.pull import check_artifacts

    check_artifacts(slug=slug, artifact_type=artifact_type)


@pubs.command()
@click.pass_obj
def stats(ctx) -> None:
    """Show publication statistics by status, type, and venue.

    \b
    Examples:
        mf pubs stats
    """
    db = _load_db()

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    venue_counts: dict[str, int] = {}

    for slug in db:
        entry = db.get(slug)
        if entry is None:
            continue
        status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
        type_counts[entry.type] = type_counts.get(entry.type, 0) + 1
        if entry.venue:
            venue_counts[entry.venue] = venue_counts.get(entry.venue, 0) + 1

    total = len(db)
    lines = [f"[cyan]Total publications:[/cyan] {total}"]

    if status_counts:
        lines.append("\n[bold]By status:[/bold]")
        for s, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {s}: {count}")

    if type_counts:
        lines.append("\n[bold]By type:[/bold]")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {count}")

    if venue_counts:
        lines.append("\n[bold]By venue:[/bold]")
        for v, count in sorted(venue_counts.items(), key=lambda x: -x[1]):
            v_display = v[:50] + "..." if len(v) > 50 else v
            lines.append(f"  {v_display}: {count}")

    console.print(Panel("\n".join(lines), title="Publication Statistics"))
