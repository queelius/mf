"""CLI commands for blog post management.

Convenience layer over Hugo content files -- no database required.
Uses ContentScanner for reading and FrontMatterEditor for writing.
"""

from __future__ import annotations

import json as json_module
import re
from datetime import datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _slugify(title: str) -> str:
    """Convert a title to a URL-friendly slug.

    Lowercase, replace spaces/special chars with hyphens, collapse runs of
    hyphens, and strip leading/trailing hyphens.
    """
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _parse_since(since: str) -> datetime:
    """Parse a relative date string (``30d``, ``4w``, ``3m``) or ISO date.

    Returns a timezone-naive ``datetime``.
    """
    # Relative patterns
    match = re.fullmatch(r"(\d+)([dwm])", since)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            delta = timedelta(days=amount)
        elif unit == "w":
            delta = timedelta(weeks=amount)
        elif unit == "m":
            delta = timedelta(days=amount * 30)
        else:
            raise click.BadParameter(f"Unknown unit: {unit}")
        return datetime.now() - delta

    # ISO date
    try:
        return datetime.fromisoformat(since)
    except ValueError:
        raise click.BadParameter(
            f"Invalid date: {since}. Use YYYY-MM-DD or relative (30d, 4w, 3m)."
        )


def _coerce_value(value: str):
    """Coerce a string value to its most specific Python type.

    ``"true"``/``"false"`` -> ``bool``; integers; floats; else ``str``.
    """
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _find_post_file(slug: str) -> Path | None:
    """Find the ``index.md`` for a post whose directory contains *slug*.

    Searches ``content/post/`` for a directory whose name equals *slug* or
    ends with *slug* (to handle date-prefixed directories like
    ``2024-01-15-my-post``).
    """
    from mf.core.config import get_paths

    posts_dir = get_paths().posts
    if not posts_dir.exists():
        return None

    # Exact match first
    candidate = posts_dir / slug / "index.md"
    if candidate.exists():
        return candidate

    # Date-prefixed match (e.g. 2024-01-15-my-post)
    for child in sorted(posts_dir.iterdir()):
        if child.is_dir() and child.name.endswith(slug):
            index = child / "index.md"
            if index.exists():
                return index

    return None


# ---------------------------------------------------------------------------
# Click command group
# ---------------------------------------------------------------------------


@click.group(name="posts")
def posts() -> None:
    """Manage blog posts.

    Convenience layer over Hugo content files -- no database.
    """
    pass


# ---------------------------------------------------------------------------
# mf posts list
# ---------------------------------------------------------------------------


@posts.command(name="list")
@click.option("-q", "--query", default=None, help="Full-text search in title/body")
@click.option("-t", "--tag", multiple=True, help="Filter by tag (can repeat)")
@click.option("-c", "--category", multiple=True, help="Filter by category (can repeat)")
@click.option("--series", "series_slug", default=None, help="Filter by series slug")
@click.option("--featured", is_flag=True, help="Only featured posts")
@click.option("--include-drafts", is_flag=True, help="Include draft posts")
@click.option(
    "--since", default=None, help="Only posts since date (YYYY-MM-DD or 30d/4w/3m)"
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON array")
def list_posts(
    query: str | None,
    tag: tuple[str, ...],
    category: tuple[str, ...],
    series_slug: str | None,
    featured: bool,
    include_drafts: bool,
    since: str | None,
    as_json: bool,
) -> None:
    """List blog posts with optional filters."""
    from mf.content.scanner import ContentScanner

    scanner = ContentScanner()
    items = scanner.scan_type("post", include_drafts=include_drafts)

    # --- filters ---
    if query:
        items = [it for it in items if it.mentions_text(query)]

    if tag:
        tag_set = set(tag)
        items = [it for it in items if tag_set & set(it.tags)]

    if category:
        cat_set = set(category)
        items = [it for it in items if cat_set & set(it.categories)]

    if series_slug:
        items = [
            it
            for it in items
            if series_slug in it.front_matter.get("series", [])
        ]

    if featured:
        items = [it for it in items if it.front_matter.get("featured")]

    if since:
        cutoff = _parse_since(since)
        filtered = []
        for it in items:
            d = it.date
            if d:
                try:
                    post_dt = datetime.fromisoformat(str(d)[:10])
                    if post_dt >= cutoff:
                        filtered.append(it)
                except ValueError:
                    filtered.append(it)
            else:
                filtered.append(it)
        items = filtered

    # Sort newest first
    def _sort_key(item):
        d = item.date
        return str(d)[:10] if d else ""

    items.sort(key=_sort_key, reverse=True)

    # --- output ---
    if as_json:
        output = []
        for it in items:
            output.append(
                {
                    "slug": it.slug,
                    "title": it.title,
                    "date": it.date,
                    "tags": it.tags,
                    "categories": it.categories,
                    "series": it.front_matter.get("series", []),
                    "featured": bool(it.front_matter.get("featured")),
                    "draft": it.is_draft,
                }
            )
        click.echo(json_module.dumps(output, indent=2, default=str))
        return

    if not items:
        console.print("[yellow]No posts found matching criteria.[/yellow]")
        return

    table = Table(title=f"Posts ({len(items)})")
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Title", no_wrap=False)
    table.add_column("Tags", style="dim")
    table.add_column("Flags", justify="center")

    for it in items:
        flags = []
        if it.front_matter.get("featured"):
            flags.append("F")
        if it.is_draft:
            flags.append("D")
        if it.front_matter.get("series"):
            flags.append("S")

        tags_str = ", ".join(it.tags[:4])
        if len(it.tags) > 4:
            tags_str += f" +{len(it.tags) - 4}"

        table.add_row(
            str(it.date or "")[:10],
            it.title,
            tags_str,
            " ".join(flags),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# mf posts create
# ---------------------------------------------------------------------------


@posts.command(name="create")
@click.option("--title", required=True, help="Post title")
@click.option("--slug", default=None, help="URL slug (auto-generated if omitted)")
@click.option(
    "--date",
    default=None,
    help="Post date YYYY-MM-DD (default: today)",
)
@click.option("-t", "--tag", multiple=True, help="Tag (can repeat)")
@click.option("-c", "--category", multiple=True, help="Category (can repeat)")
@click.option("-s", "--series", multiple=True, help="Series slug (can repeat)")
@click.option("--description", default=None, help="Card preview text")
@click.option("--featured", is_flag=True, help="Mark as featured")
def create_post(
    title: str,
    slug: str | None,
    date: str | None,
    tag: tuple[str, ...],
    category: tuple[str, ...],
    series: tuple[str, ...],
    description: str | None,
    featured: bool,
) -> None:
    """Scaffold a new blog post."""
    import yaml

    from mf.core.config import get_paths

    if slug is None:
        slug = _slugify(title)

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    dir_name = f"{date}-{slug}"
    posts_dir = get_paths().posts
    post_dir = posts_dir / dir_name
    index_file = post_dir / "index.md"

    if index_file.exists():
        console.print(f"[red]Post already exists: {index_file}[/red]")
        raise SystemExit(1)

    # Build front matter
    fm: dict = {
        "title": title,
        "date": date,
        "draft": True,
    }
    if tag:
        fm["tags"] = list(tag)
    if category:
        fm["categories"] = list(category)
    if series:
        fm["series"] = list(series)
    if description:
        fm["description"] = description
    if featured:
        fm["featured"] = True

    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_str}---\n\n"

    post_dir.mkdir(parents=True, exist_ok=True)
    index_file.write_text(content, encoding="utf-8")

    console.print(f"[green]Created:[/green] {index_file}")
    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  1. Edit {index_file}")
    console.print("  2. Remove `draft: true` when ready to publish")
    console.print("  3. Run `make deploy` to build the site")


# ---------------------------------------------------------------------------
# mf posts set
# ---------------------------------------------------------------------------


@posts.command(name="set")
@click.argument("slug")
@click.argument("field")
@click.argument("value")
def set_field(slug: str, field: str, value: str) -> None:
    """Set a front matter field on a post.

    Values are auto-coerced: true/false -> bool, integers, floats, else string.
    """
    from mf.content.frontmatter import FrontMatterEditor

    path = _find_post_file(slug)
    if path is None:
        console.print(f"[red]Post not found: {slug}[/red]")
        raise SystemExit(1)

    editor = FrontMatterEditor(path)
    if not editor.load():
        raise SystemExit(1)

    coerced = _coerce_value(value)
    editor.set(field, coerced)
    if editor.save():
        console.print(f"[green]Set[/green] {field}={coerced!r} on [cyan]{slug}[/cyan]")
    else:
        console.print("[red]Failed to save.[/red]")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# mf posts unset
# ---------------------------------------------------------------------------


@posts.command(name="unset")
@click.argument("slug")
@click.argument("field")
def unset_field(slug: str, field: str) -> None:
    """Remove a front matter field from a post."""
    from mf.content.frontmatter import FrontMatterEditor

    path = _find_post_file(slug)
    if path is None:
        console.print(f"[red]Post not found: {slug}[/red]")
        raise SystemExit(1)

    editor = FrontMatterEditor(path)
    if not editor.load():
        raise SystemExit(1)

    if field not in editor.front_matter:
        console.print(f"[yellow]Field '{field}' not present on {slug}[/yellow]")
        return

    del editor.front_matter[field]
    if editor.save():
        console.print(f"[green]Removed[/green] '{field}' from [cyan]{slug}[/cyan]")
    else:
        console.print("[red]Failed to save.[/red]")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# mf posts tag
# ---------------------------------------------------------------------------


@posts.command(name="tag")
@click.argument("slug")
@click.option("--add", multiple=True, help="Add tag(s)")
@click.option("--remove", multiple=True, help="Remove tag(s)")
@click.option("--set", "set_tags", default=None, help="Replace all tags (comma-separated)")
def manage_tags(
    slug: str,
    add: tuple[str, ...],
    remove: tuple[str, ...],
    set_tags: str | None,
) -> None:
    """Manage tags on a post."""
    from mf.content.frontmatter import FrontMatterEditor

    path = _find_post_file(slug)
    if path is None:
        console.print(f"[red]Post not found: {slug}[/red]")
        raise SystemExit(1)

    editor = FrontMatterEditor(path)
    if not editor.load():
        raise SystemExit(1)

    if set_tags is not None:
        new_tags = [t.strip() for t in set_tags.split(",") if t.strip()]
        editor.set("tags", new_tags)
    else:
        for t in add:
            editor.add_to_list("tags", t)
        for t in remove:
            editor.remove_from_list("tags", t)

    if editor.save():
        console.print(
            f"[green]Updated tags[/green] on [cyan]{slug}[/cyan]: "
            f"{editor.front_matter.get('tags', [])}"
        )
    else:
        console.print("[red]Failed to save.[/red]")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# mf posts feature
# ---------------------------------------------------------------------------


@posts.command(name="feature")
@click.argument("slug")
@click.option("--off", is_flag=True, help="Remove featured status")
def feature_post(slug: str, off: bool) -> None:
    """Toggle featured status on a post."""
    from mf.content.frontmatter import FrontMatterEditor

    path = _find_post_file(slug)
    if path is None:
        console.print(f"[red]Post not found: {slug}[/red]")
        raise SystemExit(1)

    editor = FrontMatterEditor(path)
    if not editor.load():
        raise SystemExit(1)

    if off:
        if "featured" in editor.front_matter:
            del editor.front_matter["featured"]
    else:
        editor.set("featured", True)

    if editor.save():
        status = "unfeatured" if off else "featured"
        console.print(f"[green]{status.capitalize()}[/green] [cyan]{slug}[/cyan]")
    else:
        console.print("[red]Failed to save.[/red]")
        raise SystemExit(1)
