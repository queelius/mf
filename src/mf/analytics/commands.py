"""CLI commands for content analytics."""

import json as json_module

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group(name="analytics")
def analytics() -> None:
    """Content analytics and insights.

    Provides statistics about projects, content gaps, tags, and activity.
    """
    pass


@analytics.command(name="projects")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results")
@click.option("--include-hidden", is_flag=True, help="Include hidden projects")
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_projects(
    as_json: bool,
    limit: int | None,
    include_hidden: bool,
    include_drafts: bool,
) -> None:
    """Show projects ranked by linked content count.

    Lists all projects with the number of content items linking to them.

    \b
    Examples:
        mf analytics projects              # All projects ranked by content
        mf analytics projects --limit 10   # Top 10 projects
        mf analytics projects --json       # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    stats = analytics.get_project_link_stats(
        include_hidden=include_hidden,
        include_drafts=include_drafts,
    )

    if limit:
        stats = stats[:limit]

    if as_json:
        output = [s.to_dict() for s in stats]
        console.print(json_module.dumps(output, indent=2))
        return

    table = Table(title="Projects by Linked Content")
    table.add_column("Rank", style="dim")
    table.add_column("Project", style="cyan")
    table.add_column("Title")
    table.add_column("Posts", style="green")
    table.add_column("Papers", style="blue")
    table.add_column("Other", style="yellow")
    table.add_column("Total", style="bold")

    for i, s in enumerate(stats, 1):
        hidden_marker = " [dim](hidden)[/dim]" if s.is_hidden else ""
        table.add_row(
            str(i),
            s.slug,
            (s.title[:30] + "..." if len(s.title) > 30 else s.title) + hidden_marker,
            str(len(s.linked_posts)),
            str(len(s.linked_papers)),
            str(len(s.linked_other)),
            str(s.linked_content_count),
        )

    console.print(table)
    console.print()
    console.print(f"[dim]Total projects: {len(stats)}[/dim]")


@analytics.command(name="gaps")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results")
@click.option("--with-mentions", is_flag=True, help="Show projects mentioned but not linked")
@click.option("--include-hidden", is_flag=True, help="Include hidden projects")
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_gaps(
    as_json: bool,
    limit: int | None,
    with_mentions: bool,
    include_hidden: bool,
    include_drafts: bool,
) -> None:
    """Find projects without any linked content.

    Identifies content gaps where projects exist but have no related content.

    \b
    Examples:
        mf analytics gaps                  # Projects without content
        mf analytics gaps --with-mentions  # Show where they're mentioned
        mf analytics gaps --json           # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    gaps = analytics.get_content_gaps(
        with_mentions=with_mentions,
        include_hidden=include_hidden,
        include_drafts=include_drafts,
    )

    if limit:
        gaps = gaps[:limit]

    if as_json:
        output = [g.to_dict() for g in gaps]
        console.print(json_module.dumps(output, indent=2))
        return

    if not gaps:
        console.print("[green]No content gaps found! All projects have linked content.[/green]")
        return

    table = Table(title="Projects Without Linked Content (Content Gaps)")
    table.add_column("#", style="dim")
    table.add_column("Project", style="cyan")
    table.add_column("Title")
    if with_mentions:
        table.add_column("Mentioned In", style="yellow")

    for i, g in enumerate(gaps, 1):
        hidden_marker = " [dim](hidden)[/dim]" if g.is_hidden else ""
        row = [
            str(i),
            g.slug,
            (g.title[:30] + "..." if len(g.title) > 30 else g.title) + hidden_marker,
        ]
        if with_mentions:
            mentions = str(len(g.mentioned_in)) if g.mentioned_in else "-"
            row.append(mentions)
        table.add_row(*row)

    console.print(table)
    console.print()
    console.print(f"[yellow]Content gaps: {len(gaps)} projects without linked content[/yellow]")


@analytics.command(name="tags")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--limit", "-n", type=int, default=50, help="Limit number of results")
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_tags(
    as_json: bool,
    limit: int,
    include_drafts: bool,
) -> None:
    """Show tag usage distribution.

    Displays most used tags across all content.

    \b
    Examples:
        mf analytics tags              # Top 50 tags
        mf analytics tags --limit 20   # Top 20 tags
        mf analytics tags --json       # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    tags = analytics.get_tag_distribution(
        limit=limit,
        include_drafts=include_drafts,
    )

    if as_json:
        output = [t.to_dict() for t in tags]
        console.print(json_module.dumps(output, indent=2))
        return

    table = Table(title=f"Tag Distribution (Top {len(tags)})")
    table.add_column("Rank", style="dim")
    table.add_column("Tag", style="cyan")
    table.add_column("Count", style="bold")
    table.add_column("Posts", style="green")
    table.add_column("Papers", style="blue")
    table.add_column("Projects", style="yellow")

    for i, t in enumerate(tags, 1):
        table.add_row(
            str(i),
            t.tag,
            str(t.count),
            str(t.content_types.get("post", 0)),
            str(t.content_types.get("papers", 0)),
            str(t.content_types.get("projects", 0)),
        )

    console.print(table)
    console.print()
    console.print(f"[dim]Total unique tags: {len(tags)}[/dim]")


@analytics.command(name="timeline")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--months", "-m", type=int, default=12, help="Number of months to show")
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_timeline(
    as_json: bool,
    months: int,
    include_drafts: bool,
) -> None:
    """Show content activity over time.

    Displays content creation by month.

    \b
    Examples:
        mf analytics timeline              # Last 12 months
        mf analytics timeline --months 24  # Last 24 months
        mf analytics timeline --json       # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    timeline = analytics.get_activity_timeline(
        months=months,
        include_drafts=include_drafts,
    )

    if as_json:
        output = [t.to_dict() for t in timeline]
        console.print(json_module.dumps(output, indent=2))
        return

    if not timeline:
        console.print("[yellow]No timeline data available.[/yellow]")
        return

    table = Table(title=f"Content Timeline (Last {len(timeline)} Months)")
    table.add_column("Month", style="cyan")
    table.add_column("Posts", style="green")
    table.add_column("Papers", style="blue")
    table.add_column("Projects", style="yellow")
    table.add_column("Other", style="dim")
    table.add_column("Total", style="bold")

    total_posts = 0
    total_papers = 0
    total_projects = 0
    total_other = 0

    for t in timeline:
        table.add_row(
            t.month,
            str(t.posts),
            str(t.papers),
            str(t.projects),
            str(t.other),
            str(t.total),
        )
        total_posts += t.posts
        total_papers += t.papers
        total_projects += t.projects
        total_other += t.other

    # Add totals row
    table.add_row(
        "[bold]Total[/bold]",
        f"[green]{total_posts}[/green]",
        f"[blue]{total_papers}[/blue]",
        f"[yellow]{total_projects}[/yellow]",
        f"[dim]{total_other}[/dim]",
        f"[bold]{total_posts + total_papers + total_projects + total_other}[/bold]",
    )

    console.print(table)


@analytics.command(name="suggestions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--limit", "-n", type=int, default=20, help="Limit number of results")
@click.option(
    "--threshold",
    "-t",
    type=float,
    default=0.5,
    help="Minimum confidence threshold (0.0-1.0)",
)
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_suggestions(
    as_json: bool,
    limit: int,
    threshold: float,
    include_drafts: bool,
) -> None:
    """Suggest content that should be linked to projects.

    Finds content that mentions projects but doesn't link to them.

    \b
    Examples:
        mf analytics suggestions              # Suggestions above 50% confidence
        mf analytics suggestions --threshold 0.7  # Higher confidence only
        mf analytics suggestions --json       # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    suggestions = analytics.suggest_cross_references(
        confidence_threshold=threshold,
        include_drafts=include_drafts,
    )

    if limit:
        suggestions = suggestions[:limit]

    if as_json:
        output = [s.to_dict() for s in suggestions]
        console.print(json_module.dumps(output, indent=2))
        return

    if not suggestions:
        console.print("[green]No cross-reference suggestions found.[/green]")
        return

    table = Table(title=f"Cross-Reference Suggestions (Confidence >= {threshold:.0%})")
    table.add_column("#", style="dim")
    table.add_column("Content", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Project", style="yellow")
    table.add_column("Confidence", style="bold")
    table.add_column("Reason")

    for i, s in enumerate(suggestions, 1):
        conf_color = "green" if s.confidence >= 0.8 else "yellow" if s.confidence >= 0.6 else "red"
        table.add_row(
            str(i),
            s.content_title[:30] + "..." if len(s.content_title) > 30 else s.content_title,
            s.content_type,
            s.project_slug,
            f"[{conf_color}]{s.confidence:.0%}[/{conf_color}]",
            s.reason[:40] + "..." if len(s.reason) > 40 else s.reason,
        )

    console.print(table)
    console.print()
    console.print(f"[dim]Total suggestions: {len(suggestions)}[/dim]")
    console.print("[dim]Use 'mf content match-projects' to apply suggestions.[/dim]")


@analytics.command(name="summary")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--include-drafts", is_flag=True, help="Include draft content")
def analytics_summary(
    as_json: bool,
    include_drafts: bool,
) -> None:
    """Show full analytics overview.

    Displays a comprehensive summary of all analytics.

    \b
    Examples:
        mf analytics summary       # Full overview
        mf analytics summary --json  # JSON output
    """
    from mf.analytics import ContentAnalytics

    analytics = ContentAnalytics()
    summary = analytics.get_summary(include_drafts=include_drafts)

    if as_json:
        console.print(json_module.dumps(summary, indent=2))
        return

    # Content overview
    console.print()
    console.print("[bold cyan]Content Overview[/bold cyan]")
    content = summary["content"]
    console.print(f"  Total content: {content['total']}")
    console.print(f"  Published: {content['published']}")
    console.print(f"  Drafts: {content['drafts']}")
    by_type = content.get("by_type", {})
    for ct, count in sorted(by_type.items()):
        console.print(f"    {ct}: {count}")

    # Project overview
    console.print()
    console.print("[bold cyan]Project Overview[/bold cyan]")
    projects = summary["projects"]
    console.print(f"  Total projects: {projects['total']}")
    console.print(f"  With content: {projects['with_content']}")
    console.print(f"  Content gaps: {projects['without_content']}")
    console.print(f"  Hidden: {projects['hidden']}")

    # Top linked projects
    top_projects = summary.get("top_linked_projects", [])
    if top_projects:
        console.print()
        console.print("[bold cyan]Top Linked Projects[/bold cyan]")
        for i, p in enumerate(top_projects[:5], 1):
            console.print(f"  {i}. {p['slug']} ({p['linked_content_count']} items)")

    # Content gaps preview
    gaps = summary.get("content_gaps", [])
    if gaps:
        console.print()
        console.print("[bold yellow]Content Gaps (Projects without content)[/bold yellow]")
        for g in gaps[:5]:
            console.print(f"  • {g['slug']}")
        if len(gaps) > 5:
            console.print(f"  [dim]... and {len(gaps) - 5} more[/dim]")

    # Top tags
    top_tags = summary.get("top_tags", [])
    if top_tags:
        console.print()
        console.print("[bold cyan]Top Tags[/bold cyan]")
        tag_strs = [f"{t['tag']} ({t['count']})" for t in top_tags[:10]]
        console.print(f"  {', '.join(tag_strs)}")

    # Recent activity
    recent = summary.get("recent_activity", [])
    if recent:
        console.print()
        console.print("[bold cyan]Recent Activity (Last 6 Months)[/bold cyan]")
        for t in recent:
            console.print(f"  {t['month']}: {t['total']} items")

    console.print()
