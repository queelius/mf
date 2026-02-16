"""
Pluggable audit checks for content validation.

Provides a base class for audit checks and implementations for common checks:
- required_fields: Missing title/date
- date_format: Invalid date format
- orphaned_content: No tags or categories
- stale_drafts: Draft older than 90 days
- related_content: Invalid related_posts/projects refs
- internal_links: Broken markdown links in body
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mf.content.scanner import ContentItem


@dataclass
class CheckContext:
    """Context passed to audit checks.

    Provides access to site-wide data needed for validation.
    """

    site_root: Path
    all_project_slugs: set[str]
    hidden_project_slugs: set[str]
    all_paper_slugs: set[str]
    all_post_slugs: set[str]
    all_content_paths: set[str]  # Hugo paths like /post/slug/


@dataclass
class CheckIssue:
    """A single issue found by an audit check."""

    check_name: str
    message: str
    severity: str  # "error", "warning", "info"
    field: str | None = None  # Optional field name
    extra: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        result: dict[str, Any] = {
            "check": self.check_name,
            "message": self.message,
            "severity": self.severity,
        }
        if self.field:
            result["field"] = self.field
        if self.extra:
            result["extra"] = self.extra
        return result


class AuditCheck(ABC):
    """Base class for pluggable audit checks."""

    # Check metadata
    name: str = "base"
    description: str = "Base audit check"
    default_severity: str = "warning"

    @abstractmethod
    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        """Run the check on a content item.

        Args:
            item: Content item to check
            ctx: Check context with site-wide data

        Returns:
            List of issues found (empty if none)
        """
        pass


class RequiredFieldsCheck(AuditCheck):
    """Check for missing required fields (title, date)."""

    name = "required_fields"
    description = "Check for missing title or date fields"
    default_severity = "error"

    # Required fields by content type
    REQUIRED_FIELDS = {
        "default": ["title", "date"],
        "projects": ["title"],  # Projects may not need date
    }

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        required = self.REQUIRED_FIELDS.get(
            item.content_type, self.REQUIRED_FIELDS["default"]
        )

        for field_name in required:
            if field_name not in item.front_matter or not item.front_matter[field_name]:
                issues.append(
                    CheckIssue(
                        check_name=self.name,
                        message=f"Missing required field: {field_name}",
                        severity=self.default_severity,
                        field=field_name,
                    )
                )

        return issues


class DateFormatCheck(AuditCheck):
    """Check for invalid date format."""

    name = "date_format"
    description = "Check for invalid date format"
    default_severity = "warning"

    # Acceptable date formats
    DATE_FORMATS = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        date_value = item.front_matter.get("date")

        if date_value is None:
            return issues  # RequiredFieldsCheck handles missing date

        # Handle datetime objects (already parsed by YAML)
        if isinstance(date_value, datetime):
            return issues

        # Handle date objects
        from datetime import date as date_type

        if isinstance(date_value, date_type):
            return issues

        # Try to parse string date
        if isinstance(date_value, str):
            for fmt in self.DATE_FORMATS:
                try:
                    datetime.strptime(date_value, fmt)
                    return issues  # Valid format found
                except ValueError:
                    continue

            issues.append(
                CheckIssue(
                    check_name=self.name,
                    message=f"Invalid date format: '{date_value}' (expected YYYY-MM-DD)",
                    severity=self.default_severity,
                    field="date",
                )
            )

        return issues


class OrphanedContentCheck(AuditCheck):
    """Check for content with no tags or categories."""

    name = "orphaned_content"
    description = "Check for content without tags or categories"
    default_severity = "info"

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues: list[CheckIssue] = []

        # Skip project pages (they don't need tags/categories)
        if item.content_type == "projects":
            return issues

        has_tags = bool(item.tags)
        has_categories = bool(item.categories)

        if not has_tags and not has_categories:
            issues.append(
                CheckIssue(
                    check_name=self.name,
                    message="Content has no tags or categories",
                    severity=self.default_severity,
                )
            )

        return issues


class StaleDraftsCheck(AuditCheck):
    """Check for drafts older than a threshold."""

    name = "stale_drafts"
    description = "Check for drafts older than 90 days"
    default_severity = "info"

    # Default threshold in days
    STALE_THRESHOLD_DAYS = 90

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues: list[CheckIssue] = []

        # Only check drafts
        if not item.is_draft:
            return issues

        date_value = item.front_matter.get("date")
        if date_value is None:
            return issues

        # Parse the date
        try:
            if isinstance(date_value, datetime):
                item_date = date_value
            elif isinstance(date_value, str):
                # Try common formats
                for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                    try:
                        item_date = datetime.strptime(date_value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return issues  # Can't parse date
            else:
                from datetime import date as date_type

                if isinstance(date_value, date_type):
                    item_date = datetime.combine(date_value, datetime.min.time())
                else:
                    return issues
        except (ValueError, TypeError):
            return issues

        # Check if stale
        threshold = datetime.now() - timedelta(days=self.STALE_THRESHOLD_DAYS)
        if item_date < threshold:
            days_old = (datetime.now() - item_date).days
            issues.append(
                CheckIssue(
                    check_name=self.name,
                    message=f"Draft is {days_old} days old (threshold: {self.STALE_THRESHOLD_DAYS})",
                    severity=self.default_severity,
                    extra={"days_old": days_old},
                )
            )

        return issues


class RelatedContentCheck(AuditCheck):
    """Check for invalid related_posts/related_projects references."""

    name = "related_content"
    description = "Check for invalid related_posts/projects references"
    default_severity = "error"

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues = []

        # Check related_posts
        for post_ref in item.related_posts:
            if not self._is_valid_post_ref(post_ref, ctx):
                issues.append(
                    CheckIssue(
                        check_name=self.name,
                        message=f"Invalid related_posts reference: '{post_ref}'",
                        severity=self.default_severity,
                        field="related_posts",
                        extra={"reference": post_ref},
                    )
                )

        # Check related_projects
        for proj_ref in item.related_projects:
            if not self._is_valid_project_ref(proj_ref, ctx):
                issues.append(
                    CheckIssue(
                        check_name=self.name,
                        message=f"Invalid related_projects reference: '{proj_ref}'",
                        severity=self.default_severity,
                        field="related_projects",
                        extra={"reference": proj_ref},
                    )
                )

        return issues

    def _is_valid_post_ref(self, ref: str, ctx: CheckContext) -> bool:
        """Check if a post reference is valid."""
        # Normalize path
        path = ref.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        path = path + "/"

        return path in ctx.all_content_paths

    def _is_valid_project_ref(self, ref: str, ctx: CheckContext) -> bool:
        """Check if a project reference is valid."""
        # Handle both path and slug formats
        if "/" in ref:
            # Extract slug from path like /projects/my-project/
            match = re.match(r"^/?projects?/([^/]+)/?$", ref)
            if match:
                slug = match.group(1)
                return slug in ctx.all_project_slugs
            return False
        else:
            # Plain slug
            return ref in ctx.all_project_slugs


class InternalLinksCheck(AuditCheck):
    """Check for broken internal markdown links in body."""

    name = "internal_links"
    description = "Check for broken internal markdown links"
    default_severity = "warning"

    def check(self, item: ContentItem, ctx: CheckContext) -> list[CheckIssue]:
        issues = []

        # Extract internal links from body
        internal_links = item.extract_internal_links()

        for link in internal_links:
            if not self._is_valid_link(link, ctx):
                issues.append(
                    CheckIssue(
                        check_name=self.name,
                        message=f"Broken internal link: '{link}'",
                        severity=self.default_severity,
                        extra={"link": link},
                    )
                )

        return issues

    def _is_valid_link(self, link: str, ctx: CheckContext) -> bool:
        """Check if an internal link is valid."""
        # Ignore anchor-only links
        if link.startswith("#"):
            return True

        # Ignore external-looking links
        if link.startswith("http://") or link.startswith("https://"):
            return True

        # Normalize path
        path = link.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        path = path + "/"

        # Check against known content paths
        if path in ctx.all_content_paths:
            return True

        # Check if it's a static file (we can't easily validate these)
        # Allow links to common static paths
        static_prefixes = ["/images/", "/latex/", "/css/", "/js/", "/files/"]
        return any(link.startswith(prefix) for prefix in static_prefixes)


# Registry of all available checks
AVAILABLE_CHECKS: dict[str, type[AuditCheck]] = {
    "required_fields": RequiredFieldsCheck,
    "date_format": DateFormatCheck,
    "orphaned_content": OrphanedContentCheck,
    "stale_drafts": StaleDraftsCheck,
    "related_content": RelatedContentCheck,
    "internal_links": InternalLinksCheck,
}


def get_check(name: str) -> AuditCheck | None:
    """Get an audit check instance by name."""
    check_class = AVAILABLE_CHECKS.get(name)
    if check_class:
        return check_class()
    return None


def get_all_checks() -> list[AuditCheck]:
    """Get instances of all available checks."""
    return [cls() for cls in AVAILABLE_CHECKS.values()]


def list_checks() -> list[dict[str, str]]:
    """List all available checks with metadata."""
    result = []
    for name, cls in AVAILABLE_CHECKS.items():
        result.append(
            {
                "name": name,
                "description": cls.description,
                "severity": cls.default_severity,
            }
        )
    return result
