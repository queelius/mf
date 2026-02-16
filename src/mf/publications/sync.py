"""
Publications to papers synchronization.

Syncs metadata from content/publications/ to paper_db.json.
"""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console

from mf.core.config import get_paths
from mf.core.database import PaperDatabase

console = Console()


def extract_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content.

    Args:
        content: Markdown file content

    Returns:
        Frontmatter dict
    """
    # Match YAML frontmatter between --- markers
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    yaml_content = match.group(1)

    # Simple YAML parsing (for our use case)
    fm_data: dict[str, Any] = {}
    current_list: list[str] | None = None

    for line in yaml_content.split("\n"):
        line = line.rstrip()

        if not line or line.startswith("#"):
            continue

        # List item
        if line.startswith("  - "):
            if current_list is not None:
                value = line[4:].strip().strip('"').strip("'")
                current_list.append(value)
            continue

        # Key: value
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            current_list = None

            if value == "":
                # Might be a list or nested object
                fm_data[key] = []
                current_list = fm_data[key]
            elif value.startswith("[") and value.endswith("]"):
                # Inline list
                items = value[1:-1].split(",")
                fm_data[key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            else:
                # Simple value
                fm_data[key] = value

    return fm_data


def extract_paper_slug_from_pdf_path(pdf_path: str) -> str | None:
    """Extract paper slug from PDF path.

    Args:
        pdf_path: Path like "/latex/paper-name/file.pdf"

    Returns:
        Paper slug or None
    """
    if not pdf_path:
        return None

    # Handle various path formats
    if "/latex/" in pdf_path:
        parts = pdf_path.split("/latex/")
        if len(parts) > 1:
            slug_part = parts[1].split("/")[0]
            return slug_part

    return None


def map_publication_to_paper(pub_data: dict[str, Any]) -> dict[str, Any]:
    """Map publication frontmatter to paper database format.

    Args:
        pub_data: Publication frontmatter

    Returns:
        Paper database entry dict
    """
    paper = {}

    # Direct mappings
    if pub_data.get("title"):
        paper["title"] = pub_data["title"]

    if pub_data.get("abstract"):
        paper["abstract"] = pub_data["abstract"]

    if pub_data.get("date"):
        paper["date"] = str(pub_data["date"])[:10]  # Just date part

    if pub_data.get("tags"):
        paper["tags"] = pub_data["tags"]

    # Authors
    authors = pub_data.get("authors", [])
    if authors:
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                author_names.append(author.get("name", ""))
            elif isinstance(author, str):
                author_names.append(author)
        paper["authors"] = [a for a in author_names if a]

    # Links
    links = pub_data.get("links", [])
    for link in links:
        if isinstance(link, dict):
            name = link.get("name", "").lower()
            url = link.get("url", "")

            if "arxiv" in name:
                # Extract arxiv ID from URL
                if "arxiv.org" in url:
                    arxiv_id = url.split("/")[-1]
                    paper["arxiv_id"] = arxiv_id
            elif "github" in name:
                paper["github_url"] = url

    # DOI
    if pub_data.get("doi"):
        paper["doi"] = pub_data["doi"]

    # PDF path
    if pub_data.get("pdf"):
        paper["pdf_path"] = pub_data["pdf"]

    return paper


def sync_publications(dry_run: bool = False) -> None:
    """Sync publications to paper database.

    Reads frontmatter from content/publications/ and updates paper_db.json.

    Args:
        dry_run: Preview only
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        console.print("=" * 60)
        console.print()

    paths = get_paths()
    pub_dir = paths.publications

    if not pub_dir.exists():
        console.print(f"[red]Publications directory not found: {pub_dir}[/red]")
        return

    # Find publication files
    pub_files = list(pub_dir.rglob("index.md"))
    console.print(f"Found {len(pub_files)} publication(s)")

    if not pub_files:
        return

    # Load paper database
    db = PaperDatabase()
    db.load()

    synced = 0
    skipped = 0

    for pub_file in pub_files:
        pub_slug = pub_file.parent.name

        try:
            content = pub_file.read_text(encoding="utf-8")
            pub_data = extract_frontmatter(content)

            if not pub_data:
                console.print(f"  [dim]Skipping {pub_slug}: No frontmatter[/dim]")
                skipped += 1
                continue

            # Try to find corresponding paper slug
            pdf_path = pub_data.get("pdf", "")
            paper_slug = extract_paper_slug_from_pdf_path(pdf_path)

            if not paper_slug:
                # Use publication slug as paper slug
                paper_slug = pub_slug

            # Check if paper exists in static/latex
            if not (paths.latex / paper_slug).exists():
                console.print(f"  [dim]Skipping {pub_slug}: No paper directory[/dim]")
                skipped += 1
                continue

            # Map publication data to paper format
            paper_data = map_publication_to_paper(pub_data)

            if not paper_data:
                skipped += 1
                continue

            console.print(f"  [cyan]{pub_slug}[/cyan] → [green]{paper_slug}[/green]")

            # Update paper database (preserve existing manual fields)
            if not dry_run:
                existing = db.get(paper_slug)
                if existing:
                    # Merge: existing manual data takes precedence
                    for key, value in paper_data.items():
                        if key not in existing.data or not existing.data[key]:
                            existing.data[key] = value
                else:
                    db.set(paper_slug, paper_data)

            synced += 1

        except Exception as e:
            console.print(f"  [red]Error processing {pub_slug}: {e}[/red]")
            skipped += 1

    # Save database
    if not dry_run and synced > 0:
        db.save()

    console.print(f"\n[green]Synced:[/green] {synced}")
    if skipped:
        console.print(f"[dim]Skipped:[/dim] {skipped}")
