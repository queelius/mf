"""Hugo content generator for packages.

Generates content/packages/{slug}/index.md (leaf bundle) from package database entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from mf.core.config import SitePaths, get_paths

if TYPE_CHECKING:
    from mf.packages.database import PackageDatabase, PackageEntry

console = Console()


def _yaml_escape(s: str) -> str:
    """Escape a string value for safe embedding in double-quoted YAML."""
    return s.replace('"', '\\"').replace("\n", " ")


def render_package_page(slug: str, entry: PackageEntry) -> str:
    """Render the index.md text for a package. Pure: no writes, no wall clock."""
    lines: list[str] = ["---"]
    lines.append(f'title: "{_yaml_escape(entry.name)}"')
    lines.append(f'slug: "{_yaml_escape(slug)}"')
    entry_date = entry.data.get("date_added")
    if entry_date:
        lines.append(f"date: {entry_date}")

    if entry.description:
        lines.append(f'description: "{_yaml_escape(entry.description)}"')
    if entry.registry:
        lines.append(f'registry: "{_yaml_escape(entry.registry)}"')
    if entry.latest_version:
        lines.append(f'latest_version: "{_yaml_escape(entry.latest_version)}"')
    if entry.install_command:
        lines.append(f'install_command: "{_yaml_escape(entry.install_command)}"')
    if entry.registry_url:
        lines.append(f'registry_url: "{_yaml_escape(entry.registry_url)}"')
    if entry.downloads is not None:
        lines.append(f"downloads: {entry.downloads}")
    if entry.license:
        lines.append(f'license: "{_yaml_escape(entry.license)}"')
    if entry.featured:
        lines.append("featured: true")
    if entry.tags:
        lines.append("tags:")
        for tag in entry.tags:
            lines.append(f'  - "{_yaml_escape(tag)}"')
    if entry.project:
        lines.append(f'linked_project: "/projects/{_yaml_escape(entry.project)}/"')
    aliases = entry.data.get("aliases", [])
    if aliases:
        lines.append("aliases:")
        for alias in aliases:
            lines.append(f'  - "{_yaml_escape(alias)}"')

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def generate_package_content(
    slug: str,
    entry: PackageEntry,
    dry_run: bool = False,
) -> None:
    """Generate Hugo content for a single package (render + write).

    Creates ``content/packages/{slug}/index.md`` (leaf bundle) with YAML
    frontmatter derived from the package entry.

    Args:
        slug: Package slug.
        entry: Package database entry.
        dry_run: If True, print what would be written but don't write.

    Raises:
        OSError: If the file cannot be written.
    """
    paths = get_paths()
    content_path = paths.packages / slug / "index.md"
    content = render_package_page(slug, entry)

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        return

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_path}")


def generate_all_packages(
    db: PackageDatabase,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Generate Hugo content for all packages in the database.

    Args:
        db: Package database (must be loaded).
        dry_run: If True, preview only.

    Returns:
        Tuple of (success_count, failed_count).
    """
    success = 0
    failed = 0

    for slug, entry in db.items():
        try:
            generate_package_content(slug, entry, dry_run=dry_run)
            success += 1
        except Exception as exc:
            console.print(f"  [red]Error generating {slug}: {exc}[/red]")
            failed += 1

    return success, failed


class PackagesRenderer:
    """Renderer binding for the render-drift engine."""

    section = "packages"

    def __init__(self, db: PackageDatabase, paths: SitePaths) -> None:
        self._db = db
        self._paths = paths

    def iter_slugs(self) -> list[str]:
        return [slug for slug, _ in self._db.items()]

    def existing_slugs(self) -> list[str]:
        d = self._paths.packages
        if not d.exists():
            return []
        return [p.name for p in d.iterdir() if (p / "index.md").exists()]

    def hugo_path(self, slug: str) -> Path:
        return self._paths.packages / slug / "index.md"

    def render_page(self, slug: str) -> str | None:
        entry = self._db.get(slug)
        if entry is None:
            return None
        return render_package_page(slug, entry)


def make_renderer() -> PackagesRenderer:
    """Build a PackagesRenderer with a freshly loaded db."""
    from mf.core.config import get_paths
    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()
    return PackagesRenderer(db, get_paths())
