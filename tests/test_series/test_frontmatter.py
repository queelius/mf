"""Tests for `mf.series.frontmatter` parsing, classification, and comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from mf.core.database import SeriesEntry
from mf.series.frontmatter import (
    DEFAULT_BLOG_OWNED,
    DEFAULT_SHARED,
    FrontmatterFieldDiff,
    classify_field,
    compare_frontmatter,
    compute_body_hash,
    frontmatter_equal,
    get_ownership_sets,
    parse_post,
)


def _write_index(post_dir: Path, *, frontmatter_text: str, body: str) -> Path:
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(f"---\n{frontmatter_text}\n---\n\n{body}")
    return post_dir


# ---------------------------------------------------------------------------
# parse_post
# ---------------------------------------------------------------------------


class TestParsePost:
    def test_returns_metadata_and_body(self, tmp_path):
        post = _write_index(
            tmp_path / "p",
            frontmatter_text="title: Hi\nseries: [\"x\"]",
            body="hello world",
        )
        meta, body = parse_post(post)
        assert meta["title"] == "Hi"
        assert meta["series"] == ["x"]
        assert body.strip() == "hello world"

    def test_accepts_directory_or_file(self, tmp_path):
        post = _write_index(
            tmp_path / "p",
            frontmatter_text="title: Hi",
            body="content",
        )
        meta_dir, body_dir = parse_post(post)
        meta_file, body_file = parse_post(post / "index.md")
        assert meta_dir == meta_file
        assert body_dir == body_file

    def test_missing_index_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            parse_post(empty)


# ---------------------------------------------------------------------------
# compute_body_hash
# ---------------------------------------------------------------------------


class TestComputeBodyHash:
    """The body-only hash is the load-bearing claim: frontmatter drift is invisible."""

    def test_equal_bodies_with_different_frontmatter_match(self, tmp_path):
        a = _write_index(
            tmp_path / "a",
            frontmatter_text="title: A\ndate: 2024-01-01",
            body="same body content",
        )
        b = _write_index(
            tmp_path / "b",
            frontmatter_text="title: B\ndate: 2025-01-01\ntts: true",
            body="same body content",
        )
        assert compute_body_hash(a) == compute_body_hash(b)

    def test_different_bodies_differ(self, tmp_path):
        a = _write_index(
            tmp_path / "a",
            frontmatter_text="title: T",
            body="alpha",
        )
        b = _write_index(
            tmp_path / "b",
            frontmatter_text="title: T",
            body="beta",
        )
        assert compute_body_hash(a) != compute_body_hash(b)

    def test_frontmatter_field_order_does_not_change_body_hash(self, tmp_path):
        a = _write_index(
            tmp_path / "a",
            frontmatter_text="title: T\ndate: 2024-01-01\ntags:\n  - x\n  - y",
            body="content",
        )
        b = _write_index(
            tmp_path / "b",
            frontmatter_text="tags:\n  - x\n  - y\ndate: 2024-01-01\ntitle: T",
            body="content",
        )
        assert compute_body_hash(a) == compute_body_hash(b)


# ---------------------------------------------------------------------------
# classify_field / get_ownership_sets
# ---------------------------------------------------------------------------


class TestClassifyField:
    def test_blog_owned_recognized(self):
        assert classify_field(
            "tts", blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        ) == "blog-owned"

    def test_shared_recognized(self):
        assert classify_field(
            "tags", blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        ) == "shared"

    def test_unknown_field_defaults_to_source_owned(self):
        assert classify_field(
            "novel_field", blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        ) == "source-owned"

    def test_blog_owned_takes_precedence_over_shared(self):
        # Same name in both sets: blog_owned check happens first.
        assert classify_field(
            "tags",
            blog_owned=frozenset({"tags"}),
            shared=DEFAULT_SHARED,
        ) == "blog-owned"


class TestGetOwnershipSets:
    def test_defaults_when_no_entry_config(self):
        entry = SeriesEntry(slug="x", data={})
        blog_owned, shared = get_ownership_sets(entry)
        assert "tts" in blog_owned
        assert "tags" in shared

    def test_per_series_extends_defaults(self):
        entry = SeriesEntry(
            slug="x",
            data={
                "frontmatter_ownership": {
                    "blog_owned": ["custom_field"],
                    "shared": ["status"],
                }
            },
        )
        blog_owned, shared = get_ownership_sets(entry)
        assert "tts" in blog_owned  # default still present
        assert "custom_field" in blog_owned  # extended
        assert "status" in shared

    def test_handles_missing_keys_in_config(self):
        entry = SeriesEntry(
            slug="x",
            data={"frontmatter_ownership": {}},
        )
        blog_owned, shared = get_ownership_sets(entry)
        assert blog_owned == DEFAULT_BLOG_OWNED
        assert shared == DEFAULT_SHARED

    def test_handles_null_config_values(self):
        entry = SeriesEntry(
            slug="x",
            data={
                "frontmatter_ownership": {
                    "blog_owned": None,
                    "shared": None,
                }
            },
        )
        blog_owned, shared = get_ownership_sets(entry)
        assert blog_owned == DEFAULT_BLOG_OWNED
        assert shared == DEFAULT_SHARED


# ---------------------------------------------------------------------------
# compare_frontmatter / FrontmatterFieldDiff
# ---------------------------------------------------------------------------


class TestCompareFrontmatter:
    def test_identical_dicts_yield_all_equal(self):
        a = {"title": "T", "tags": ["x"]}
        b = {"title": "T", "tags": ["x"]}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        assert all(d.status == "equal" for d in diffs)
        assert {d.name for d in diffs} == {"title", "tags"}

    def test_field_only_on_source(self):
        a = {"title": "T", "extra": 1}
        b = {"title": "T"}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        extra = next(d for d in diffs if d.name == "extra")
        assert extra.status == "source-only"
        assert extra.in_source and not extra.in_target

    def test_field_only_on_blog_classified_as_blog_owned(self):
        a = {"title": "T"}
        b = {"title": "T", "tts": True}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        tts = next(d for d in diffs if d.name == "tts")
        assert tts.status == "blog-only"
        assert tts.tier == "blog-owned"

    def test_value_differs_marked_differ(self):
        a = {"title": "Alpha"}
        b = {"title": "Beta"}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        assert diffs[0].status == "differ"

    def test_tier_classification_in_output(self):
        a = {"title": "T", "tags": ["x"], "tts": False}
        b = {"title": "T", "tags": ["y"], "tts": True}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        by_name = {d.name: d for d in diffs}
        assert by_name["title"].tier == "source-owned"
        assert by_name["tags"].tier == "shared"
        assert by_name["tts"].tier == "blog-owned"

    def test_results_sorted_by_field_name(self):
        a = {"zeta": 1, "alpha": 1, "mu": 1}
        b = {"zeta": 1, "alpha": 1, "mu": 1}
        diffs = compare_frontmatter(
            a, b, blog_owned=DEFAULT_BLOG_OWNED, shared=DEFAULT_SHARED
        )
        assert [d.name for d in diffs] == ["alpha", "mu", "zeta"]


class TestFrontmatterFieldDiffStatus:
    def test_equal_when_values_match_on_both_sides(self):
        d = FrontmatterFieldDiff(
            name="x", tier="source-owned",
            source_value=1, target_value=1,
            in_source=True, in_target=True,
        )
        assert d.status == "equal"

    def test_differ_when_values_mismatch(self):
        d = FrontmatterFieldDiff(
            name="x", tier="source-owned",
            source_value=1, target_value=2,
            in_source=True, in_target=True,
        )
        assert d.status == "differ"


class TestFrontmatterEqual:
    def test_dict_order_independence(self):
        a = {"a": 1, "b": 2}
        b = {"b": 2, "a": 1}
        assert frontmatter_equal(a, b)

    def test_value_difference_breaks_equality(self):
        assert not frontmatter_equal({"a": 1}, {"a": 2})

    def test_extra_key_breaks_equality(self):
        assert not frontmatter_equal({"a": 1}, {"a": 1, "b": 2})

    def test_list_order_matters(self):
        # Strict equality keeps list order significant.
        assert not frontmatter_equal({"x": [1, 2]}, {"x": [2, 1]})
