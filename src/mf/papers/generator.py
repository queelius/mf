"""
Hugo content generator for papers.

Generates content/papers/{slug}/index.md from /static/latex/ and paper_db.json.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from mf.core.config import get_paths
from mf.core.database import PaperDatabase
from mf.papers.metadata import extract_from_html, extract_from_pdf
from mf.papers.templates import PAPER_TEMPLATE, PDF_ONLY_TEMPLATE, render_paper_frontmatter

console = Console()

# Optional thumbnail support
try:
    from pdf2image import convert_from_path
    from PIL import Image
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


def find_pdf_file(paper_dir: Path) -> Path | None:
    """Find PDF file in paper directory.

    Args:
        paper_dir: Directory in /static/latex/{slug}/

    Returns:
        Path to PDF or None
    """
    pdfs = list(paper_dir.glob("*.pdf"))
    if pdfs:
        return pdfs[0]
    return None


def find_html_file(paper_dir: Path) -> Path | None:
    """Find HTML file in paper directory.

    Args:
        paper_dir: Directory in /static/latex/{slug}/

    Returns:
        Path to index.html or None
    """
    index = paper_dir / "index.html"
    if index.exists():
        return index
    return None


def format_file_size(size_bytes: int) -> str:
    """Format file size as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def generate_thumbnail(
    pdf_path: Path,
    output_path: Path,
    width: int = 300,
    dry_run: bool = False,
) -> bool:
    """Generate thumbnail image from PDF.

    Args:
        pdf_path: Path to PDF file
        output_path: Path for output thumbnail
        width: Thumbnail width in pixels
        dry_run: Preview only

    Returns:
        True if successful
    """
    if not HAS_PDF2IMAGE:
        return False

    if dry_run:
        return True

    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
        if images:
            img = images[0]
            # Calculate height maintaining aspect ratio
            aspect = img.height / img.width
            height = int(width * aspect)
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            img.save(str(output_path), "JPEG", quality=85)
            return True
    except Exception:
        pass
    return False


def extract_paper_metadata(slug: str, paper_dir: Path) -> dict:
    """Extract metadata from paper files.

    Args:
        slug: Paper slug
        paper_dir: Directory containing paper files

    Returns:
        Dict of extracted metadata
    """
    metadata = {}

    # Try HTML first
    html_file = find_html_file(paper_dir)
    if html_file:
        html_meta = extract_from_html(html_file)
        metadata.update(html_meta.to_dict())

    # Then PDF
    pdf_file = find_pdf_file(paper_dir)
    if pdf_file:
        pdf_meta = extract_from_pdf(pdf_file)
        # PDF page count and size override HTML
        if pdf_meta.page_count:
            metadata["page_count"] = pdf_meta.page_count
        if pdf_meta.file_size_mb:
            metadata["file_size_mb"] = pdf_meta.file_size_mb
        # PDF title/authors only if not from HTML
        if not metadata.get("title") and pdf_meta.title:
            metadata["title"] = pdf_meta.title
        if not metadata.get("authors") and pdf_meta.authors:
            metadata["authors"] = pdf_meta.authors

    return metadata


def generate_paper_content(
    slug: str,
    db: PaperDatabase,
    use_image_cache: bool = True,
    dry_run: bool = False,
) -> bool:
    """Generate Hugo content for a single paper.

    Args:
        slug: Paper slug
        db: Paper database (must be loaded)
        use_image_cache: Skip thumbnail generation if exists
        dry_run: Preview only

    Returns:
        True if successful
    """
    paths = get_paths()
    paper_dir = paths.latex / slug

    if not paper_dir.exists():
        console.print(f"  [red]Paper directory not found: {paper_dir}[/red]")
        return False

    # Check for HTML or PDF
    html_file = find_html_file(paper_dir)
    pdf_file = find_pdf_file(paper_dir)

    if not html_file and not pdf_file:
        console.print(f"  [red]No HTML or PDF found for {slug}[/red]")
        return False

    # Determine if PDF-only
    is_pdf_only = not html_file and pdf_file

    # Extract metadata from files
    extracted = extract_paper_metadata(slug, paper_dir)

    # Get manual overrides from database
    entry = db.get(slug)
    manual = entry.data if entry else {}

    # Merge: manual overrides take precedence
    metadata = {**extracted, **manual}

    # Ensure required fields
    if not metadata.get("title"):
        metadata["title"] = slug.replace("-", " ").title()

    if not metadata.get("date"):
        # Use file modification time as fallback
        import datetime
        mtime = paper_dir.stat().st_mtime
        metadata["date"] = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    # PDF info
    pdf_filename = pdf_file.name if pdf_file else ""
    pdf_size = format_file_size(pdf_file.stat().st_size) if pdf_file else ""
    page_count = metadata.get("page_count", 0)

    # Generate thumbnail if needed
    if pdf_file and HAS_PDF2IMAGE:
        thumb_path = paper_dir / "thumbnail.jpg"
        if (not thumb_path.exists() or not use_image_cache) and generate_thumbnail(pdf_file, thumb_path, dry_run=dry_run):
                metadata["image"] = f"/latex/{slug}/thumbnail.jpg"

    # Render frontmatter
    vars = render_paper_frontmatter(
        slug=slug,
        metadata=metadata,
        pdf_file=pdf_filename,
        pdf_size=pdf_size,
        page_count=page_count,
    )

    # Select template
    template = PDF_ONLY_TEMPLATE if is_pdf_only else PAPER_TEMPLATE
    content = template.format(**vars)

    # Write content file
    content_dir = paths.papers / slug
    content_file = content_dir / "index.md"

    if dry_run:
        console.print(f"  [dim]Would write: {content_file}[/dim]")
        return True

    content_dir.mkdir(parents=True, exist_ok=True)
    content_file.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_file}")

    return True


def generate_papers(
    slug: str | None = None,
    use_image_cache: bool = True,
    dry_run: bool = False,
) -> None:
    """Generate Hugo content for papers.

    Args:
        slug: Generate only this paper (None = all)
        use_image_cache: Skip thumbnail generation if exists
        dry_run: Preview only
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No files will be modified[/yellow]")
        console.print("=" * 60)
        console.print()

    # Load database
    db = PaperDatabase()
    db.load()

    paths = get_paths()

    if slug:
        # Single paper
        console.print(f"Generating content for: {slug}")
        if generate_paper_content(slug, db, use_image_cache, dry_run):
            console.print(f"\n[green]Successfully generated: {slug}[/green]")
        else:
            console.print(f"\n[red]Failed to generate: {slug}[/red]")
        return

    # All papers
    paper_dirs = [d for d in paths.latex.iterdir() if d.is_dir() and not d.name.startswith(".")]
    console.print(f"Generating content for {len(paper_dirs)} papers...")

    success = 0
    failed = 0

    for paper_dir in sorted(paper_dirs):
        paper_slug = paper_dir.name
        console.print(f"\n[cyan]{paper_slug}[/cyan]")

        if generate_paper_content(paper_slug, db, use_image_cache, dry_run):
            success += 1
        else:
            failed += 1

    console.print("\n" + "=" * 60)
    console.print(f"[green]Generated:[/green] {success}")
    if failed:
        console.print(f"[red]Failed:[/red] {failed}")
    console.print("=" * 60)
