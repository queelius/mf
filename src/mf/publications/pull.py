"""
Pull publication artifacts from source repos into static/.

Resolves source_repo (relative to repos_root) and copies artifacts
to their target paths in static/. Requires artifacts_source mapping
in pubs_db entries to know where source files live.

Example pubs_db entry:
    "my-paper": {
        "source_repo": "papers/my-paper",
        "artifacts": {
            "pdf": "/latex/my-paper/paper.pdf"
        },
        "artifacts_source": {
            "pdf": "paper/paper.pdf"
        }
    }

The artifacts_source paths are relative to the source_repo directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from mf.core.config import get_paths
from mf.publications.database import PubEntry, PubsDatabase

console = Console()

# Artifact types that are local files (not URLs)
LOCAL_ARTIFACT_TYPES = frozenset({"pdf", "html", "slides", "poster", "bibtex"})


def _resolve_repos_root() -> Path:
    """Resolve the root directory containing all repos (~/github/)."""
    paths = get_paths()
    # site_root is ~/github/repos/metafunctor, repos_root is ~/github/
    return paths.root.parent.parent


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def pull_artifacts(
    slug: str | None = None,
    artifact_type: str | None = None,
    dry_run: bool = False,
) -> None:
    """Pull artifacts from source repos into static/.

    Args:
        slug: Pull only this publication (all if None).
        artifact_type: Pull only this artifact type, e.g. "pdf" (all if None).
        dry_run: Preview only, don't copy files.
    """
    paths = get_paths()
    repos_root = _resolve_repos_root()
    static_dir = paths.static

    db = PubsDatabase()
    db.load()

    slugs = [slug] if slug else list(db)
    copied = 0
    skipped = 0
    missing_source = 0
    errors: list[str] = []

    for s in slugs:
        entry = db.get(s)
        if entry is None:
            console.print(f"[red]Not found: {s}[/red]")
            continue

        if not entry.source_repo:
            skipped += 1
            continue

        source_dir = repos_root / entry.source_repo
        if not source_dir.is_dir():
            errors.append(f"{s}: source_repo not found: {source_dir}")
            continue

        artifacts_source = _get_artifacts_source(entry)
        if not artifacts_source:
            skipped += 1
            continue

        for atype, source_rel in artifacts_source.items():
            if artifact_type and atype != artifact_type:
                continue

            target_path_str = entry.artifacts.get(atype)
            if not target_path_str or _is_url(target_path_str):
                continue

            source_path = source_dir / source_rel
            target_path = static_dir / target_path_str.lstrip("/")

            if not source_path.is_file():
                missing_source += 1
                errors.append(f"{s}/{atype}: source not found: {source_path}")
                continue

            if dry_run:
                console.print(f"  [dim][dry-run] {s}/{atype}: {source_path} -> {target_path}[/dim]")
                copied += 1
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            console.print(f"  [green]{s}[/green]/{atype}: copied")
            copied += 1

    # Summary
    console.print()
    if copied:
        label = "Would copy" if dry_run else "Copied"
        console.print(f"[green]{label}:[/green] {copied}")
    if skipped:
        console.print(f"[dim]Skipped (no source_repo or artifacts_source):[/dim] {skipped}")
    if errors:
        console.print(f"[red]Errors:[/red] {len(errors)}")
        for err in errors:
            console.print(f"  [red]{err}[/red]")


def _get_artifacts_source(entry: PubEntry) -> dict[str, str]:
    """Get the artifacts_source mapping for an entry."""
    return entry.artifacts_source


def check_artifacts(
    slug: str | None = None,
    artifact_type: str | None = None,
) -> None:
    """Check which artifacts are present/missing without copying.

    Args:
        slug: Check only this publication (all if None).
        artifact_type: Check only this artifact type (all if None).
    """
    paths = get_paths()
    repos_root = _resolve_repos_root()
    static_dir = paths.static

    db = PubsDatabase()
    db.load()

    slugs = [slug] if slug else list(db)

    table = Table(title="Artifact Status")
    table.add_column("Publication", style="cyan")
    table.add_column("Type")
    table.add_column("Target", style="dim")
    table.add_column("In static/")
    table.add_column("Source exists")

    for s in slugs:
        entry = db.get(s)
        if entry is None:
            continue

        source_dir = (repos_root / entry.source_repo) if entry.source_repo else None
        artifacts_source = _get_artifacts_source(entry)

        for atype, target_path_str in entry.artifacts.items():
            if artifact_type and atype != artifact_type:
                continue
            if not target_path_str or _is_url(target_path_str):
                continue

            target_path = static_dir / target_path_str.lstrip("/")
            target_ok = "[green]yes[/green]" if target_path.is_file() else "[red]no[/red]"

            source_rel = artifacts_source.get(atype)
            if source_rel and source_dir:
                source_path = source_dir / source_rel
                source_ok = "[green]yes[/green]" if source_path.is_file() else "[red]no[/red]"
            else:
                source_ok = "[dim]no mapping[/dim]"

            table.add_row(s, atype, target_path_str, target_ok, source_ok)

    console.print(table)
