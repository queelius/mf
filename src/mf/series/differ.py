"""
Series diff: read-only inspection of drift between source and metafunctor posts.

Shows where source repos and the metafunctor blog diverge, without modifying
anything. Complements `mf series audit` (which checks structural drift) and
`mf series sync` (which acts on drift).

Comparison semantics
--------------------
By default, diff compares only the **body** of each post (the content after
the YAML frontmatter), so tooling-injected metadata fields and frontmatter
formatting drift do not count as "modified." With `--frontmatter`, the
comparison also considers parsed frontmatter, classified by ownership tier
(source-owned, blog-owned, shared).

Note: this differs from `mf series sync`, which uses a whole-file hash to
decide whether to copy. A post that diff calls "unchanged" may still be a
no-op for sync, but a post diff calls "frontmatter-only" will be a sync
update unless the formatting also matches. This is intentional: sync
reflects what would be *copied*, diff reflects what *semantically differs*.

Diff convention: '-' lines are source, '+' lines are metafunctor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from mf.core.database import SeriesDatabase, SeriesEntry
from mf.series.frontmatter import (
    FrontmatterFieldDiff,
    compare_frontmatter,
    compute_body_hash,
    frontmatter_equal,
    get_ownership_sets,
    parse_post,
)
from mf.series.syncer import (
    generate_diff,
    generate_diffstat,
    get_metafunctor_posts,
    get_source_posts,
    list_syncable_series,
)

console = Console()


@dataclass
class PostDiff:
    """Drift status for a single post.

    `status` reflects body-only comparison (the default). Frontmatter
    comparison is layered on via `extended_status` and `frontmatter_diffs`,
    which callers invoke when `--frontmatter` is set.
    """

    slug: str
    source: Path | None
    target: Path | None
    _frontmatter_cache: dict[str, list[FrontmatterFieldDiff]] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def status(self) -> str:
        if self.source and not self.target:
            return "source-only"
        if self.target and not self.source:
            return "metafunctor-only"
        if self.source and self.target:
            if compute_body_hash(self.source) == compute_body_hash(self.target):
                return "unchanged"
            return "modified"
        return "missing"

    def extended_status(self, entry: SeriesEntry) -> str:
        """Status that distinguishes 'frontmatter-only' from truly unchanged."""
        s = self.status
        if s != "unchanged":
            return s
        s_fm, _ = parse_post(self.source)
        t_fm, _ = parse_post(self.target)
        return "unchanged" if frontmatter_equal(s_fm, t_fm) else "frontmatter-only"

    def frontmatter_diffs(self, entry: SeriesEntry) -> list[FrontmatterFieldDiff]:
        """Per-field frontmatter comparison, classified by ownership tier."""
        cache_key = entry.slug
        if cache_key in self._frontmatter_cache:
            return self._frontmatter_cache[cache_key]
        if not self.source or not self.target:
            return []
        blog_owned, shared = get_ownership_sets(entry)
        s_fm, _ = parse_post(self.source)
        t_fm, _ = parse_post(self.target)
        diffs = compare_frontmatter(
            s_fm, t_fm, blog_owned=blog_owned, shared=shared
        )
        self._frontmatter_cache[cache_key] = diffs
        return diffs

    @property
    def detail(self) -> str:
        s = self.status
        if s == "modified":
            return generate_diffstat(self.source, self.target)
        if s == "source-only":
            return "would be added on pull"
        if s == "metafunctor-only":
            return "would be removed on pull (or kept if push)"
        return ""


def collect_post_diffs(entry: SeriesEntry) -> list[PostDiff]:
    """Return drift status for every post in a series, sorted by slug."""
    source_posts = get_source_posts(entry)
    mf_posts = get_metafunctor_posts(entry.slug)
    all_slugs = sorted(set(source_posts) | set(mf_posts))
    return [
        PostDiff(slug=s, source=source_posts.get(s), target=mf_posts.get(s))
        for s in all_slugs
    ]


STATUS_STYLE = {
    "modified": "yellow",
    "source-only": "green",
    "metafunctor-only": "red",
    "frontmatter-only": "cyan",
    "unchanged": "dim",
}

TIER_STYLE = {
    "source-owned": "yellow",
    "blog-owned": "cyan",
    "shared": "magenta",
}

FIELD_STATUS_STYLE = {
    "differ": "yellow",
    "source-only": "green",
    "blog-only": "cyan",
    "equal": "dim",
}


def _format_value(value: Any) -> str:
    """Render a frontmatter value compactly for table display."""
    if value is None:
        return ""
    if isinstance(value, list):
        rendered = ", ".join(str(v) for v in value)
        return rendered if len(rendered) <= 60 else rendered[:57] + "..."
    s = str(value)
    return s if len(s) <= 60 else s[:57] + "..."


def _print_post_diff(post: PostDiff) -> None:
    """Print a unified body diff panel for one post."""
    if not post.source or not post.target:
        console.print(f"[dim]{post.slug}: {post.status}, no diff to show[/dim]")
        return
    diff_lines = generate_diff(post.source, post.target)
    if not diff_lines:
        console.print(
            f"[dim]{post.slug}: no textual differences in index.md "
            f"(body and full-file are equal)[/dim]"
        )
        return
    syntax = Syntax("\n".join(diff_lines), "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"diff: {post.slug}", border_style="cyan"))


def _print_frontmatter_diff(
    post: PostDiff,
    diffs: list[FrontmatterFieldDiff],
    *,
    show_equal: bool = False,
) -> None:
    """Print a per-field frontmatter table for one post."""
    relevant = diffs if show_equal else [d for d in diffs if d.status != "equal"]
    if not relevant:
        console.print(
            f"[dim]{post.slug}: frontmatter equal across all fields[/dim]"
        )
        return
    table = Table(
        title=f"frontmatter: {post.slug}",
        title_style="cyan",
        show_lines=False,
    )
    table.add_column("Field")
    table.add_column("Tier")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Metafunctor")
    for d in relevant:
        tier_style = TIER_STYLE.get(d.tier, "")
        status_style = FIELD_STATUS_STYLE.get(d.status, "")
        table.add_row(
            d.name,
            f"[{tier_style}]{d.tier}[/{tier_style}]" if tier_style else d.tier,
            f"[{status_style}]{d.status}[/{status_style}]" if status_style else d.status,
            _format_value(d.source_value) if d.in_source else "[dim]<absent>[/dim]",
            _format_value(d.target_value) if d.in_target else "[dim]<absent>[/dim]",
        )
    console.print(table)


def _drift_status(post: PostDiff, entry: SeriesEntry, *, frontmatter: bool) -> str:
    return post.extended_status(entry) if frontmatter else post.status


def diff_series(
    slug: str,
    *,
    post: str | None = None,
    full: bool = False,
    frontmatter: bool = False,
) -> None:
    """Print drift for a single series.

    Args:
        slug: Series slug.
        post: If set, show full unified body diff for just that post.
        full: Append a full unified body diff for every modified post.
        frontmatter: Compare frontmatter semantically; show per-field
            tables annotated with ownership tier; promotes frontmatter-only
            drift to its own status.
    """
    db = SeriesDatabase()
    db.load()
    entry = db.get(slug)
    if entry is None:
        console.print(f"[red]Series not found: {slug}[/red]")
        raise SystemExit(1)

    if not entry.has_source():
        console.print(f"[yellow]Series '{slug}' has no source_dir configured[/yellow]")
        raise SystemExit(1)

    if entry.source_dir and not entry.source_dir.exists():
        console.print(f"[yellow]source_dir does not exist: {entry.source_dir}[/yellow]")
        raise SystemExit(1)

    diffs = collect_post_diffs(entry)

    if post is not None:
        match = next((d for d in diffs if d.slug == post), None)
        if match is None:
            console.print(f"[red]Post not found in series '{slug}': {post}[/red]")
            raise SystemExit(1)
        _print_post_diff(match)
        if frontmatter and match.source and match.target:
            _print_frontmatter_diff(match, match.frontmatter_diffs(entry))
        return

    drift = [
        d for d in diffs if _drift_status(d, entry, frontmatter=frontmatter) != "unchanged"
    ]

    if not drift:
        console.print(
            f"[green]No drift in series '{slug}' "
            f"({len(diffs)} posts unchanged)[/green]"
        )
        return

    table = Table(title=f"Drift for series '{slug}'", show_lines=False)
    table.add_column("Post", overflow="fold")
    table.add_column("Status")
    table.add_column("Detail")
    for d in drift:
        s = _drift_status(d, entry, frontmatter=frontmatter)
        style = STATUS_STYLE.get(s, "")
        status_cell = f"[{style}]{s}[/{style}]" if style else s
        table.add_row(d.slug, status_cell, d.detail)
    console.print(table)

    if full:
        for d in drift:
            if d.status == "modified":
                _print_post_diff(d)

    if frontmatter:
        for d in drift:
            if d.source and d.target:
                fm_diffs = d.frontmatter_diffs(entry)
                if any(f.status != "equal" for f in fm_diffs):
                    _print_frontmatter_diff(d, fm_diffs)


def diff_all(*, frontmatter: bool = False) -> None:
    """Print drift rollup across all syncable series."""
    db = SeriesDatabase()
    db.load()
    series_entries = list_syncable_series(db)

    if not series_entries:
        console.print("[dim]No syncable series configured[/dim]")
        return

    table = Table(title="Series drift rollup")
    table.add_column("Series")
    table.add_column("Modified", justify="right")
    table.add_column("Source-only", justify="right")
    table.add_column("MF-only", justify="right")
    if frontmatter:
        table.add_column("Frontmatter-only", justify="right")
    table.add_column("Total drift", justify="right", style="bold")

    any_drift = False
    for entry in series_entries:
        if entry.source_dir and not entry.source_dir.exists():
            continue
        diffs = collect_post_diffs(entry)
        modified = sum(1 for d in diffs if d.status == "modified")
        source_only = sum(1 for d in diffs if d.status == "source-only")
        mf_only = sum(1 for d in diffs if d.status == "metafunctor-only")
        fm_only = (
            sum(
                1 for d in diffs
                if d.status == "unchanged"
                and d.extended_status(entry) == "frontmatter-only"
            )
            if frontmatter
            else 0
        )
        total = modified + source_only + mf_only + fm_only
        if total == 0:
            continue
        any_drift = True
        row = [entry.slug, str(modified), str(source_only), str(mf_only)]
        if frontmatter:
            row.append(str(fm_only))
        row.append(str(total))
        table.add_row(*row)

    if not any_drift:
        console.print("[green]No drift across any syncable series[/green]")
        return

    console.print(table)
    console.print()
    console.print("[dim]Run 'mf series diff <slug>' for per-post detail[/dim]")
