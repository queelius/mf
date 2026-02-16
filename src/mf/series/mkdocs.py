"""
MkDocs integration for series sync.

When pushing series content to an external source repo that uses MkDocs,
this module handles:
- Copying posts to docs/post/ in the source repo
- Generating a links.md page from series associations
- Updating mkdocs.yml nav with post entries and links
"""

from __future__ import annotations

import shutil
from pathlib import Path

import frontmatter
import yaml
from rich.console import Console

from mf.core.database import PaperDatabase, ProjectsDatabase, SeriesEntry
from mf.series.syncer import get_metafunctor_posts

console = Console()


def validate_mkdocs_repo(source_dir: Path) -> tuple[bool, str]:
    """Check that the source directory has a mkdocs.yml file.

    Args:
        source_dir: Path to the source repository

    Returns:
        Tuple of (valid, message)
    """
    mkdocs_yml = source_dir / "mkdocs.yml"
    if mkdocs_yml.exists():
        return True, str(mkdocs_yml)
    return False, f"mkdocs.yml not found in {source_dir}"


def get_site_base_url() -> str:
    """Get the site base URL for generating links.

    Checks .mf/config.yaml for a site_url override first,
    then falls back to reading hugo.toml baseURL.

    Returns:
        Base URL string (with trailing slash)
    """
    from mf.core.config import get_paths

    paths = get_paths()

    # Check .mf/config.yaml for override
    config_file = paths.config_file
    if config_file.exists():
        try:
            config_data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
            if config_data and isinstance(config_data, dict):
                site_url = config_data.get("site_url")
                if site_url:
                    return str(site_url).rstrip("/") + "/"
        except Exception:
            pass

    # Fall back to hugo.toml
    hugo_toml = paths.root / "hugo.toml"
    if hugo_toml.exists():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        try:
            with open(hugo_toml, "rb") as f:
                hugo_config = tomllib.load(f)
            base_url = str(hugo_config.get("baseURL", ""))
            if base_url:
                return base_url.rstrip("/") + "/"
        except Exception:
            pass

    # Default fallback
    return "https://metafunctor.com/"


def copy_posts_to_mkdocs(
    entry: SeriesEntry,
    source_dir: Path,
    dry_run: bool = False,
) -> int:
    """Copy series posts from metafunctor to docs/post/ in the source repo.

    Args:
        entry: Series entry
        source_dir: Path to the source repository
        dry_run: If True, don't actually copy

    Returns:
        Number of posts copied
    """
    posts = get_metafunctor_posts(entry.slug)
    if not posts:
        return 0

    docs_post_dir = source_dir / "docs" / "post"

    if not dry_run:
        docs_post_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for post_slug, post_path in sorted(posts.items()):
        target = docs_post_dir / post_slug
        if not dry_run:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(post_path, target)
        count += 1

    return count


def _truncate_text(text: str, max_chars: int = 200) -> str:
    """Truncate text to approximately max_chars, ending at a sentence boundary.

    Args:
        text: Text to truncate
        max_chars: Maximum character count

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_chars:
        return text

    # Try to end at a sentence boundary
    truncated = text[:max_chars]
    for sep in (". ", "! ", "? "):
        last_sep = truncated.rfind(sep)
        if last_sep > max_chars // 2:
            return truncated[: last_sep + 1]

    # Fall back to word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        return truncated[:last_space] + "..."
    return truncated + "..."


def generate_links_md(
    entry: SeriesEntry,
    base_url: str,
    paper_db: PaperDatabase | None = None,
    projects_db: ProjectsDatabase | None = None,
) -> str | None:
    """Generate a links.md page from series associations.

    Reads the _index.md associations (papers, projects, links) and
    generates a markdown page with links back to the main site.

    Args:
        entry: Series entry with associations
        base_url: Site base URL for generating links
        paper_db: Paper database for looking up paper details
        projects_db: Projects database for looking up project details

    Returns:
        Markdown content string, or None if no associations
    """
    associations = entry.associations
    if not associations:
        return None

    papers = associations.get("papers", [])
    projects = associations.get("projects", [])
    links = associations.get("links", [])

    # Check if there's anything to generate
    if not papers and not projects and not links:
        return None

    lines: list[str] = []
    lines.append("# Related Content")
    lines.append("")
    lines.append(f"Resources related to the **{entry.title}** series.")
    lines.append("")

    # Papers section
    if papers and paper_db:
        paper_entries = []
        for slug in papers:
            pe = paper_db.get(slug)
            if pe:
                paper_entries.append(pe)
            else:
                console.print(f"[yellow]Warning: paper '{slug}' not found in paper_db[/yellow]")

        if paper_entries:
            lines.append("## Papers")
            lines.append("")
            for pe in paper_entries:
                url = f"{base_url}papers/{pe.slug}/"
                lines.append(f"- **[{pe.title}]({url})**")
                if pe.abstract:
                    truncated = _truncate_text(pe.abstract)
                    lines.append(f"  {truncated}")
                lines.append("")

    # Projects section
    if projects and projects_db:
        project_entries = []
        for slug in projects:
            proj_data = projects_db.get(slug)
            if proj_data:
                project_entries.append((slug, proj_data))
            else:
                console.print(f"[yellow]Warning: project '{slug}' not found in projects_db[/yellow]")

        if project_entries:
            lines.append("## Projects")
            lines.append("")
            for slug, proj_data in project_entries:
                url = f"{base_url}projects/{slug}/"
                title = str(proj_data.get("title", slug))
                lines.append(f"- **[{title}]({url})**")
                desc = str(proj_data.get("description") or proj_data.get("abstract", ""))
                if desc:
                    truncated = _truncate_text(desc)
                    lines.append(f"  {truncated}")
                lines.append("")

    # External links section
    if links:
        lines.append("## External Links")
        lines.append("")
        for link in links:
            name = str(link.get("name", "Link"))
            url = str(link.get("url", ""))
            if url:
                lines.append(f"- [{name}]({url})")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by mf series sync*")
    lines.append("")

    return "\n".join(lines)


def update_mkdocs_nav(
    source_dir: Path,
    entry: SeriesEntry,
    has_links: bool,
    dry_run: bool = False,
) -> None:
    """Update the mkdocs.yml nav section with posts and links.

    Rebuilds the "Posts" section of the nav based on actual post files
    in source_dir/docs/post/. Adds a "Links" entry if links.md was
    generated. Leaves other nav sections untouched.

    Args:
        source_dir: Path to the source repository
        entry: Series entry
        has_links: Whether links.md was generated
        dry_run: If True, don't write changes
    """
    mkdocs_yml = source_dir / "mkdocs.yml"
    if not mkdocs_yml.exists():
        console.print("[yellow]Warning: mkdocs.yml not found, skipping nav update[/yellow]")
        return

    config = yaml.safe_load(mkdocs_yml.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        console.print("[yellow]Warning: mkdocs.yml is not a valid YAML dict[/yellow]")
        return

    nav = config.get("nav")
    if nav is None:
        nav = []
        config["nav"] = nav

    # Build posts entries from docs/post/
    docs_post_dir = source_dir / "docs" / "post"
    post_entries = []

    if docs_post_dir.exists():
        for post_dir in sorted(docs_post_dir.iterdir()):
            if not post_dir.is_dir():
                continue
            # Reject directory names with path traversal characters
            if ".." in post_dir.name or "/" in post_dir.name or "\\" in post_dir.name:
                console.print(f"[yellow]Warning: skipping suspicious directory name: {post_dir.name}[/yellow]")
                continue
            # Ensure resolved path stays within docs_post_dir
            if not post_dir.resolve().is_relative_to(docs_post_dir.resolve()):
                console.print(f"[yellow]Warning: skipping path outside docs: {post_dir.name}[/yellow]")
                continue
            index_file = post_dir / "index.md"
            if not index_file.exists():
                continue

            try:
                post = frontmatter.load(index_file)
                title = str(post.get("title", post_dir.name))
                weight = post.get("series_weight")
                date_val = post.get("date", "")
                date = str(date_val) if date_val else ""
                post_entries.append({
                    "title": title,
                    "path": f"post/{post_dir.name}/index.md",
                    "weight": weight,
                    "date": date,
                })
            except Exception:
                # Fall back to directory name
                post_entries.append({
                    "title": post_dir.name,
                    "path": f"post/{post_dir.name}/index.md",
                    "weight": None,
                    "date": "",
                })

    # Sort by series_weight (ascending), then date (ascending)
    def sort_key(p: dict) -> tuple:
        weight = p["weight"] if p["weight"] is not None else float("inf")
        return (weight, p["date"])

    post_entries.sort(key=sort_key)

    # Build nav post items
    posts_nav_items = [{p["title"]: p["path"]} for p in post_entries]

    # Find and replace "Posts" section in nav
    posts_idx = None
    links_idx = None
    for i, item in enumerate(nav):
        if isinstance(item, dict):
            if "Posts" in item:
                posts_idx = i
            if "Links" in item:
                links_idx = i

    if posts_idx is not None:
        nav[posts_idx] = {"Posts": posts_nav_items}
    elif posts_nav_items:
        nav.append({"Posts": posts_nav_items})

    # Handle Links entry
    if has_links:
        if links_idx is not None:
            nav[links_idx] = {"Links": "links.md"}
        else:
            nav.append({"Links": "links.md"})
    elif links_idx is not None:
        # Remove Links entry if no links.md
        nav.pop(links_idx)

    if not dry_run:
        mkdocs_yml.write_text(
            yaml.safe_dump(config, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )


def execute_mkdocs_sync(
    entry: SeriesEntry,
    source_dir: Path,
    paper_db: PaperDatabase | None = None,
    projects_db: ProjectsDatabase | None = None,
    dry_run: bool = False,
) -> None:
    """Orchestrate the full MkDocs sync for a series.

    After the normal push sync completes, this:
    1. Validates mkdocs.yml exists
    2. Copies posts to docs/post/
    3. Generates links.md from associations
    4. Updates mkdocs.yml nav

    Args:
        entry: Series entry
        source_dir: Path to the source repository
        paper_db: Paper database (optional, for links)
        projects_db: Projects database (optional, for links)
        dry_run: If True, preview only
    """
    console.print("\n[cyan]MkDocs sync...[/cyan]")

    # 1. Validate
    valid, msg = validate_mkdocs_repo(source_dir)
    if not valid:
        console.print(f"[yellow]Warning: {msg} — skipping MkDocs sync[/yellow]")
        return

    # 2. Copy posts
    count = copy_posts_to_mkdocs(entry, source_dir, dry_run=dry_run)
    console.print(f"  [green]Copied {count} post(s) to docs/post/[/green]")

    # 3. Generate links.md
    base_url = get_site_base_url()
    links_content = generate_links_md(entry, base_url, paper_db, projects_db)

    has_links = links_content is not None
    if has_links:
        links_path = source_dir / "docs" / "links.md"
        if not dry_run:
            links_path.parent.mkdir(parents=True, exist_ok=True)
            assert links_content is not None  # guarded by has_links
            links_path.write_text(links_content, encoding="utf-8")
        console.print("  [green]Generated docs/links.md[/green]")
    else:
        console.print("  [dim]No associations found, skipping links.md[/dim]")

    # 4. Update mkdocs.yml nav
    update_mkdocs_nav(source_dir, entry, has_links, dry_run=dry_run)
    console.print("  [green]Updated mkdocs.yml nav[/green]")

    if dry_run:
        console.print("  [yellow]DRY RUN — no files were written[/yellow]")
