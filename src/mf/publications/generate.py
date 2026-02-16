"""
Generate publication content from paper database.

Creates/updates content/publications/ markdown files from paper_db.json
entries that qualify as publications (have venue, status=published, or DOI).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from mf.core.config import get_paths
from mf.core.database import PaperDatabase, PaperEntry

console = Console()


def is_publication(entry: PaperEntry) -> bool:
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


def map_paper_to_publication(entry: PaperEntry) -> dict[str, Any]:
    """Map paper database entry to publication front matter format.

    Args:
        entry: Paper database entry

    Returns:
        Publication front matter dict
    """
    data = entry.data
    fm: dict[str, Any] = {}

    # Required fields
    fm["title"] = data.get("title", entry.slug)

    # Subtitle
    if data.get("subtitle"):
        fm["SubTitle"] = data["subtitle"]

    # Abstract
    if data.get("abstract"):
        fm["abstract"] = data["abstract"]

    # Authors - convert to publication format
    authors = data.get("authors", [])
    if authors:
        fm_authors = []
        for author in authors:
            if isinstance(author, dict):
                fm_authors.append(author)
            elif isinstance(author, str):
                fm_authors.append({"name": author})
        fm["authors"] = fm_authors

    # Date
    if data.get("date"):
        fm["date"] = f"{data['date']}T00:00:00Z"

    # Publisher
    if data.get("publisher"):
        fm["publisher"] = data["publisher"]

    # Publication metadata
    pub_meta: dict[str, Any] = {}
    if data.get("category"):
        pub_meta["type"] = data["category"]
    if data.get("venue"):
        pub_meta["venue"] = data["venue"]
    if data.get("status"):
        pub_meta["status"] = data["status"]
    if data.get("doi"):
        pub_meta["doi"] = data["doi"]
    if data.get("arxiv_id"):
        pub_meta["arxiv"] = data["arxiv_id"]
    if data.get("year"):
        pub_meta["year"] = data["year"]
    if pub_meta:
        fm["publication"] = pub_meta

    # Links
    links = []
    if data.get("github_url"):
        links.append({"name": "GitHub", "url": data["github_url"]})
    if data.get("external_url"):
        links.append({"name": "External", "url": data["external_url"]})
    # Add paper page link
    links.append({"name": "Paper", "url": f"/papers/{entry.slug}/"})
    # Add any existing links from paper_db
    for link in data.get("links", []):
        if isinstance(link, dict) and link not in links:
            links.append(link)
    if links:
        fm["links"] = links

    # Tags
    if data.get("tags"):
        fm["tags"] = data["tags"]

    # Static asset paths - these are the key fields for /publications display
    if data.get("pdf_path"):
        fm["pdf"] = data["pdf_path"]
    if data.get("html_path"):
        # Use directory path for cleaner URLs (index.html implied)
        html_path = data["html_path"]
        if html_path.endswith("/index.html"):
            html_path = html_path[:-10]  # Remove /index.html
        elif html_path.endswith("index.html"):
            html_path = html_path[:-10]
        fm["html"] = html_path
    if data.get("cite_path"):
        fm["cite"] = data["cite_path"]

    return fm


def generate_publication_content(fm: dict[str, Any]) -> str:
    """Generate markdown content for a publication.

    Args:
        fm: Front matter dict

    Returns:
        Complete markdown file content
    """
    # Use yaml.dump for proper formatting
    yaml_content = yaml.dump(
        fm,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,  # Prevent line wrapping in abstracts
    )

    return f"---\n{yaml_content}---\n"


def get_publication_slug(entry: PaperEntry) -> str:
    """Determine the publication slug for a paper.

    Some papers may have different slugs in /publications vs /papers.
    This function handles known mappings.

    Args:
        entry: Paper database entry

    Returns:
        Publication slug
    """
    # Known slug mappings (paper_db slug -> publication slug)
    slug_mappings = {
        "reliability-estimation-in-series-systems": "math-proj",
        "2016-ieee-int-8-ccts": "mab",
        "2015-cs-thesis": "cs-thesis",
        "cognitive-mri-ai-conversations": "cognitive-mri",
        "ransomware-icci2025": "ransomware",
    }

    return slug_mappings.get(entry.slug, entry.slug)


def generate_publications(
    slug: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate publication content files from paper database.

    Args:
        slug: Generate only a specific publication (by paper slug)
        dry_run: Preview without writing
        force: Overwrite existing files
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        console.print("=" * 60)
        console.print()

    paths = get_paths()
    pub_dir = paths.publications

    # Ensure directory exists
    if not dry_run:
        pub_dir.mkdir(parents=True, exist_ok=True)

    # Load paper database
    db = PaperDatabase()
    db.load()

    generated = 0
    skipped = 0
    updated = 0

    # Process papers
    slugs_to_process = [slug] if slug else list(db)

    for paper_slug in slugs_to_process:
        entry = db.get(paper_slug)
        if not entry:
            if slug:
                console.print(f"[red]Paper not found: {paper_slug}[/red]")
            continue

        # Check if it qualifies as a publication
        if not is_publication(entry):
            if slug:
                console.print(
                    f"[yellow]{paper_slug} doesn't qualify as a publication "
                    "(no venue/status/DOI)[/yellow]"
                )
            skipped += 1
            continue

        # Determine publication slug
        pub_slug = get_publication_slug(entry)
        pub_path = pub_dir / pub_slug / "index.md"

        # Check if file exists
        exists = pub_path.exists()
        if exists and not force:
            # Update existing file - merge fields
            console.print(f"  [cyan]{paper_slug}[/cyan] → updating [green]{pub_slug}[/green]")
            if not dry_run:
                _update_publication_file(pub_path, entry)
            updated += 1
        else:
            # Create new file
            action = "overwriting" if exists else "creating"
            console.print(f"  [cyan]{paper_slug}[/cyan] → {action} [green]{pub_slug}[/green]")

            if not dry_run:
                pub_path.parent.mkdir(parents=True, exist_ok=True)
                fm = map_paper_to_publication(entry)
                content = generate_publication_content(fm)
                pub_path.write_text(content, encoding="utf-8")

            generated += 1

    # Summary
    console.print()
    if generated:
        console.print(f"[green]Generated:[/green] {generated}")
    if updated:
        console.print(f"[blue]Updated:[/blue] {updated}")
    if skipped and not slug:
        console.print(f"[dim]Skipped (not publications):[/dim] {skipped}")


def _update_publication_file(pub_path: Path, entry: PaperEntry) -> None:
    """Update an existing publication file with new data from paper_db.

    Only updates specific fields (pdf, html, cite, links) without
    overwriting manual edits to other fields.

    Args:
        pub_path: Path to publication index.md
        entry: Paper database entry
    """
    import re

    content = pub_path.read_text(encoding="utf-8")

    # Parse existing frontmatter
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not match:
        return

    try:
        existing_fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return

    body = match.group(2)
    data = entry.data

    # Update specific fields from paper_db
    if data.get("pdf_path"):
        existing_fm["pdf"] = data["pdf_path"]

    if data.get("html_path"):
        html_path = data["html_path"]
        if html_path.endswith("/index.html") or html_path.endswith("index.html"):
            html_path = html_path[:-10]
        existing_fm["html"] = html_path

    if data.get("cite_path"):
        existing_fm["cite"] = data["cite_path"]

    # Update publication metadata
    if "publication" not in existing_fm:
        existing_fm["publication"] = {}

    if data.get("doi"):
        existing_fm["publication"]["doi"] = data["doi"]
    if data.get("arxiv_id"):
        existing_fm["publication"]["arxiv"] = data["arxiv_id"]
    if data.get("status"):
        existing_fm["publication"]["status"] = data["status"]
    if data.get("venue"):
        existing_fm["publication"]["venue"] = data["venue"]
    if data.get("category"):
        existing_fm["publication"]["type"] = data["category"]
    if data.get("year"):
        existing_fm["publication"]["year"] = data["year"]

    # Regenerate file
    yaml_content = yaml.dump(
        existing_fm,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )

    new_content = f"---\n{yaml_content}---\n{body}"
    pub_path.write_text(new_content, encoding="utf-8")
