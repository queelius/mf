"""
Database management for papers and projects.

Provides unified interfaces for loading, saving, and manipulating
the various JSON databases.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from mf.core.backup import safe_write_json
from mf.core.config import get_paths

console = Console()


@dataclass
class PaperEntry:
    """A single paper entry in the database."""

    slug: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.data.get("title", self.slug))

    @property
    def date(self) -> str | None:
        return self.data.get("date")

    @property
    def abstract(self) -> str | None:
        return self.data.get("abstract")

    @property
    def authors(self) -> list:
        """Get authors (handles both simple list and rich format)."""
        return list(self.data.get("authors", []))

    @property
    def advisors(self) -> list:
        """Get advisors (for theses)."""
        return list(self.data.get("advisors", []))

    @property
    def venue(self) -> str | None:
        return self.data.get("venue")

    @property
    def status(self) -> str | None:
        return self.data.get("status")

    @property
    def doi(self) -> str | None:
        return self.data.get("doi")

    @property
    def arxiv_id(self) -> str | None:
        return self.data.get("arxiv_id")

    @property
    def links(self) -> list[dict]:
        """Get links [{name, url}]."""
        return list(self.data.get("links", []))

    @property
    def pdf_path(self) -> str | None:
        return self.data.get("pdf_path")

    @property
    def cite_path(self) -> str | None:
        return self.data.get("cite_path")

    @property
    def source_path(self) -> Path | None:
        if path := self.data.get("source_path"):
            return Path(path)
        return None

    @property
    def source_hash(self) -> str | None:
        return self.data.get("source_hash")

    @property
    def source_format(self) -> str:
        """Get source format (tex, docx, pregenerated). Defaults to tex."""
        return str(self.data.get("source_format", "tex"))

    @property
    def last_generated(self) -> str | None:
        return self.data.get("last_generated")

    @property
    def zenodo_deposit_id(self) -> int | None:
        """Get Zenodo deposit ID."""
        return self.data.get("zenodo_deposit_id")

    @property
    def zenodo_doi(self) -> str | None:
        """Get Zenodo DOI (separate from other DOIs)."""
        return self.data.get("zenodo_doi")

    @property
    def zenodo_url(self) -> str | None:
        """Get Zenodo record URL."""
        return self.data.get("zenodo_url")

    @property
    def zenodo_registered_at(self) -> str | None:
        """Get timestamp of Zenodo registration."""
        return self.data.get("zenodo_registered_at")

    @property
    def stars(self) -> int:
        """Get star rating (0-5)."""
        return int(self.data.get("stars", 0))

    def has_zenodo(self) -> bool:
        """Check if this paper is registered on Zenodo."""
        return self.zenodo_doi is not None

    def is_publication(self) -> bool:
        """Check if this paper is a formal publication."""
        if self.status == "published":
            return True
        if self.venue:
            return True
        return bool(self.doi and "arxiv" not in self.doi.lower())

    def is_preprint(self) -> bool:
        """Check if this is an arXiv preprint."""
        return bool(self.arxiv_id)

    def update(self, **kwargs: Any) -> None:
        """Update entry data."""
        self.data.update(kwargs)

    def set_source_tracking(self, source_path: Path, source_hash: str) -> None:
        """Set source file tracking info."""
        self.data["source_path"] = str(source_path)
        self.data["source_hash"] = source_hash
        self.data["last_generated"] = datetime.now().isoformat()

    @property
    def zenodo_concept_doi(self) -> str | None:
        """Get Zenodo concept DOI (points to latest version)."""
        return self.data.get("zenodo_concept_doi")

    @property
    def zenodo_version(self) -> int:
        """Get current Zenodo version number."""
        return int(self.data.get("zenodo_version", 1))

    def set_zenodo_registration(
        self,
        deposit_id: int,
        doi: str,
        url: str,
        concept_doi: str | None = None,
        version: int = 1,
    ) -> None:
        """Set Zenodo registration info.

        Args:
            deposit_id: Zenodo deposit ID
            doi: Zenodo version DOI (e.g., "10.5281/zenodo.12345678")
            url: Zenodo record URL
            concept_doi: Zenodo concept DOI (points to latest version)
            version: Version number
        """
        self.data["zenodo_deposit_id"] = deposit_id
        self.data["zenodo_doi"] = doi
        self.data["zenodo_url"] = url
        self.data["zenodo_registered_at"] = datetime.now().isoformat()
        self.data["zenodo_version"] = version
        if concept_doi:
            self.data["zenodo_concept_doi"] = concept_doi


class PaperDatabase:
    """Manages paper_db.json with safe loading/saving and validation."""

    # Keys that are metadata, not paper entries
    SPECIAL_KEYS = {"_comment", "_example", "_schema_version"}

    # Default metadata structure
    DEFAULT_META = {
        "_comment": "Paper metadata database. Manual overrides take precedence.",
        "_schema_version": "2.0",
        "_example": {
            # Core metadata
            "date": "2024-01-15",
            "title": "Paper Title",
            "abstract": "Paper abstract...",
            "tags": ["tag1", "tag2"],
            "category": "research paper",
            "stars": 5,
            "featured": True,
            # Authors - simple list or rich format
            "authors": [
                {"name": "Author One", "email": "author@example.com"},
                {"name": "Author Two", "email": "author2@example.com"},
            ],
            # For theses
            "advisors": [
                {"name": "Advisor Name", "email": "advisor@example.edu"},
            ],
            # Publication info (for published works)
            "status": "published",  # published, preprint, draft, submitted
            "venue": "Conference/Journal Name",
            "publication_type": "conference",  # conference, journal, thesis, technical-report
            "year": 2024,
            "doi": "10.1234/example",
            "arxiv_id": "2401.12345",
            # Links and resources
            "links": [
                {"name": "GitHub", "url": "https://github.com/user/repo"},
                {"name": "Slides", "url": "/latex/paper/slides.pdf"},
                {"name": "Video", "url": "https://youtube.com/..."},
            ],
            "pdf_path": "/latex/paper/paper.pdf",
            "html_path": "/latex/paper/index.html",
            "cite_path": "/latex/paper/cite.bib",
            # Related content
            "github_url": "https://github.com/user/repo",
            "project_url": "/projects/related-project/",
            "related_posts": ["/post/2024-01-01-about-this-paper/"],
            # Source tracking (for LaTeX processing)
            "source_path": "/path/to/source/paper.tex",
            "source_format": "tex",  # tex (default), docx, pregenerated
            "source_hash": "sha256:abcdef...",
            "last_generated": "2025-10-07T12:34:56",
        },
    }

    def __init__(self, db_path: Path | None = None):
        """Initialize database.

        Args:
            db_path: Path to paper_db.json (uses default if not provided)
        """
        if db_path is None:
            db_path = get_paths().paper_db
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load database from file.

        Raises:
            SystemExit: If JSON is invalid (to prevent data loss)
        """
        if not self.db_path.exists():
            self._data = dict(self.DEFAULT_META)
            self._loaded = True
            return

        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True

        except json.JSONDecodeError as e:
            console.print(f"\n[red]{'='*70}[/red]")
            console.print(f"[red]ERROR: {self.db_path} contains invalid JSON![/red]")
            console.print(f"[red]{'='*70}[/red]")
            console.print(f"\nJSON Error: {e}")
            console.print("\n[yellow]REFUSING TO CONTINUE - This would overwrite your manual metadata![/yellow]")
            console.print("\nFix the JSON syntax error or restore from backup:")
            console.print(f"  cp {self.db_path.parent}/backups/paper_db_*.json {self.db_path}")
            sys.exit(1)

    def save(self, create_backup: bool = True) -> None:
        """Save database to file.

        Args:
            create_backup: Create backup before saving
        """
        if not self._loaded:
            raise RuntimeError("Database not loaded. Call load() first.")

        # Ensure metadata keys are present
        for key, value in self.DEFAULT_META.items():
            if key not in self._data:
                self._data[key] = value

        # Sort paper entries alphabetically
        sorted_data = {key: self._data[key] for key in sorted(self._data)}

        safe_write_json(
            self.db_path,
            sorted_data,
            create_backup_first=create_backup,
        )

    def __contains__(self, slug: str) -> bool:
        """Check if a paper exists in the database."""
        return slug in self._data and slug not in self.SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        """Iterate over paper slugs."""
        for key in self._data:
            if key not in self.SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        """Return number of papers in database."""
        return sum(1 for key in self._data if key not in self.SPECIAL_KEYS)

    def get(self, slug: str) -> PaperEntry | None:
        """Get a paper entry by slug.

        Args:
            slug: Paper slug

        Returns:
            PaperEntry or None if not found
        """
        if slug in self.SPECIAL_KEYS or slug not in self._data:
            return None
        return PaperEntry(slug=slug, data=self._data[slug])

    def get_or_create(self, slug: str) -> PaperEntry:
        """Get or create a paper entry.

        Args:
            slug: Paper slug

        Returns:
            PaperEntry (existing or new)
        """
        if slug not in self._data or slug in self.SPECIAL_KEYS:
            self._data[slug] = {}
        return PaperEntry(slug=slug, data=self._data[slug])

    def set(self, slug: str, data: dict[str, Any]) -> None:
        """Set or update a paper entry.

        Args:
            slug: Paper slug
            data: Paper data
        """
        if slug in self.SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {slug}")
        self._data[slug] = data

    def update(self, slug: str, **kwargs: Any) -> None:
        """Update specific fields of a paper entry.

        Args:
            slug: Paper slug
            **kwargs: Fields to update
        """
        entry = self.get_or_create(slug)
        entry.update(**kwargs)

    def delete(self, slug: str) -> bool:
        """Delete a paper entry.

        Args:
            slug: Paper slug

        Returns:
            True if deleted, False if not found
        """
        if slug in self._data and slug not in self.SPECIAL_KEYS:
            del self._data[slug]
            return True
        return False

    def items(self) -> Iterator[tuple[str, PaperEntry]]:
        """Iterate over (slug, entry) pairs."""
        for slug in self:
            entry = self.get(slug)
            if entry is not None:
                yield slug, entry

    def papers_with_source(self) -> Iterator[PaperEntry]:
        """Iterate over papers that have source tracking."""
        for slug in self:
            entry = self.get(slug)
            if entry and entry.source_path:
                yield entry

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        has_source: bool | None = None,
        featured: bool | None = None,
    ) -> list[PaperEntry]:
        """Search papers with filters.

        Args:
            query: Text search in title/abstract
            tags: Filter by tags (any match)
            category: Filter by category
            has_source: Filter by whether source tracking exists
            featured: Filter by featured status

        Returns:
            List of matching PaperEntry objects
        """
        results = []

        for slug in self:
            entry = self.get(slug)
            if not entry:
                continue

            # Text search
            if query:
                query_lower = query.lower()
                title = entry.data.get("title", slug).lower()
                abstract = entry.data.get("abstract", "").lower()
                if query_lower not in title and query_lower not in abstract:
                    continue

            # Tags filter
            if tags:
                entry_tags = entry.data.get("tags", [])
                if not any(tag in entry_tags for tag in tags):
                    continue

            # Category filter
            if category and entry.data.get("category") != category:
                continue

            # Source tracking filter
            if has_source is not None:
                has_src = entry.source_path is not None
                if has_src != has_source:
                    continue

            # Featured filter
            if featured is not None:
                is_featured = entry.data.get("featured", False)
                if is_featured != featured:
                    continue

            results.append(entry)

        return results

    def list_categories(self) -> list[str]:
        """Get all unique categories."""
        categories = set()
        for _slug, entry in self.items():
            if cat := entry.data.get("category"):
                categories.add(cat)
        return sorted(categories)

    def list_tags(self) -> list[str]:
        """Get all unique tags."""
        tags: set[str] = set()
        for _slug, entry in self.items():
            tags.update(entry.data.get("tags", []))
        return sorted(tags)

    def stats(self) -> dict[str, Any]:
        """Get database statistics."""
        total = len(self)
        with_source = 0
        featured = 0

        for _slug, entry in self.items():
            if entry.source_path:
                with_source += 1
            if entry.data.get("featured"):
                featured += 1

        categories = self.list_categories()

        return {
            "total": total,
            "with_source": with_source,
            "featured": featured,
            "categories": categories,
            "category_count": len(categories),
        }


class ProjectsDatabase:
    """Manages projects_db.json with safe loading/saving."""

    SPECIAL_KEYS = {"_comment", "_example", "_schema_version"}

    DEFAULT_META = {
        "_comment": "Manual overrides for projects. GitHub data is cached separately.",
        "_schema_version": "2.0",
        "_example": {
            "title": "Custom Project Title",
            "abstract": "Custom description",
            "stars": 5,
            "featured": True,
            "hide": False,
            "maturity": "stable",
            "category": "library",
            "tags": ["tag1", "tag2"],
            # Rich project settings (branch bundle with sub-pages)
            "rich_project": True,
            "content_sections": ["docs", "tutorials", "examples"],
            # External documentation links
            "external_docs": {
                "mkdocs": "https://username.github.io/project/",
                "readthedocs": "https://project.readthedocs.io/",
                "api_reference": "https://username.github.io/project/api/",
                "github_wiki": "https://github.com/username/project/wiki",
            },
            # Related content (populated by mf content match-projects)
            "related_posts": ["/post/2024-01-15-introducing-project/"],
            "related_papers": ["/papers/project-whitepaper/"],
        },
    }

    def __init__(self, db_path: Path | None = None):
        """Initialize database.

        Args:
            db_path: Path to projects_db.json (uses default if not provided)
        """
        if db_path is None:
            db_path = get_paths().projects_db
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load database from file."""
        if not self.db_path.exists():
            self._data = dict(self.DEFAULT_META)
            self._loaded = True
            return

        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True

        except json.JSONDecodeError as e:
            console.print(f"[red]ERROR: Invalid JSON in {self.db_path}: {e}[/red]")
            sys.exit(1)

    def save(self, create_backup: bool = True) -> None:
        """Save database to file."""
        if not self._loaded:
            raise RuntimeError("Database not loaded. Call load() first.")

        for key, value in self.DEFAULT_META.items():
            if key not in self._data:
                self._data[key] = value

        safe_write_json(
            self.db_path,
            self._data,
            create_backup_first=create_backup,
            backup_dir=get_paths().projects_backups,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._data and slug not in self.SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        for key in self._data:
            if key not in self.SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        """Return number of projects in database."""
        return sum(1 for key in self._data if key not in self.SPECIAL_KEYS)

    def get(self, slug: str) -> dict[str, Any] | None:
        """Get project overrides by slug."""
        if slug in self.SPECIAL_KEYS or slug not in self._data:
            return None
        result: dict[str, Any] = self._data[slug]
        return result

    def set(self, slug: str, data: dict[str, Any]) -> None:
        """Set project overrides."""
        if slug in self.SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {slug}")
        self._data[slug] = data

    def update(self, slug: str, **kwargs: Any) -> None:
        """Update specific fields."""
        if slug not in self._data:
            self._data[slug] = {}
        self._data[slug].update(kwargs)

    def delete(self, slug: str) -> bool:
        """Delete a project entry.

        Args:
            slug: Project slug to delete

        Returns:
            True if deleted, False if not found
        """
        if slug in self._data and slug not in self.SPECIAL_KEYS:
            del self._data[slug]
            return True
        return False

    def is_hidden(self, slug: str) -> bool:
        """Check if project should be hidden."""
        data = self.get(slug)
        return data.get("hide", False) if data else False

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        featured: bool | None = None,
        hidden: bool | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Search projects with filters.

        Args:
            query: Text search in title/abstract
            tags: Filter by tags (any match)
            category: Filter by category
            featured: Filter by featured status
            hidden: Filter by hidden status

        Returns:
            List of (slug, data) tuples
        """
        results = []

        for slug in self:
            data = self.get(slug)
            if not data:
                continue

            # Text search
            if query:
                query_lower = query.lower()
                title = data.get("title", slug).lower()
                abstract = data.get("abstract", "").lower()
                if query_lower not in title and query_lower not in abstract:
                    continue

            # Tags filter
            if tags:
                proj_tags = data.get("tags", [])
                if not any(tag in proj_tags for tag in tags):
                    continue

            # Category filter
            if category and data.get("category") != category:
                continue

            # Featured filter
            if featured is not None:
                is_featured = data.get("featured", False)
                if is_featured != featured:
                    continue

            # Hidden filter
            if hidden is not None:
                is_hidden = data.get("hide", False)
                if is_hidden != hidden:
                    continue

            results.append((slug, data))

        return results

    def list_categories(self) -> list[str]:
        """Get all unique categories."""
        categories = set()
        for slug in self:
            data = self.get(slug)
            if data and (cat := data.get("category")):
                categories.add(cat)
        return sorted(categories)

    def list_tags(self) -> list[str]:
        """Get all unique tags."""
        tags: set[str] = set()
        for slug in self:
            data = self.get(slug)
            if data:
                tags.update(data.get("tags", []))
        return sorted(tags)

    def is_rich_project(self, slug: str) -> bool:
        """Check if project should use branch bundle (rich content)."""
        data = self.get(slug)
        return data.get("rich_project", False) if data else False

    def get_content_sections(self, slug: str) -> list[str]:
        """Get content sections for a rich project."""
        data = self.get(slug)
        return data.get("content_sections", []) if data else []

    def get_external_docs(self, slug: str) -> dict[str, str]:
        """Get external documentation URLs for a project."""
        data = self.get(slug)
        return data.get("external_docs", {}) if data else {}

    def list_rich_projects(self) -> list[str]:
        """Get all projects configured as rich projects."""
        return [slug for slug in self if self.is_rich_project(slug)]

    def stats(self) -> dict[str, Any]:
        """Get database statistics."""
        total = len(self)
        featured = 0
        hidden = 0
        rich = 0
        with_external_docs = 0

        for slug in self:
            data = self.get(slug)
            if data is None:
                continue
            if data.get("featured"):
                featured += 1
            if data.get("hide"):
                hidden += 1
            if data.get("rich_project"):
                rich += 1
            if data.get("external_docs"):
                with_external_docs += 1

        categories = self.list_categories()

        return {
            "total": total,
            "featured": featured,
            "hidden": hidden,
            "visible": total - hidden,
            "rich_projects": rich,
            "with_external_docs": with_external_docs,
            "categories": categories,
            "category_count": len(categories),
        }


@dataclass
class SeriesEntry:
    """A single series entry in the database."""

    slug: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.data.get("title", self.slug.replace("-", " ").title()))

    @property
    def description(self) -> str | None:
        return self.data.get("description")

    @property
    def status(self) -> str:
        return str(self.data.get("status", "active"))

    @property
    def featured(self) -> bool:
        return bool(self.data.get("featured", False))

    @property
    def tags(self) -> list[str]:
        return list(self.data.get("tags", []))

    @property
    def color(self) -> str | None:
        return self.data.get("color")

    @property
    def icon(self) -> str | None:
        return self.data.get("icon")

    @property
    def created_date(self) -> str | None:
        return self.data.get("created_date")

    @property
    def related_projects(self) -> list[str]:
        return list(self.data.get("related_projects", []))

    @property
    def associations(self) -> dict[str, Any]:
        """Get all associations for this series.

        Returns a dict with keys like:
        - papers: List of paper slugs
        - media: List of media slugs (books, videos, etc.)
        - links: List of external URLs/dicts
        - posts: List of post slugs (manual additions beyond series taxonomy)
        """
        result: dict[str, Any] = self.data.get("associations", {})
        return result

    @property
    def related_papers(self) -> list[str]:
        """Get papers associated with this series."""
        return list(self.associations.get("papers", []))

    @property
    def related_media(self) -> list[str]:
        """Get media (books, videos, etc.) associated with this series."""
        return list(self.associations.get("media", []))

    @property
    def external_links(self) -> list[dict[str, str]]:
        """Get external links associated with this series.

        Returns list of dicts with 'name' and 'url' keys.
        """
        result: list[dict[str, str]] = self.associations.get("links", [])
        return result

    @property
    def source_dir(self) -> Path | None:
        """Get the source directory for this series (external repo)."""
        if path := self.data.get("source_dir"):
            # Expand ~ to home directory
            return Path(path).expanduser()
        return None

    @property
    def posts_subdir(self) -> str:
        """Get the subdirectory within source_dir containing posts."""
        return str(self.data.get("posts_subdir", "post"))

    @property
    def landing_page(self) -> str | None:
        """Get the relative path to the landing page within source_dir."""
        value: str | None = self.data.get("landing_page", "docs/index.md")
        return value

    @property
    def sync_state(self) -> dict[str, dict[str, str | None]]:
        """Get the sync state tracking hashes for posts.

        Returns:
            Dict mapping post slug to sync state dict with keys:
            - source_hash: Hash of source version at last sync
            - target_hash: Hash of target (metafunctor) version at last sync
            - last_synced: ISO timestamp of last sync

        Note: Automatically migrates old format (plain hash strings) to new format.
        """
        raw_state: dict[str, Any] = self.data.get("_sync_state", {})
        result: dict[str, dict[str, str | None]] = {}
        for slug, value in raw_state.items():
            if isinstance(value, str):
                # Old format: migrate to new format (assume source hash only)
                result[slug] = {
                    "source_hash": value,
                    "target_hash": None,
                    "last_synced": None,
                }
            elif isinstance(value, dict):
                result[slug] = value
            # Skip invalid entries
        return result

    def get_sync_hashes(self, post_slug: str) -> tuple[str | None, str | None]:
        """Get the source and target hashes for a post.

        Args:
            post_slug: Post slug

        Returns:
            Tuple of (source_hash, target_hash), either can be None
        """
        state = self.sync_state.get(post_slug, {})
        return state.get("source_hash"), state.get("target_hash")

    def has_source(self) -> bool:
        """Check if this series has an external source configured."""
        return self.source_dir is not None

    def update(self, **kwargs: Any) -> None:
        """Update entry data."""
        self.data.update(kwargs)

    def set_sync_state(
        self,
        post_slug: str,
        source_hash: str | None = None,
        target_hash: str | None = None,
    ) -> None:
        """Set the sync hashes for a post.

        Args:
            post_slug: Post slug
            source_hash: Hash of source version (optional)
            target_hash: Hash of target/metafunctor version (optional)
        """
        if "_sync_state" not in self.data:
            self.data["_sync_state"] = {}

        # Get existing state or create new
        current = self.data["_sync_state"].get(post_slug, {})
        if isinstance(current, str):
            # Migrate old format
            current = {"source_hash": current, "target_hash": None}

        # Update with new values (only if provided)
        if source_hash is not None:
            current["source_hash"] = source_hash
        if target_hash is not None:
            current["target_hash"] = target_hash
        current["last_synced"] = datetime.now().isoformat()

        self.data["_sync_state"][post_slug] = current

    def clear_sync_state(self, post_slug: str) -> None:
        """Clear the sync hash for a post."""
        if "_sync_state" in self.data:
            self.data["_sync_state"].pop(post_slug, None)


class SeriesDatabase:
    """Manages series_db.json with safe loading/saving."""

    SPECIAL_KEYS = {"_comment", "_example", "_schema_version"}

    DEFAULT_META = {
        "_comment": "Series metadata database.",
        "_schema_version": "1.3",  # 1.3: _sync_state now tracks both source and target hashes
        "_example": {
            "title": "Series Title",
            "description": "Short description for cards",
            "status": "active",  # active, completed, archived
            "featured": False,
            "tags": ["tag1", "tag2"],
            "color": "#667eea",
            "icon": "code",
            "created_date": "2024-01-01",
            "related_projects": ["project-slug"],
            # Associations to other content (metafunctor-only, not synced to source)
            "associations": {
                "papers": ["paper-slug-1", "paper-slug-2"],
                "media": ["book-slug", "video-slug"],
                "links": [
                    {"name": "External Resource", "url": "https://example.com"},
                    {"name": "Reference Material", "url": "https://reference.com"},
                ],
            },
            # Source sync configuration (optional)
            "source_dir": "~/github/alpha/series-name",  # External source repo
            "posts_subdir": "post",  # Subdir in source containing posts (default: "post")
            "landing_page": "docs/index.md",  # Landing page path in source (default)
            # Sync state tracking (managed automatically)
            # New format tracks both source and target hashes for conflict detection
            "_sync_state": {
                "post-slug": {
                    "source_hash": "sha256:abcdef123456...",
                    "target_hash": "sha256:fedcba654321...",
                    "last_synced": "2026-01-20T12:00:00",
                },
            },
        },
    }

    def __init__(self, db_path: Path | None = None):
        """Initialize database.

        Args:
            db_path: Path to series_db.json (uses default if not provided)
        """
        if db_path is None:
            db_path = get_paths().series_db
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load database from file."""
        if not self.db_path.exists():
            self._data = dict(self.DEFAULT_META)
            self._loaded = True
            return

        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True

        except json.JSONDecodeError as e:
            console.print(f"[red]ERROR: Invalid JSON in {self.db_path}: {e}[/red]")
            sys.exit(1)

    def save(self, create_backup: bool = True) -> None:
        """Save database to file."""
        if not self._loaded:
            raise RuntimeError("Database not loaded. Call load() first.")

        for key, value in self.DEFAULT_META.items():
            if key not in self._data:
                self._data[key] = value

        safe_write_json(
            self.db_path,
            self._data,
            create_backup_first=create_backup,
            backup_dir=get_paths().series_backups,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._data and slug not in self.SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        for key in self._data:
            if key not in self.SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        """Return number of series in database."""
        return sum(1 for key in self._data if key not in self.SPECIAL_KEYS)

    def get(self, slug: str) -> SeriesEntry | None:
        """Get a series entry by slug.

        Args:
            slug: Series slug

        Returns:
            SeriesEntry or None if not found
        """
        if slug in self.SPECIAL_KEYS or slug not in self._data:
            return None
        return SeriesEntry(slug=slug, data=self._data[slug])

    def get_or_create(self, slug: str) -> SeriesEntry:
        """Get or create a series entry.

        Args:
            slug: Series slug

        Returns:
            SeriesEntry (existing or new)
        """
        if slug not in self._data or slug in self.SPECIAL_KEYS:
            self._data[slug] = {}
        return SeriesEntry(slug=slug, data=self._data[slug])

    def set(self, slug: str, data: dict[str, Any]) -> None:
        """Set or update a series entry.

        Args:
            slug: Series slug
            data: Series data
        """
        if slug in self.SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {slug}")
        self._data[slug] = data

    def update(self, slug: str, **kwargs: Any) -> None:
        """Update specific fields of a series entry.

        Args:
            slug: Series slug
            **kwargs: Fields to update
        """
        entry = self.get_or_create(slug)
        entry.update(**kwargs)

    def delete(self, slug: str) -> bool:
        """Delete a series entry.

        Args:
            slug: Series slug

        Returns:
            True if deleted, False if not found
        """
        if slug in self._data and slug not in self.SPECIAL_KEYS:
            del self._data[slug]
            return True
        return False

    def items(self) -> Iterator[tuple[str, SeriesEntry]]:
        """Iterate over (slug, entry) pairs."""
        for slug in self:
            entry = self.get(slug)
            if entry:
                yield slug, entry

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        featured: bool | None = None,
    ) -> list[SeriesEntry]:
        """Search series with filters.

        Args:
            query: Text search in title/description
            tags: Filter by tags (any match)
            status: Filter by status
            featured: Filter by featured status

        Returns:
            List of matching SeriesEntry objects
        """
        results = []

        for slug in self:
            entry = self.get(slug)
            if not entry:
                continue

            # Text search
            if query:
                query_lower = query.lower()
                title = entry.title.lower()
                desc = (entry.description or "").lower()
                if query_lower not in title and query_lower not in desc:
                    continue

            # Tags filter
            if tags:
                entry_tags = entry.tags
                if not any(tag in entry_tags for tag in tags):
                    continue

            # Status filter
            if status and entry.status != status:
                continue

            # Featured filter
            if featured is not None and entry.featured != featured:
                continue

            results.append(entry)

        return results

    def list_tags(self) -> list[str]:
        """Get all unique tags."""
        tags: set[str] = set()
        for _slug, entry in self.items():
            tags.update(entry.tags)
        return sorted(tags)

    def list_statuses(self) -> list[str]:
        """Get all unique statuses."""
        statuses: set[str] = set()
        for _slug, entry in self.items():
            statuses.add(entry.status)
        return sorted(statuses)

    def stats(self) -> dict[str, Any]:
        """Get database statistics."""
        total = len(self)
        featured = 0
        active = 0

        for _slug, entry in self.items():
            if entry.featured:
                featured += 1
            if entry.status == "active":
                active += 1

        return {
            "total": total,
            "featured": featured,
            "active": active,
            "statuses": self.list_statuses(),
        }


class ProjectsCache:
    """Manages projects_cache.json (GitHub API responses)."""

    def __init__(self, cache_path: Path | None = None):
        """Initialize cache.

        Args:
            cache_path: Path to projects_cache.json
        """
        if cache_path is None:
            cache_path = get_paths().projects_cache
        self.cache_path = Path(cache_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load cache from file."""
        if not self.cache_path.exists():
            self._data = {}
            self._loaded = True
            return

        try:
            with open(self.cache_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True
        except (json.JSONDecodeError, OSError) as e:
            console.print(f"[yellow]Warning: Could not load cache: {e}[/yellow]")
            self._data = {}
            self._loaded = True

    def save(self) -> None:
        """Save cache to file (no backup needed - regenerable)."""
        if not self._loaded:
            raise RuntimeError("Cache not loaded. Call load() first.")

        # Use safe_write_json but without backup
        safe_write_json(
            self.cache_path,
            self._data,
            create_backup_first=False,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def get(self, slug: str) -> dict[str, Any] | None:
        """Get cached GitHub data for a project."""
        return self._data.get(slug)

    def set(self, slug: str, data: dict[str, Any]) -> None:
        """Cache GitHub data for a project."""
        self._data[slug] = data

    def delete(self, slug: str) -> bool:
        """Remove project from cache."""
        if slug in self._data:
            del self._data[slug]
            return True
        return False
