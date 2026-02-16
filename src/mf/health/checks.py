"""Content health checker.

Checks for broken links, missing descriptions/images, stale projects, and drafts.
"""

from __future__ import annotations

import json
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

from mf.content.scanner import ContentScanner
from mf.core.config import get_paths


class HealthChecker:
    """Runs content health checks."""

    STATIC_PREFIXES = ("/images/", "/latex/", "/css/", "/js/", "/files/")

    def __init__(self, site_root: Path | None = None):
        if site_root is None:
            site_root = get_paths().root
        self.site_root = site_root
        self.scanner = ContentScanner(site_root)

    def _build_known_paths(self) -> set[str]:
        """Build set of known Hugo content paths."""
        paths: set[str] = set()
        for ct in self.scanner.CONTENT_TYPES:
            for item in self.scanner.scan_type(ct, include_drafts=True):
                paths.add(item.hugo_path)
        return paths

    def check_links(
        self,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find broken internal links.

        Returns list of dicts: slug, title, link, content_type.
        """
        known = self._build_known_paths()
        issues: list[dict[str, Any]] = []

        if content_types is None:
            content_types = list(self.scanner.CONTENT_TYPES.keys())

        for ct in content_types:
            for item in self.scanner.scan_type(ct, include_drafts=True):
                for link in item.extract_internal_links():
                    if self._is_link_valid(link, known):
                        continue
                    issues.append(
                        {
                            "slug": item.slug,
                            "title": item.title,
                            "link": link,
                            "content_type": ct,
                        }
                    )

        return issues

    def _is_link_valid(self, link: str, known_paths: set[str]) -> bool:
        """Check whether an internal link is valid."""
        if link.startswith("#"):
            return True
        if link.startswith(("http://", "https://")):
            return True
        if any(link.startswith(p) for p in self.STATIC_PREFIXES):
            return True

        normalized = link.rstrip("/")
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        normalized += "/"

        return normalized in known_paths

    def check_descriptions(
        self,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find posts missing description field.

        Returns list of dicts: slug, title, content_type.
        """
        if content_types is None:
            content_types = ["post"]

        issues: list[dict[str, Any]] = []
        for ct in content_types:
            for item in self.scanner.scan_type(ct):
                desc = item.front_matter.get("description", "")
                if not desc or (isinstance(desc, str) and not desc.strip()):
                    issues.append(
                        {
                            "slug": item.slug,
                            "title": item.title,
                            "content_type": ct,
                        }
                    )
        return issues

    def check_images(
        self,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find posts missing featured_image.

        Returns list of dicts: slug, title, content_type.
        """
        if content_types is None:
            content_types = ["post"]

        issues: list[dict[str, Any]] = []
        for ct in content_types:
            for item in self.scanner.scan_type(ct):
                if not item.front_matter.get("featured_image"):
                    issues.append(
                        {
                            "slug": item.slug,
                            "title": item.title,
                            "content_type": ct,
                        }
                    )
        return issues

    def check_drafts(self) -> list[dict[str, Any]]:
        """List all drafts with age.

        Returns list of dicts: slug, title, date, days_old, content_type.
        Sorted by days_old descending (oldest first).
        """
        results: list[dict[str, Any]] = []
        now = datetime.now()

        for ct in self.scanner.CONTENT_TYPES:
            for item in self.scanner.scan_type(ct, include_drafts=True):
                if not item.is_draft:
                    continue

                date_val = item.front_matter.get("date")
                days_old = 0

                if date_val is not None:
                    dt = self._parse_date(date_val)
                    if dt is not None:
                        days_old = (now - dt).days

                results.append(
                    {
                        "slug": item.slug,
                        "title": item.title,
                        "date": item.date,
                        "days_old": days_old,
                        "content_type": ct,
                    }
                )

        return sorted(results, key=lambda x: x.get("days_old", 0), reverse=True)

    @staticmethod
    def _parse_date(date_value: Any) -> datetime | None:
        """Parse a front matter date value into a naive datetime."""
        dt: datetime | None = None
        if isinstance(date_value, datetime):
            dt = date_value
        elif isinstance(date_value, date_type):
            dt = datetime.combine(date_value, datetime.min.time())
        elif isinstance(date_value, str):
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt = datetime.strptime(date_value, fmt)
                    break
                except ValueError:
                    continue
        # Strip timezone info for safe comparison with datetime.now()
        if dt is not None and dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    def check_stale(self) -> list[dict[str, Any]]:
        """Find projects where content description diverged from DB.

        Returns list of dicts: slug, title, content_desc, db_desc.
        """
        paths = get_paths()
        db_path = paths.projects_db

        if not db_path.exists():
            return []

        try:
            db_data = json.loads(db_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        issues: list[dict[str, Any]] = []
        projects = self.scanner.scan_type("projects", include_drafts=True)

        for item in projects:
            slug = item.slug
            entry = db_data.get(slug, {})
            if isinstance(entry, str) or not entry:
                continue

            db_desc = str(entry.get("description", "")).strip()
            content_desc = str(item.front_matter.get("description", "")).strip()

            if db_desc and content_desc and db_desc != content_desc:
                issues.append(
                    {
                        "slug": slug,
                        "title": item.title,
                        "content_desc": content_desc,
                        "db_desc": db_desc,
                    }
                )

        return issues
