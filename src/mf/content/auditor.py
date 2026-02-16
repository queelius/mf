"""
Content auditor for validating linked_project references.

Validates that linked_project entries in Hugo content files
reference existing projects in the database or cache.

Extended with pluggable audit checks for comprehensive validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from mf.content.frontmatter import FrontMatterEditor
from mf.content.scanner import ContentItem, ContentScanner
from mf.core.config import get_paths
from mf.core.database import PaperDatabase, ProjectsCache, ProjectsDatabase

if TYPE_CHECKING:
    from mf.content.audit_checks import CheckContext

console = Console()


class IssueType(Enum):
    """Types of audit issues."""

    MISSING_PROJECT = "missing_project"  # Project doesn't exist
    HIDDEN_PROJECT = "hidden_project"  # Project exists but is hidden
    INVALID_FORMAT = "invalid_format"  # Path instead of slug


class IssueSeverity(Enum):
    """Severity levels for audit issues."""

    ERROR = "error"  # Should be fixed
    WARNING = "warning"  # May be intentional
    INFO = "info"  # Informational


@dataclass
class AuditIssue:
    """A single audit issue."""

    path: Path
    title: str
    project_slug: str
    issue_type: IssueType
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "path": str(self.path),
            "title": self.title,
            "project_slug": self.project_slug,
            "issue_type": self.issue_type.value,
            "message": self.message,
            "severity": self.severity.value,
        }


@dataclass
class AuditStats:
    """Statistics from an audit run."""

    content_audited: int = 0
    with_project_links: int = 0
    without_links: int = 0
    valid_links: int = 0
    broken_links: int = 0
    hidden_project_links: int = 0
    invalid_format_links: int = 0
    projects_total: int = 0
    projects_with_content: int = 0
    projects_without_content: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "content_audited": self.content_audited,
            "with_project_links": self.with_project_links,
            "without_links": self.without_links,
            "valid_links": self.valid_links,
            "broken_links": self.broken_links,
            "hidden_project_links": self.hidden_project_links,
            "invalid_format_links": self.invalid_format_links,
            "projects_total": self.projects_total,
            "projects_with_content": self.projects_with_content,
            "projects_without_content": self.projects_without_content,
        }


@dataclass
class AuditResult:
    """Result of an audit run."""

    issues: list[AuditIssue] = field(default_factory=list)
    stats: AuditStats = field(default_factory=AuditStats)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "stats": self.stats.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(
            issue.severity == IssueSeverity.ERROR for issue in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues."""
        return any(
            issue.severity == IssueSeverity.WARNING for issue in self.issues
        )

    def errors(self) -> list[AuditIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    def warnings(self) -> list[AuditIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]


class ContentAuditor:
    """Audits Hugo content for invalid linked_project references."""

    # Default content types to audit
    DEFAULT_CONTENT_TYPES = ("post", "papers", "writing")

    def __init__(self, site_root: Path | None = None):
        """Initialize auditor.

        Args:
            site_root: Hugo site root directory (auto-detected if not provided)
        """
        if site_root is None:
            site_root = get_paths().root
        self.site_root = site_root

        self.scanner = ContentScanner(site_root)
        self.projects_db = ProjectsDatabase()
        self.projects_cache = ProjectsCache()

        self._all_project_slugs: set[str] = set()
        self._hidden_slugs: set[str] = set()
        self._loaded = False

    def _load_projects(self) -> None:
        """Load project data from DB and cache."""
        if self._loaded:
            return

        self.projects_db.load()
        self.projects_cache.load()

        # Collect all known project slugs
        for slug in self.projects_db:
            self._all_project_slugs.add(slug)
            data = self.projects_db.get(slug)
            if data and data.get("hide", False):
                self._hidden_slugs.add(slug)

        for slug in self.projects_cache:
            self._all_project_slugs.add(slug)

        self._loaded = True

    def _is_valid_format(self, project_ref: str) -> bool:
        """Check if a project reference has valid format (slug, not path).

        Valid: 'my-project', 'project_name'
        Invalid: '/projects/my-project/', 'projects/my-project'
        """
        # Should not contain slashes, not start/end with special characters
        return (
            "/" not in project_ref
            and not project_ref.startswith(("/", "."))
            and not project_ref.endswith("/")
        )

    def _extract_slug_from_path(self, path_ref: str) -> str | None:
        """Try to extract a project slug from a path reference.

        Args:
            path_ref: Path-like reference (e.g., '/projects/my-project/')

        Returns:
            Extracted slug or None if can't be extracted
        """
        # Handle /projects/slug/ format
        import re
        match = re.match(r"^/?projects?/([^/]+)/?$", path_ref)
        if match:
            return match.group(1)
        return None

    def _validate_project_ref(
        self, item: ContentItem, project_ref: str
    ) -> AuditIssue | None:
        """Validate a single project reference.

        Args:
            item: Content item containing the reference
            project_ref: The linked_project value to validate

        Returns:
            AuditIssue if invalid, None if valid
        """
        # Check format first
        if not self._is_valid_format(project_ref):
            # Try to extract slug for helpful message
            extracted = self._extract_slug_from_path(project_ref)
            suggestion = f" (did you mean '{extracted}'?)" if extracted else ""

            return AuditIssue(
                path=item.path,
                title=item.title,
                project_slug=project_ref,
                issue_type=IssueType.INVALID_FORMAT,
                message=f"Invalid format: use slug not path{suggestion}",
                severity=IssueSeverity.WARNING,
            )

        # Check if project exists
        if project_ref not in self._all_project_slugs:
            return AuditIssue(
                path=item.path,
                title=item.title,
                project_slug=project_ref,
                issue_type=IssueType.MISSING_PROJECT,
                message=f"Project '{project_ref}' not found in database or cache",
                severity=IssueSeverity.ERROR,
            )

        # Check if project is hidden
        if project_ref in self._hidden_slugs:
            return AuditIssue(
                path=item.path,
                title=item.title,
                project_slug=project_ref,
                issue_type=IssueType.HIDDEN_PROJECT,
                message=f"Project '{project_ref}' is hidden but still linked",
                severity=IssueSeverity.WARNING,
            )

        return None

    def audit(
        self,
        content_types: tuple[str, ...] | list[str] | None = None,
        include_drafts: bool = False,
    ) -> AuditResult:
        """Run a full audit of linked_project references.

        Args:
            content_types: Content types to audit (default: post, papers, writing)
            include_drafts: Include draft content in audit

        Returns:
            AuditResult with issues and statistics
        """
        self._load_projects()

        if content_types is None:
            content_types = self.DEFAULT_CONTENT_TYPES

        result = AuditResult()
        result.stats.projects_total = len(self._all_project_slugs)

        # Track which projects have content linking to them
        projects_with_content: set[str] = set()

        # Scan all content
        for content_type in content_types:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)

            for item in items:
                result.stats.content_audited += 1
                linked_projects = item.projects

                if not linked_projects:
                    result.stats.without_links += 1
                    continue

                result.stats.with_project_links += 1

                for project_ref in linked_projects:
                    issue = self._validate_project_ref(item, project_ref)

                    if issue:
                        result.issues.append(issue)

                        if issue.issue_type == IssueType.MISSING_PROJECT:
                            result.stats.broken_links += 1
                        elif issue.issue_type == IssueType.HIDDEN_PROJECT:
                            result.stats.hidden_project_links += 1
                            # Still count as having content
                            projects_with_content.add(project_ref)
                        elif issue.issue_type == IssueType.INVALID_FORMAT:
                            result.stats.invalid_format_links += 1
                            # Try to match extracted slug
                            extracted = self._extract_slug_from_path(project_ref)
                            if extracted and extracted in self._all_project_slugs:
                                projects_with_content.add(extracted)
                    else:
                        result.stats.valid_links += 1
                        projects_with_content.add(project_ref)

        # Calculate project coverage
        result.stats.projects_with_content = len(projects_with_content)
        result.stats.projects_without_content = (
            result.stats.projects_total - result.stats.projects_with_content
        )

        return result

    def fix_issues(
        self,
        issues: list[AuditIssue],
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Fix audit issues by removing broken linked_project entries.

        Only fixes MISSING_PROJECT issues (removes the reference).
        Does not fix HIDDEN_PROJECT or INVALID_FORMAT (those may be intentional).

        Args:
            issues: List of AuditIssue to fix
            dry_run: If True, don't actually modify files

        Returns:
            Tuple of (fixed_count, failed_count)
        """
        fixed = 0
        failed = 0

        # Group issues by file path for efficient processing
        by_path: dict[Path, list[AuditIssue]] = {}
        for issue in issues:
            # Only auto-fix missing project issues
            if issue.issue_type != IssueType.MISSING_PROJECT:
                continue
            by_path.setdefault(issue.path, []).append(issue)

        for path, path_issues in by_path.items():
            editor = FrontMatterEditor(path)
            if not editor.load():
                failed += len(path_issues)
                continue

            any_changed = False
            for issue in path_issues:
                if editor.remove_from_list("linked_project", issue.project_slug):
                    any_changed = True

            if any_changed:
                if editor.save(dry_run=dry_run):
                    fixed += len(path_issues)
                    if not dry_run:
                        console.print(
                            f"[green]Fixed {len(path_issues)} issue(s) in {path.name}[/green]"
                        )
                    else:
                        console.print(
                            f"[dim]Would fix {len(path_issues)} issue(s) in {path.name}[/dim]"
                        )
                else:
                    failed += len(path_issues)
            else:
                # No changes needed (already fixed?)
                fixed += len(path_issues)

        return fixed, failed

    def get_projects_without_content(
        self,
        content_types: tuple[str, ...] | list[str] | None = None,
        include_drafts: bool = False,
        include_hidden: bool = False,
    ) -> list[str]:
        """Get list of projects that have no content linking to them.

        Args:
            content_types: Content types to check
            include_drafts: Include draft content
            include_hidden: Include hidden projects in result

        Returns:
            List of project slugs with no linked content
        """
        # Run audit to ensure data is loaded
        self.audit(content_types=content_types, include_drafts=include_drafts)

        # Get all project slugs
        all_slugs = self._all_project_slugs.copy()

        # Optionally exclude hidden
        if not include_hidden:
            all_slugs -= self._hidden_slugs

        # Find projects with content
        projects_with_content: set[str] = set()
        for content_type in content_types or self.DEFAULT_CONTENT_TYPES:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)
            for item in items:
                for project_ref in item.projects:
                    if self._is_valid_format(project_ref):
                        projects_with_content.add(project_ref)

        return sorted(all_slugs - projects_with_content)

    def _build_check_context(
        self,
        content_types: tuple[str, ...] | list[str] | None = None,
        include_drafts: bool = False,
    ) -> CheckContext:
        """Build context for pluggable audit checks.

        Args:
            content_types: Content types to scan
            include_drafts: Include drafts in context

        Returns:
            CheckContext with site-wide data
        """
        from mf.content.audit_checks import CheckContext

        self._load_projects()

        # Load paper database for related_papers validation
        paper_db = PaperDatabase()
        try:
            paper_db.load()
            all_paper_slugs = set(paper_db)
        except Exception:
            all_paper_slugs = set()

        # Collect all post slugs
        all_post_slugs: set[str] = set()
        all_content_paths: set[str] = set()

        # Scan all content to build path registry
        for ct in content_types or self.DEFAULT_CONTENT_TYPES:
            items = self.scanner.scan_type(ct, include_drafts=include_drafts)
            for item in items:
                if item.content_type == "post":
                    all_post_slugs.add(item.slug)
                all_content_paths.add(item.hugo_path)

        # Also scan papers and projects for reference validation
        for ct in ["papers", "projects"]:
            items = self.scanner.scan_type(ct, include_drafts=include_drafts)
            for item in items:
                all_content_paths.add(item.hugo_path)

        return CheckContext(
            site_root=self.site_root,
            all_project_slugs=self._all_project_slugs.copy(),
            hidden_project_slugs=self._hidden_slugs.copy(),
            all_paper_slugs=all_paper_slugs,
            all_post_slugs=all_post_slugs,
            all_content_paths=all_content_paths,
        )

    def run_checks(
        self,
        content_types: tuple[str, ...] | list[str] | None = None,
        include_drafts: bool = False,
        check_names: list[str] | None = None,
        min_severity: str | None = None,
    ) -> ExtendedAuditResult:
        """Run pluggable audit checks on content.

        Args:
            content_types: Content types to audit
            include_drafts: Include drafts in audit
            check_names: Specific checks to run (None = all)
            min_severity: Minimum severity to report ("error", "warning", "info")

        Returns:
            ExtendedAuditResult with all issues found
        """
        from mf.content.audit_checks import (
            get_all_checks,
            get_check,
        )

        if content_types is None:
            content_types = self.DEFAULT_CONTENT_TYPES

        # Get checks to run
        if check_names:
            checks = []
            for name in check_names:
                check = get_check(name)
                if check:
                    checks.append(check)
        else:
            checks = get_all_checks()

        # Build context
        ctx = self._build_check_context(content_types, include_drafts)

        # Severity ranking for filtering
        severity_order = {"error": 0, "warning": 1, "info": 2}
        min_sev_rank = severity_order.get(min_severity or "info", 2)

        # Run checks on all content
        result = ExtendedAuditResult()

        for content_type in content_types:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)

            for item in items:
                result.content_checked += 1
                item_issues: list[ExtendedIssue] = []

                for check in checks:
                    check_issues = check.check(item, ctx)
                    for ci in check_issues:
                        # Filter by severity
                        sev_rank = severity_order.get(ci.severity, 2)
                        if sev_rank <= min_sev_rank:
                            item_issues.append(
                                ExtendedIssue(
                                    path=item.path,
                                    title=item.title,
                                    content_type=item.content_type,
                                    check_name=ci.check_name,
                                    message=ci.message,
                                    severity=ci.severity,
                                    field_name=ci.field,
                                    extra=ci.extra,
                                )
                            )

                result.issues.extend(item_issues)
                if item_issues:
                    result.content_with_issues += 1

        return result


@dataclass
class ExtendedIssue:
    """An issue found by extended audit checks."""

    path: Path
    title: str
    content_type: str
    check_name: str
    message: str
    severity: str
    field_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        result: dict[str, Any] = {
            "path": str(self.path),
            "title": self.title,
            "content_type": self.content_type,
            "check": self.check_name,
            "message": self.message,
            "severity": self.severity,
        }
        if self.field_name:
            result["field"] = self.field_name
        if self.extra:
            result["extra"] = self.extra
        return result


@dataclass
class ExtendedAuditResult:
    """Result of extended audit run."""

    content_checked: int = 0
    content_with_issues: int = 0
    issues: list[ExtendedIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "content_checked": self.content_checked,
            "content_with_issues": self.content_with_issues,
            "issues": [i.to_dict() for i in self.issues],
            "by_check": self._group_by_check(),
            "by_severity": self._group_by_severity(),
        }

    def _group_by_check(self) -> dict[str, int]:
        """Group issues by check name."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.check_name] = counts.get(issue.check_name, 0) + 1
        return counts

    def _group_by_severity(self) -> dict[str, int]:
        """Group issues by severity."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def errors(self) -> list[ExtendedIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[ExtendedIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]

    def infos(self) -> list[ExtendedIssue]:
        """Get only info-level issues."""
        return [i for i in self.issues if i.severity == "info"]

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues."""
        return any(i.severity == "warning" for i in self.issues)
