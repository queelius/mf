"""
Migrate paper_db.json to pubs_db.json.

Reads the legacy paper_db.json format and creates a curated pubs_db.json
using PubEntry / PubsDatabase. Applies inclusion criteria, field mapping,
slug normalisation, and seeds timeline events.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from mf.publications.database import PubEntry, PubsDatabase

console = Console()

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Keys that are metadata, not paper entries.
_SKIP_KEYS: frozenset[str] = frozenset({"_comment", "_example", "_schema_version"})

# Categories that are creative/non-academic works — skip them before any
# inclusion check so that novels with pdf_path don't slip through.
_SKIP_CATEGORIES: frozenset[str] = frozenset({
    "novel", "essay", "novella", "short story",
})

# paper_db slug -> desired pubs_db slug
SLUG_MAPPINGS: dict[str, str] = {
    "reliability-estimation-in-series-systems": "math-proj",
    "2016-ieee-int-8-ccts": "mab",
    "2015-cs-thesis": "cs-thesis",
    "cognitive-mri-ai-conversations": "cognitive-mri",
    "ransomware-icci2025": "ransomware",
}

# paper_db category -> PubEntry type
_CATEGORY_MAP: dict[str, str] = {
    "research paper": "conference paper",
    "conference": "conference paper",
    "conference paper": "conference paper",
    "master's thesis": "thesis",
    "technical paper": "technical report",
    "technical report": "technical report",
    "white paper": "white paper",
    "journal article": "journal article",
    "workshop paper": "workshop paper",
    "book chapter": "book chapter",
}

_ARXIV_PREFIX = "arxiv."


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalise_authors(raw: Any) -> list[dict]:
    """Return a list of author dicts, wrapping bare strings."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [{"name": raw}]
    result: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            result.append(item)
    return result


def _map_type(category: str) -> str:
    """Map a paper_db category string to a valid PubEntry type."""
    return _CATEGORY_MAP.get(category.lower(), "preprint")


def _is_non_arxiv_doi(doi: str | None) -> bool:
    """Return True when DOI exists and is not an arXiv DOI."""
    if not doi:
        return False
    return _ARXIV_PREFIX not in doi.lower()


def _extract_slides(links: list[dict]) -> str | None:
    """Return the URL of the first link whose name looks like slides/talk."""
    keywords = {"slides", "presentation", "talk"}
    for link in links:
        name = link.get("name", "").lower()
        if any(kw in name for kw in keywords):
            return link.get("url")
    return None


def _strip_github_prefix(source_path: str | None) -> str | None:
    """Strip the ~/github/ absolute prefix, return repo-level path segment."""
    if not source_path:
        return None
    # Normalise both absolute /home/*/github/ and ~/github/ variants.
    for prefix in (
        "/home/spinoza/github/",
        "~/github/",
    ):
        if source_path.startswith(prefix):
            rest = source_path[len(prefix):]
            # Keep only the repo-level path (first two path components: owner/repo).
            parts = rest.split("/")
            # For paths like "beta/dreamlog/paper/…" keep "beta/dreamlog".
            # For paths like "papers/aperture/paper/…" keep "papers/aperture".
            if len(parts) >= 2:
                return "/".join(parts[:2])
            return parts[0]
    return source_path


def _determine_status_and_include(entry: dict) -> tuple[str, bool]:
    """
    Apply inclusion rules (in order) and return (status, include).

    Rule 1: status=published OR has venue OR has non-arxiv DOI → published
    Rule 2: has arxiv_id → preprint
    Rule 3: has pdf_path or html_path → draft
    Otherwise: skip.
    """
    status = entry.get("status", "")
    venue = entry.get("venue")
    doi = entry.get("doi")
    arxiv_id = entry.get("arxiv_id")
    pdf_path = entry.get("pdf_path")
    html_path = entry.get("html_path")

    if status == "published" or venue or _is_non_arxiv_doi(doi):
        return "published", True
    if arxiv_id:
        return "preprint", True
    if pdf_path or html_path:
        return "draft", True
    return "skip", False


# ──────────────────────────────────────────────────────────────────────────────
# Core migration function
# ──────────────────────────────────────────────────────────────────────────────

def migrate_paper_db(
    paper_db_path: Path,
    pubs_db_path: Path,
) -> dict[str, list[str]]:
    """
    Read *paper_db_path* and write migrated entries to *pubs_db_path*.

    Returns ``{"included": [slugs], "skipped": [slugs]}``.
    """
    with open(paper_db_path, encoding="utf-8") as fh:
        raw_db: dict[str, Any] = json.load(fh)

    db = PubsDatabase(pubs_db_path)
    db.load()

    included: list[str] = []
    skipped: list[str] = []

    # Rich summary table
    table = Table(title="paper_db migration", show_lines=False)
    table.add_column("slug", style="cyan", no_wrap=True)
    table.add_column("disposition", style="bold")
    table.add_column("reason", style="dim")

    for raw_slug, entry_data in raw_db.items():
        # Skip metadata keys
        if raw_slug in _SKIP_KEYS:
            continue

        # Apply slug mapping
        slug = SLUG_MAPPINGS.get(raw_slug, raw_slug)

        # --- Rule 0: skip non-academic categories BEFORE inclusion checks ---
        category_raw = entry_data.get("category", "")
        if category_raw.lower() in _SKIP_CATEGORIES:
            skipped.append(raw_slug)
            table.add_row(raw_slug, "[red]skipped[/red]", f"category={category_raw!r}")
            continue

        # --- Inclusion criteria ---
        status, include = _determine_status_and_include(entry_data)
        if not include:
            skipped.append(raw_slug)
            table.add_row(raw_slug, "[yellow]skipped[/yellow]", "no qualifying artifact/venue/doi/arxiv")
            continue

        # --- Field mapping ---
        title = entry_data.get("title", "")
        if not title:
            skipped.append(raw_slug)
            table.add_row(raw_slug, "[yellow]skipped[/yellow]", "missing title")
            continue

        authors = _normalise_authors(entry_data.get("authors"))
        date = entry_data.get("date", "")
        pub_type = _map_type(category_raw)

        # Artifacts
        artifacts: dict[str, str | None] = {}
        if entry_data.get("pdf_path"):
            artifacts["pdf"] = entry_data["pdf_path"]
        if entry_data.get("html_path"):
            artifacts["html"] = entry_data["html_path"]
        if entry_data.get("cite_path"):
            artifacts["bibtex"] = entry_data["cite_path"]
        if entry_data.get("github_url"):
            artifacts["code"] = entry_data["github_url"]
        slides_url = _extract_slides(entry_data.get("links", []))
        if slides_url:
            artifacts["slides"] = slides_url

        source_repo = _strip_github_prefix(entry_data.get("source_path"))

        # Timeline seed
        timeline: list[dict] = [
            {
                "date": date,
                "event": "migrated",
                "note": "Migrated from paper_db",
            }
        ]

        pub_entry = PubEntry(
            slug=slug,
            title=title,
            authors=authors,
            date=date,
            status=status,
            type=pub_type,
            abstract=entry_data.get("abstract"),
            tags=entry_data.get("tags", []),
            venue=entry_data.get("venue"),
            doi=entry_data.get("doi"),
            arxiv_id=entry_data.get("arxiv_id"),
            artifacts=artifacts,
            timeline=timeline,
            source_repo=source_repo,
        )

        db.set(pub_entry)
        included.append(raw_slug)
        reason = f"status={status}, type={pub_type}"
        if raw_slug != slug:
            reason += f", slug={slug}"
        table.add_row(raw_slug, "[green]included[/green]", reason)

    db.save()
    console.print(table)
    console.print(
        f"\n[bold]Migration complete:[/bold] "
        f"[green]{len(included)} included[/green], "
        f"[yellow]{len(skipped)} skipped[/yellow] "
        f"→ {pubs_db_path}"
    )

    return {"included": included, "skipped": skipped}
