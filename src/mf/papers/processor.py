"""
LaTeX paper processor.

Pipeline: .tex file → HTML (tex2any) → PDF (pdflatex) → Hugo content
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from mf.core.config import get_paths
from mf.core.crypto import compute_file_hash
from mf.core.database import PaperDatabase
from mf.core.prompts import confirm, prompt_user, select_from_list

console = Console()


def find_tex_files(path: Path) -> list[Path]:
    """Find all .tex files in a path.

    Args:
        path: File or directory path

    Returns:
        List of .tex file paths
    """
    path = Path(path).resolve()

    if path.is_file() and path.suffix == ".tex":
        return [path]

    if path.is_dir():
        return list(path.rglob("*.tex"))

    return []


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    dry_run: bool = False,
    capture: bool = True,
) -> bool:
    """Run a shell command.

    Args:
        cmd: Command and arguments
        cwd: Working directory
        dry_run: Just print command, don't run
        capture: Capture output (suppress stdout/stderr)

    Returns:
        True if successful
    """
    if dry_run:
        console.print(f"  [dim]Would run: {' '.join(cmd)}[/dim]")
        return True

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode == 0
    except Exception as e:
        console.print(f"  [red]Error running {cmd[0]}: {e}[/red]")
        return False


def generate_html(tex_file: Path, output_dir: Path, dry_run: bool = False) -> bool:
    """Generate HTML from LaTeX using tex2any.

    Args:
        tex_file: Path to .tex file
        output_dir: Directory for HTML output
        dry_run: Preview only

    Returns:
        True if successful
    """
    console.print("  Generating HTML with tex2any...")

    cmd = ["tex2any", str(tex_file), "-f", "html5", "-o", str(output_dir)]
    return run_command(cmd, cwd=tex_file.parent, dry_run=dry_run)


def generate_pdf(tex_file: Path, output_dir: Path, dry_run: bool = False) -> Path | None:
    """Generate PDF from LaTeX.

    Runs: pdflatex x3 → bibtex → pdflatex x2

    Args:
        tex_file: Path to .tex file
        output_dir: Directory to copy PDF to
        dry_run: Preview only

    Returns:
        Path to PDF in output_dir, or None on failure
    """
    console.print("  Generating PDF...")
    tex_dir = tex_file.parent

    # Run pdflatex 3 times
    for i in range(3):
        console.print(f"    pdflatex pass {i+1}/3...")
        run_command(
            ["pdflatex", "-interaction=nonstopmode", tex_file.name],
            cwd=tex_dir,
            dry_run=dry_run,
        )

    # Run bibtex
    aux_file = tex_file.with_suffix(".aux")
    if aux_file.exists() or dry_run:
        console.print("    Running bibtex...")
        run_command(["bibtex", aux_file.name], cwd=tex_dir, dry_run=dry_run)

    # Run pdflatex 2 more times
    for i in range(2):
        console.print(f"    pdflatex final pass {i+1}/2...")
        run_command(
            ["pdflatex", "-interaction=nonstopmode", tex_file.name],
            cwd=tex_dir,
            dry_run=dry_run,
        )

    # Check for PDF
    pdf_file = tex_dir / tex_file.with_suffix(".pdf").name

    if dry_run:
        return output_dir / pdf_file.name

    if not pdf_file.exists():
        console.print(f"  [red]PDF not created at {pdf_file}[/red]")
        return None

    # Copy to output directory
    output_pdf = output_dir / pdf_file.name
    shutil.copy2(pdf_file, output_pdf)
    console.print(f"  [green]✓[/green] PDF created: {output_pdf.name}")

    return output_pdf


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


def process_paper(
    source_path: str,
    slug: str | None = None,
    auto_yes: bool = False,
    dry_run: bool = False,
) -> bool:
    """Process a LaTeX paper into Hugo content.

    Args:
        source_path: Path to .tex file or directory
        slug: Override paper slug
        auto_yes: Auto-confirm prompts
        dry_run: Preview only

    Returns:
        True if successful
    """
    source = Path(source_path).resolve()

    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No files will be modified[/yellow]")
        console.print("=" * 60)
        console.print()

    # Find .tex files
    console.print(f"Scanning {source}...")
    tex_files = find_tex_files(source)

    if not tex_files:
        console.print(f"[red]No .tex files found in {source}[/red]")
        return False

    # Select tex file
    tex_file: Path | None
    if len(tex_files) == 1:
        tex_file = tex_files[0]
        if not auto_yes:
            console.print(f"Found: {tex_file}")
            if not confirm("Process this paper?", auto_yes=auto_yes):
                return False
    else:
        tex_file = select_from_list(
            tex_files,
            message="Select .tex file to process",
            display_func=lambda p: str(p.relative_to(source)),
        )
        if not tex_file:
            return False

    console.print(f"\n[cyan]Processing: {tex_file}[/cyan]")

    # Determine slug
    if not slug:
        suggested = tex_file.stem.lower().replace("_", "-").replace(" ", "-")
        slug = prompt_user("Enter slug for this paper", default=suggested)

    assert slug, "slug must not be empty"
    console.print(f"Slug: {slug}")

    # Load database and check if exists
    db = PaperDatabase()
    db.load()

    if slug in db:
        console.print(f"\n[yellow]Paper '{slug}' already exists[/yellow]")
        console.print("  (Existing metadata will be preserved)")
        if not confirm("Regenerate?", auto_yes=auto_yes):
            return False

    # Compute source hash
    source_hash = compute_file_hash(tex_file)
    console.print(f"Source hash: {source_hash[:20]}...")

    # Check if unchanged
    existing = db.get(slug)
    if existing and existing.source_hash == source_hash:
        console.print("[yellow]Source file unchanged[/yellow]")
        if not confirm("Regenerate anyway?", auto_yes=auto_yes):
            return False

    # Generate in temp directory first
    console.print("\n" + "=" * 60)
    console.print("[cyan]GENERATING HTML AND PDF[/cyan]")
    console.print("=" * 60)

    backup_path = None

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            html_dir = Path(temp_dir) / "html"
            html_dir.mkdir()

            # Generate HTML
            if not generate_html(tex_file, html_dir, dry_run):
                console.print("[red]HTML generation failed[/red]")
                return False

            # Verify HTML created
            if not dry_run and not (html_dir / "index.html").exists():
                console.print("[red]index.html not created[/red]")
                return False

            # Generate PDF
            pdf_path = generate_pdf(tex_file, html_dir, dry_run)
            if not pdf_path:
                console.print("[red]PDF generation failed[/red]")
                return False

            console.print("\n" + "=" * 60)
            console.print("[green]GENERATION SUCCESSFUL[/green]")
            console.print("=" * 60)

            # Backup existing and copy new
            backup_path = backup_existing_paper(slug, dry_run)

            if not copy_to_static(html_dir, slug, dry_run):
                if backup_path:
                    restore_backup(backup_path, slug, dry_run)
                return False

        # Update database
        console.print("  Updating paper database...")
        if not dry_run:
            entry = db.get_or_create(slug)
            entry.set_source_tracking(tex_file, source_hash)
            db.save()

            # Generate Hugo content
            from mf.papers.generator import generate_paper_content

            generate_paper_content(slug, db)

        console.print("\n" + "=" * 60)
        console.print(f"[green]Successfully processed: {slug}[/green]")
        console.print("=" * 60)

        return True

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if backup_path and backup_path.exists():
            console.print("Restoring from backup...")
            restore_backup(backup_path, slug, dry_run)
        import traceback
        traceback.print_exc()
        return False


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
