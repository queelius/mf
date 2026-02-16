"""
Project matching algorithm.

Matches content items to projects based on:
- Exact slug matches
- Title matches
- GitHub URL matches
- Fuzzy matching
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console

from mf.content.scanner import ContentItem, ContentScanner
from mf.core.config import get_paths
from mf.core.database import ProjectsCache, ProjectsDatabase

console = Console()


class MatchType(Enum):
    """Type of match found."""

    GITHUB_URL = "github_url"  # Contains GitHub URL for project
    EXACT_SLUG = "exact_slug"  # Slug appears as word in content
    PROJECT_TITLE = "project_title"  # Project title appears in content
    FUZZY = "fuzzy"  # Fuzzy match on slug or title
    TAG_OVERLAP = "tag_overlap"  # Significant tag overlap
    INTERNAL_LINK = "internal_link"  # Links to /projects/slug/


@dataclass
class Match:
    """A potential match between content and a project."""

    content_item: ContentItem
    project_slug: str
    match_type: MatchType
    confidence: float  # 0.0 to 1.0
    evidence: str  # What triggered the match

    def __lt__(self, other: Match) -> bool:
        """Sort by confidence descending."""
        return self.confidence > other.confidence


class ProjectMatcher:
    """Matches content to projects."""

    # Confidence thresholds by match type
    CONFIDENCE = {
        MatchType.GITHUB_URL: 1.0,
        MatchType.INTERNAL_LINK: 0.95,
        MatchType.EXACT_SLUG: 0.85,
        MatchType.PROJECT_TITLE: 0.80,
        MatchType.FUZZY: 0.60,
        MatchType.TAG_OVERLAP: 0.50,
    }

    # Minimum slug length for exact matching (avoid false positives)
    MIN_SLUG_LENGTH = 3

    def __init__(self, site_root: Path | None = None):
        """Initialize matcher.

        Args:
            site_root: Hugo site root directory
        """
        if site_root is None:
            site_root = get_paths().root
        self.site_root = site_root

        self.scanner = ContentScanner(site_root)
        self.projects_db = ProjectsDatabase()
        self.projects_cache = ProjectsCache()

        self._projects: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load_projects(self) -> None:
        """Load project data from DB and cache."""
        if self._loaded:
            return

        self.projects_db.load()
        self.projects_cache.load()

        # Collect hidden projects first
        hidden_slugs = set()
        for slug in self.projects_db:
            overrides = self.projects_db.get(slug) or {}
            if overrides.get("hide", False):
                hidden_slugs.add(slug)

        # Build project lookup with merged data
        for slug in self.projects_db:
            if slug in hidden_slugs:
                continue

            overrides = self.projects_db.get(slug) or {}
            cached = self.projects_cache.get(slug) or {}

            self._projects[slug] = {
                "slug": slug,
                "title": overrides.get("title") or cached.get("name") or slug,
                "tags": overrides.get("tags", []) + cached.get("topics", []),
                "github_url": f"github.com/queelius/{slug}",
            }

        # Also add projects from cache that aren't in DB and aren't hidden
        for slug in self.projects_cache:
            if slug not in self._projects and slug not in hidden_slugs:
                cached = self.projects_cache.get(slug) or {}
                self._projects[slug] = {
                    "slug": slug,
                    "title": cached.get("name") or slug,
                    "tags": cached.get("topics", []),
                    "github_url": f"github.com/queelius/{slug}",
                }

        self._loaded = True

    def get_project_slugs(self) -> list[str]:
        """Get all project slugs."""
        self._load_projects()
        return list(self._projects.keys())

    def get_project(self, slug: str) -> dict[str, Any] | None:
        """Get project data by slug."""
        self._load_projects()
        return self._projects.get(slug)

    def match_content(
        self,
        item: ContentItem,
        threshold: float = 0.5,
    ) -> list[Match]:
        """Find all project matches for a content item.

        Args:
            item: Content item to match
            threshold: Minimum confidence threshold

        Returns:
            List of Match objects sorted by confidence
        """
        self._load_projects()
        matches = []

        for slug, project in self._projects.items():
            match = self._check_match(item, slug, project)
            if match and match.confidence >= threshold:
                matches.append(match)

        # Sort by confidence and dedupe
        matches.sort()
        return matches

    def _check_match(
        self, item: ContentItem, slug: str, project: dict[str, Any]
    ) -> Match | None:
        """Check if content item matches a project.

        Returns the highest confidence match found, or None.
        """
        # Already has this project in taxonomy - skip
        if slug in item.projects:
            return None

        # Check GitHub URL (highest confidence)
        github_url = project["github_url"]
        if item.contains_url(github_url):
            return Match(
                content_item=item,
                project_slug=slug,
                match_type=MatchType.GITHUB_URL,
                confidence=self.CONFIDENCE[MatchType.GITHUB_URL],
                evidence=f"Contains URL: {github_url}",
            )

        # Check internal links to project page
        project_path = f"/projects/{slug}/"
        internal_links = item.extract_internal_links()
        if project_path in internal_links:
            return Match(
                content_item=item,
                project_slug=slug,
                match_type=MatchType.INTERNAL_LINK,
                confidence=self.CONFIDENCE[MatchType.INTERNAL_LINK],
                evidence=f"Links to: {project_path}",
            )

        # Check project title in content
        title = project["title"]
        if len(title) >= 4 and self._word_match(title, item.title + " " + item.body):
            return Match(
                content_item=item,
                project_slug=slug,
                match_type=MatchType.PROJECT_TITLE,
                confidence=self.CONFIDENCE[MatchType.PROJECT_TITLE],
                evidence=f"Title match: '{title}'",
            )

        # Check exact slug match (with word boundaries)
        if len(slug) >= self.MIN_SLUG_LENGTH and self._word_match(slug, item.title + " " + item.body):
                # Boost confidence if in title
                conf = self.CONFIDENCE[MatchType.EXACT_SLUG]
                if self._word_match(slug, item.title):
                    conf = min(conf + 0.1, 0.95)

                return Match(
                    content_item=item,
                    project_slug=slug,
                    match_type=MatchType.EXACT_SLUG,
                    confidence=conf,
                    evidence=f"Slug '{slug}' appears in content",
                )

        # Check tag overlap
        if project["tags"] and item.tags:
            overlap = set(project["tags"]) & set(item.tags)
            if len(overlap) >= 2:  # Require at least 2 shared tags
                conf = min(0.5 + (len(overlap) * 0.1), 0.75)
                return Match(
                    content_item=item,
                    project_slug=slug,
                    match_type=MatchType.TAG_OVERLAP,
                    confidence=conf,
                    evidence=f"Shared tags: {', '.join(overlap)}",
                )

        return None

    def _word_match(self, needle: str, haystack: str) -> bool:
        """Check if needle appears as a word in haystack.

        Uses word boundary matching to avoid false positives.
        """
        # Escape special regex characters in needle
        escaped = re.escape(needle)
        # Word boundary pattern (handles underscores and hyphens as word separators)
        pattern = rf"(?:^|[\s\-_/\"\'(])({escaped})(?:[\s\-_/\"\').,!?:]|$)"
        return bool(re.search(pattern, haystack, re.IGNORECASE))

    def find_matches_for_project(
        self,
        project_slug: str,
        content_types: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[Match]:
        """Find all content that might be about a project.

        Args:
            project_slug: Project to find matches for
            content_types: Content types to search (default: post, papers)
            threshold: Minimum confidence threshold

        Returns:
            List of Match objects
        """
        self._load_projects()

        if project_slug not in self._projects:
            console.print(f"[yellow]Project not found: {project_slug}[/yellow]")
            return []

        project = self._projects[project_slug]

        # Default to posts and papers
        if content_types is None:
            content_types = ["post", "papers"]

        matches = []
        for content_type in content_types:
            items = self.scanner.scan_type(content_type, include_drafts=False)
            for item in items:
                match = self._check_match(item, project_slug, project)
                if match and match.confidence >= threshold:
                    matches.append(match)

        matches.sort()
        return matches

    def find_all_matches(
        self,
        content_types: list[str] | None = None,
        threshold: float = 0.5,
    ) -> dict[str, list[Match]]:
        """Find all content-to-project matches.

        Args:
            content_types: Content types to search
            threshold: Minimum confidence threshold

        Returns:
            Dict mapping content paths to lists of matches
        """
        self._load_projects()

        if content_types is None:
            content_types = ["post", "papers", "writing"]

        result: dict[str, list[Match]] = {}

        for content_type in content_types:
            items = self.scanner.scan_type(content_type, include_drafts=False)
            for item in items:
                matches = self.match_content(item, threshold=threshold)
                if matches:
                    result[str(item.path)] = matches

        return result

    def suggest_matches(
        self,
        threshold: float = 0.7,
        content_types: list[str] | None = None,
    ) -> list[tuple[ContentItem, list[Match]]]:
        """Suggest project matches for content without project taxonomy.

        Only suggests for content that doesn't already have projects set.

        Args:
            threshold: Minimum confidence for suggestions
            content_types: Content types to check

        Returns:
            List of (content_item, matches) tuples
        """
        all_matches = self.find_all_matches(
            content_types=content_types,
            threshold=threshold,
        )

        suggestions = []
        for _path, matches in all_matches.items():
            item = matches[0].content_item
            # Only suggest if no projects currently set
            if not item.projects:
                suggestions.append((item, matches))

        return suggestions
