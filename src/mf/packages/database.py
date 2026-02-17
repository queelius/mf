"""
Package database management.

Provides PackageEntry dataclass and PackageDatabase for managing
package metadata in packages_db.json.
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


@dataclass
class PackageEntry:
    """A single package entry in the database."""

    slug: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.data.get("name", self.slug))

    @property
    def registry(self) -> str | None:
        return self.data.get("registry")

    @property
    def description(self) -> str | None:
        return self.data.get("description")

    @property
    def latest_version(self) -> str | None:
        return self.data.get("latest_version")

    @property
    def featured(self) -> bool:
        return bool(self.data.get("featured", False))

    @property
    def tags(self) -> list[str]:
        return list(self.data.get("tags", []))

    @property
    def project(self) -> str | None:
        return self.data.get("project")

    @property
    def install_command(self) -> str | None:
        return self.data.get("install_command")

    @property
    def registry_url(self) -> str | None:
        return self.data.get("registry_url")

    @property
    def license(self) -> str | None:
        return self.data.get("license")

    @property
    def downloads(self) -> int | None:
        return self.data.get("downloads")

    @property
    def last_synced(self) -> str | None:
        return self.data.get("last_synced")

    @property
    def stars(self) -> int:
        return int(self.data.get("stars", 0))

    def update(self, **kwargs: Any) -> None:
        """Update entry data."""
        self.data.update(kwargs)


class PackageDatabase:
    """Manages packages_db.json with safe loading/saving."""

    SPECIAL_KEYS = {"_comment", "_example", "_schema_version"}

    DEFAULT_META = {
        "_comment": "Package metadata database.",
        "_schema_version": "1.0",
        "_example": {
            "name": "my-package",
            "registry": "pypi",
            "description": "Short description",
            "latest_version": "1.2.3",
            "featured": False,
            "tags": ["python", "utility"],
            "project": "linked-project-slug",
            "install_command": "pip install my-package",
            "registry_url": "https://pypi.org/project/my-package/",
            "license": "MIT",
            "downloads": 10000,
            "last_synced": "2026-01-01T12:00:00",
            "stars": 42,
        },
    }

    def __init__(self, db_path: Path | None = None):
        """Initialize database.

        Args:
            db_path: Path to packages_db.json (uses default if not provided)
        """
        if db_path is None:
            db_path = get_paths().packages_db
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
            backup_dir=get_paths().packages_backups,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._data and slug not in self.SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        for key in self._data:
            if key not in self.SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        """Return number of packages in database."""
        return sum(1 for key in self._data if key not in self.SPECIAL_KEYS)

    def get(self, slug: str) -> PackageEntry | None:
        """Get a package entry by slug.

        Args:
            slug: Package slug

        Returns:
            PackageEntry or None if not found
        """
        if slug in self.SPECIAL_KEYS or slug not in self._data:
            return None
        return PackageEntry(slug=slug, data=self._data[slug])

    def get_or_create(self, slug: str) -> PackageEntry:
        """Get or create a package entry.

        Args:
            slug: Package slug

        Returns:
            PackageEntry (existing or new)
        """
        if slug not in self._data or slug in self.SPECIAL_KEYS:
            self._data[slug] = {}
        return PackageEntry(slug=slug, data=self._data[slug])

    def set(self, slug: str, data: dict[str, Any]) -> None:
        """Set or update a package entry.

        Args:
            slug: Package slug
            data: Package data
        """
        if slug in self.SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {slug}")
        self._data[slug] = data

    def update(self, slug: str, **kwargs: Any) -> None:
        """Update specific fields of a package entry.

        Args:
            slug: Package slug
            **kwargs: Fields to update
        """
        entry = self.get_or_create(slug)
        entry.update(**kwargs)

    def delete(self, slug: str) -> bool:
        """Delete a package entry.

        Args:
            slug: Package slug

        Returns:
            True if deleted, False if not found
        """
        if slug in self._data and slug not in self.SPECIAL_KEYS:
            del self._data[slug]
            return True
        return False

    def items(self) -> Iterator[tuple[str, PackageEntry]]:
        """Iterate over (slug, entry) pairs."""
        for slug in self:
            entry = self.get(slug)
            if entry:
                yield slug, entry

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        registry: str | None = None,
        featured: bool | None = None,
    ) -> list[PackageEntry]:
        """Search packages with filters.

        Args:
            query: Text search in name and description
            tags: Filter by tags (any match)
            registry: Filter by registry (exact match)
            featured: Filter by featured status

        Returns:
            List of matching PackageEntry objects
        """
        results = []

        for slug in self:
            entry = self.get(slug)
            if not entry:
                continue

            # Text search
            if query:
                query_lower = query.lower()
                name = entry.name.lower()
                desc = (entry.description or "").lower()
                if query_lower not in name and query_lower not in desc:
                    continue

            # Tags filter
            if tags:
                entry_tags = entry.tags
                if not any(tag in entry_tags for tag in tags):
                    continue

            # Registry filter
            if registry and entry.registry != registry:
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

    def list_registries(self) -> list[str]:
        """Get all unique registries."""
        registries: set[str] = set()
        for _slug, entry in self.items():
            if entry.registry:
                registries.add(entry.registry)
        return sorted(registries)

    def stats(self) -> dict[str, Any]:
        """Get database statistics."""
        total = len(self)
        featured = 0

        for _slug, entry in self.items():
            if entry.featured:
                featured += 1

        return {
            "total": total,
            "featured": featured,
            "registries": self.list_registries(),
        }
