"""
Database integrity checker.

Validates cross-database consistency and detects orphaned entries,
stale cache entries, and invalid references.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console

from mf.content.scanner import ContentScanner
from mf.core.config import get_paths
from mf.core.database import (
    PaperDatabase,
    ProjectsCache,
    ProjectsDatabase,
    SeriesDatabase,
)

console = Console()


class IssueType(Enum):
    """Types of integrity issues."""

    ORPHANED_DB_ENTRY = "orphaned_db_entry"  # DB entry without content file
    STALE_CACHE = "stale_cache"  # Cache entry without DB entry
    INVALID_REFERENCE = "invalid_reference"  # Reference to non-existent entry
    MISSING_SOURCE = "missing_source"  # Paper source file doesn't exist
    CONTENT_WITHOUT_DB = "content_without_db"  # Content file not in any DB
    SYNC_STATE_ORPHAN = "sync_state_orphan"  # Series sync state for non-existent post
    MISSING_STATIC_ASSET = "missing_static_asset"  # Static asset (pdf/html/bib) doesn't exist


class IssueSeverity(Enum):
    """Severity levels for integrity issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class IntegrityIssue:
    """A single integrity issue."""

    database: str  # Which database has the issue
    entry_id: str  # The affected entry identifier
    issue_type: IssueType
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR
    fixable: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        result: dict[str, Any] = {
            "database": self.database,
            "entry_id": self.entry_id,
            "issue_type": self.issue_type.value,
            "message": self.message,
            "severity": self.severity.value,
            "fixable": self.fixable,
        }
        if self.extra:
            result["extra"] = self.extra
        return result


@dataclass
class IntegrityResult:
    """Result of an integrity check."""

    issues: list[IntegrityIssue] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)  # DB name -> count checked

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "issues": [i.to_dict() for i in self.issues],
            "checked": self.checked,
            "by_database": self._group_by_database(),
            "by_severity": self._group_by_severity(),
            "fixable_count": len([i for i in self.issues if i.fixable]),
        }

    def _group_by_database(self) -> dict[str, int]:
        """Group issues by database."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.database] = counts.get(issue.database, 0) + 1
        return counts

    def _group_by_severity(self) -> dict[str, int]:
        """Group issues by severity."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.severity.value] = counts.get(issue.severity.value, 0) + 1
        return counts

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def has_fixable(self) -> bool:
        """Check if there are any fixable issues."""
        return any(i.fixable for i in self.issues)

    def errors(self) -> list[IntegrityIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    def fixable_issues(self) -> list[IntegrityIssue]:
        """Get only fixable issues."""
        return [i for i in self.issues if i.fixable]


class IntegrityChecker:
    """Checks database integrity across all mf databases."""

    DATABASES = ["paper_db", "projects_db", "projects_cache", "series_db"]

    def __init__(self, site_root: Path | None = None):
        """Initialize checker.

        Args:
            site_root: Hugo site root directory (auto-detected if not provided)
        """
        if site_root is None:
            site_root = get_paths().root
        self.site_root = site_root
        self.paths = get_paths()

        self.paper_db = PaperDatabase()
        self.projects_db = ProjectsDatabase()
        self.projects_cache = ProjectsCache()
        self.series_db = SeriesDatabase()
        self.scanner = ContentScanner(site_root)

        self._loaded = False

    def _load_all(self) -> None:
        """Load all databases."""
        if self._loaded:
            return

        try:
            self.paper_db.load()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load paper_db: {e}[/yellow]")

        try:
            self.projects_db.load()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load projects_db: {e}[/yellow]")

        try:
            self.projects_cache.load()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load projects_cache: {e}[/yellow]")

        try:
            self.series_db.load()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load series_db: {e}[/yellow]")

        self._loaded = True

    def check_all(self) -> IntegrityResult:
        """Run all integrity checks.

        Returns:
            IntegrityResult with all issues found
        """
        self._load_all()
        result = IntegrityResult()

        # Check each database
        self._check_paper_db(result)
        self._check_projects_db(result)
        self._check_projects_cache(result)
        self._check_series_db(result)

        # Check static assets
        self._check_static_assets(result)

        return result

    def check_database(self, db_name: str) -> IntegrityResult:
        """Check a specific database.

        Args:
            db_name: Database name (paper_db, projects_db, projects_cache, series_db)

        Returns:
            IntegrityResult for that database
        """
        self._load_all()
        result = IntegrityResult()

        checkers = {
            "paper_db": self._check_paper_db,
            "projects_db": self._check_projects_db,
            "projects_cache": self._check_projects_cache,
            "series_db": self._check_series_db,
        }

        if db_name in checkers:
            checkers[db_name](result)
        else:
            console.print(f"[red]Unknown database: {db_name}[/red]")

        return result

    def _check_paper_db(self, result: IntegrityResult) -> None:
        """Check paper database integrity."""
        count = 0

        # Get existing paper content
        paper_content_slugs: set[str] = set()
        papers_dir = self.site_root / "content" / "papers"
        if papers_dir.exists():
            for item in self.scanner.scan_type("papers", include_drafts=True):
                paper_content_slugs.add(item.slug)

        for slug in self.paper_db:
            count += 1
            entry = self.paper_db.get(slug)
            if not entry:
                continue

            # Check if content file exists
            if slug not in paper_content_slugs:
                result.issues.append(
                    IntegrityIssue(
                        database="paper_db",
                        entry_id=slug,
                        issue_type=IssueType.ORPHANED_DB_ENTRY,
                        message=f"Paper '{slug}' in database but no content file exists",
                        severity=IssueSeverity.WARNING,
                        fixable=False,
                    )
                )

            # Check if source file exists (if tracked)
            if entry.source_path:
                source_path = Path(entry.source_path)
                if not source_path.is_absolute():
                    source_path = self.site_root / source_path
                if not source_path.exists():
                    result.issues.append(
                        IntegrityIssue(
                            database="paper_db",
                            entry_id=slug,
                            issue_type=IssueType.MISSING_SOURCE,
                            message=f"Source file not found: {entry.source_path}",
                            severity=IssueSeverity.WARNING,
                            fixable=False,
                            extra={"source_path": str(entry.source_path)},
                        )
                    )

        result.checked["paper_db"] = count

    def _check_projects_db(self, result: IntegrityResult) -> None:
        """Check projects database integrity."""
        count = 0

        # Get existing project content
        project_content_slugs: set[str] = set()
        projects_dir = self.site_root / "content" / "projects"
        if projects_dir.exists():
            for item in self.scanner.scan_type("projects", include_drafts=True):
                project_content_slugs.add(item.slug)

        for slug in self.projects_db:
            count += 1
            data = self.projects_db.get(slug)
            if not data:
                continue

            # Check if content file exists (warning - project might exist in cache only)
            if slug not in project_content_slugs and slug not in self.projects_cache:
                    result.issues.append(
                        IntegrityIssue(
                            database="projects_db",
                            entry_id=slug,
                            issue_type=IssueType.ORPHANED_DB_ENTRY,
                            message=f"Project '{slug}' in DB but no content file and not in cache",
                            severity=IssueSeverity.INFO,
                            fixable=False,
                        )
                    )

            # Check related_posts references
            for ref in data.get("related_posts", []):
                if not self._is_valid_content_ref(ref):
                    result.issues.append(
                        IntegrityIssue(
                            database="projects_db",
                            entry_id=slug,
                            issue_type=IssueType.INVALID_REFERENCE,
                            message=f"Invalid related_posts reference: {ref}",
                            severity=IssueSeverity.ERROR,
                            extra={"reference": ref},
                        )
                    )

            # Check related_papers references
            for ref in data.get("related_papers", []):
                if not self._is_valid_content_ref(ref):
                    result.issues.append(
                        IntegrityIssue(
                            database="projects_db",
                            entry_id=slug,
                            issue_type=IssueType.INVALID_REFERENCE,
                            message=f"Invalid related_papers reference: {ref}",
                            severity=IssueSeverity.ERROR,
                            extra={"reference": ref},
                        )
                    )

        result.checked["projects_db"] = count

    def _check_projects_cache(self, result: IntegrityResult) -> None:
        """Check projects cache integrity."""
        count = 0

        for slug in self.projects_cache:
            count += 1

            # Check if corresponding DB entry exists (cache is subordinate to DB)
            # This is informational - cache can have entries not in DB
            # We check for truly orphaned cache entries (no DB, no content)
            if slug not in self.projects_db:
                # Check if content exists
                content_exists = self._content_file_exists("projects", slug)
                if not content_exists:
                    result.issues.append(
                        IntegrityIssue(
                            database="projects_cache",
                            entry_id=slug,
                            issue_type=IssueType.STALE_CACHE,
                            message=f"Cache entry '{slug}' has no DB entry and no content file",
                            severity=IssueSeverity.INFO,
                            fixable=True,
                        )
                    )

        result.checked["projects_cache"] = count

    def _check_series_db(self, result: IntegrityResult) -> None:
        """Check series database integrity."""
        count = 0

        # Get existing series content
        series_content_slugs: set[str] = set()
        series_dir = self.site_root / "content" / "series"
        if series_dir.exists():
            for subdir in series_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("."):
                    series_content_slugs.add(subdir.name)

        for slug in self.series_db:
            count += 1
            entry = self.series_db.get(slug)
            if not entry:
                continue

            # Check if content directory exists
            if slug not in series_content_slugs:
                result.issues.append(
                    IntegrityIssue(
                        database="series_db",
                        entry_id=slug,
                        issue_type=IssueType.ORPHANED_DB_ENTRY,
                        message=f"Series '{slug}' in database but no content directory exists",
                        severity=IssueSeverity.WARNING,
                        fixable=False,
                    )
                )

            # Check sync state for orphaned entries
            sync_state = entry.sync_state
            for post_slug in sync_state:
                # Check if the post actually exists in content
                if not self._post_in_series_exists(slug, post_slug):
                    result.issues.append(
                        IntegrityIssue(
                            database="series_db",
                            entry_id=f"{slug}::{post_slug}",
                            issue_type=IssueType.SYNC_STATE_ORPHAN,
                            message=f"Sync state for '{post_slug}' but post doesn't exist in series '{slug}'",
                            severity=IssueSeverity.INFO,
                            fixable=True,
                            extra={"series": slug, "post": post_slug},
                        )
                    )

            # Check related_projects references
            for proj_slug in entry.related_projects:
                if proj_slug not in self.projects_db and proj_slug not in self.projects_cache:
                    result.issues.append(
                        IntegrityIssue(
                            database="series_db",
                            entry_id=slug,
                            issue_type=IssueType.INVALID_REFERENCE,
                            message=f"Invalid related_projects reference: {proj_slug}",
                            severity=IssueSeverity.WARNING,
                            extra={"reference": proj_slug},
                        )
                    )

        result.checked["series_db"] = count

    def _is_valid_content_ref(self, ref: str) -> bool:
        """Check if a content reference (path) is valid."""
        # Extract content type and slug from path like /post/slug/
        import re

        match = re.match(r"^/?(\w+)/([^/]+)/?$", ref)
        if not match:
            return False

        content_type, slug = match.groups()
        return self._content_file_exists(content_type, slug)

    def _content_file_exists(self, content_type: str, slug: str) -> bool:
        """Check if a content file exists for the given type and slug."""
        content_dir = self.site_root / "content" / content_type / slug
        if content_dir.exists():
            # Check for index.md or _index.md
            if (content_dir / "index.md").exists():
                return True
            if (content_dir / "_index.md").exists():
                return True
        # Also check for direct file
        direct_file = self.site_root / "content" / content_type / f"{slug}.md"
        return direct_file.exists()

    def _post_in_series_exists(self, series_slug: str, post_slug: str) -> bool:
        """Check if a post exists for a series sync state entry.

        Posts can be in multiple locations:
        1. content/series/{series}/{post}/index.md (nested in series)
        2. content/post/{post}/index.md (synced to main posts)
        3. _landing_page is special (maps to series _index.md)
        """
        # Special case: _landing_page refers to the series _index.md
        if post_slug == "_landing_page":
            series_dir = self.site_root / "content" / "series" / series_slug
            return (series_dir / "_index.md").exists()

        # Check in series directory first
        series_dir = self.site_root / "content" / "series" / series_slug
        if series_dir.exists():
            post_dir = series_dir / post_slug
            if post_dir.exists() and (post_dir / "index.md").exists():
                return True

        # Check in main content/post/ directory (where series sync puts posts)
        return self._content_file_exists("post", post_slug)

    def _check_static_assets(self, result: IntegrityResult) -> None:
        """Check that static assets referenced in paper_db exist.

        Validates that pdf_path, html_path, and cite_path fields point
        to files that actually exist in the static/ directory.
        """
        count = 0
        asset_fields = ["pdf_path", "html_path", "cite_path"]

        for slug in self.paper_db:
            count += 1
            entry = self.paper_db.get(slug)
            if not entry:
                continue

            for asset_field in asset_fields:
                path_raw = entry.data.get(asset_field)
                if not path_raw:
                    continue

                # Convert URL path to filesystem path
                # Path is like "/latex/paper/paper.pdf" -> "static/latex/paper/paper.pdf"
                path_str = str(path_raw)
                asset_path = self.site_root / "static" / path_str.lstrip("/")
                if not asset_path.exists():
                    result.issues.append(
                        IntegrityIssue(
                            database="paper_db",
                            entry_id=slug,
                            issue_type=IssueType.MISSING_STATIC_ASSET,
                            message=f"Static asset not found: {path_str}",
                            severity=IssueSeverity.WARNING,
                            fixable=False,
                            extra={"field": asset_field, "path": path_str},
                        )
                    )

        result.checked["static_assets"] = count

    def find_orphans(self) -> IntegrityResult:
        """Find all orphaned entries across databases.

        Returns:
            IntegrityResult with only orphan-type issues
        """
        result = self.check_all()
        orphan_types = {
            IssueType.ORPHANED_DB_ENTRY,
            IssueType.STALE_CACHE,
            IssueType.SYNC_STATE_ORPHAN,
        }
        result.issues = [i for i in result.issues if i.issue_type in orphan_types]
        return result

    def fix_issues(
        self,
        issues: list[IntegrityIssue],
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Fix fixable integrity issues.

        Args:
            issues: List of issues to fix
            dry_run: Preview fixes without making changes

        Returns:
            Tuple of (fixed_count, failed_count)
        """
        fixed = 0
        failed = 0

        for issue in issues:
            if not issue.fixable:
                continue

            try:
                if issue.issue_type == IssueType.STALE_CACHE:
                    if not dry_run and self.projects_cache.delete(issue.entry_id):
                            self.projects_cache.save()
                    fixed += 1
                    if dry_run:
                        console.print(f"[dim]Would remove cache entry: {issue.entry_id}[/dim]")
                    else:
                        console.print(f"[green]Removed cache entry: {issue.entry_id}[/green]")

                elif issue.issue_type == IssueType.SYNC_STATE_ORPHAN:
                    series_slug = issue.extra.get("series")
                    post_slug = issue.extra.get("post")
                    if series_slug and post_slug:
                        entry = self.series_db.get(series_slug)
                        if entry:
                            if not dry_run:
                                entry.clear_sync_state(post_slug)
                                self.series_db.save()
                            fixed += 1
                            if dry_run:
                                console.print(
                                    f"[dim]Would clear sync state: {series_slug}::{post_slug}[/dim]"
                                )
                            else:
                                console.print(
                                    f"[green]Cleared sync state: {series_slug}::{post_slug}[/green]"
                                )

            except Exception as e:
                failed += 1
                console.print(f"[red]Failed to fix {issue.entry_id}: {e}[/red]")

        return fixed, failed
