"""Tests for `mf series classify-frontmatter` and the classifier module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from mf.cli import main
from mf.core.database import SeriesDatabase
from mf.series.classify import (
    CorpusReport,
    FieldStat,
    aggregate_global,
    classify_series,
)


def _write_index(post_dir: Path, *, frontmatter_text: str, body: str = "x") -> Path:
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(f"---\n{frontmatter_text}\n---\n\n{body}")
    return post_dir


@pytest.fixture
def classify_corpus(tmp_path, mock_site_root):
    """A series with predictable per-field patterns for the classifier.

    Two posts on both sides:

      - post-a:
          source: title=A, date=2024-01-01, series=[demo]
          blog:   title=A, date=2024-01-01, series=[demo], tts=true
        -> tts is blog-only

      - post-b:
          source: title=B, date=2024-01-02, series=[demo], series_weight=10
          blog:   title=B, date=2024-01-02, series=[demo], tts=true, tags=[x]
        -> tts blog-only, series_weight source-only, tags blog-only
    """
    source_dir = tmp_path / "src"
    posts_dir = source_dir / "post"

    _write_index(
        posts_dir / "post-a",
        frontmatter_text='title: A\ndate: 2024-01-01\nseries: ["demo"]',
    )
    _write_index(
        posts_dir / "post-b",
        frontmatter_text='title: B\ndate: 2024-01-02\nseries: ["demo"]\nseries_weight: 10',
    )

    mf_posts = mock_site_root / "content" / "post"
    _write_index(
        mf_posts / "post-a",
        frontmatter_text='title: A\ndate: 2024-01-01\nseries: ["demo"]\ntts: true',
    )
    _write_index(
        mf_posts / "post-b",
        frontmatter_text=(
            'title: B\ndate: 2024-01-02\nseries: ["demo"]\ntts: true\ntags: ["x"]'
        ),
    )

    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(
        json.dumps(
            {
                "_comment": "Test",
                "_schema_version": "1.2",
                "demo": {
                    "title": "Demo",
                    "description": "classifier corpus",
                    "status": "active",
                    "source_dir": str(source_dir),
                    "posts_subdir": "post",
                },
                "no-source": {
                    "title": "No Source",
                    "description": "inline",
                    "status": "active",
                },
            },
            indent=2,
        )
    )
    db = SeriesDatabase(db_path)
    db.load()
    return {"db": db, "site_root": mock_site_root, "entry": db.get("demo")}


# ---------------------------------------------------------------------------
# FieldStat
# ---------------------------------------------------------------------------


class TestFieldStatTier:
    def test_blog_only_when_only_blog_count_nonzero(self):
        s = FieldStat(name="tts", blog_only=3)
        assert s.proposed_tier == "blog-owned"

    def test_source_only_when_only_source_count_nonzero(self):
        s = FieldStat(name="weight", source_only=3)
        assert s.proposed_tier == "source-only"

    def test_shared_when_values_disagree(self):
        s = FieldStat(name="summary", shared_differ=2)
        assert s.proposed_tier == "shared"

    def test_consistent_when_only_shared_equal(self):
        s = FieldStat(name="title", shared_equal=5)
        assert s.proposed_tier == "consistent"

    def test_mixed_otherwise(self):
        # blog-only on some posts, shared-equal on others -> mixed
        s = FieldStat(name="weird", blog_only=1, shared_equal=2)
        assert s.proposed_tier == "mixed"


# ---------------------------------------------------------------------------
# classify_series
# ---------------------------------------------------------------------------


class TestClassifySeries:
    def test_counts_posts_compared(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        assert report.posts_compared == 2

    def test_classifies_blog_only_field(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        assert "tts" in report.field_stats
        tts = report.field_stats["tts"]
        assert tts.blog_only == 2
        assert tts.proposed_tier == "blog-owned"

    def test_classifies_source_only_field(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        assert "series_weight" in report.field_stats
        sw = report.field_stats["series_weight"]
        assert sw.source_only == 1
        assert sw.proposed_tier == "source-only"

    def test_consistent_field_marked_consistent(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        title = report.field_stats["title"]
        assert title.shared_equal == 2
        assert title.proposed_tier == "consistent"

    def test_field_present_on_one_post_only_marked_blog_or_source_only(
        self, classify_corpus
    ):
        # tags appears only on post-b on the blog side
        report = classify_series(classify_corpus["entry"])
        tags = report.field_stats["tags"]
        assert tags.blog_only == 1
        assert tags.proposed_tier == "blog-owned"


class TestSamples:
    def test_blog_only_field_records_blog_sample(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        assert report.field_stats["tts"].sample_blog is True
        assert report.field_stats["tts"].sample_source is None

    def test_source_only_field_records_source_sample(self, classify_corpus):
        report = classify_series(classify_corpus["entry"])
        assert report.field_stats["series_weight"].sample_source == 10


# ---------------------------------------------------------------------------
# aggregate_global
# ---------------------------------------------------------------------------


class TestAggregateGlobal:
    def test_counts_series_per_field_tier(self):
        r1 = CorpusReport(
            series_slug="a", posts_compared=2,
            field_stats={"tts": FieldStat(name="tts", blog_only=2)},
        )
        r2 = CorpusReport(
            series_slug="b", posts_compared=3,
            field_stats={"tts": FieldStat(name="tts", blog_only=3)},
        )
        g = aggregate_global([r1, r2])
        assert g.series_count == 2
        assert g.field_appearances["tts"]["blog-owned"] == 2

    def test_skips_empty_corpora(self):
        r = CorpusReport(series_slug="x", posts_compared=0, field_stats={})
        g = aggregate_global([r])
        assert g.series_count == 1
        assert not g.field_appearances


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestClassifyFrontmatterCommand:
    def test_runs_for_one_series(self, classify_corpus):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter", "demo"])
        assert result.exit_code == 0
        assert "demo" in result.output

    def test_proposes_yaml_patch_for_blog_owned_field(self, classify_corpus):
        # Use a custom field not in DEFAULT_BLOG_OWNED so the suggestion fires.
        site = classify_corpus["site_root"]
        # Add a custom blog-only field to one post
        index = site / "content" / "post" / "post-a" / "index.md"
        text = index.read_text()
        index.write_text(text.replace("tts: true", "tts: true\ncustom_field: 1"))

        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter", "demo"])
        assert result.exit_code == 0
        assert "frontmatter_ownership" in result.output
        assert "custom_field" in result.output

    def test_skips_yaml_patch_when_only_default_fields_proposed(
        self, mock_site_root, tmp_path
    ):
        # Build a corpus where the only blog-only field is tts (which IS in
        # DEFAULT_BLOG_OWNED) so no per-series patch should be suggested.
        source_dir = tmp_path / "src_only_defaults"
        _write_index(
            source_dir / "post" / "a",
            frontmatter_text='title: A\ndate: 2024-01-01\nseries: ["only-defaults"]',
        )
        mf = mock_site_root / "content" / "post"
        _write_index(
            mf / "a",
            frontmatter_text=(
                'title: A\ndate: 2024-01-01\nseries: ["only-defaults"]\ntts: true'
            ),
        )
        db_path = mock_site_root / ".mf" / "series_db.json"
        db_path.write_text(
            json.dumps(
                {
                    "_comment": "Test",
                    "_schema_version": "1.2",
                    "only-defaults": {
                        "title": "OD",
                        "description": "",
                        "status": "active",
                        "source_dir": str(source_dir),
                        "posts_subdir": "post",
                    },
                },
                indent=2,
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["series", "classify-frontmatter", "only-defaults"]
        )
        assert result.exit_code == 0
        assert "already covered by global defaults" in result.output

    def test_runs_for_all_series(self, classify_corpus):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter"])
        assert result.exit_code == 0
        assert "demo" in result.output

    def test_global_flag_adds_rollup(self, classify_corpus):
        # Need >1 syncable series for global rollup to render.
        site = classify_corpus["site_root"]
        # Add a second syncable series
        src2 = classify_corpus["entry"].source_dir.parent / "src2"
        _write_index(
            src2 / "post" / "alpha",
            frontmatter_text='title: A\ndate: 2024-01-01\nseries: ["second"]',
        )
        _write_index(
            site / "content" / "post" / "alpha",
            frontmatter_text=(
                'title: A\ndate: 2024-01-01\nseries: ["second"]\ntts: true'
            ),
        )
        # Re-write the db to add the second series
        db_path = site / ".mf" / "series_db.json"
        data = json.loads(db_path.read_text())
        data["second"] = {
            "title": "Second",
            "description": "x",
            "status": "active",
            "source_dir": str(src2),
            "posts_subdir": "post",
        }
        db_path.write_text(json.dumps(data, indent=2))

        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter", "--global"])
        assert result.exit_code == 0
        assert "Cross-series patterns" in result.output

    def test_unknown_slug_exits(self, classify_corpus):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter", "ghost"])
        assert result.exit_code == 1
        assert "Series not found" in result.output

    def test_no_source_configured_exits(self, classify_corpus):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "classify-frontmatter", "no-source"])
        assert result.exit_code == 1
        assert "no source_dir configured" in result.output
