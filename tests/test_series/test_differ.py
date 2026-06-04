"""Tests for `mf series diff` and the differ module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from mf.cli import main
from mf.core.database import SeriesDatabase
from mf.series.differ import (
    PostDiff,
    collect_post_diffs,
    diff_all,
    diff_series,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_post(
    post_dir: Path,
    *,
    slug_value: str,
    body: str,
    title: str = "Test Post",
) -> None:
    """Write a Hugo-style post bundle with an index.md carrying the series tag.

    Title is independent of `post_dir.name` so that two posts with the same
    intended slug can live under different parent directories and still hash
    identically when the body matches.
    """
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(
        f"""---
title: {title}
date: 2024-01-01
series: ["{slug_value}"]
---

{body}
"""
    )


@pytest.fixture
def drifted_series(tmp_path, mock_site_root):
    """Series 'demo' with four posts illustrating each drift status.

    Source posts:
        unchanged-post   (identical to mf)
        modified-post    (different body from mf)
        source-only-post (no mf counterpart)

    Metafunctor posts:
        unchanged-post
        modified-post
        mf-only-post     (no source counterpart)
    """
    source_dir = tmp_path / "source_repo"
    posts_dir = source_dir / "post"

    _write_post(posts_dir / "unchanged-post", slug_value="demo", body="same content")
    _write_post(posts_dir / "modified-post", slug_value="demo", body="source body")
    _write_post(posts_dir / "source-only-post", slug_value="demo", body="only here")

    mf_posts = mock_site_root / "content" / "post"
    _write_post(mf_posts / "unchanged-post", slug_value="demo", body="same content")
    _write_post(mf_posts / "modified-post", slug_value="demo", body="metafunctor body")
    _write_post(mf_posts / "mf-only-post", slug_value="demo", body="lives on blog only")

    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(
        json.dumps(
            {
                "_comment": "Test",
                "_schema_version": "1.2",
                "demo": {
                    "title": "Demo",
                    "description": "Drift demo",
                    "status": "active",
                    "source_dir": str(source_dir),
                    "posts_subdir": "post",
                },
                "no-source": {
                    "title": "No Source",
                    "description": "Inline series",
                    "status": "active",
                },
            },
            indent=2,
        )
    )

    db = SeriesDatabase(db_path)
    db.load()
    return {
        "db": db,
        "site_root": mock_site_root,
        "source_dir": source_dir,
        "entry": db.get("demo"),
    }


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestPostDiffStatus:
    """`PostDiff.status` covers all four drift cases."""

    def test_unchanged(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _write_post(a, slug_value="x", body="same")
        _write_post(b, slug_value="x", body="same")
        assert PostDiff(slug="p", source=a, target=b).status == "unchanged"

    def test_modified(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _write_post(a, slug_value="x", body="alpha")
        _write_post(b, slug_value="x", body="beta")
        assert PostDiff(slug="p", source=a, target=b).status == "modified"

    def test_source_only(self, tmp_path):
        a = tmp_path / "a"
        _write_post(a, slug_value="x", body="alpha")
        assert PostDiff(slug="p", source=a, target=None).status == "source-only"

    def test_metafunctor_only(self, tmp_path):
        b = tmp_path / "b"
        _write_post(b, slug_value="x", body="beta")
        assert PostDiff(slug="p", source=None, target=b).status == "metafunctor-only"

    def test_missing_when_neither_side(self):
        assert PostDiff(slug="p", source=None, target=None).status == "missing"


class TestPostDiffDetail:
    """`PostDiff.detail` carries human-readable annotations."""

    def test_modified_returns_diffstat(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _write_post(a, slug_value="x", body="alpha")
        _write_post(b, slug_value="x", body="beta")
        detail = PostDiff(slug="p", source=a, target=b).detail
        assert "lines" in detail and ("+" in detail or "-" in detail)

    def test_source_only_message(self, tmp_path):
        a = tmp_path / "a"
        _write_post(a, slug_value="x", body="alpha")
        assert "added on pull" in PostDiff(slug="p", source=a, target=None).detail

    def test_mf_only_message(self, tmp_path):
        b = tmp_path / "b"
        _write_post(b, slug_value="x", body="beta")
        assert "removed on pull" in PostDiff(slug="p", source=None, target=b).detail

    def test_unchanged_empty(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _write_post(a, slug_value="x", body="same")
        _write_post(b, slug_value="x", body="same")
        assert PostDiff(slug="p", source=a, target=b).detail == ""


class TestCollectPostDiffs:
    """`collect_post_diffs` walks both sides and merges by slug."""

    def test_collects_all_four_statuses(self, drifted_series):
        diffs = collect_post_diffs(drifted_series["entry"])
        by_slug = {d.slug: d.status for d in diffs}
        assert by_slug == {
            "modified-post": "modified",
            "mf-only-post": "metafunctor-only",
            "source-only-post": "source-only",
            "unchanged-post": "unchanged",
        }

    def test_results_are_sorted(self, drifted_series):
        diffs = collect_post_diffs(drifted_series["entry"])
        assert [d.slug for d in diffs] == sorted(d.slug for d in diffs)


# ---------------------------------------------------------------------------
# Library-level entry points
# ---------------------------------------------------------------------------


class TestDiffSeries:
    """`diff_series` orchestrates the per-series view."""

    def test_lists_drift_table(self, drifted_series, capsys):
        diff_series("demo")
        out = capsys.readouterr().out
        assert "modified-post" in out
        assert "source-only-post" in out
        assert "mf-only-post" in out
        assert "unchanged-post" not in out  # filtered from table

    def test_full_appends_unified_diff(self, drifted_series, capsys):
        diff_series("demo", full=True)
        out = capsys.readouterr().out
        assert "metafunctor body" in out or "source body" in out
        assert "diff: modified-post" in out

    def test_post_filter_shows_one(self, drifted_series, capsys):
        diff_series("demo", post="modified-post")
        out = capsys.readouterr().out
        assert "diff: modified-post" in out
        assert "source-only-post" not in out

    def test_post_filter_unknown_exits(self, drifted_series):
        with pytest.raises(SystemExit) as exc:
            diff_series("demo", post="nonexistent")
        assert exc.value.code == 1

    def test_unknown_slug_exits(self, drifted_series):
        with pytest.raises(SystemExit) as exc:
            diff_series("not-a-series")
        assert exc.value.code == 1

    def test_no_source_dir_configured_exits(self, drifted_series):
        with pytest.raises(SystemExit) as exc:
            diff_series("no-source")
        assert exc.value.code == 1

    def test_missing_source_dir_exits(self, drifted_series, capsys):
        # Reroute the demo series' source_dir to a path that does not exist.
        db_path = drifted_series["site_root"] / ".mf" / "series_db.json"
        data = json.loads(db_path.read_text())
        data["demo"]["source_dir"] = str(drifted_series["site_root"] / "ghost")
        db_path.write_text(json.dumps(data, indent=2))

        with pytest.raises(SystemExit) as exc:
            diff_series("demo")
        assert exc.value.code == 1
        assert "does not exist" in capsys.readouterr().out

    def test_clean_series_reports_no_drift(self, mock_site_root, tmp_path, capsys):
        source_dir = tmp_path / "clean_repo"
        _write_post(source_dir / "post" / "shared", slug_value="clean", body="x")
        _write_post(
            mock_site_root / "content" / "post" / "shared",
            slug_value="clean",
            body="x",
        )
        db_path = mock_site_root / ".mf" / "series_db.json"
        db_path.write_text(
            json.dumps(
                {
                    "_comment": "Test",
                    "_schema_version": "1.2",
                    "clean": {
                        "title": "Clean",
                        "description": "no drift",
                        "status": "active",
                        "source_dir": str(source_dir),
                        "posts_subdir": "post",
                    },
                },
                indent=2,
            )
        )
        diff_series("clean")
        out = capsys.readouterr().out
        assert "No drift" in out


class TestDiffAll:
    """`diff_all` produces a rollup across syncable series."""

    def test_rollup_lists_drifted_series(self, drifted_series, capsys):
        diff_all()
        out = capsys.readouterr().out
        assert "demo" in out
        assert "Series drift rollup" in out

    def test_no_syncable_series(self, mock_site_root, capsys):
        db_path = mock_site_root / ".mf" / "series_db.json"
        db_path.write_text(
            json.dumps(
                {
                    "_comment": "Test",
                    "_schema_version": "1.2",
                    "x": {"title": "X", "description": "", "status": "active"},
                },
                indent=2,
            )
        )
        diff_all()
        assert "No syncable series" in capsys.readouterr().out

    def test_no_drift(self, mock_site_root, tmp_path, capsys):
        source_dir = tmp_path / "clean"
        _write_post(source_dir / "post" / "shared", slug_value="c", body="same")
        _write_post(
            mock_site_root / "content" / "post" / "shared",
            slug_value="c",
            body="same",
        )
        db_path = mock_site_root / ".mf" / "series_db.json"
        db_path.write_text(
            json.dumps(
                {
                    "_comment": "Test",
                    "_schema_version": "1.2",
                    "c": {
                        "title": "C",
                        "description": "",
                        "status": "active",
                        "source_dir": str(source_dir),
                        "posts_subdir": "post",
                    },
                },
                indent=2,
            )
        )
        diff_all()
        assert "No drift" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestDiffCommand:
    """`mf series diff` Click command."""

    def test_command_runs_for_series(self, drifted_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "demo"])
        assert result.exit_code == 0
        assert "modified-post" in result.output

    def test_command_runs_rollup(self, drifted_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff"])
        assert result.exit_code == 0
        assert "demo" in result.output

    def test_post_without_slug_errors(self, drifted_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "--post", "anything"])
        assert result.exit_code == 1
        assert "require a series slug" in result.output

    def test_full_without_slug_errors(self, drifted_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "--full"])
        assert result.exit_code == 1
        assert "require a series slug" in result.output

    def test_unknown_slug_exits_nonzero(self, drifted_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "ghost"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# --frontmatter behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def fm_drift_series(tmp_path, mock_site_root):
    """Series 'fm' with body-equal posts that diverge only in frontmatter.

    Source posts:
        body-equal-fm-equal     : identical on both sides
        body-equal-fm-differs   : same body; blog has tts: true; source does not
        body-differs            : real body change

    Built so that body-only diff (default) classifies post 'body-equal-fm-differs'
    as 'unchanged', while --frontmatter promotes it to 'frontmatter-only'.
    """
    source_dir = tmp_path / "src_fm"
    posts_dir = source_dir / "post"

    # body-equal-fm-equal: same on both sides
    (posts_dir / "body-equal-fm-equal").mkdir(parents=True)
    (posts_dir / "body-equal-fm-equal" / "index.md").write_text(
        "---\ntitle: Equal\ndate: 2024-01-01\nseries: [\"fm\"]\n---\n\nshared body\n"
    )

    # body-equal-fm-differs: source has no tts, blog has tts: true
    (posts_dir / "body-equal-fm-differs").mkdir(parents=True)
    (posts_dir / "body-equal-fm-differs" / "index.md").write_text(
        "---\ntitle: Same\ndate: 2024-01-01\nseries: [\"fm\"]\n---\n\nshared body\n"
    )

    # body-differs: actual body change
    (posts_dir / "body-differs").mkdir(parents=True)
    (posts_dir / "body-differs" / "index.md").write_text(
        "---\ntitle: Body\ndate: 2024-01-01\nseries: [\"fm\"]\n---\n\nsource body\n"
    )

    mf_posts = mock_site_root / "content" / "post"

    (mf_posts / "body-equal-fm-equal").mkdir(parents=True)
    (mf_posts / "body-equal-fm-equal" / "index.md").write_text(
        "---\ntitle: Equal\ndate: 2024-01-01\nseries: [\"fm\"]\n---\n\nshared body\n"
    )

    (mf_posts / "body-equal-fm-differs").mkdir(parents=True)
    (mf_posts / "body-equal-fm-differs" / "index.md").write_text(
        "---\ntitle: Same\ndate: 2024-01-01\nseries: [\"fm\"]\ntts: true\n---\n\nshared body\n"
    )

    (mf_posts / "body-differs").mkdir(parents=True)
    (mf_posts / "body-differs" / "index.md").write_text(
        "---\ntitle: Body\ndate: 2024-01-01\nseries: [\"fm\"]\n---\n\nblog body\n"
    )

    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(
        json.dumps(
            {
                "_comment": "Test",
                "_schema_version": "1.2",
                "fm": {
                    "title": "FM",
                    "description": "frontmatter drift demo",
                    "status": "active",
                    "source_dir": str(source_dir),
                    "posts_subdir": "post",
                },
            },
            indent=2,
        )
    )
    db = SeriesDatabase(db_path)
    db.load()
    return {"db": db, "site_root": mock_site_root, "entry": db.get("fm")}


class TestPostDiffFrontmatterAware:
    """`PostDiff.extended_status` and `frontmatter_diffs` integrate with the tier model."""

    def test_default_status_unchanged_when_only_frontmatter_differs(self, fm_drift_series):
        from mf.series.differ import collect_post_diffs

        by_slug = {d.slug: d for d in collect_post_diffs(fm_drift_series["entry"])}
        assert by_slug["body-equal-fm-differs"].status == "unchanged"
        assert by_slug["body-equal-fm-equal"].status == "unchanged"
        assert by_slug["body-differs"].status == "modified"

    def test_extended_status_promotes_frontmatter_only(self, fm_drift_series):
        from mf.series.differ import collect_post_diffs

        by_slug = {d.slug: d for d in collect_post_diffs(fm_drift_series["entry"])}
        entry = fm_drift_series["entry"]
        assert (
            by_slug["body-equal-fm-differs"].extended_status(entry) == "frontmatter-only"
        )
        assert by_slug["body-equal-fm-equal"].extended_status(entry) == "unchanged"
        assert by_slug["body-differs"].extended_status(entry) == "modified"

    def test_frontmatter_diffs_classify_blog_only_field(self, fm_drift_series):
        from mf.series.differ import collect_post_diffs

        by_slug = {d.slug: d for d in collect_post_diffs(fm_drift_series["entry"])}
        diffs = by_slug["body-equal-fm-differs"].frontmatter_diffs(
            fm_drift_series["entry"]
        )
        tts_diff = next(d for d in diffs if d.name == "tts")
        assert tts_diff.status == "blog-only"
        assert tts_diff.tier == "blog-owned"


class TestDiffSeriesFrontmatterFlag:
    def test_default_does_not_show_frontmatter_only(self, fm_drift_series, capsys):
        from mf.series.differ import diff_series

        diff_series("fm")
        out = capsys.readouterr().out
        # body-differs is the only drift visible by default
        assert "body-differs" in out
        assert "body-equal-fm-differs" not in out

    def test_frontmatter_flag_surfaces_frontmatter_only_drift(
        self, fm_drift_series, capsys
    ):
        from mf.series.differ import diff_series

        diff_series("fm", frontmatter=True)
        out = capsys.readouterr().out
        assert "body-equal-fm-differs" in out
        assert "frontmatter-only" in out

    def test_frontmatter_flag_renders_field_table_with_tier(
        self, fm_drift_series, capsys
    ):
        from mf.series.differ import diff_series

        diff_series("fm", frontmatter=True)
        out = capsys.readouterr().out
        assert "tts" in out
        assert "blog-owned" in out
        assert "blog-only" in out

    def test_frontmatter_flag_with_post_filter(self, fm_drift_series, capsys):
        from mf.series.differ import diff_series

        diff_series("fm", post="body-equal-fm-differs", frontmatter=True)
        out = capsys.readouterr().out
        assert "tts" in out
        # Body diff helper finds no body differences for this post
        assert "no textual differences" in out or "body-equal-fm-differs" in out


class TestDiffAllFrontmatterFlag:
    def test_rollup_adds_frontmatter_only_column(self, fm_drift_series, capsys):
        from mf.series.differ import diff_all

        diff_all(frontmatter=True)
        out = capsys.readouterr().out
        assert "Frontmatter-only" in out
        assert "fm" in out

    def test_default_rollup_omits_frontmatter_column(self, fm_drift_series, capsys):
        from mf.series.differ import diff_all

        diff_all()
        out = capsys.readouterr().out
        assert "Frontmatter-only" not in out


class TestCliFrontmatterFlag:
    def test_command_accepts_frontmatter_flag(self, fm_drift_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "fm", "--frontmatter"])
        assert result.exit_code == 0
        assert "frontmatter-only" in result.output
        assert "blog-owned" in result.output

    def test_rollup_accepts_frontmatter_flag(self, fm_drift_series):
        runner = CliRunner()
        result = runner.invoke(main, ["series", "diff", "--frontmatter"])
        assert result.exit_code == 0
        assert "Frontmatter-only" in result.output
