"""
Publication database: typed data model and JSON persistence.

Decoupled from paper_db.json. Self-contained lifecycle tracking,
artifact management, and timeline events.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from mf.core.backup import safe_write_json
from mf.core.config import get_paths

console = Console()

VALID_STATUSES = frozenset({
    "draft", "preprint", "submitted", "under-review",
    "accepted", "published", "rejected", "revised", "withdrawn",
})

VALID_TYPES = frozenset({
    "conference paper", "journal article", "workshop paper",
    "thesis", "technical report", "white paper", "preprint",
    "book chapter",
})

# Documented artifact keys for the artifacts dict.
# These are conventions, not enforced: any key is allowed, but using these
# names ensures Hugo templates render the artifact with the right icon/label.
#
# Each value is either:
#   - A site-relative path starting with "/" (e.g., "/latex/foo/paper.pdf")
#   - A URL starting with "http" (e.g., "https://github.com/...")
#   - The string "pending" as a placeholder for an artifact not yet available
ARTIFACT_KEYS = frozenset({
    # Paper artifacts
    "pdf",        # The paper PDF (camera-ready or preprint version)
    "html",       # Web-rendered HTML version of the paper
    "bibtex",     # BibTeX citation file
    "supplement", # Supplementary material (appendix, extended proofs)
    # Presentation artifacts
    "slides",     # Presentation slides (PDF or URL)
    "poster",     # Conference poster
    "video",      # Recorded talk (YouTube, conference recording, etc.)
    # Reproducibility artifacts
    "code",       # Code repository URL (GitHub, GitLab, etc.)
    "data",       # Dataset URL (Zenodo, OSF, figshare, etc.)
    # Preprint hosting
    "zenodo",     # Zenodo deposit URL (for citable DOIs)
    "arxiv",      # arXiv abstract URL (for cs.* preprints)
    "osf",        # OSF preprints URL
    "techrxiv",   # TechRxiv URL
    # Social/media artifacts
    "photos",     # Conference/event photos (directory or gallery URL)
})

SPECIAL_KEYS = frozenset({"_schema_version"})


@dataclass
class PubEntry:
    """A single publication entry."""

    slug: str
    title: str
    authors: list[dict] = field(default_factory=list)
    date: str = ""
    status: str = "draft"
    type: str = "preprint"

    abstract: str | None = None
    tags: list[str] = field(default_factory=list)
    venue: str | None = None
    venue_details: dict | None = None
    doi: str | None = None
    arxiv_id: str | None = None

    artifacts: dict[str, str | None] = field(default_factory=dict)
    artifacts_source: dict[str, str] = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    source_repo: str | None = None

    @classmethod
    def from_dict(cls, slug: str, data: dict[str, Any]) -> PubEntry:
        """Create a PubEntry from a dict, validating required fields."""
        if not data.get("title"):
            raise ValueError(f"Publication '{slug}' missing required field: title")
        status = data.get("status", "draft")
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Publication '{slug}' has invalid status '{status}'. "
                f"Valid: {sorted(VALID_STATUSES)}"
            )
        pub_type = data.get("type", "preprint")
        if pub_type not in VALID_TYPES:
            raise ValueError(
                f"Publication '{slug}' has invalid type '{pub_type}'. "
                f"Valid: {sorted(VALID_TYPES)}"
            )
        return cls(
            slug=slug,
            title=data["title"],
            authors=data.get("authors", []),
            date=data.get("date", ""),
            status=status,
            type=pub_type,
            abstract=data.get("abstract"),
            tags=data.get("tags", []),
            venue=data.get("venue"),
            venue_details=data.get("venue_details"),
            doi=data.get("doi"),
            arxiv_id=data.get("arxiv_id"),
            artifacts=data.get("artifacts", {}),
            artifacts_source=data.get("artifacts_source", {}),
            links=data.get("links", []),
            timeline=data.get("timeline", []),
            source_repo=data.get("source_repo"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict (for JSON storage)."""
        d: dict[str, Any] = {
            "title": self.title,
            "authors": self.authors,
            "date": self.date,
            "status": self.status,
            "type": self.type,
        }
        if self.abstract:
            d["abstract"] = self.abstract
        if self.tags:
            d["tags"] = self.tags
        if self.venue:
            d["venue"] = self.venue
        if self.venue_details:
            d["venue_details"] = self.venue_details
        if self.doi:
            d["doi"] = self.doi
        if self.arxiv_id:
            d["arxiv_id"] = self.arxiv_id
        if self.artifacts:
            d["artifacts"] = self.artifacts
        if self.artifacts_source:
            d["artifacts_source"] = self.artifacts_source
        if self.links:
            d["links"] = self.links
        if self.timeline:
            d["timeline"] = self.timeline
        if self.source_repo:
            d["source_repo"] = self.source_repo
        return d


class PubsDatabase:
    """Manages pubs_db.json with safe loading/saving and validation."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = get_paths().pubs_db
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        if not self.db_path.exists():
            self._data = {"_schema_version": 1}
            self._loaded = True
            return
        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True
        except json.JSONDecodeError as e:
            console.print(f"[red]ERROR: {self.db_path} contains invalid JSON![/red]")
            console.print(f"JSON Error: {e}")
            sys.exit(1)

    def save(self) -> None:
        if not self._loaded:
            raise RuntimeError("Database not loaded. Call load() first.")
        if "_schema_version" not in self._data:
            self._data["_schema_version"] = 1
        sorted_data = {k: self._data[k] for k in sorted(self._data)}
        safe_write_json(self.db_path, sorted_data, create_backup_first=True)

    def get(self, slug: str) -> PubEntry | None:
        if slug in SPECIAL_KEYS or slug not in self._data:
            return None
        return PubEntry.from_dict(slug, self._data[slug])

    def set(self, entry: PubEntry) -> None:
        if entry.slug in SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {entry.slug}")
        self._data[entry.slug] = entry.to_dict()

    def remove(self, slug: str) -> None:
        self._data.pop(slug, None)

    def __contains__(self, slug: str) -> bool:
        return slug in self._data and slug not in SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        for key in self._data:
            if key not in SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        return sum(1 for k in self._data if k not in SPECIAL_KEYS)
