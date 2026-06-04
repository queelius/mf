"""
Frontmatter ownership classifier (read-only).

Walks the corpus of a series (or all syncable series), parses frontmatter on
both sides for each post, and accumulates per-field statistics: which fields
appear blog-only, source-only, shared-equal, or shared-but-divergent.

The output is a proposed `frontmatter_ownership` config the user can paste
into `series_db.json`, plus a global summary highlighting fields that show
the same pattern across many series (candidates for the default set in
`mf.series.frontmatter`).

Read-only: emits proposals; does not modify config or data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.table import Table

from mf.core.database import SeriesDatabase, SeriesEntry
from mf.series.frontmatter import (
    DEFAULT_BLOG_OWNED,
    DEFAULT_SHARED,
    parse_post,
)
from mf.series.syncer import (
    get_metafunctor_posts,
    get_source_posts,
    list_syncable_series,
)

console = Console()


@dataclass
class FieldStat:
    """Per-field statistics over a corpus.

    Counts only posts where both sides exist (cross-side classification is
    only meaningful when there's something to compare).
    """

    name: str
    blog_only: int = 0
    source_only: int = 0
    shared_equal: int = 0
    shared_differ: int = 0
    sample_blog: Any = None
    sample_source: Any = None

    @property
    def total(self) -> int:
        return (
            self.blog_only
            + self.source_only
            + self.shared_equal
            + self.shared_differ
        )

    @property
    def proposed_tier(self) -> str:
        """Heuristic classification based on observed pattern.

        - 'blog-owned': only ever appears on the blog (tooling-injected).
        - 'source-owned': only ever appears on source (canonical metadata
          the blog hasn't picked up).
        - 'shared': appears on both sides with values that disagree at least
          once (both authorities are editing it).
        - 'consistent': appears on both sides and always matches (no
          intervention needed; defaults to source-owned).
        - 'mixed': irregular pattern (e.g., on some posts it's blog-only,
          on others it's shared); user should review manually.
        """
        if self.blog_only and not self.source_only and not self.shared_equal and not self.shared_differ:
            return "blog-owned"
        if self.source_only and not self.blog_only and not self.shared_equal and not self.shared_differ:
            return "source-only"
        if self.shared_differ and not self.blog_only and not self.source_only:
            return "shared"
        if self.shared_equal and not self.blog_only and not self.source_only and not self.shared_differ:
            return "consistent"
        return "mixed"


@dataclass
class CorpusReport:
    """Per-series classification."""

    series_slug: str
    posts_compared: int
    field_stats: dict[str, FieldStat] = field(default_factory=dict)


def classify_series(entry: SeriesEntry) -> CorpusReport:
    """Walk all posts present on both sides; accumulate field statistics."""
    source_posts = get_source_posts(entry)
    mf_posts = get_metafunctor_posts(entry.slug)
    common = set(source_posts) & set(mf_posts)

    report = CorpusReport(series_slug=entry.slug, posts_compared=len(common))

    for slug in common:
        try:
            s_fm, _ = parse_post(source_posts[slug])
            m_fm, _ = parse_post(mf_posts[slug])
        except (FileNotFoundError, Exception):
            # Skip posts we can't parse; classifier is best-effort.
            continue

        for key in set(s_fm) | set(m_fm):
            stat = report.field_stats.setdefault(key, FieldStat(name=key))
            in_s = key in s_fm
            in_m = key in m_fm
            if in_s and not in_m:
                stat.source_only += 1
                if stat.sample_source is None:
                    stat.sample_source = s_fm[key]
            elif in_m and not in_s:
                stat.blog_only += 1
                if stat.sample_blog is None:
                    stat.sample_blog = m_fm[key]
            elif s_fm[key] == m_fm[key]:
                stat.shared_equal += 1
                if stat.sample_source is None:
                    stat.sample_source = s_fm[key]
                    stat.sample_blog = m_fm[key]
            else:
                stat.shared_differ += 1
                if stat.sample_source is None:
                    stat.sample_source = s_fm[key]
                    stat.sample_blog = m_fm[key]

    return report


TIER_STYLE = {
    "blog-owned": "cyan",
    "source-only": "green",
    "shared": "magenta",
    "consistent": "dim",
    "mixed": "yellow",
}


def _format_value(value: Any, *, max_len: int = 40) -> str:
    if value is None:
        return ""
    s = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def _print_series_report(report: CorpusReport) -> None:
    if report.posts_compared == 0:
        console.print(
            f"[yellow]Series '{report.series_slug}': no posts present on both "
            f"sides; nothing to classify.[/yellow]"
        )
        return

    console.print(
        f"\n[bold cyan]{report.series_slug}[/bold cyan] "
        f"([dim]{report.posts_compared} posts compared[/dim])"
    )

    interesting = [
        s for s in report.field_stats.values() if s.proposed_tier != "consistent"
    ]
    if not interesting:
        console.print("[green]  All shared fields agree across all posts. No proposals.[/green]")
        return

    table = Table(show_lines=False)
    table.add_column("Field")
    table.add_column("Proposed tier")
    table.add_column("Coverage", justify="right")
    table.add_column("Sample (source)")
    table.add_column("Sample (blog)")

    for stat in sorted(
        interesting, key=lambda s: (s.proposed_tier, -s.total, s.name)
    ):
        tier = stat.proposed_tier
        style = TIER_STYLE.get(tier, "")
        coverage_parts = []
        if stat.blog_only:
            coverage_parts.append(f"[cyan]blog={stat.blog_only}[/cyan]")
        if stat.source_only:
            coverage_parts.append(f"[green]src={stat.source_only}[/green]")
        if stat.shared_equal:
            coverage_parts.append(f"[dim]eq={stat.shared_equal}[/dim]")
        if stat.shared_differ:
            coverage_parts.append(f"[magenta]differ={stat.shared_differ}[/magenta]")
        coverage = " ".join(coverage_parts)
        table.add_row(
            stat.name,
            f"[{style}]{tier}[/{style}]" if style else tier,
            coverage,
            _format_value(stat.sample_source),
            _format_value(stat.sample_blog),
        )

    console.print(table)


def _print_proposed_yaml(report: CorpusReport) -> None:
    """Render a YAML snippet the user can paste into series_db.json."""
    blog_owned = sorted(
        s.name for s in report.field_stats.values() if s.proposed_tier == "blog-owned"
    )
    shared = sorted(
        s.name for s in report.field_stats.values() if s.proposed_tier == "shared"
    )

    if not blog_owned and not shared:
        return

    # Subtract entries already covered by the global defaults so the suggestion
    # is purely additive and the user sees only what's new for this series.
    blog_owned_new = [n for n in blog_owned if n not in DEFAULT_BLOG_OWNED]
    shared_new = [n for n in shared if n not in DEFAULT_SHARED]

    if not blog_owned_new and not shared_new:
        console.print(
            "[dim]  All proposed tiers already covered by global defaults.[/dim]"
        )
        return

    console.print()
    console.print(
        f"[bold]Suggested patch for '{report.series_slug}' in series_db.json:[/bold]"
    )
    console.print('[dim]  "frontmatter_ownership": {[/dim]')
    if blog_owned_new:
        rendered = ", ".join(f'"{n}"' for n in blog_owned_new)
        console.print(f'[dim]    "blog_owned": [{rendered}],[/dim]')
    if shared_new:
        rendered = ", ".join(f'"{n}"' for n in shared_new)
        console.print(f'[dim]    "shared": [{rendered}],[/dim]')
    console.print("[dim]  }[/dim]")


@dataclass
class GlobalReport:
    """Aggregate field statistics across all syncable series."""

    series_count: int = 0
    field_appearances: dict[str, dict[str, int]] = field(default_factory=dict)
    # field_appearances[field_name][tier] = count of series where field has that tier


def aggregate_global(reports: list[CorpusReport]) -> GlobalReport:
    """Combine per-series reports into a global view by field-and-tier."""
    g = GlobalReport(series_count=len(reports))
    for r in reports:
        if r.posts_compared == 0:
            continue
        for stat in r.field_stats.values():
            tier = stat.proposed_tier
            g.field_appearances.setdefault(stat.name, defaultdict(int))[tier] += 1
    return g


def _print_global_report(g: GlobalReport) -> None:
    if not g.field_appearances:
        console.print("[dim]No field appearances across series.[/dim]")
        return

    console.print()
    console.print(
        f"[bold]Cross-series patterns[/bold] "
        f"([dim]{g.series_count} series sampled[/dim])"
    )

    table = Table(show_lines=False)
    table.add_column("Field")
    table.add_column("Blog-owned in", justify="right")
    table.add_column("Source-only in", justify="right")
    table.add_column("Shared in", justify="right")
    table.add_column("Consistent in", justify="right")
    table.add_column("Mixed in", justify="right")
    table.add_column("Recommendation")

    rows = []
    for name, by_tier in g.field_appearances.items():
        blog = by_tier.get("blog-owned", 0)
        src = by_tier.get("source-only", 0)
        shared = by_tier.get("shared", 0)
        consistent = by_tier.get("consistent", 0)
        mixed = by_tier.get("mixed", 0)

        # Recommendation: which tier dominates? Threshold of >= 2 series
        # (or 50% of those where the field appears) to suggest a global default.
        if blog >= 2 and blog > src and blog > shared:
            rec = (
                "[cyan]Add to DEFAULT_BLOG_OWNED[/cyan]"
                if name not in DEFAULT_BLOG_OWNED
                else "[dim]already in defaults[/dim]"
            )
        elif shared >= 2 and shared > blog:
            rec = (
                "[magenta]Add to DEFAULT_SHARED[/magenta]"
                if name not in DEFAULT_SHARED
                else "[dim]already in defaults[/dim]"
            )
        elif mixed > 0:
            rec = "[yellow]review manually[/yellow]"
        else:
            rec = ""

        rows.append((name, blog, src, shared, consistent, mixed, rec))

    rows.sort(key=lambda r: (-(r[1] + r[3]), r[0]))
    for r in rows:
        table.add_row(r[0], str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]), r[6])

    console.print(table)


def classify_frontmatter(slug: str | None = None, *, show_global: bool = False) -> None:
    """Public entry point used by the CLI command.

    Args:
        slug: classify one series; if None, classify all syncable series.
        show_global: append a cross-series rollup with default-additions.
    """
    db = SeriesDatabase()
    db.load()

    if slug is not None:
        entry = db.get(slug)
        if entry is None:
            console.print(f"[red]Series not found: {slug}[/red]")
            raise SystemExit(1)
        if not entry.has_source():
            console.print(
                f"[yellow]Series '{slug}' has no source_dir configured[/yellow]"
            )
            raise SystemExit(1)
        targets = [entry]
    else:
        targets = list_syncable_series(db)
        if not targets:
            console.print("[dim]No syncable series configured[/dim]")
            return

    reports: list[CorpusReport] = []
    for entry in targets:
        if entry.source_dir and not entry.source_dir.exists():
            continue
        report = classify_series(entry)
        reports.append(report)
        _print_series_report(report)
        _print_proposed_yaml(report)

    if show_global and len(reports) > 1:
        g = aggregate_global(reports)
        _print_global_report(g)
