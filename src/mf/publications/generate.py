"""
Generate Hugo publication content from pubs_db.json.

Creates content/publications/{slug}/index.md with artifacts frontmatter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from mf.core.config import get_paths
from mf.publications.database import PubsDatabase, PubEntry

console = Console()


def pub_to_frontmatter(entry: PubEntry) -> dict[str, Any]:
    """Convert a PubEntry to Hugo frontmatter dict."""
    fm: dict[str, Any] = {"title": entry.title}

    if entry.abstract:
        fm["abstract"] = entry.abstract

    if entry.authors:
        fm["authors"] = entry.authors

    if entry.date:
        fm["date"] = f"{entry.date}T00:00:00Z"

    pub_meta: dict[str, Any] = {
        "type": entry.type,
        "status": entry.status,
    }
    if entry.venue:
        pub_meta["venue"] = entry.venue
    if entry.doi:
        pub_meta["doi"] = entry.doi
    if entry.arxiv_id:
        pub_meta["arxiv"] = entry.arxiv_id
    if entry.date:
        try:
            pub_meta["year"] = int(entry.date[:4])
        except (ValueError, IndexError):
            pass
    fm["publication"] = pub_meta

    if entry.tags:
        fm["tags"] = entry.tags

    artifacts = {k: v for k, v in entry.artifacts.items() if v}
    if artifacts:
        fm["artifacts"] = artifacts

    if entry.links:
        fm["links"] = entry.links

    return fm


def generate_publication_content(fm: dict[str, Any]) -> str:
    """Render frontmatter dict to Hugo markdown."""
    yaml_content = yaml.dump(
        fm, default_flow_style=False, allow_unicode=True,
        sort_keys=False, width=1000,
    )
    return f"---\n{yaml_content}---\n"


def generate_publications(
    slug: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate Hugo publication pages from pubs_db."""
    paths = get_paths()
    db = PubsDatabase()
    db.load()

    slugs = [slug] if slug else list(db)
    generated = 0

    for pub_slug in slugs:
        entry = db.get(pub_slug)
        if not entry:
            if slug:
                console.print(f"[red]Not found: {pub_slug}[/red]")
            continue

        out_dir = paths.publications / pub_slug
        out_file = out_dir / "index.md"

        fm = pub_to_frontmatter(entry)
        content = generate_publication_content(fm)

        if dry_run:
            action = "update" if out_file.exists() else "create"
            console.print(f"[yellow]DRY RUN: would {action} {out_file}[/yellow]")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file.write_text(content)
            action = "Updated" if out_file.exists() else "Created"
            console.print(f"[green]{action}: {out_file}[/green]")
        generated += 1

    console.print(f"\n[bold]Generated {generated} publication(s)[/bold]")
