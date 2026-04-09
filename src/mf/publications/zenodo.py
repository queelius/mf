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


def map_pub_to_zenodo_metadata(entry: PubEntry) -> dict[str, Any]:
    """Map a PubEntry to Zenodo deposit metadata."""
    upload_type, publication_type = TYPE_TO_UPLOAD.get(
        entry.type, ("publication", "other"))

    # Creators
    creators = []
    for author in entry.authors:
        if isinstance(author, dict):
            creator: dict[str, str] = {"name": author.get("name", "Unknown")}
            if "affiliation" in author:
                creator["affiliation"] = author["affiliation"]
            if "orcid" in author:
                creator["orcid"] = author["orcid"]
        else:
            creator = {"name": str(author)}
        creators.append(creator)
    if not creators:
        creators = [{"name": "Unknown"}]

    metadata: dict[str, Any] = {
        "title": entry.title,
        "upload_type": upload_type,
        "creators": creators,
        "access_right": "open",
        "license": "cc-by-4.0",
    }

    if publication_type:
        metadata["publication_type"] = publication_type

    # Description
    metadata["description"] = entry.abstract or f"Publication: {entry.title}"

    # Date
    if entry.date:
        date_str = str(entry.date)
        metadata["publication_date"] = date_str[:10] if len(date_str) >= 10 else date_str
    else:
        metadata["publication_date"] = datetime.now().strftime("%Y-%m-%d")

    # Keywords
    if entry.tags:
        metadata["keywords"] = entry.tags

    # Related identifiers
    related = []
    code_url = entry.artifacts.get("code")
    if code_url:
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

    if pdf_path.startswith("/"):
        # Site-relative: strip leading / and resolve under static_dir parent
        # /latex/foo/paper.pdf -> static/latex/foo/paper.pdf
        candidate = static_dir.parent / pdf_path.lstrip("/")
        if candidate.exists():
            return candidate
        # Also try under static_dir directly
        candidate = static_dir / pdf_path.lstrip("/")
        if candidate.exists():
            return candidate

    # Absolute or relative path
    p = Path(pdf_path)
    if p.exists():
        return p

    return None
