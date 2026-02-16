"""
Hugo content generator for projects.

Generates content/projects/{slug}/index.md from GitHub data and manual overrides.

Supports two modes:
- Leaf bundles: Simple projects with single index.md
- Branch bundles: Rich projects with _index.md and sub-pages for docs, tutorials, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rich.console import Console

from mf.core.config import get_paths
from mf.core.database import ProjectsCache, ProjectsDatabase
from mf.projects.readme import rewrite_readme_urls

console = Console()


# Default section templates for rich projects
SECTION_TEMPLATES = {
    "docs": {
        "title": "Documentation",
        "description": "Project documentation and guides.",
        "weight": 10,
    },
    "tutorials": {
        "title": "Tutorials",
        "description": "Step-by-step tutorials and examples.",
        "weight": 20,
    },
    "examples": {
        "title": "Examples",
        "description": "Code examples and use cases.",
        "weight": 30,
    },
    "api": {
        "title": "API Reference",
        "description": "API documentation and reference.",
        "weight": 40,
    },
    "changelog": {
        "title": "Changelog",
        "description": "Version history and release notes.",
        "weight": 50,
    },
    "posts": {
        "title": "Posts",
        "description": "In-depth articles and discussions.",
        "weight": 25,
    },
}


def merge_project_data(
    slug: str,
    github_data: dict[str, Any],
    manual_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge GitHub data with manual overrides.

    Args:
        slug: Project slug
        github_data: Data from GitHub API cache
        manual_overrides: Manual overrides from projects_db.json

    Returns:
        Merged metadata dict
    """
    merged = {
        "github_url": github_data.get("html_url"),
        "github_data": github_data,
    }

    # Apply manual overrides (take precedence)
    override_keys = [
        "title", "abstract", "stars", "featured", "hide", "maturity",
        "screenshot", "demo_url", "documentation_url", "category",
        "tags", "authors", "readme_override", "packages", "papers",
        "related_posts", "related_projects", "primary_language",
        # Rich project settings
        "rich_project", "content_sections", "external_docs",
        # Hugo settings
        "aliases",
    ]

    for key in override_keys:
        if key in manual_overrides:
            merged[key] = manual_overrides[key]

    return merged


def generate_project_frontmatter(
    slug: str,
    metadata: dict[str, Any],
    is_branch_bundle: bool = False,
) -> str:
    """Generate Hugo frontmatter for a project.

    Args:
        slug: Project slug
        metadata: Merged project metadata
        is_branch_bundle: True if this is a branch bundle (_index.md)

    Returns:
        YAML frontmatter string
    """
    github_data = metadata.get("github_data", {})

    # Use manual overrides if present, otherwise use GitHub data
    title = metadata.get("title", github_data.get("name", slug))
    description = metadata.get("abstract", github_data.get("description", ""))
    tags = metadata.get("tags", github_data.get("topics", []))
    category = metadata.get("category", "library")

    # Check if project should be hidden (draft)
    is_hidden = metadata.get("hide", False)

    # Extract language info
    primary_language = metadata.get(
        "primary_language",
        github_data.get("language", "Unknown")
    )
    languages = [primary_language] if primary_language and primary_language != "Unknown" else []

    # Get URLs
    github_pages_url = github_data.get("_github_pages_url", "")
    github_url = metadata.get("github_url", "")

    # Build frontmatter
    default_date = datetime.now(timezone.utc).isoformat()
    created_at = github_data.get("created_at", default_date)

    lines = [
        "---",
        f'title: "{title}"',
    ]

    # Add layout for rich projects (branch bundles)
    if is_branch_bundle:
        lines.append("layout: project-landing")

    lines.extend([
        f"date: {created_at}",
        f"draft: {str(is_hidden).lower()}",
    ])

    if description:
        safe_desc = description.replace('"', '\\"').replace("\n", " ")
        lines.append(f'description: "{safe_desc}"')

    lines.append(f"featured: {str(metadata.get('featured', False)).lower()}")
    lines.append("categories: []")

    # Aliases for Hugo redirects
    aliases = metadata.get("aliases", [])
    if aliases:
        lines.append("aliases:")
        for alias in aliases:
            lines.append(f'  - {alias}')

    # Project section
    lines.extend([
        "",
        "project:",
        '  status: "active"',
        f'  type: "{category}"',
        f"  year_started: {created_at[:4] if created_at else datetime.now().year}",
    ])

    # Tech section
    lines.extend([
        "",
        "tech:",
        "  languages:",
    ])
    for lang in languages:
        lines.append(f'    - "{lang}"')
    lines.append("  frameworks: []")

    if tags:
        lines.append("  topics: [" + ", ".join(f'"{tag}"' for tag in tags) + "]")
    else:
        lines.append("  topics: []")

    # Sources section
    lines.extend([
        "",
        "sources:",
        f'  github: "{github_url}"',
        f'  github_pages: "{github_pages_url}"',
        f'  documentation: "{metadata.get("documentation_url", "")}"',
    ])

    # Packages section
    packages = metadata.get("packages", {})
    lines.extend([
        "",
        "packages:",
        f'  pypi: "{packages.get("pypi", "")}"',
        f'  npm: "{packages.get("npm", "")}"',
        f'  cran: "{packages.get("cran", "")}"',
        f'  r_universe: "{packages.get("r_universe", "")}"',
        f'  crates: "{packages.get("crates", "")}"',
        f'  conan: "{packages.get("conan", "")}"',
        f'  vcpkg: "{packages.get("vcpkg", "")}"',
    ])

    # External docs section (for rich projects)
    external_docs = metadata.get("external_docs", {})
    if external_docs:
        lines.extend([
            "",
            "external_docs:",
        ])
        for doc_type, url in external_docs.items():
            lines.append(f'  {doc_type}: "{url}"')

    # Papers section
    papers = metadata.get("papers", [])
    if papers:
        lines.extend(["", "papers:"])
        for paper in papers:
            lines.append(f'  - title: "{paper.get("title", "")}"')
            lines.append(f'    venue: "{paper.get("venue", "")}"')
            lines.append(f'    year: {paper.get("year", "")}')
            if paper.get("arxiv"):
                lines.append(f'    arxiv: "{paper["arxiv"]}"')
            if paper.get("doi"):
                lines.append(f'    doi: "{paper["doi"]}"')
            if paper.get("pdf"):
                lines.append(f'    pdf: "{paper["pdf"]}"')
    else:
        lines.extend(["", "papers: []"])

    # Metrics section
    lines.extend([
        "",
        "metrics:",
        f'  stars: {github_data.get("stargazers_count", 0)}',
        "  downloads: 0",
        "  citations: 0",
    ])

    # Image section
    if metadata.get("screenshot"):
        lines.append(f'\nimage: "{metadata["screenshot"]}"')

    # Related content
    related_posts = metadata.get("related_posts", [])
    if related_posts:
        lines.extend(["", "related_posts:"])
        for post in related_posts:
            lines.append(f'  - "{post}"')
    else:
        lines.extend(["", "related_posts: []"])

    related_projects = metadata.get("related_projects", [])
    if related_projects:
        lines.append("related_projects:")
        for proj in related_projects:
            lines.append(f'  - "{proj}"')
    else:
        lines.append("related_projects: []")

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def generate_section_frontmatter(
    section: str,
    project_title: str,
    template: dict[str, Any] | None = None,
) -> str:
    """Generate frontmatter for a section page.

    Args:
        section: Section name (docs, tutorials, etc.)
        project_title: Parent project title
        template: Optional template overrides

    Returns:
        YAML frontmatter string
    """
    tmpl = template or SECTION_TEMPLATES.get(section, {})
    title = tmpl.get("title", section.title())
    description = tmpl.get("description", f"{title} for {project_title}")
    weight = tmpl.get("weight", 99)

    return f"""---
title: "{title}"
layout: project-section
description: "{description}"
weight: {weight}
---

"""


def generate_project_content(
    slug: str,
    metadata: dict[str, Any],
    dry_run: bool = False,
) -> bool:
    """Generate Hugo content for a single project.

    Generates either:
    - Leaf bundle (index.md) for simple projects
    - Branch bundle (_index.md + sections) for rich projects

    Args:
        slug: Project slug
        metadata: Merged project metadata
        dry_run: Preview only

    Returns:
        True if successful
    """
    paths = get_paths()
    github_data = metadata.get("github_data", {})

    # Check if this is a rich project (branch bundle)
    is_rich = metadata.get("rich_project", False)
    content_sections = metadata.get("content_sections", [])

    # README: Use manual override if present, otherwise use GitHub README
    readme_content = metadata.get(
        "readme_override",
        github_data.get("_readme_content", "")
    )

    # Rewrite relative URLs in GitHub README (not manual overrides)
    if readme_content and not metadata.get("readme_override"):
        html_url = github_data.get("html_url", "")
        default_branch = github_data.get("default_branch", "main")
        if html_url:
            readme_content = rewrite_readme_urls(
                readme_content, html_url, default_branch
            )

    # Generate frontmatter
    frontmatter = generate_project_frontmatter(slug, metadata, is_branch_bundle=is_rich)

    # Build content
    content = frontmatter
    if readme_content:
        content += readme_content + "\n"
    elif metadata.get("abstract"):
        content += metadata["abstract"] + "\n"

    # Determine content file name based on bundle type
    if is_rich:
        content_path = paths.projects / slug / "_index.md"
    else:
        content_path = paths.projects / slug / "index.md"

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        if is_rich and content_sections:
            for section in content_sections:
                section_path = paths.projects / slug / section / "_index.md"
                console.print(f"  [dim]Would write: {section_path}[/dim]")
        return True

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_path}")

    # Generate section pages for rich projects
    if is_rich and content_sections:
        project_title = metadata.get("title", github_data.get("name", slug))
        for section in content_sections:
            section_path = paths.projects / slug / section / "_index.md"
            # Only create if doesn't exist (preserve manual edits)
            if not section_path.exists():
                section_path.parent.mkdir(parents=True, exist_ok=True)
                section_content = generate_section_frontmatter(section, project_title)
                section_path.write_text(section_content, encoding="utf-8")
                console.print(f"  [green]✓[/green] Generated section: {section_path}")
            else:
                console.print(f"  [dim]Section exists (skipped): {section_path}[/dim]")

    return True


def generate_all_projects(
    cache: ProjectsCache,
    db: ProjectsDatabase,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Generate Hugo content for all cached projects.

    Args:
        cache: Projects cache (must be loaded)
        db: Projects database (must be loaded)
        dry_run: Preview only

    Returns:
        Tuple of (success_count, failed_count)
    """
    import shutil

    paths = get_paths()
    success = 0
    failed = 0

    for slug in cache:
        github_data = cache.get(slug)
        if not github_data:
            continue

        overrides = db.get(slug) or {}

        # Hidden projects: delete content dir if it exists
        if overrides.get("hide", False):
            project_dir = paths.projects / slug
            if project_dir.exists():
                if dry_run:
                    console.print(f"  [dim]Would delete hidden: {slug}[/dim]")
                else:
                    shutil.rmtree(project_dir)
                    console.print(f"  [yellow]Deleted hidden project dir: {slug}[/yellow]")
            else:
                console.print(f"  [dim]Skipping hidden: {slug}[/dim]")
            continue

        merged = merge_project_data(slug, github_data, overrides)

        if generate_project_content(slug, merged, dry_run):
            success += 1
        else:
            failed += 1

    return success, failed
