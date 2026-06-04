"""
Zenodo integration for the publications database.

Maps PubEntry metadata to Zenodo deposit format and handles
registration (create deposit, upload PDF, publish, capture DOI).
Reuses the ZenodoClient from mf.papers.zenodo.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from mf.publications.database import PubEntry

# PubEntry type -> (zenodo upload_type, zenodo publication_type)
TYPE_TO_UPLOAD: dict[str, tuple[str, str | None]] = {
    "conference paper": ("publication", "conferencepaper"),
    "journal article": ("publication", "article"),
    "workshop paper": ("publication", "conferencepaper"),
    "thesis": ("publication", "thesis"),
    "technical report": ("publication", "technicalnote"),
    "white paper": ("publication", "technicalnote"),
    "preprint": ("publication", "preprint"),
    "book chapter": ("publication", "section"),
}


def _build_creator(author: Any) -> dict[str, str]:
    """Convert one author entry (dict or string) to a Zenodo creator dict."""
    if not isinstance(author, dict):
        return {"name": str(author)}
    creator: dict[str, str] = {"name": author.get("name", "Unknown")}
    for key in ("affiliation", "orcid"):
        if key in author:
            creator[key] = author[key]
    return creator


def map_pub_to_zenodo_metadata(entry: PubEntry) -> dict[str, Any]:
    """Map a PubEntry to Zenodo deposit metadata."""
    upload_type, publication_type = TYPE_TO_UPLOAD.get(
        entry.type, ("publication", "other"))

    creators = [_build_creator(a) for a in entry.authors] or [{"name": "Unknown"}]

    metadata: dict[str, Any] = {
        "title": entry.title,
        "upload_type": upload_type,
        "creators": creators,
        "access_right": "open",
        "license": "cc-by-4.0",
        "description": entry.abstract or f"Publication: {entry.title}",
        "publication_date": (
            str(entry.date)[:10] if entry.date
            else datetime.now().strftime("%Y-%m-%d")
        ),
    }

    if publication_type:
        metadata["publication_type"] = publication_type
    if entry.tags:
        metadata["keywords"] = entry.tags

    # Related identifiers
    related: list[dict[str, str]] = []
    if code_url := entry.artifacts.get("code"):
        related.append({
            "identifier": code_url,
            "relation": "isSupplementTo",
            "resource_type": "software",
        })
    if entry.arxiv_id:
        related.append({
            "identifier": f"arXiv:{entry.arxiv_id}",
            "relation": "isIdenticalTo",
            "scheme": "arxiv",
        })
    if related:
        metadata["related_identifiers"] = related

    # Notes
    notes = []
    if entry.venue:
        notes.append(f"Venue: {entry.venue}")
    if entry.status and entry.status != "published":
        notes.append(f"Status: {entry.status}")
    if notes:
        metadata["notes"] = " | ".join(notes)

    return metadata


def find_pub_pdf(entry: PubEntry, static_dir: Path) -> Path | None:
    """Resolve the PDF artifact path to an actual file.

    The artifacts.pdf value is either:
    - A site-relative path like "/latex/foo/paper.pdf" (resolve under static_dir)
    - An absolute path (use directly)
    - None (no PDF available)
    """
    pdf_path = entry.artifacts.get("pdf")
    if not pdf_path:
        return None

    candidates: list[Path] = []
    if pdf_path.startswith("/"):
        # Site-relative: try under static_dir.parent (e.g. site_root) and
        # then under static_dir itself.
        rel = pdf_path.lstrip("/")
        candidates.append(static_dir.parent / rel)
        candidates.append(static_dir / rel)
    candidates.append(Path(pdf_path))

    return next((p for p in candidates if p.exists()), None)
