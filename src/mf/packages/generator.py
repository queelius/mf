"""Hugo content generator for packages.

Generates content/packages/{slug}/index.md (leaf bundle) from package database entries.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from rich.console import Console

from mf.core.config import get_paths

if TYPE_CHECKING:
    from mf.packages.database import PackageDatabase, PackageEntry

console = Console()


def _yaml_escape(s: str) -> str:
    """Escape a string value for safe embedding in double-quoted YAML."""
    return s.replace('"', '\\"').replace("\n", " ")


def generate_package_content(
    slug: str,
    entry: PackageEntry,
    dry_run: bool = False,
) -> None:
    """Generate Hugo content for a single package.

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

    lines: list[str] = ["---"]

    # Title
    lines.append(f'title: "{_yaml_escape(entry.name)}"')
    lines.append(f'slug: "{_yaml_escape(slug)}"')
    entry_date = entry.data.get("date_added") or date.today().isoformat()
    lines.append(f"date: {entry_date}")

    # Optional string fields
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

    # Featured
    if entry.featured:
        lines.append("featured: true")

    # Tags
    if entry.tags:
        lines.append("tags:")
        for tag in entry.tags:
            lines.append(f'  - "{_yaml_escape(tag)}"')

    # Linked project
    if entry.project:
        lines.append(f'linked_project: "/projects/{_yaml_escape(entry.project)}/"')

    # Aliases
    aliases = entry.data.get("aliases", [])
    if aliases:
        lines.append("aliases:")
        for alias in aliases:
            lines.append(f'  - "{_yaml_escape(alias)}"')

    lines.append("---")
    lines.append("")

    content = "\n".join(lines)

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        return

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]\u2713[/green] Generated: {content_path}")


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
