"""Tests for per-item interactive sync (`prompt_item_interactively`, `execute_sync`)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from mf.cli import main
from mf.core.database import SeriesDatabase
from mf.series.syncer import (
    ConflictResolution,
    InteractiveDecision,
    PostSyncItem,
    SyncAction,
    SyncPlan,
    execute_sync,
    prompt_item_interactively,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_post(post_dir: Path, *, slug_value: str, body: str, title: str = "T") -> None:
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(
        f'---\ntitle: {title}\ndate: 2024-01-01\nseries: ["{slug_value}"]\n---\n\n{body}\n'
    )


def _make_item(
    action: SyncAction,
    slug: str,
    *,
    source: Path | None = None,
    target: Path | None = None,
) -> PostSyncItem:
    return PostSyncItem(slug=slug, action=action, source_path=source, target_path=target)


@pytest.fixture
def add_item(tmp_path):
    src = tmp_path / "src" / "post-add"
    _write_post(src, slug_value="x", body="new")
    return _make_item(SyncAction.ADD, "post-add", source=src, target=tmp_path / "tgt" / "post-add")


@pytest.fixture
def update_item(tmp_path):
    src = tmp_path / "src" / "post-up"
    tgt = tmp_path / "tgt" / "post-up"
    _write_post(src, slug_value="x", body="alpha")
    _write_post(tgt, slug_value="x", body="beta")
    return _make_item(SyncAction.UPDATE, "post-up", source=src, target=tgt)


@pytest.fixture
def conflict_item(tmp_path):
    src = tmp_path / "src" / "post-c"
    tgt = tmp_path / "tgt" / "post-c"
    _write_post(src, slug_value="x", body="alpha")
    _write_post(tgt, slug_value="x", body="beta")
    return _make_item(SyncAction.CONFLICT, "post-c", source=src, target=tgt)


# ---------------------------------------------------------------------------
# prompt_item_interactively
# ---------------------------------------------------------------------------


class TestPromptDecisions:
    """Each terminal choice maps to the expected (decision, resolved) tuple."""

    def test_accept_default_for_non_conflict(self, update_item):
        with patch("click.prompt", return_value="a"):
            decision, resolved = prompt_item_interactively(
                update_item, "pull", index=1, total=1
            )
        assert decision == InteractiveDecision.EXECUTE
        assert resolved is None

    def test_skip(self, update_item):
        with patch("click.prompt", return_value="s"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.SKIP

    def test_quit(self, update_item):
        with patch("click.prompt", return_value="q"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.QUIT

    def test_accept_all_capital(self, update_item):
        with patch("click.prompt", return_value="A"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.ACCEPT_ALL

    def test_accept_all_word(self, update_item):
        with patch("click.prompt", return_value="all"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.ACCEPT_ALL

    def test_diff_then_accept_re_prompts(self, update_item):
        with patch("click.prompt", side_effect=["d", "a"]):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.EXECUTE

    def test_unknown_choice_re_prompts(self, update_item):
        with patch("click.prompt", side_effect=["zzz", "s"]):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.SKIP

    def test_bracketed_input_accepted(self, update_item):
        # Users who copy the prompt format and type [a] should not be punished.
        with patch("click.prompt", return_value="[a]"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.EXECUTE

    def test_bracketed_capital_a_accepted(self, update_item):
        with patch("click.prompt", return_value="[A]"):
            decision, _ = prompt_item_interactively(update_item, "pull", index=1, total=1)
        assert decision == InteractiveDecision.ACCEPT_ALL


class TestPromptConflictTheirs:
    """`[t]heirs` on a conflict resolves via `resolve_conflict` direction logic."""

    def test_theirs_on_pull_resolves_to_update(self, conflict_item):
        with patch("click.prompt", return_value="t"):
            decision, resolved = prompt_item_interactively(
                conflict_item, "pull", index=1, total=1
            )
        # pull + theirs (source) = take source, overwrite target = UPDATE
        assert decision == InteractiveDecision.EXECUTE
        assert resolved == SyncAction.UPDATE

    def test_theirs_on_push_skips(self, conflict_item):
        with patch("click.prompt", return_value="t"):
            decision, resolved = prompt_item_interactively(
                conflict_item, "push", index=1, total=1
            )
        # push + theirs (source) = don't overwrite source = skip
        assert decision == InteractiveDecision.SKIP

    def test_ours_on_push_resolves_to_update(self, conflict_item):
        with patch("click.prompt", return_value="o"):
            decision, resolved = prompt_item_interactively(
                conflict_item, "push", index=1, total=1
            )
        assert decision == InteractiveDecision.EXECUTE
        assert resolved == SyncAction.UPDATE

    def test_ours_on_pull_skips(self, conflict_item):
        with patch("click.prompt", return_value="o"):
            decision, _ = prompt_item_interactively(
                conflict_item, "pull", index=1, total=1
            )
        assert decision == InteractiveDecision.SKIP

    def test_accept_letter_not_offered_for_conflict(self, conflict_item):
        # 'a' is not a valid option for conflicts; should re-prompt.
        with patch("click.prompt", side_effect=["a", "s"]):
            decision, _ = prompt_item_interactively(
                conflict_item, "pull", index=1, total=1
            )
        assert decision == InteractiveDecision.SKIP


# ---------------------------------------------------------------------------
# execute_sync interactive paths
# ---------------------------------------------------------------------------


@pytest.fixture
def two_item_plan(tmp_path, mock_site_root):
    """A plan with one UPDATE and one CONFLICT, with a real db backing."""
    src_root = tmp_path / "src"
    tgt_root = mock_site_root / "content" / "post"

    src_a = src_root / "post-a"
    tgt_a = tgt_root / "post-a"
    _write_post(src_a, slug_value="demo", body="src-body")
    _write_post(tgt_a, slug_value="demo", body="tgt-body")

    src_b = src_root / "post-b"
    tgt_b = tgt_root / "post-b"
    _write_post(src_b, slug_value="demo", body="conflict-src")
    _write_post(tgt_b, slug_value="demo", body="conflict-tgt")

    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(
        json.dumps(
            {
                "_comment": "Test",
                "_schema_version": "1.2",
                "demo": {
                    "title": "Demo",
                    "description": "x",
                    "status": "active",
                    "source_dir": str(src_root.parent),
                    "posts_subdir": src_root.name,
                },
            },
            indent=2,
        )
    )
    db = SeriesDatabase(db_path)
    db.load()

    plan = SyncPlan(
        series_slug="demo",
        direction="pull",
        posts=[
            _make_item(SyncAction.UPDATE, "post-a", source=src_a, target=tgt_a),
            _make_item(SyncAction.CONFLICT, "post-b", source=src_b, target=tgt_b),
        ],
    )
    return {"db": db, "plan": plan, "src_a": src_a, "tgt_a": tgt_a, "tgt_b": tgt_b}


class TestExecuteSyncInteractive:
    def test_skip_then_skip_yields_no_writes(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        original_tgt_a = two_item_plan["tgt_a"] / "index.md"
        original_text = original_tgt_a.read_text()

        with patch("click.prompt", side_effect=["s", "s"]):
            success, failures, skipped = execute_sync(
                plan, db, dry_run=False, interactive=True
            )

        assert success == 0
        assert failures == 0
        assert skipped == 1  # only the CONFLICT counts as skipped_conflicts
        assert original_tgt_a.read_text() == original_text

    def test_quit_aborts_remaining_items(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]

        with patch("click.prompt", return_value="q"):
            success, failures, skipped = execute_sync(
                plan, db, dry_run=False, interactive=True
            )

        # Quit before processing anything; nothing executes.
        assert success == 0
        assert skipped == 0

    def test_accept_all_executes_remaining_silently(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        # First item: accept-all. Second item is a CONFLICT; under accept_all
        # without --ours/--theirs, it falls back to SKIP (the default).
        with patch("click.prompt", return_value="A"):
            success, failures, skipped = execute_sync(
                plan, db, dry_run=False, interactive=True,
                conflict_resolution=ConflictResolution.SKIP,
            )

        # Item 1 (UPDATE) executes; item 2 (CONFLICT) falls back to SKIP.
        assert success == 1
        assert skipped == 1

    def test_accept_all_with_theirs_resolves_remaining_conflicts(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        with patch("click.prompt", return_value="A"):
            success, _, skipped = execute_sync(
                plan, db, dry_run=False, interactive=True,
                conflict_resolution=ConflictResolution.THEIRS,
            )
        # UPDATE executes; CONFLICT with theirs on pull becomes UPDATE.
        assert success == 2
        assert skipped == 0

    def test_per_item_theirs_resolves_one_conflict(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        # Item 1: skip; Item 2 (conflict): pick theirs.
        with patch("click.prompt", side_effect=["s", "t"]):
            success, _, skipped = execute_sync(
                plan, db, dry_run=False, interactive=True
            )
        # Item 1 skipped (not a conflict so doesn't increment skipped_conflicts);
        # item 2 conflict resolved to UPDATE = success.
        assert success == 1
        assert skipped == 0

    def test_conflicts_only_skips_prompt_for_non_conflict(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        # With interactive_conflicts_only, only the second item (CONFLICT)
        # prompts. Provide one input; the UPDATE runs without prompting.
        with patch("click.prompt", return_value="t"):
            success, _, skipped = execute_sync(
                plan, db, dry_run=False,
                interactive=True, interactive_conflicts_only=True,
            )
        # Item 1 ran silently (UPDATE); item 2 prompted theirs -> UPDATE.
        assert success == 2
        assert skipped == 0

    def test_non_interactive_falls_back_to_global_resolution(self, two_item_plan):
        plan, db = two_item_plan["plan"], two_item_plan["db"]
        with patch("click.prompt") as mock_prompt:
            success, _, skipped = execute_sync(
                plan, db, dry_run=False,
                interactive=False,
                conflict_resolution=ConflictResolution.SKIP,
            )
        mock_prompt.assert_not_called()
        # UPDATE runs; CONFLICT skipped under SKIP.
        assert success == 1
        assert skipped == 1


# ---------------------------------------------------------------------------
# CLI flag plumbing
# ---------------------------------------------------------------------------


class TestSyncCliFlags:
    def test_combining_ours_and_theirs_errors(self):
        runner = CliRunner()
        result = runner.invoke(
            main, ["series", "sync", "demo", "--ours", "--theirs"]
        )
        assert "Cannot combine --ours and --theirs" in result.output

    def test_interactive_conflicts_only_without_interactive_warns(
        self, two_item_plan
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["series", "sync", "demo", "--interactive-conflicts-only", "--dry-run"],
        )
        assert "no effect without --interactive" in result.output
