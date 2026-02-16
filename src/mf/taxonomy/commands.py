"""CLI commands for taxonomy hygiene.

Find near-duplicates, normalize terms, find orphans, and view stats.
"""

from __future__ import annotations

import json as json_module

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group(name="taxonomy")
def taxonomy() -> None:
    """Taxonomy hygiene: audit, normalize, orphans, stats."""
    pass


@taxonomy.command(name="audit")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--include-drafts", is_flag=True, help="Include drafts")
@click.option(
    "--taxonomy",
    "tax_type",
    type=click.Choice(["tags", "categories", "both"]),
    default="both",
    help="Which taxonomy to audit",
)
def audit_cmd(as_json: bool, include_drafts: bool, tax_type: str) -> None:
    """Find near-duplicate taxonomy terms (case mismatches, plurals, etc.)."""
    from mf.taxonomy.analyzer import TaxonomyAnalyzer

    analyzer = TaxonomyAnalyzer()
    data = analyzer.collect(include_drafts=include_drafts)

    all_dupes: list[dict] = []
    if tax_type in ("tags", "both"):
        all_dupes.extend(analyzer.find_duplicates(data, taxonomy="tags"))
    if tax_type in ("categories", "both"):
        all_dupes.extend(analyzer.find_duplicates(data, taxonomy="categories"))

    if as_json:
        click.echo(json_module.dumps(all_dupes, indent=2))
        return

    if not all_dupes:
        console.print("[green]No near-duplicate taxonomy terms found.[/green]")
        return

    table = Table(title=f"Near-Duplicate Terms ({len(all_dupes)})")
    table.add_column("Term A", style="cyan")
    table.add_column("Term B", style="cyan")
    table.add_column("Reason", style="yellow")
    table.add_column("Counts", style="dim")

    for d in all_dupes:
        a, b = d["terms"]
        counts_str = f"{a}: {d['counts'][a]}, {b}: {d['counts'][b]}"
        table.add_row(a, b, d["reason"], counts_str)

    console.print(table)
    console.print()
    console.print(
        "[dim]Use 'mf taxonomy normalize --from TERM --to TERM' to merge.[/dim]"
    )


@taxonomy.command(name="orphans")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--include-drafts", is_flag=True, help="Include drafts")
@click.option(
    "--min-count",
    default=2,
    type=int,
    help="Tags used fewer than this are orphans (default: 2)",
)
def orphans_cmd(as_json: bool, include_drafts: bool, min_count: int) -> None:
    """Find taxonomy terms used by fewer than --min-count content items."""
    from mf.taxonomy.analyzer import TaxonomyAnalyzer

    analyzer = TaxonomyAnalyzer()
    data = analyzer.collect(include_drafts=include_drafts)
    orphans = analyzer.find_orphans(data, min_count=min_count)

    if as_json:
        click.echo(json_module.dumps(orphans, indent=2))
        return

    for tax_name in ("tags", "categories"):
        terms = orphans[tax_name]
        if not terms:
            console.print(
                f"[green]No orphan {tax_name} (min_count={min_count}).[/green]"
            )
            continue

        table = Table(title=f"Orphan {tax_name.capitalize()} ({len(terms)})")
        table.add_column("Term", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Used By", style="dim")

        counts = data.tag_counts if tax_name == "tags" else data.category_counts
        items = data.tag_items if tax_name == "tags" else data.category_items
        for term in terms:
            table.add_row(term, str(counts[term]), ", ".join(items[term][:3]))

        console.print(table)
        console.print()


@taxonomy.command(name="stats")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--include-drafts", is_flag=True, help="Include drafts")
@click.option("--limit", default=20, type=int, help="Max terms to show (0=all)")
def stats_cmd(as_json: bool, include_drafts: bool, limit: int) -> None:
    """Show taxonomy frequency and co-occurrence statistics."""
    from mf.taxonomy.analyzer import TaxonomyAnalyzer

    analyzer = TaxonomyAnalyzer()
    data = analyzer.collect(include_drafts=include_drafts)
    stats = analyzer.get_stats(data, limit=limit)

    if as_json:
        # Convert to JSON-serializable format
        json_stats = {
            "tags": [{"tag": t, "count": c} for t, c in stats["tags"]],
            "categories": [
                {"category": cat, "count": c} for cat, c in stats["categories"]
            ],
            "co_occurrences": {
                f"{a}+{b}": c for (a, b), c in stats["co_occurrences"]
            },
            **stats["totals"],
        }
        click.echo(json_module.dumps(json_stats, indent=2))
        return

    totals = stats["totals"]
    console.print(f"[bold]Unique tags:[/bold] {totals['total_tags']}")
    console.print(f"[bold]Unique categories:[/bold] {totals['total_categories']}")
    console.print(f"[bold]Total tag usages:[/bold] {totals['total_tag_usages']}")
    console.print()

    # Tag frequency table
    if stats["tags"]:
        table = Table(title="Tag Frequency")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Tag", style="cyan")
        table.add_column("Count", justify="right")

        for i, (tag, count) in enumerate(stats["tags"], 1):
            table.add_row(str(i), tag, str(count))

        console.print(table)

    # Category frequency table
    if stats["categories"]:
        console.print()
        table = Table(title="Category Frequency")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Category", style="cyan")
        table.add_column("Count", justify="right")

        for i, (cat, count) in enumerate(stats["categories"], 1):
            table.add_row(str(i), cat, str(count))

        console.print(table)

    # Top co-occurrences
    cooc = stats["co_occurrences"]
    if cooc:
        console.print()
        top_pairs = cooc[:10]  # Already sorted descending
        table = Table(title="Top Co-occurring Tags")
        table.add_column("Tag A", style="cyan")
        table.add_column("Tag B", style="cyan")
        table.add_column("Times", justify="right")

        for (a, b), count in top_pairs:
            table.add_row(a, b, str(count))

        console.print(table)


@taxonomy.command(name="normalize")
@click.option("--from", "from_term", required=True, help="Term to rename from")
@click.option("--to", "to_term", required=True, help="Term to rename to")
@click.option(
    "--field", default="tags", type=click.Choice(["tags", "categories"])
)
@click.option("--dry-run", is_flag=True, help="Preview without changes")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def normalize_cmd(
    from_term: str,
    to_term: str,
    field: str,
    dry_run: bool,
    yes: bool,
) -> None:
    """Rename a taxonomy term across all content files."""
    from mf.content.frontmatter import FrontMatterEditor
    from mf.content.scanner import ContentScanner
    from mf.taxonomy.analyzer import TaxonomyAnalyzer

    analyzer = TaxonomyAnalyzer()
    data = analyzer.collect(include_drafts=True)

    items_map = data.tag_items if field == "tags" else data.category_items
    affected_slugs = items_map.get(from_term, [])

    if not affected_slugs:
        console.print(
            f"[yellow]Term '{from_term}' not found in any content.[/yellow]"
        )
        return

    console.print(
        f"Renaming [cyan]{from_term}[/cyan] → [green]{to_term}[/green] "
        f"in {len(affected_slugs)} file(s)"
    )

    if dry_run:
        for slug in affected_slugs:
            console.print(f"  [dim]Would update:[/dim] {slug}")
        return

    if not yes:
        if not click.confirm("Proceed?", default=True):
            return

    scanner = ContentScanner()
    updated = 0
    failed = 0

    for ct in scanner.CONTENT_TYPES:
        for item in scanner.scan_type(ct, include_drafts=True):
            terms = item.front_matter.get(field, [])
            if from_term in terms:
                editor = FrontMatterEditor(item.path)
                if not editor.load():
                    failed += 1
                    continue

                editor.remove_from_list(field, from_term)
                editor.add_to_list(field, to_term)

                if editor.save():
                    updated += 1
                else:
                    failed += 1

    console.print(f"[green]Updated {updated} file(s)[/green]")
    if failed:
        console.print(f"[red]Failed: {failed} file(s)[/red]")
