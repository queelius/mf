"""Tests for taxonomy analyzer."""

from __future__ import annotations

import pytest

from mf.taxonomy.analyzer import TaxonomyAnalyzer


class TestCollectTaxonomies:
    """Test taxonomy collection from content."""

    def test_collects_tags_from_posts(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "ml"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python", "rust"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        assert "python" in result.tag_counts
        assert result.tag_counts["python"] == 2
        assert result.tag_counts["ml"] == 1
        assert result.tag_counts["rust"] == 1

    def test_collects_categories(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"categories": ["AI"]})
        create_content_file(slug="post-b", extra_fm={"categories": ["AI", "Math"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        assert result.category_counts["AI"] == 2
        assert result.category_counts["Math"] == 1

    def test_tracks_which_content_uses_each_tag(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        assert len(result.tag_items["python"]) == 2

    def test_skips_drafts_by_default(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python"]})
        create_content_file(slug="draft-post", extra_fm={"tags": ["hidden"]}, draft=True)
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        assert "hidden" not in result.tag_counts

    def test_includes_drafts_when_asked(self, create_content_file):
        create_content_file(slug="draft-post", extra_fm={"tags": ["hidden"]}, draft=True)
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect(include_drafts=True)
        assert "hidden" in result.tag_counts


class TestFindDuplicates:
    """Test near-duplicate detection."""

    def test_detects_case_mismatch(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result)
        assert len(dupes) >= 1
        pair = dupes[0]
        assert set(pair["terms"]) == {"Python", "python"}
        assert pair["reason"] == "case_mismatch"

    def test_detects_plural_mismatch(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["algorithm"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["algorithms"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result)
        assert any(
            set(d["terms"]) == {"algorithm", "algorithms"}
            for d in dupes
        )

    def test_detects_hyphen_vs_space(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["machine-learning"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["machine learning"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result)
        assert any(
            set(d["terms"]) == {"machine-learning", "machine learning"}
            for d in dupes
        )

    def test_detects_underscore_vs_hyphen(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["data_science"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["data-science"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result)
        assert any(
            set(d["terms"]) == {"data_science", "data-science"}
            for d in dupes
        )

    def test_no_false_positives_for_unrelated_tags(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["rust"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result)
        assert len(dupes) == 0

    def test_categories_duplicates(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"categories": ["AI"]})
        create_content_file(slug="post-b", extra_fm={"categories": ["ai"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        dupes = analyzer.find_duplicates(result, taxonomy="categories")
        assert len(dupes) >= 1
        assert dupes[0]["reason"] == "case_mismatch"


class TestFindOrphans:
    """Test orphan detection (tags used by only 1 post)."""

    def test_finds_orphan_tags(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "rare-tag"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        orphans = analyzer.find_orphans(result)
        assert "rare-tag" in orphans["tags"]
        assert "python" not in orphans["tags"]

    def test_finds_orphan_categories(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"categories": ["AI", "Rare"]})
        create_content_file(slug="post-b", extra_fm={"categories": ["AI"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        orphans = analyzer.find_orphans(result)
        assert "Rare" in orphans["categories"]

    def test_min_count_parameter(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["a", "b"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["a", "b"]})
        create_content_file(slug="post-c", extra_fm={"tags": ["a"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        orphans = analyzer.find_orphans(result, min_count=3)
        assert "b" in orphans["tags"]
        assert "a" not in orphans["tags"]


class TestStats:
    """Test taxonomy statistics."""

    def test_stats_returns_sorted_counts(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["a", "b", "c"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["a", "b"]})
        create_content_file(slug="post-c", extra_fm={"tags": ["a"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        stats = analyzer.get_stats(result)
        # tags is a list of (name, count) tuples sorted descending
        tag_names = [t[0] for t in stats["tags"]]
        assert tag_names == ["a", "b", "c"]

    def test_stats_includes_co_occurrence(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "ml"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python", "ml"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        stats = analyzer.get_stats(result)
        # co_occurrences is a sorted list of ((a, b), count) tuples
        cooc_dict = dict(stats["co_occurrences"])
        key = tuple(sorted(["python", "ml"]))
        assert cooc_dict[key] == 2

    def test_stats_totals(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["x", "y"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        stats = analyzer.get_stats(result)
        assert stats["totals"]["total_tags"] == 2
        assert stats["totals"]["total_tag_usages"] == 2

    def test_stats_limit(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["a", "b", "c", "d"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["a", "b", "c"]})
        create_content_file(slug="post-c", extra_fm={"tags": ["a", "b"]})
        analyzer = TaxonomyAnalyzer()
        result = analyzer.collect()
        stats = analyzer.get_stats(result, limit=2)
        assert len(stats["tags"]) == 2
        # Still reports full totals
        assert stats["totals"]["total_tags"] == 4
