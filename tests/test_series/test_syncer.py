"""Tests for series synchronization functionality."""

import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch

from mf.core.database import SeriesDatabase, SeriesEntry
from mf.series.syncer import (
    SyncAction,
    PostSyncItem,
    SyncPlan,
    copy_post_directory,
    get_source_posts,
    get_metafunctor_posts,
    plan_pull_sync,
    plan_push_sync,
    execute_sync,
    list_syncable_series,
    compute_post_hash,
    generate_diff,
    ConflictResolution,
    strip_date_prefix,
    _detect_renames,
)


@pytest.fixture
def series_with_source(tmp_path, mock_site_root):
    """Create a series database with source_dir configured."""
    # Create source repo structure
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    (source_dir / "post").mkdir()
    (source_dir / "docs").mkdir()

    # Create a post in source
    post1_dir = source_dir / "post" / "2024-01-01-test-post"
    post1_dir.mkdir()
    (post1_dir / "index.md").write_text("""---
title: Test Post
date: 2024-01-01
series: ["test-series"]
---

Content of test post.
""")
    (post1_dir / "example.cpp").write_text("int main() { return 0; }")

    # Create landing page
    (source_dir / "docs" / "index.md").write_text("""---
title: Test Series
---

Welcome to the test series.
""")

    # Create series database
    data = {
        "_comment": "Test series",
        "_schema_version": "1.2",
        "test-series": {
            "title": "Test Series",
            "description": "A test series",
            "status": "active",
            "source_dir": str(source_dir),
            "posts_subdir": "post",
            "landing_page": "docs/index.md",
        },
        "inline-series": {
            "title": "Inline Series",
            "description": "A series without external source",
            "status": "active",
        },
    }
    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(json.dumps(data, indent=2))

    db = SeriesDatabase(db_path)
    db.load()

    return {
        "db": db,
        "db_path": db_path,
        "source_dir": source_dir,
        "site_root": mock_site_root,
    }


class TestSeriesEntry:
    """Tests for SeriesEntry properties."""

    def test_source_dir_expansion(self, tmp_path):
        """Test that source_dir expands ~ to home directory."""
        entry = SeriesEntry(
            slug="test",
            data={"source_dir": "~/github/test"}
        )
        assert entry.source_dir is not None
        assert "~" not in str(entry.source_dir)
        assert entry.source_dir == Path.home() / "github" / "test"

    def test_has_source(self):
        """Test has_source method."""
        entry_with = SeriesEntry(slug="test", data={"source_dir": "/path"})
        entry_without = SeriesEntry(slug="test", data={})

        assert entry_with.has_source() is True
        assert entry_without.has_source() is False

    def test_posts_subdir_default(self):
        """Test default posts_subdir."""
        entry = SeriesEntry(slug="test", data={})
        assert entry.posts_subdir == "post"

    def test_landing_page_default(self):
        """Test default landing_page."""
        entry = SeriesEntry(slug="test", data={})
        assert entry.landing_page == "docs/index.md"

    def test_sync_state(self):
        """Test sync state management with new format (source + target hashes)."""
        entry = SeriesEntry(slug="test", data={})

        assert entry.sync_state == {}

        # Set with source hash only
        entry.set_sync_state("post-1", source_hash="sha256:abc123")
        state = entry.sync_state["post-1"]
        assert state["source_hash"] == "sha256:abc123"
        assert "last_synced" in state

        # Set with both hashes
        entry.set_sync_state("post-2", source_hash="sha256:def456", target_hash="sha256:ghi789")
        state = entry.sync_state["post-2"]
        assert state["source_hash"] == "sha256:def456"
        assert state["target_hash"] == "sha256:ghi789"

        # Test get_sync_hashes helper
        src, tgt = entry.get_sync_hashes("post-2")
        assert src == "sha256:def456"
        assert tgt == "sha256:ghi789"

        entry.clear_sync_state("post-1")
        assert "post-1" not in entry.sync_state
        assert "post-2" in entry.sync_state

    def test_sync_state_migration(self):
        """Test that old sync state format is migrated to new format."""
        # Old format: plain hash strings
        entry = SeriesEntry(slug="test", data={
            "_sync_state": {
                "post-1": "sha256:old_format_hash",
            }
        })

        # Should migrate to new format
        state = entry.sync_state["post-1"]
        assert state["source_hash"] == "sha256:old_format_hash"
        assert state["target_hash"] is None
        assert state["last_synced"] is None

    def test_associations(self):
        """Test associations property."""
        entry = SeriesEntry(slug="test", data={
            "associations": {
                "papers": ["paper-1", "paper-2"],
                "media": ["book-1"],
                "links": [{"name": "Ref", "url": "https://example.com"}],
            }
        })

        assert entry.related_papers == ["paper-1", "paper-2"]
        assert entry.related_media == ["book-1"]
        assert len(entry.external_links) == 1
        assert entry.external_links[0]["name"] == "Ref"


class TestGetSourcePosts:
    """Tests for get_source_posts function."""

    def test_returns_posts_from_source(self, series_with_source):
        """Test that source posts are found."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        posts = get_source_posts(entry)

        assert "2024-01-01-test-post" in posts
        assert posts["2024-01-01-test-post"].is_dir()

    def test_returns_empty_for_missing_source(self, series_with_source):
        """Test returns empty dict when source doesn't exist."""
        entry = SeriesEntry(
            slug="test",
            data={"source_dir": "/nonexistent/path"}
        )

        posts = get_source_posts(entry)
        assert posts == {}

    def test_returns_empty_for_no_source_config(self, series_with_source):
        """Test returns empty dict when no source_dir configured."""
        db = series_with_source["db"]
        entry = db.get("inline-series")

        posts = get_source_posts(entry)
        assert posts == {}

    def test_filters_by_frontmatter_series(self, series_with_source):
        """Test that posts without matching series in frontmatter are skipped."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Create a post without series frontmatter (should be skipped)
        no_series_post = source_dir / "post" / "2024-01-02-no-series"
        no_series_post.mkdir()
        (no_series_post / "index.md").write_text("""---
title: Post Without Series
date: 2024-01-02
---

No series field in frontmatter.
""")

        # Create a post with different series (should be skipped)
        other_series_post = source_dir / "post" / "2024-01-03-other-series"
        other_series_post.mkdir()
        (other_series_post / "index.md").write_text("""---
title: Post With Other Series
date: 2024-01-03
series: ["different-series"]
---

Belongs to a different series.
""")

        posts = get_source_posts(entry)

        # Only the original test post should be included
        assert "2024-01-01-test-post" in posts
        assert "2024-01-02-no-series" not in posts
        assert "2024-01-03-other-series" not in posts
        assert len(posts) == 1

    def test_handles_series_as_string(self, series_with_source):
        """Test that series field as string (not list) is handled."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Create a post with series as string (not list)
        string_series_post = source_dir / "post" / "2024-01-04-string-series"
        string_series_post.mkdir()
        (string_series_post / "index.md").write_text("""---
title: Post With String Series
date: 2024-01-04
series: "test-series"
---

Series is a string, not a list.
""")

        posts = get_source_posts(entry)

        assert "2024-01-04-string-series" in posts

    def test_skips_malformed_frontmatter(self, series_with_source):
        """Test that posts with malformed frontmatter are skipped."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Create a post with malformed frontmatter
        malformed_post = source_dir / "post" / "2024-01-05-malformed"
        malformed_post.mkdir()
        (malformed_post / "index.md").write_text("""---
title: Malformed
this is not: valid: yaml: frontmatter
---

Content.
""")

        posts = get_source_posts(entry)

        # Malformed post should be skipped, but original should still work
        assert "2024-01-01-test-post" in posts
        assert "2024-01-05-malformed" not in posts


class TestGetMetafunctorPosts:
    """Tests for get_metafunctor_posts function."""

    def test_finds_posts_in_series(self, series_with_source):
        """Test that posts with series frontmatter are found."""
        site_root = series_with_source["site_root"]

        # Create a post in metafunctor with series frontmatter
        post_dir = site_root / "content" / "post" / "2024-02-01-existing-post"
        post_dir.mkdir()
        (post_dir / "index.md").write_text("""---
title: Existing Post
date: 2024-02-01
series: ["test-series"]
---

Content.
""")

        posts = get_metafunctor_posts("test-series")

        assert "2024-02-01-existing-post" in posts

    def test_returns_empty_for_no_matches(self, series_with_source):
        """Test returns empty when no posts match series."""
        posts = get_metafunctor_posts("nonexistent-series")
        assert posts == {}


class TestPlanPullSync:
    """Tests for plan_pull_sync function."""

    def test_detects_new_posts(self, series_with_source):
        """Test that new posts in source are detected."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry)

        assert not plan.errors
        assert plan.add_count >= 1

        # Find the new post
        new_posts = [p for p in plan.posts if p.action == SyncAction.ADD]
        assert len(new_posts) >= 1
        assert any(p.slug == "2024-01-01-test-post" for p in new_posts)

    def test_detects_landing_page_add(self, series_with_source):
        """Test that new landing page is detected."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry)

        assert plan.landing_page is not None
        assert plan.landing_page.action == SyncAction.ADD

    def test_errors_when_no_source_dir(self, series_with_source):
        """Test errors when source_dir not configured."""
        db = series_with_source["db"]
        entry = db.get("inline-series")

        plan = plan_pull_sync(entry)

        assert len(plan.errors) > 0
        assert "No source_dir" in plan.errors[0]

    def test_posts_only_flag(self, series_with_source):
        """Test posts-only flag skips landing page."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry, include_landing=False)

        assert plan.landing_page is None


class TestPlanPushSync:
    """Tests for plan_push_sync function."""

    def test_detects_new_posts_in_metafunctor(self, series_with_source):
        """Test that new posts in metafunctor are detected for push."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        entry = db.get("test-series")

        # Create a post only in metafunctor
        post_dir = site_root / "content" / "post" / "2024-03-01-new-post"
        post_dir.mkdir()
        (post_dir / "index.md").write_text("""---
title: New Post
date: 2024-03-01
series: ["test-series"]
---

New content.
""")

        plan = plan_push_sync(entry)

        assert not plan.errors
        # Should detect the new post for push
        new_posts = [p for p in plan.posts if p.action == SyncAction.ADD]
        assert any(p.slug == "2024-03-01-new-post" for p in new_posts)


class TestSyncPlan:
    """Tests for SyncPlan properties."""

    def test_has_changes_when_add(self):
        """Test has_changes returns True when there are adds."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[PostSyncItem(slug="post1", action=SyncAction.ADD)],
        )
        assert plan.has_changes is True

    def test_has_changes_when_update(self):
        """Test has_changes returns True when there are updates."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[PostSyncItem(slug="post1", action=SyncAction.UPDATE)],
        )
        assert plan.has_changes is True

    def test_has_changes_when_remove(self):
        """Test has_changes returns True when there are removes."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[PostSyncItem(slug="post1", action=SyncAction.REMOVE)],
        )
        assert plan.has_changes is True

    def test_no_changes_when_unchanged(self):
        """Test has_changes returns False when all unchanged."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[PostSyncItem(slug="post1", action=SyncAction.UNCHANGED)],
        )
        assert plan.has_changes is False

    def test_counts(self):
        """Test add/update/remove/unchanged counts."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[
                PostSyncItem(slug="add1", action=SyncAction.ADD),
                PostSyncItem(slug="add2", action=SyncAction.ADD),
                PostSyncItem(slug="update1", action=SyncAction.UPDATE),
                PostSyncItem(slug="remove1", action=SyncAction.REMOVE),
                PostSyncItem(slug="unchanged1", action=SyncAction.UNCHANGED),
                PostSyncItem(slug="unchanged2", action=SyncAction.UNCHANGED),
            ],
        )

        assert plan.add_count == 2
        assert plan.update_count == 1
        assert plan.remove_count == 1
        assert plan.unchanged_count == 2


class TestExecuteSync:
    """Tests for execute_sync function."""

    def test_dry_run_makes_no_changes(self, series_with_source):
        """Test that dry run doesn't modify files."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry)

        success, failures, skipped = execute_sync(plan, db, dry_run=True)

        # Should report success but not create files
        target_post = site_root / "content" / "post" / "2024-01-01-test-post"
        assert not target_post.exists()

    def test_sync_creates_post(self, series_with_source):
        """Test that sync creates new posts."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry)
        success, failures, skipped = execute_sync(plan, db, dry_run=False)

        # Check post was created
        target_post = site_root / "content" / "post" / "2024-01-01-test-post"
        assert target_post.exists()
        assert (target_post / "index.md").exists()
        assert (target_post / "example.cpp").exists()

    def test_sync_creates_landing_page(self, series_with_source):
        """Test that sync creates landing page."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        entry = db.get("test-series")

        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Check landing page was created
        landing = site_root / "content" / "series" / "test-series" / "_index.md"
        assert landing.exists()

    def test_landing_page_unchanged_after_sync(self, series_with_source):
        """Regression: landing page should be UNCHANGED on re-sync when nothing changed."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        # First sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Re-plan without any changes
        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        # Landing page should be unchanged
        assert plan.landing_page is not None
        assert plan.landing_page.action == SyncAction.UNCHANGED

    def test_sync_updates_sync_state(self, series_with_source):
        """Test that sync updates the sync state in database."""
        db = series_with_source["db"]
        entry = db.get("test-series")

        # Initial state should be empty
        assert entry.sync_state == {}

        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Reload database and check sync state was updated
        db.load()
        entry = db.get("test-series")
        state = entry.sync_state.get("2024-01-01-test-post", {})
        assert "source_hash" in state
        assert "target_hash" in state
        assert "last_synced" in state


class TestListSyncableSeries:
    """Tests for list_syncable_series function."""

    def test_returns_only_series_with_source(self, series_with_source):
        """Test that only series with source_dir are returned."""
        db = series_with_source["db"]

        syncable = list_syncable_series(db)

        slugs = [e.slug for e in syncable]
        assert "test-series" in slugs
        assert "inline-series" not in slugs


class TestConflictDetection:
    """Tests for conflict detection functionality."""

    def test_detects_conflict_when_both_changed(self, series_with_source):
        """Test that conflicts are detected when both source and target changed."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # First, do an initial sync to establish baseline
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Now modify the post in source
        source_post = source_dir / "post" / "2024-01-01-test-post" / "index.md"
        source_post.write_text("""---
title: Test Post - Modified in Source
date: 2024-01-01
series: ["test-series"]
---

Content modified in SOURCE.
""")

        # And modify the post in metafunctor (target)
        target_post = site_root / "content" / "post" / "2024-01-01-test-post" / "index.md"
        target_post.write_text("""---
title: Test Post - Modified in Metafunctor
date: 2024-01-01
series: ["test-series"]
---

Content modified in METAFUNCTOR.
""")

        # Reload database to get updated sync state
        db.load()
        entry = db.get("test-series")

        # Plan should detect conflict
        plan = plan_pull_sync(entry)

        assert plan.conflict_count >= 1
        conflicts = plan.conflicts
        assert any(c.slug == "2024-01-01-test-post" for c in conflicts)

    def test_no_conflict_when_only_source_changed(self, series_with_source):
        """Test no conflict when only source changed (safe to pull)."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # First, do an initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Now modify only the source
        source_post = source_dir / "post" / "2024-01-01-test-post" / "index.md"
        source_post.write_text("""---
title: Test Post - Modified in Source Only
date: 2024-01-01
series: ["test-series"]
---

Content modified in SOURCE only.
""")

        # Reload and plan
        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        # Should be an UPDATE, not a CONFLICT
        assert plan.conflict_count == 0
        updates = [p for p in plan.posts if p.action == SyncAction.UPDATE]
        assert any(p.slug == "2024-01-01-test-post" for p in updates)


class TestConflictResolution:
    """Tests for conflict resolution functionality."""

    def test_skip_conflicts_by_default(self, series_with_source):
        """Test that conflicts are skipped by default."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Create conflict - need to write proper frontmatter so posts are recognized
        source_post = source_dir / "post" / "2024-01-01-test-post" / "index.md"
        source_post.write_text("""---
title: Modified in Source
date: 2024-01-01
series: ["test-series"]
---

Content modified in SOURCE.
""")

        target_post = site_root / "content" / "post" / "2024-01-01-test-post" / "index.md"
        target_post.write_text("""---
title: Modified in Metafunctor
date: 2024-01-01
series: ["test-series"]
---

Content modified in METAFUNCTOR.
""")

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        # Execute with default (skip) resolution
        success, failures, skipped = execute_sync(plan, db, dry_run=False)

        assert skipped >= 1

        # Target should still have metafunctor content (not overwritten)
        assert "METAFUNCTOR" in target_post.read_text()

    def test_theirs_resolution_overwrites_target(self, series_with_source):
        """Test that --theirs resolution overwrites target with source."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Create conflict
        source_content = """---
title: Source Version
date: 2024-01-01
series: ["test-series"]
---

Source wins!
"""
        source_post = source_dir / "post" / "2024-01-01-test-post" / "index.md"
        source_post.write_text(source_content)

        target_post = site_root / "content" / "post" / "2024-01-01-test-post" / "index.md"
        target_post.write_text("Modified in metafunctor")

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        # Execute with THEIRS resolution
        success, failures, skipped = execute_sync(
            plan, db, dry_run=False,
            conflict_resolution=ConflictResolution.THEIRS
        )

        # Target should now have source content
        assert "Source wins!" in target_post.read_text()


class TestDiffGeneration:
    """Tests for diff generation functionality."""

    def test_generate_diff_shows_changes(self, series_with_source):
        """Test that diff is generated correctly."""
        source_dir = series_with_source["source_dir"]
        site_root = series_with_source["site_root"]

        # Create different content in source and target
        source_post = source_dir / "post" / "2024-01-01-test-post"
        target_post = site_root / "content" / "post" / "2024-01-01-test-post"
        target_post.mkdir(parents=True, exist_ok=True)

        (source_post / "index.md").write_text("""---
title: Source Title
---

Line A
Line B
""")

        (target_post / "index.md").write_text("""---
title: Target Title
---

Line A
Line C
""")

        diff_lines = generate_diff(source_post, target_post)

        # Should have diff content
        assert len(diff_lines) > 0

        # Join to check for expected content
        diff_text = "\n".join(diff_lines)
        assert "Source Title" in diff_text or "Target Title" in diff_text
        assert "-Line B" in diff_text or "+Line C" in diff_text


class TestSyncPlanConflicts:
    """Tests for SyncPlan conflict properties."""

    def test_conflict_count(self):
        """Test conflict_count property."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[
                PostSyncItem(slug="conflict1", action=SyncAction.CONFLICT),
                PostSyncItem(slug="conflict2", action=SyncAction.CONFLICT),
                PostSyncItem(slug="normal", action=SyncAction.UPDATE),
            ],
        )
        assert plan.conflict_count == 2

    def test_conflicts_property(self):
        """Test conflicts property returns only conflicted items."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[
                PostSyncItem(slug="conflict1", action=SyncAction.CONFLICT),
                PostSyncItem(slug="normal", action=SyncAction.UPDATE),
                PostSyncItem(slug="conflict2", action=SyncAction.CONFLICT),
            ],
        )
        conflicts = plan.conflicts
        assert len(conflicts) == 2
        assert all(c.action == SyncAction.CONFLICT for c in conflicts)

    def test_has_changes_with_conflicts(self):
        """Test has_changes returns True when there are conflicts."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[PostSyncItem(slug="conflict1", action=SyncAction.CONFLICT)],
        )
        assert plan.has_changes is True


class TestCopyPostDirectory:
    """Tests for copy_post_directory with merge behavior."""

    def test_copy_updates_existing_target(self, tmp_path):
        """Test that copy updates files in an existing target directory."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.md").write_text("new content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "index.md").write_text("old content")

        copy_post_directory(source, target)

        assert target.exists()
        assert (target / "index.md").read_text() == "new content"

    def test_copy_creates_new_target(self, tmp_path):
        """Test copy when target does not exist."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.md").write_text("content")

        target = tmp_path / "target"
        assert not target.exists()

        copy_post_directory(source, target)

        assert target.exists()
        assert (target / "index.md").read_text() == "content"

    def test_copy_preserves_extra_files_in_target(self, tmp_path):
        """Extra files in target (e.g., .hpp, .cpp) are preserved."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.md").write_text("new content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "index.md").write_text("old content")
        (target / "code.hpp").write_text("// C++ header")
        (target / "test_code.cpp").write_text("// test file")

        copy_post_directory(source, target)

        assert (target / "index.md").read_text() == "new content"
        assert (target / "code.hpp").read_text() == "// C++ header"
        assert (target / "test_code.cpp").read_text() == "// test file"

    def test_copy_preserves_extra_subdirectories_in_target(self, tmp_path):
        """Extra subdirectories in target are preserved."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.md").write_text("content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "index.md").write_text("old")
        examples = target / "examples"
        examples.mkdir()
        (examples / "main.cpp").write_text("int main() {}")

        copy_post_directory(source, target)

        assert (target / "index.md").read_text() == "content"
        assert (target / "examples" / "main.cpp").read_text() == "int main() {}"

    def test_copy_preserves_target_on_copytree_failure(self, tmp_path):
        """If copytree fails before writing, the original target survives."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "index.md").write_text("new content")

        target = tmp_path / "target"
        target.mkdir()
        (target / "index.md").write_text("precious data")

        def failing_copytree(*args, **kwargs):
            raise OSError("Simulated disk error")

        with patch("mf.series.syncer.shutil.copytree", side_effect=failing_copytree):
            with pytest.raises(OSError, match="Simulated disk error"):
                copy_post_directory(source, target)

        assert target.exists()
        assert (target / "index.md").read_text() == "precious data"


class TestComputePostHash:
    """Tests for compute_post_hash — hashes only index.md."""

    def test_hash_depends_only_on_index_md(self, tmp_path):
        """Hash is the same regardless of extra files in the directory."""
        # Directory with only index.md
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "index.md").write_text("# Hello\n\nContent here.\n")

        # Directory with index.md + extra files
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        (dir_b / "index.md").write_text("# Hello\n\nContent here.\n")
        (dir_b / "code.hpp").write_text("// C++ code")
        (dir_b / "test.cpp").write_text("// test")
        sub = dir_b / "examples"
        sub.mkdir()
        (sub / "main.cpp").write_text("int main() {}")

        assert compute_post_hash(dir_a) == compute_post_hash(dir_b)

    def test_hash_changes_when_index_md_changes(self, tmp_path):
        """Hash differs when index.md content differs."""
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "index.md").write_text("version 1")

        dir_b = tmp_path / "b"
        dir_b.mkdir()
        (dir_b / "index.md").write_text("version 2")

        assert compute_post_hash(dir_a) != compute_post_hash(dir_b)

    def test_hash_raises_without_index_md(self, tmp_path):
        """Raises FileNotFoundError if directory has no index.md."""
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(FileNotFoundError, match="No index.md"):
            compute_post_hash(empty)

    def test_hash_format(self, tmp_path):
        """Hash has sha256: prefix."""
        post = tmp_path / "post"
        post.mkdir()
        (post / "index.md").write_text("content")

        h = compute_post_hash(post)
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64  # sha256 hex digest


class TestFirstSyncConflictDetection:
    """Regression tests for asymmetric conflict detection on first sync (Fix #9)."""

    def test_first_sync_detects_diverged_target(self, series_with_source):
        """When stored_target_hash is None but target exists with different
        content than source, it should be detected as a conflict."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Create the same post slug in metafunctor with DIFFERENT content
        target_post = site_root / "content" / "post" / "2024-01-01-test-post"
        target_post.mkdir(parents=True, exist_ok=True)
        (target_post / "index.md").write_text("""---
title: Test Post - DIVERGED
date: 2024-01-01
series: ["test-series"]
---

This content diverges from the source.
""")

        # No sync state exists yet (first sync)
        assert entry.sync_state == {}

        plan = plan_pull_sync(entry)

        # The post should be detected as a conflict since target differs from source
        # and there's no stored hash to tell us which side changed.
        conflicted = [p for p in plan.posts if p.slug == "2024-01-01-test-post"]
        assert len(conflicted) == 1
        assert conflicted[0].action == SyncAction.CONFLICT


class TestStripDatePrefix:
    """Tests for strip_date_prefix() helper."""

    def test_strips_full_date(self):
        assert strip_date_prefix("2024-01-01-test-post") == "test-post"

    def test_preserves_partial_date(self):
        # 2025-10-ctk has only year-month, not full YYYY-MM-DD-
        assert strip_date_prefix("2025-10-ctk") == "2025-10-ctk"

    def test_preserves_bare_slug(self):
        assert strip_date_prefix("algotree") == "algotree"

    def test_strips_only_first_date(self):
        assert strip_date_prefix("2024-01-01-2024-02-02-post") == "2024-02-02-post"


class TestDetectRenames:
    """Tests for _detect_renames() function."""

    def test_detects_date_change_rename(self):
        """ADD + REMOVE with same base slug -> RENAME."""
        plan = SyncPlan(series_slug="test", direction="pull", posts=[
            PostSyncItem(slug="2025-07-15-chop", action=SyncAction.ADD,
                         source_path=Path("/src/2025-07-15-chop"),
                         target_path=Path("/tgt/2025-07-15-chop")),
            PostSyncItem(slug="2026-01-30-chop", action=SyncAction.REMOVE,
                         target_path=Path("/tgt/2026-01-30-chop")),
        ])
        _detect_renames(plan)

        renames = [p for p in plan.posts if p.action == SyncAction.RENAME]
        assert len(renames) == 1
        assert renames[0].slug == "2025-07-15-chop"
        assert renames[0].old_slug == "2026-01-30-chop"
        # REMOVE item should be gone
        removes = [p for p in plan.posts if p.action == SyncAction.REMOVE]
        assert len(removes) == 0

    def test_no_rename_for_different_bases(self):
        """ADD and REMOVE with different base slugs stay as-is."""
        plan = SyncPlan(series_slug="test", direction="pull", posts=[
            PostSyncItem(slug="2025-01-01-foo", action=SyncAction.ADD),
            PostSyncItem(slug="2024-01-01-bar", action=SyncAction.REMOVE),
        ])
        _detect_renames(plan)

        assert plan.add_count == 1
        assert plan.remove_count == 1
        assert plan.rename_count == 0

    def test_no_rename_for_ambiguous_match(self):
        """Two removes with same base slug -> no rename (ambiguous)."""
        plan = SyncPlan(series_slug="test", direction="pull", posts=[
            PostSyncItem(slug="2025-01-01-post", action=SyncAction.ADD),
            PostSyncItem(slug="2024-01-01-post", action=SyncAction.REMOVE),
            PostSyncItem(slug="2023-06-01-post", action=SyncAction.REMOVE),
        ])
        _detect_renames(plan)

        # Should leave everything as-is (ambiguous)
        assert plan.rename_count == 0
        assert plan.add_count == 1
        assert plan.remove_count == 2

    def test_bare_slug_no_rename(self):
        """Bare slugs can't rename to themselves (same base = same slug)."""
        plan = SyncPlan(series_slug="test", direction="pull", posts=[
            PostSyncItem(slug="algotree", action=SyncAction.ADD),
            PostSyncItem(slug="entropy_map", action=SyncAction.REMOVE),
        ])
        _detect_renames(plan)

        assert plan.rename_count == 0

    def test_push_direction_uses_source_path_for_old(self):
        """In push direction, old_path should be the source path of the remove."""
        plan = SyncPlan(series_slug="test", direction="push", posts=[
            PostSyncItem(slug="2025-07-15-chop", action=SyncAction.ADD,
                         source_path=Path("/src/2025-07-15-chop"),
                         target_path=Path("/tgt/2025-07-15-chop")),
            PostSyncItem(slug="2026-01-30-chop", action=SyncAction.REMOVE,
                         source_path=Path("/src/2026-01-30-chop")),
        ])
        _detect_renames(plan)

        renames = [p for p in plan.posts if p.action == SyncAction.RENAME]
        assert len(renames) == 1
        assert renames[0].old_path == Path("/src/2026-01-30-chop")


class TestPlanPullSyncRename:
    """Integration tests for rename detection in pull sync planner."""

    def test_detects_date_rename_in_pull(self, series_with_source):
        """Renaming a post date in source is detected as rename during pull."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Rename the post in source (change date)
        old_post = source_dir / "post" / "2024-01-01-test-post"
        new_post = source_dir / "post" / "2025-07-15-test-post"
        old_post.rename(new_post)

        # Reload and re-plan
        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        assert plan.rename_count == 1
        assert plan.add_count == 0
        assert plan.remove_count == 0

        rename = [p for p in plan.posts if p.action == SyncAction.RENAME][0]
        assert rename.slug == "2025-07-15-test-post"
        assert rename.old_slug == "2024-01-01-test-post"

    def test_rename_leaves_unrelated_posts_alone(self, series_with_source):
        """Rename detection doesn't affect unrelated ADD/REMOVE posts."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Rename one post and add a genuinely new post
        old_post = source_dir / "post" / "2024-01-01-test-post"
        new_post = source_dir / "post" / "2025-07-15-test-post"
        old_post.rename(new_post)

        new_post2 = source_dir / "post" / "2024-06-01-brand-new"
        new_post2.mkdir()
        (new_post2 / "index.md").write_text('---\ntitle: Brand New\nseries: ["test-series"]\n---\n')

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        assert plan.rename_count == 1
        assert plan.add_count == 1  # brand-new is genuinely new

    def test_rename_with_bare_slug_no_false_match(self, series_with_source):
        """A bare-slug post removed + date-prefixed post added = no rename."""
        db = series_with_source["db"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Create a bare-slug post in source
        bare_post_src = source_dir / "post" / "bare-post"
        bare_post_src.mkdir()
        (bare_post_src / "index.md").write_text('---\ntitle: Bare\nseries: ["test-series"]\n---\n')

        # Sync it
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Now remove bare-post from source and add a date-prefixed one
        shutil.rmtree(bare_post_src)
        new_post = source_dir / "post" / "2025-01-01-different"
        new_post.mkdir()
        (new_post / "index.md").write_text('---\ntitle: Different\nseries: ["test-series"]\n---\n')

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)

        # These have different base slugs, so no rename
        assert plan.rename_count == 0


class TestExecuteSyncRename:
    """Tests for rename execution."""

    def test_execute_rename_pull(self, series_with_source):
        """Execute a rename during pull: copies new, deletes old, migrates state."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Rename post in source
        old_src = source_dir / "post" / "2024-01-01-test-post"
        new_src = source_dir / "post" / "2025-07-15-test-post"
        old_src.rename(new_src)

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)
        success, failures, skipped = execute_sync(plan, db, dry_run=False)

        assert success >= 1
        assert failures == 0

        # New target should exist, old should not
        new_target = site_root / "content" / "post" / "2025-07-15-test-post"
        old_target = site_root / "content" / "post" / "2024-01-01-test-post"
        assert new_target.exists()
        assert not old_target.exists()

        # Sync state should track new slug, not old
        db.load()
        entry = db.get("test-series")
        assert "2025-07-15-test-post" in entry.sync_state
        assert "2024-01-01-test-post" not in entry.sync_state

    def test_execute_rename_dry_run(self, series_with_source):
        """Dry run rename should not modify filesystem or sync state."""
        db = series_with_source["db"]
        site_root = series_with_source["site_root"]
        source_dir = series_with_source["source_dir"]
        entry = db.get("test-series")

        # Initial sync
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=False)

        # Rename in source
        old_src = source_dir / "post" / "2024-01-01-test-post"
        new_src = source_dir / "post" / "2025-07-15-test-post"
        old_src.rename(new_src)

        db.load()
        entry = db.get("test-series")
        plan = plan_pull_sync(entry)
        execute_sync(plan, db, dry_run=True)

        # Old target should still exist, new should not
        old_target = site_root / "content" / "post" / "2024-01-01-test-post"
        new_target = site_root / "content" / "post" / "2025-07-15-test-post"
        assert old_target.exists()
        assert not new_target.exists()

    def test_rename_count_in_plan(self):
        """SyncPlan.rename_count works correctly."""
        plan = SyncPlan(
            series_slug="test",
            direction="pull",
            posts=[
                PostSyncItem(slug="new", action=SyncAction.RENAME, old_slug="old"),
                PostSyncItem(slug="other", action=SyncAction.ADD),
                PostSyncItem(slug="unchanged", action=SyncAction.UNCHANGED),
            ],
        )
        assert plan.rename_count == 1
        assert plan.has_changes is True
