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


def generate_package_content(
    slug: str,
    entry: PackageEntry,
    dry_run: bool = False,
) -> bool:
    """Generate Hugo content for a single package.

    Creates ``content/packages/{slug}/index.md`` (leaf bundle) with YAML
    frontmatter derived from the package entry.

    Args:
        slug: Package slug.
        entry: Package database entry.
        dry_run: If True, print what would be written but don't write.

    Returns:
        True if generation succeeded.
    """
    paths = get_paths()
    content_path = paths.packages / slug / "index.md"

    lines: list[str] = ["---"]

    # Title
    lines.append(f'title: "{entry.name}"')
    lines.append(f'slug: "{slug}"')
    lines.append(f"date: {date.today().isoformat()}")

    # Optional string fields
    if entry.description:
        safe_desc = entry.description.replace('"', '\\"').replace("\n", " ")
        lines.append(f'description: "{safe_desc}"')

    if entry.registry:
        lines.append(f'registry: "{entry.registry}"')

    if entry.latest_version:
        lines.append(f'latest_version: "{entry.latest_version}"')

    if entry.install_command:
        lines.append(f'install_command: "{entry.install_command}"')

    if entry.registry_url:
        lines.append(f'registry_url: "{entry.registry_url}"')

    if entry.downloads is not None:
        lines.append(f"downloads: {entry.downloads}")

    if entry.license:
        lines.append(f'license: "{entry.license}"')

    # Featured
    if entry.featured:
        lines.append(f"featured: {str(entry.featured).lower()}")

    # Tags
    if entry.tags:
        lines.append("tags:")
        for tag in entry.tags:
            lines.append(f'  - "{tag}"')

    # Linked project
    if entry.project:
        lines.append(f'linked_project: "/projects/{entry.project}/"')

    # Aliases
    aliases = entry.data.get("aliases", [])
    if aliases:
        lines.append("aliases:")
        for alias in aliases:
            lines.append(f"  - {alias}")

    lines.append("---")
    lines.append("")

    content = "\n".join(lines)

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        return True

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]\u2713[/green] Generated: {content_path}")

    return True


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
            if generate_package_content(slug, entry, dry_run=dry_run):
                success += 1
            else:
                failed += 1
        except Exception as exc:
            console.print(f"  [red]Error generating {slug}: {exc}[/red]")
            failed += 1

    return success, failed
