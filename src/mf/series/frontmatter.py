"""
Frontmatter parsing, ownership classification, and semantic comparison.

This module separates "what does the post say" (body) from "what metadata
describes the post" (frontmatter) so that `mf series diff` can ignore
tooling-driven frontmatter churn while still showing genuine semantic
changes when asked.

Three ownership tiers govern how each field is treated:

- source-owned: canonical post metadata authored on the source side
  (title, date, slug, series, draft, ...). Source wins on pull.

- blog-owned: tooling-injected fields that exist only on the metafunctor
  side (tts, layout flags, related_post, ...). These never travel back
  to source and are invisible to diff unless --frontmatter is set.

- shared: fields with two write authorities where conflicts must be
  surfaced explicitly (tags, summary, categories).

Classification falls back to "source-owned" for any field not listed in
the blog-owned or shared sets. The user can override the sets per-series
via `frontmatter_ownership` in the series_db entry, or globally via
`.mf/config.yaml` (future work).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mf.core.database import SeriesEntry
from mf.core.frontmatter import (
    compute_body_hash,
    frontmatter_equal,
    parse_post,
    parse_text,
)

__all__ = [
    "compute_body_hash",
    "frontmatter_equal",
    "parse_post",
    "parse_text",
    "DEFAULT_BLOG_OWNED",
    "DEFAULT_SHARED",
    "get_ownership_sets",
    "classify_field",
    "FrontmatterFieldDiff",
    "compare_frontmatter",
]

# Default ownership sets. These are conservative starting points; users add to
# blog_owned as their tooling grows. The shared set covers Hugo conventions
# where edits can plausibly happen on either side.

DEFAULT_BLOG_OWNED: frozenset[str] = frozenset({
    "tts",
    "layout",
    "og_image",
    "related_post",
    "linked_project",
})

DEFAULT_SHARED: frozenset[str] = frozenset({
    "tags",
    "categories",
    "summary",
})


def get_ownership_sets(entry: SeriesEntry) -> tuple[frozenset[str], frozenset[str]]:
    """Resolve the (blog_owned, shared) sets for a series.

    Per-series overrides in `entry.data['frontmatter_ownership']` extend
    the defaults; they do not replace them. This keeps the global
    convention as a floor.
    """
    cfg = entry.data.get("frontmatter_ownership", {}) or {}
    blog_owned = DEFAULT_BLOG_OWNED | frozenset(cfg.get("blog_owned") or [])
    shared = DEFAULT_SHARED | frozenset(cfg.get("shared") or [])
    return blog_owned, shared


def classify_field(name: str, *, blog_owned: frozenset[str], shared: frozenset[str]) -> str:
    """Return one of 'source-owned', 'blog-owned', or 'shared' for a field name."""
    if name in blog_owned:
        return "blog-owned"
    if name in shared:
        return "shared"
    return "source-owned"


@dataclass
class FrontmatterFieldDiff:
    """A single field's drift status between source and metafunctor frontmatter."""

    name: str
    tier: str  # source-owned | blog-owned | shared
    source_value: Any  # None means absent on source
    target_value: Any  # None means absent on metafunctor
    in_source: bool
    in_target: bool

    @property
    def status(self) -> str:
        if self.in_source and not self.in_target:
            return "source-only"
        if self.in_target and not self.in_source:
            return "blog-only"
        if self.source_value == self.target_value:
            return "equal"
        return "differ"


def compare_frontmatter(
    source_fm: dict[str, Any],
    target_fm: dict[str, Any],
    *,
    blog_owned: frozenset[str],
    shared: frozenset[str],
) -> list[FrontmatterFieldDiff]:
    """Produce a per-field comparison of two parsed frontmatter dicts.

    Returns one entry per field in the union of both sides, sorted by name.
    Fields whose values are equal on both sides are still included (status
    'equal'); callers can filter them out for display.
    """
    all_keys = sorted(set(source_fm) | set(target_fm))
    diffs: list[FrontmatterFieldDiff] = []
    for key in all_keys:
        in_s = key in source_fm
        in_t = key in target_fm
        diffs.append(
            FrontmatterFieldDiff(
                name=key,
                tier=classify_field(key, blog_owned=blog_owned, shared=shared),
                source_value=source_fm.get(key),
                target_value=target_fm.get(key),
                in_source=in_s,
                in_target=in_t,
            )
        )
    return diffs


