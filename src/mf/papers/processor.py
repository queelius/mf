"""
Paper artifact ingestion.

Copies pre-built HTML/PDF from paper repos into the Hugo static directory.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from mf.core.config import get_paths
from mf.core.crypto import compute_file_hash
from mf.core.database import PaperDatabase, PaperEntry

console = Console()


@dataclass
class ArtifactPaths:
    """Resolved artifact locations for a paper."""

    html_dir: Path | None = None
    pdf_path: Path | None = None


def resolve_artifact_paths(entry: PaperEntry) -> ArtifactPaths:
    """Resolve artifact locations from source_path + format + overrides.

    Convention for tex format:
    - HTML: html_paper/ in same directory as .tex file
    - PDF: {stem}.pdf in same directory as .tex file

    Convention for pdf format:
    - HTML: none
    - PDF: the source file itself

    Convention for pregenerated format:
    - HTML: parent directory of source file
    - PDF: first *.pdf found in that directory

    Override fields (html_dir, pdf_file_source) in the DB entry take
    precedence, resolved relative to source_path's parent directory.

    Returns absolute paths. Returns None for artifacts that don't exist.
    """
    source_path = entry.source_path
    if not source_path:
        return ArtifactPaths()

    parent = source_path.parent
    fmt = entry.source_format

    # Resolve HTML directory
    html_dir: Path | None = None
    if entry.html_dir:
        candidate = parent / entry.html_dir
        if candidate.is_dir() and (candidate / "index.html").exists():
            html_dir = candidate
    elif fmt == "tex":
        candidate = parent / "html_paper"
        if candidate.is_dir() and (candidate / "index.html").exists():
            html_dir = candidate
    elif fmt == "pregenerated":
        html_dir = parent

    # Resolve PDF path
    pdf_path: Path | None = None
    if entry.pdf_file_source:
        candidate = parent / entry.pdf_file_source
        if candidate.exists():
            pdf_path = candidate
    elif fmt == "tex":
        candidate = parent / f"{source_path.stem}.pdf"
        if candidate.exists():
            pdf_path = candidate
    elif fmt == "pdf":
        if source_path.exists():
            pdf_path = source_path
    elif fmt == "pregenerated":
        pdfs = sorted(parent.glob("*.pdf"))
        if pdfs:
            pdf_path = pdfs[0]

    return ArtifactPaths(html_dir=html_dir, pdf_path=pdf_path)


def ingest_paper(
    slug: str,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Ingest pre-built artifacts for a paper into Hugo static directory.

    Requires the paper to already exist in paper_db.json with a source_path.
    Copies HTML directory and/or PDF to /static/latex/{slug}/.

    Args:
        slug: Paper slug (must exist in DB)
        force: Copy even if source hash unchanged
        dry_run: Preview only

    Returns:
        True if successful (or skipped because unchanged)
    """
    db = PaperDatabase()
    db.load()

    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Paper not found: {slug}[/red]")
        return False

    source_path = entry.source_path
    if not source_path:
        console.print(f"[red]No source_path set for {slug}[/red]")
        return False

    if not source_path.exists():
        console.print(f"[red]Source file missing: {source_path}[/red]")
        return False

    # Resolve artifact locations
    artifacts = resolve_artifact_paths(entry)
    if not artifacts.html_dir and not artifacts.pdf_path:
        console.print(f"[red]No artifacts found for {slug}[/red]")
        console.print(f"  Looked for HTML in: {source_path.parent / 'html_paper'}")
        console.print(f"  Looked for PDF: {source_path.parent / (source_path.stem + '.pdf')}")
        return False

    # Check staleness
    source_hash = compute_file_hash(source_path)
    if not force and entry.source_hash == source_hash:
        console.print(f"[green]{slug} is up to date[/green]")
        return True

    console.print(f"[cyan]Ingesting {slug}...[/cyan]")

    backup_path = None
    try:
        # Backup existing
        backup_path = backup_existing_paper(slug, dry_run)

        # Copy HTML directory
        if artifacts.html_dir and not copy_to_static(artifacts.html_dir, slug, dry_run):
            if backup_path:
                restore_backup(backup_path, slug, dry_run)
            return False

        # Copy PDF (may be in a different location than HTML)
        if artifacts.pdf_path and not dry_run:
            paths = get_paths()
            target_dir = paths.latex / slug
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(artifacts.pdf_path, target_dir / artifacts.pdf_path.name)

        # Update database
        if not dry_run:
            entry.set_source_tracking(source_path, source_hash)
            db.save()

            # Generate Hugo content
            from mf.papers.generator import generate_paper_content
            generate_paper_content(slug, db)

        console.print(f"[green]Successfully ingested: {slug}[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if backup_path and backup_path.exists():
            restore_backup(backup_path, slug, dry_run)
        return False


def backup_existing_paper(slug: str, dry_run: bool = False) -> Path | None:
    """Backup existing paper directory.

    Args:
        slug: Paper slug
        dry_run: Preview only

    Returns:
        Path to backup directory, or None
    """
    paths = get_paths()
    target = paths.latex / slug

    if not target.exists():
        return None

    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = paths.latex / ".backup"
    backup_path = backup_dir / f"{slug}-{timestamp}"

    console.print(f"  Backing up existing {slug}...")

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup_path))

    return backup_path


def copy_to_static(source_dir: Path, slug: str, dry_run: bool = False) -> bool:
    """Copy generated files to /static/latex/{slug}/.

    Args:
        source_dir: Directory containing HTML/PDF
        slug: Paper slug
        dry_run: Preview only

    Returns:
        True if successful
    """
    paths = get_paths()
    target_dir = paths.latex / slug

    console.print(f"  Copying to {target_dir}...")

    if dry_run:
        return True

    target_dir.mkdir(parents=True, exist_ok=True)

    for item in source_dir.iterdir():
        dest = target_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    return True


def restore_backup(backup_path: Path, slug: str, dry_run: bool = False) -> None:
    """Restore paper from backup.

    Args:
        backup_path: Path to backup directory
        slug: Paper slug
        dry_run: Preview only
    """
    if not backup_path or not backup_path.exists():
        return

    paths = get_paths()
    target = paths.latex / slug

    console.print(f"  Restoring {slug} from backup...")

    if not dry_run:
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(backup_path), str(target))
