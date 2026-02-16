"""Taxonomy analyzer for Hugo content.

Collects, analyzes, and reports on tag/category usage across all content.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from mf.content.scanner import ContentScanner


@dataclass
class TaxonomyData:
    """Collected taxonomy data from content scan."""

    tag_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    category_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tag_items: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    category_items: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # Per-item tag lists for co-occurrence analysis
    item_tags: list[list[str]] = field(default_factory=list)


class TaxonomyAnalyzer:
    """Analyzes taxonomy usage across Hugo content."""

    def __init__(self, site_root: Path | None = None):
        self.scanner = ContentScanner(site_root)

    def collect(
        self,
        content_types: list[str] | None = None,
        include_drafts: bool = False,
    ) -> TaxonomyData:
        """Scan content and collect all taxonomy data.

        Args:
            content_types: Types to scan (default: all scanner types).
            include_drafts: Include draft content.

        Returns:
            TaxonomyData with counts and item mappings.
        """
        if content_types is None:
            content_types = list(self.scanner.CONTENT_TYPES.keys())

        data = TaxonomyData()

        for ct in content_types:
            items = self.scanner.scan_type(ct, include_drafts=include_drafts)
            for item in items:
                slug = item.slug

                for tag in item.tags:
                    data.tag_counts[tag] += 1
                    data.tag_items[tag].append(slug)

                for cat in item.categories:
                    data.category_counts[cat] += 1
                    data.category_items[cat].append(slug)

                if item.tags:
                    data.item_tags.append(item.tags)

        return data

    def find_duplicates(
        self,
        data: TaxonomyData,
        taxonomy: str = "tags",
    ) -> list[dict[str, Any]]:
        """Find near-duplicate taxonomy terms.

        Detects: case mismatches, plural/singular, hyphen vs space,
        underscore vs hyphen.

        Args:
            data: Collected taxonomy data.
            taxonomy: "tags" or "categories".

        Returns:
            List of dicts with keys: terms, reason, counts.
        """
        counts = data.tag_counts if taxonomy == "tags" else data.category_counts
        terms = list(counts.keys())
        duplicates: list[dict[str, Any]] = []
        seen: set[frozenset[str]] = set()

        for i, a in enumerate(terms):
            for b in terms[i + 1 :]:
                pair = frozenset([a, b])
                if pair in seen:
                    continue

                reason = self._check_similarity(a, b)
                if reason:
                    seen.add(pair)
                    duplicates.append(
                        {
                            "terms": sorted([a, b]),
                            "reason": reason,
                            "counts": {a: counts[a], b: counts[b]},
                        }
                    )

        return duplicates

    def _check_similarity(self, a: str, b: str) -> str | None:
        """Check if two terms are near-duplicates. Returns reason or None."""
        if a == b:
            return None

        # Case mismatch
        if a.lower() == b.lower():
            return "case_mismatch"

        # Hyphen vs space
        if a.replace("-", " ") == b.replace("-", " "):
            return "hyphen_space"

        # Underscore vs hyphen
        if a.replace("_", "-") == b.replace("_", "-"):
            return "underscore_hyphen"

        # Plural (simple English: trailing s/es)
        a_low, b_low = a.lower(), b.lower()
        if a_low + "s" == b_low or b_low + "s" == a_low:
            return "plural"
        if a_low + "es" == b_low or b_low + "es" == a_low:
            return "plural"

        return None

    def find_orphans(
        self,
        data: TaxonomyData,
        min_count: int = 2,
    ) -> dict[str, list[str]]:
        """Find taxonomy terms used fewer than min_count times.

        Args:
            data: Collected taxonomy data.
            min_count: Minimum usage count. Terms below this are orphans.

        Returns:
            Dict with "tags" and "categories" lists of orphan terms.
        """
        return {
            "tags": sorted(
                t for t, c in data.tag_counts.items() if c < min_count
            ),
            "categories": sorted(
                c for c, cnt in data.category_counts.items() if cnt < min_count
            ),
        }

    def get_stats(
        self,
        data: TaxonomyData,
        limit: int = 0,
    ) -> dict[str, Any]:
        """Get taxonomy statistics including co-occurrence.

        Args:
            data: Collected taxonomy data.
            limit: Max tags/categories to return (0 = all).

        Returns:
            Dict with tags, categories, co_occurrences, totals.
        """
        # Sorted tag stats (descending by count)
        tag_stats = sorted(
            data.tag_counts.items(), key=lambda x: x[1], reverse=True
        )
        if limit:
            tag_stats = tag_stats[:limit]

        cat_stats = sorted(
            data.category_counts.items(), key=lambda x: x[1], reverse=True
        )
        if limit:
            cat_stats = cat_stats[:limit]

        # Co-occurrence: count how often pairs of tags appear together
        cooc: dict[tuple[str, str], int] = defaultdict(int)
        for tags in data.item_tags:
            for a, b in combinations(sorted(tags), 2):
                cooc[(a, b)] += 1

        cooc_sorted = sorted(cooc.items(), key=lambda x: x[1], reverse=True)

        return {
            "tags": tag_stats,
            "categories": cat_stats,
            "co_occurrences": cooc_sorted,
            "totals": {
                "total_tags": len(data.tag_counts),
                "total_categories": len(data.category_counts),
                "total_tag_usages": sum(data.tag_counts.values()),
                "total_category_usages": sum(data.category_counts.values()),
            },
        }
