"""
Content analytics aggregator.

Provides statistics and insights about content, projects, and their relationships.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mf.content.scanner import ContentItem, ContentScanner
from mf.core.config import get_paths
from mf.core.database import PaperDatabase, ProjectsCache, ProjectsDatabase


@dataclass
class ProjectLinkStats:
    """Statistics about a project's linked content."""

    slug: str
    title: str
    linked_content_count: int
    linked_posts: list[str] = field(default_factory=list)
    linked_papers: list[str] = field(default_factory=list)
    linked_other: list[str] = field(default_factory=list)
    is_hidden: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "slug": self.slug,
            "title": self.title,
            "linked_content_count": self.linked_content_count,
            "linked_posts": self.linked_posts,
            "linked_papers": self.linked_papers,
            "linked_other": self.linked_other,
            "is_hidden": self.is_hidden,
        }


@dataclass
class ContentGap:
    """A project without linked content (content gap)."""

    slug: str
    title: str
    is_hidden: bool
    mentioned_in: list[str] = field(default_factory=list)  # Mentioned but not linked

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "slug": self.slug,
            "title": self.title,
            "is_hidden": self.is_hidden,
            "mentioned_in": self.mentioned_in,
        }


@dataclass
class TagStats:
    """Statistics about tag usage."""

    tag: str
    count: int
    content_types: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "tag": self.tag,
            "count": self.count,
            "content_types": self.content_types,
        }


@dataclass
class TimelineEntry:
    """A point in the content timeline."""

    month: str  # YYYY-MM format
    posts: int = 0
    papers: int = 0
    projects: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        return self.posts + self.papers + self.projects + self.other

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "month": self.month,
            "posts": self.posts,
            "papers": self.papers,
            "projects": self.projects,
            "other": self.other,
            "total": self.total,
        }


@dataclass
class CrossReferenceSuggestion:
    """A suggested cross-reference between content and project."""

    content_path: Path
    content_title: str
    content_type: str
    project_slug: str
    project_title: str
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "content_path": str(self.content_path),
            "content_title": self.content_title,
            "content_type": self.content_type,
            "project_slug": self.project_slug,
            "project_title": self.project_title,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class ContentAnalytics:
    """Analytics aggregator for content insights."""

    def __init__(self, site_root: Path | None = None):
        """Initialize analytics.

        Args:
            site_root: Hugo site root directory (auto-detected if not provided)
        """
        if site_root is None:
            site_root = get_paths().root
        self.site_root = site_root

        self.scanner = ContentScanner(site_root)
        self.projects_db = ProjectsDatabase()
        self.projects_cache = ProjectsCache()
        self.paper_db = PaperDatabase()

        self._loaded = False
        self._all_projects: dict[str, dict[str, Any]] = {}
        self._hidden_slugs: set[str] = set()

    def _load_data(self) -> None:
        """Load all necessary data."""
        if self._loaded:
            return

        # Load projects
        self.projects_db.load()
        self.projects_cache.load()

        # Merge DB and cache
        for slug in self.projects_db:
            data = self.projects_db.get(slug) or {}
            self._all_projects[slug] = {
                "title": data.get("title", slug),
                "hide": data.get("hide", False),
            }
            if data.get("hide"):
                self._hidden_slugs.add(slug)

        for slug in self.projects_cache:
            if slug not in self._all_projects:
                data = self.projects_cache.get(slug) or {}
                self._all_projects[slug] = {
                    "title": data.get("name", slug),
                    "hide": False,
                }

        # Load papers (may not exist)
        with contextlib.suppress(Exception):
            self.paper_db.load()

        self._loaded = True

    def get_project_link_stats(
        self,
        include_hidden: bool = False,
        include_drafts: bool = False,
    ) -> list[ProjectLinkStats]:
        """Get statistics about content linked to each project.

        Args:
            include_hidden: Include hidden projects
            include_drafts: Include draft content

        Returns:
            List of ProjectLinkStats sorted by linked content count (descending)
        """
        self._load_data()

        # Count content per project
        project_content: dict[str, ProjectLinkStats] = {}

        # Initialize all projects
        for slug, data in self._all_projects.items():
            if not include_hidden and slug in self._hidden_slugs:
                continue
            project_content[slug] = ProjectLinkStats(
                slug=slug,
                title=data.get("title", slug),
                linked_content_count=0,
                is_hidden=slug in self._hidden_slugs,
            )

        # Scan content
        for content_type in ["post", "papers", "writing", "publications"]:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)
            for item in items:
                for proj_slug in item.projects:
                    if proj_slug in project_content:
                        stats = project_content[proj_slug]
                        stats.linked_content_count += 1
                        if content_type == "post":
                            stats.linked_posts.append(item.hugo_path)
                        elif content_type == "papers":
                            stats.linked_papers.append(item.hugo_path)
                        else:
                            stats.linked_other.append(item.hugo_path)

        # Sort by count descending
        return sorted(
            project_content.values(),
            key=lambda x: x.linked_content_count,
            reverse=True,
        )

    def get_content_gaps(
        self,
        with_mentions: bool = False,
        include_hidden: bool = False,
        include_drafts: bool = False,
    ) -> list[ContentGap]:
        """Get projects that have no linked content.

        Args:
            with_mentions: Also check for mentions in content body
            include_hidden: Include hidden projects
            include_drafts: Include draft content in analysis

        Returns:
            List of ContentGap objects
        """
        self._load_data()

        # Get project link stats
        stats = self.get_project_link_stats(
            include_hidden=include_hidden,
            include_drafts=include_drafts,
        )

        # Filter to projects with no links
        gaps: list[ContentGap] = []

        for proj_stats in stats:
            if proj_stats.linked_content_count > 0:
                continue

            gap = ContentGap(
                slug=proj_stats.slug,
                title=proj_stats.title,
                is_hidden=proj_stats.is_hidden,
            )

            # Check for mentions if requested (populated in batch below)
            gaps.append(gap)

        # Batch-find mentions for all gaps in a single content scan
        if with_mentions and gaps:
            gap_slugs = [g.slug for g in gaps]
            all_mentions = self._find_all_project_mentions(
                gap_slugs, include_drafts=include_drafts
            )
            for gap in gaps:
                gap.mentioned_in = all_mentions.get(gap.slug, [])

        return gaps

    def _find_all_project_mentions(
        self,
        project_slugs: list[str],
        include_drafts: bool = False,
    ) -> dict[str, list[str]]:
        """Find content that mentions any of the given projects but doesn't link to them.

        Scans content once for all projects, avoiding O(N*M) repeated scans.

        Args:
            project_slugs: List of project slugs to search for.
            include_drafts: Include draft content.

        Returns:
            Dict mapping project slug to list of content paths that mention it.
        """
        mentions: dict[str, list[str]] = {slug: [] for slug in project_slugs}

        # Build search patterns for all projects
        set(project_slugs)
        patterns: dict[str, list[str]] = {}
        for slug in project_slugs:
            patterns[slug] = [
                slug,
                f"github.com/queelius/{slug}",
            ]

        for content_type in ["post", "papers", "writing"]:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)
            for item in items:
                for slug in project_slugs:
                    # Skip if already linked
                    if slug in item.projects:
                        continue
                    # Check for mentions
                    for pattern in patterns[slug]:
                        if item.mentions_text(pattern) or item.contains_url(pattern):
                            mentions[slug].append(item.hugo_path)
                            break

        return mentions

    def _find_project_mentions(
        self,
        project_slug: str,
        include_drafts: bool = False,
    ) -> list[str]:
        """Find content that mentions a project but doesn't link to it."""
        result = self._find_all_project_mentions(
            [project_slug], include_drafts=include_drafts
        )
        return result.get(project_slug, [])

    def get_tag_distribution(
        self,
        limit: int | None = None,
        include_drafts: bool = False,
    ) -> list[TagStats]:
        """Get tag usage distribution across content.

        Args:
            limit: Maximum number of tags to return (None = all)
            include_drafts: Include draft content

        Returns:
            List of TagStats sorted by count (descending)
        """
        self._load_data()

        tag_counts: dict[str, TagStats] = {}

        # Scan all content types
        for content_type in ["post", "papers", "writing", "projects"]:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)
            for item in items:
                for tag in item.tags:
                    if tag not in tag_counts:
                        tag_counts[tag] = TagStats(tag=tag, count=0)
                    tag_counts[tag].count += 1
                    tag_counts[tag].content_types[content_type] = (
                        tag_counts[tag].content_types.get(content_type, 0) + 1
                    )

        # Sort by count
        result = sorted(tag_counts.values(), key=lambda x: x.count, reverse=True)

        if limit:
            result = result[:limit]

        return result

    def get_activity_timeline(
        self,
        months: int | None = None,
        include_drafts: bool = False,
    ) -> list[TimelineEntry]:
        """Get content activity over time.

        Args:
            months: Number of months to include (None = all)
            include_drafts: Include draft content

        Returns:
            List of TimelineEntry sorted by month (ascending)
        """
        self._load_data()

        timeline: dict[str, TimelineEntry] = {}

        def get_month(date_value: Any) -> str | None:
            """Extract YYYY-MM from date value."""
            if date_value is None:
                return None

            if isinstance(date_value, datetime):
                return date_value.strftime("%Y-%m")

            from datetime import date as date_type

            if isinstance(date_value, date_type):
                return date_value.strftime("%Y-%m")

            if isinstance(date_value, str):
                # Try to parse YYYY-MM-DD
                match = re.match(r"(\d{4}-\d{2})", date_value)
                if match:
                    return match.group(1)

            return None

        # Scan all content
        for content_type in ["post", "papers", "projects", "writing"]:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)
            for item in items:
                month = get_month(item.date)
                if not month:
                    continue

                if month not in timeline:
                    timeline[month] = TimelineEntry(month=month)

                entry = timeline[month]
                if content_type == "post":
                    entry.posts += 1
                elif content_type == "papers":
                    entry.papers += 1
                elif content_type == "projects":
                    entry.projects += 1
                else:
                    entry.other += 1

        # Sort by month
        result = sorted(timeline.values(), key=lambda x: x.month)

        if months:
            result = result[-months:]

        return result

    def suggest_cross_references(
        self,
        confidence_threshold: float = 0.5,
        include_drafts: bool = False,
    ) -> list[CrossReferenceSuggestion]:
        """Suggest content that should be linked to projects.

        Args:
            confidence_threshold: Minimum confidence for suggestions
            include_drafts: Include draft content

        Returns:
            List of CrossReferenceSuggestion objects
        """
        self._load_data()

        suggestions: list[CrossReferenceSuggestion] = []

        # Scan content
        for content_type in ["post", "papers", "writing"]:
            items = self.scanner.scan_type(content_type, include_drafts=include_drafts)

            for item in items:
                # Check each project
                for slug, data in self._all_projects.items():
                    # Skip if already linked
                    if slug in item.projects:
                        continue

                    # Skip hidden projects
                    if slug in self._hidden_slugs:
                        continue

                    # Check for matches
                    confidence, reason = self._calculate_match_confidence(item, slug)

                    if confidence >= confidence_threshold:
                        suggestions.append(
                            CrossReferenceSuggestion(
                                content_path=item.path,
                                content_title=item.title,
                                content_type=item.content_type,
                                project_slug=slug,
                                project_title=data.get("title", slug),
                                confidence=confidence,
                                reason=reason,
                            )
                        )

        # Sort by confidence descending
        return sorted(suggestions, key=lambda x: x.confidence, reverse=True)

    def _calculate_match_confidence(
        self,
        item: ContentItem,
        project_slug: str,
    ) -> tuple[float, str]:
        """Calculate confidence that content should link to project.

        Returns:
            Tuple of (confidence, reason)
        """
        confidence = 0.0
        reasons: list[str] = []

        # Check for GitHub URL
        github_url = f"github.com/queelius/{project_slug}"
        if item.contains_url(github_url):
            confidence += 0.8
            reasons.append("Contains GitHub URL")

        # Check for slug mention in title
        if project_slug.lower() in item.title.lower():
            confidence += 0.6
            reasons.append("Project name in title")

        # Check for slug mention in body
        elif item.mentions_text(project_slug):
            confidence += 0.3
            reasons.append("Project name in body")

        # Cap at 1.0
        confidence = min(confidence, 1.0)
        reason = "; ".join(reasons) if reasons else "No match"

        return confidence, reason

    def get_summary(
        self,
        include_drafts: bool = False,
    ) -> dict[str, Any]:
        """Get a full analytics summary.

        Args:
            include_drafts: Include draft content

        Returns:
            Dictionary with all analytics data
        """
        self._load_data()

        project_stats = self.get_project_link_stats(include_drafts=include_drafts)
        gaps = self.get_content_gaps(include_drafts=include_drafts)
        tags = self.get_tag_distribution(limit=20, include_drafts=include_drafts)
        timeline = self.get_activity_timeline(months=12, include_drafts=include_drafts)

        # Content stats
        content_stats = self.scanner.stats()

        return {
            "content": content_stats,
            "projects": {
                "total": len(self._all_projects),
                "hidden": len(self._hidden_slugs),
                "with_content": len([s for s in project_stats if s.linked_content_count > 0]),
                "without_content": len(gaps),
            },
            "top_linked_projects": [
                s.to_dict() for s in project_stats[:10] if s.linked_content_count > 0
            ],
            "content_gaps": [g.to_dict() for g in gaps[:10]],
            "top_tags": [t.to_dict() for t in tags[:20]],
            "recent_activity": [t.to_dict() for t in timeline[-6:]],
        }
