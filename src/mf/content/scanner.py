"""
Hugo content scanner.

Scans Hugo content directories and parses front matter and content.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from mf.core.config import get_paths

console = Console()


@dataclass
class ContentItem:
    """A single piece of Hugo content."""

    path: Path
    slug: str
    content_type: str  # post, paper, project, writing, etc.
    front_matter: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def title(self) -> str:
        return str(self.front_matter.get("title", self.slug))

    @property
    def date(self) -> str | None:
        val = self.front_matter.get("date")
        return str(val) if val is not None else None

    @property
    def tags(self) -> list[str]:
        return list(self.front_matter.get("tags", []))

    @property
    def categories(self) -> list[str]:
        cats = self.front_matter.get("categories", [])
        if isinstance(cats, str):
            return [cats]
        return list(cats)

    @property
    def projects(self) -> list[str]:
        """Get linked_project taxonomy terms (for linking content to projects)."""
        projs = self.front_matter.get("linked_project", [])
        if isinstance(projs, str):
            return [projs]
        return list(projs)

    @property
    def related_posts(self) -> list[str]:
        return list(self.front_matter.get("related_posts", []))

    @property
    def related_projects(self) -> list[str]:
        return list(self.front_matter.get("related_projects", []))

    @property
    def is_draft(self) -> bool:
        return bool(self.front_matter.get("draft", False))

    @property
    def hugo_path(self) -> str:
        """Get the Hugo URL path for this content."""
        # e.g., /post/2024-01-15-my-post/ or /papers/my-paper/
        return f"/{self.content_type}/{self.slug}/"

    def mentions_text(self, text: str, case_sensitive: bool = False) -> bool:
        """Check if text appears in title or body."""
        search_text = text if case_sensitive else text.lower()
        title = self.title if case_sensitive else self.title.lower()
        body = self.body if case_sensitive else self.body.lower()
        return search_text in title or search_text in body

    def contains_url(self, url_pattern: str) -> bool:
        """Check if a URL pattern appears in the body."""
        return url_pattern in self.body

    def extract_github_urls(self) -> list[str]:
        """Extract GitHub URLs from body."""
        pattern = r'https?://github\.com/[\w-]+/[\w.-]+'
        return list(set(re.findall(pattern, self.body)))

    def extract_internal_links(self) -> list[str]:
        """Extract internal Hugo links from body."""
        # Match markdown links like [text](/path/) or (/path/)
        pattern = r'\]\((/[^)]+)\)'
        return list(set(re.findall(pattern, self.body)))


class ContentScanner:
    """Scans Hugo content directories."""

    # Content directories to scan (relative to Hugo root)
    CONTENT_TYPES = {
        "post": "content/post",
        "papers": "content/papers",
        "projects": "content/projects",
        "writing": "content/writing",
        "publications": "content/publications",
        "research": "content/research",
        "series": "content/series",
    }

    def __init__(self, site_root: Path | None = None):
        """Initialize scanner.

        Args:
            site_root: Hugo site root directory (auto-detected if not provided)
        """
        if site_root is None:
            site_root = get_paths().root
        self.site_root = Path(site_root)
        self._cache: dict[str, ContentItem] = {}

    def scan_all(self, include_drafts: bool = False) -> list[ContentItem]:
        """Scan all content types.

        Args:
            include_drafts: Include draft content

        Returns:
            List of ContentItem objects
        """
        items = []
        for content_type, _rel_path in self.CONTENT_TYPES.items():
            items.extend(self.scan_type(content_type, include_drafts=include_drafts))
        return items

    def scan_type(
        self, content_type: str, include_drafts: bool = False
    ) -> list[ContentItem]:
        """Scan a specific content type.

        Args:
            content_type: Type like 'post', 'papers', 'projects'
            include_drafts: Include draft content

        Returns:
            List of ContentItem objects
        """
        if content_type not in self.CONTENT_TYPES:
            console.print(f"[yellow]Unknown content type: {content_type}[/yellow]")
            return []

        content_dir = self.site_root / self.CONTENT_TYPES[content_type]
        if not content_dir.exists():
            return []

        items = []
        for item in self._scan_directory(content_dir, content_type):
            if include_drafts or not item.is_draft:
                items.append(item)
                # Cache by path for quick lookup
                self._cache[str(item.path)] = item

        return items

    def _scan_directory(
        self, directory: Path, content_type: str
    ) -> Iterator[ContentItem]:
        """Scan a directory for content files.

        Handles both:
        - Leaf bundles: slug/index.md
        - Branch bundles: slug/_index.md
        - Single files: slug.md
        """
        for path in directory.rglob("*.md"):
            # Skip directories (rare edge case: directory named with .md extension)
            if path.is_dir():
                continue

            # Skip symlinks to prevent traversal outside content directory
            if path.is_symlink():
                continue

            # Skip non-content files
            if path.name.startswith("."):
                continue

            # Determine slug
            slug = path.parent.name if path.name in ("index.md", "_index.md") else path.stem

            # Skip the section _index.md files
            if path.name == "_index.md" and path.parent == directory:
                continue

            try:
                item = self._parse_file(path, slug, content_type)
                if item:
                    yield item
            except Exception as e:
                console.print(f"[yellow]Error parsing {path}: {e}[/yellow]")

    def _parse_file(
        self, path: Path, slug: str, content_type: str
    ) -> ContentItem | None:
        """Parse a single content file.

        Args:
            path: Path to the markdown file
            slug: Content slug
            content_type: Type of content

        Returns:
            ContentItem or None if parsing fails
        """
        content = path.read_text(encoding="utf-8")

        # Split front matter and body
        front_matter, body = self._split_content(content, path=path)

        if front_matter is None:
            return None

        return ContentItem(
            path=path,
            slug=slug,
            content_type=content_type,
            front_matter=front_matter,
            body=body,
        )

    def _split_content(
        self, content: str, path: Path | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """Split content into front matter and body.

        Args:
            content: Raw file content
            path: Optional file path for better error messages

        Returns:
            Tuple of (front_matter dict, body string)
        """
        if not content.startswith("---"):
            return None, content

        # Find the closing ---
        try:
            # Split on first two occurrences of ---
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None, content

            fm_text = parts[1].strip()
            body = parts[2].strip()

            # Parse YAML front matter
            loaded = yaml.safe_load(fm_text)
            front_matter: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
            return front_matter, body

        except yaml.YAMLError as e:
            location = f" in {path}" if path else ""
            console.print(f"[yellow]YAML error{location}: {e}[/yellow]")
            return None, content

    def get_by_path(self, path: str | Path) -> ContentItem | None:
        """Get a content item by its file path."""
        path_str = str(path)
        if path_str in self._cache:
            return self._cache[path_str]

        # Try to parse it
        path = Path(path)
        if not path.exists():
            return None

        # Determine content type from path
        for content_type, rel_path in self.CONTENT_TYPES.items():
            content_dir = self.site_root / rel_path
            if path.is_relative_to(content_dir):
                slug = path.parent.name if path.name in ("index.md", "_index.md") else path.stem
                item = self._parse_file(path, slug, content_type)
                if item:
                    self._cache[path_str] = item
                return item

        return None

    def search(
        self,
        query: str | None = None,
        content_types: list[str] | None = None,
        tags: list[str] | None = None,
        projects: list[str] | None = None,
        include_drafts: bool = False,
    ) -> list[ContentItem]:
        """Search content with filters.

        Args:
            query: Text search in title/body
            content_types: Filter by content types
            tags: Filter by tags (any match)
            projects: Filter by project taxonomy
            include_drafts: Include draft content

        Returns:
            List of matching ContentItem objects
        """
        if content_types:
            items = []
            for ct in content_types:
                items.extend(self.scan_type(ct, include_drafts=include_drafts))
        else:
            items = self.scan_all(include_drafts=include_drafts)

        results = []
        for item in items:
            # Text search
            if query:
                query_lower = query.lower()
                if not item.mentions_text(query_lower):
                    continue

            # Tags filter
            if tags:
                item_tags = item.tags
                if not any(tag in item_tags for tag in tags):
                    continue

            # Projects filter
            if projects:
                item_projects = item.projects
                if not any(proj in item_projects for proj in projects):
                    continue

            results.append(item)

        return results

    def find_content_about_project(self, project_slug: str) -> list[ContentItem]:
        """Find content that references a project.

        Checks:
        1. projects taxonomy
        2. related_projects field
        3. GitHub URL in body
        4. Project slug mentioned in text

        Args:
            project_slug: The project slug to search for

        Returns:
            List of ContentItem objects that reference the project
        """
        items = self.scan_all(include_drafts=False)
        results = []

        # Build GitHub URL pattern
        github_url = f"github.com/queelius/{project_slug}"

        for item in items:
            # Skip the project itself
            if item.content_type == "projects" and item.slug == project_slug:
                continue

            # Check projects taxonomy
            if project_slug in item.projects:
                results.append(item)
                continue

            # Check related_projects
            project_path = f"/projects/{project_slug}/"
            if project_path in item.related_projects:
                results.append(item)
                continue

            # Check for GitHub URL
            if item.contains_url(github_url):
                results.append(item)
                continue

            # Check for slug mention (word boundary)
            # Be careful with short slugs - require word boundaries
            if len(project_slug) >= 3 and item.mentions_text(project_slug):
                results.append(item)
                continue

        return results

    def stats(self) -> dict[str, Any]:
        """Get content statistics."""
        items = self.scan_all(include_drafts=True)

        by_type: dict[str, int] = {}
        drafts = 0
        with_projects = 0

        for item in items:
            by_type[item.content_type] = by_type.get(item.content_type, 0) + 1
            if item.is_draft:
                drafts += 1
            if item.projects:
                with_projects += 1

        return {
            "total": len(items),
            "by_type": by_type,
            "drafts": drafts,
            "published": len(items) - drafts,
            "with_project_taxonomy": with_projects,
        }
