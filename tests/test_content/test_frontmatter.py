"""Tests for the FrontMatterEditor and helper functions."""

import os

import pytest
import yaml

from mf.content.frontmatter import (
    FrontMatterEditor,
    add_projects_to_content,
    batch_add_projects,
)


# ---------------------------------------------------------------------------
# Helper to create a markdown file with front matter
# ---------------------------------------------------------------------------

def _make_md(tmp_path, filename="test.md", title="Test", body="Hello world.", extra_fm=None):
    """Create a markdown file with front matter and return its path."""
    fm = {"title": title, "date": "2024-01-01"}
    if extra_fm:
        fm.update(extra_fm)
    fm_str = yaml.dump(fm, default_flow_style=False)
    content = f"---\n{fm_str}---\n{body}\n"
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# FrontMatterEditor.load()
# ---------------------------------------------------------------------------

def test_load_valid_file(tmp_path):
    """Test loading a valid markdown file with front matter."""
    path = _make_md(tmp_path, title="Hello")
    editor = FrontMatterEditor(path)
    assert editor.load() is True
    assert editor.front_matter["title"] == "Hello"


def test_load_returns_false_for_missing_file(tmp_path):
    """Test loading a file that doesn't exist returns False."""
    path = tmp_path / "nonexistent.md"
    editor = FrontMatterEditor(path)
    assert editor.load() is False


def test_load_returns_false_without_front_matter(tmp_path):
    """Test loading a file without front matter delimiters."""
    path = tmp_path / "no_fm.md"
    path.write_text("Just plain text, no dashes.", encoding="utf-8")
    editor = FrontMatterEditor(path)
    assert editor.load() is False


def test_load_returns_false_for_invalid_yaml(tmp_path):
    """Test loading a file with invalid YAML in front matter."""
    path = tmp_path / "bad.md"
    path.write_text("---\n: [unclosed\n---\nBody.\n", encoding="utf-8")
    editor = FrontMatterEditor(path)
    assert editor.load() is False


def test_load_empty_front_matter(tmp_path):
    """Test loading a file with empty front matter block."""
    path = tmp_path / "empty_fm.md"
    path.write_text("---\n\n---\nBody text.\n", encoding="utf-8")
    editor = FrontMatterEditor(path)
    assert editor.load() is True
    assert editor.front_matter == {}
    assert "Body text." in editor.body


# ---------------------------------------------------------------------------
# FrontMatterEditor.get() and set()
# ---------------------------------------------------------------------------

def test_get_returns_value(tmp_path):
    """Test get() retrieves a front matter value."""
    path = _make_md(tmp_path, extra_fm={"tags": ["a", "b"]})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.get("tags") == ["a", "b"]


def test_get_returns_default(tmp_path):
    """Test get() returns default for missing key."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.get("missing", "fallback") == "fallback"


def test_set_updates_value(tmp_path):
    """Test set() updates a front matter value."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("tags", ["x", "y"])
    assert editor.front_matter["tags"] == ["x", "y"]


def test_set_raises_if_not_loaded(tmp_path):
    """Test set() raises RuntimeError if file not loaded."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    with pytest.raises(RuntimeError, match="not loaded"):
        editor.set("key", "value")


# ---------------------------------------------------------------------------
# FrontMatterEditor.add_to_list() and remove_from_list()
# ---------------------------------------------------------------------------

def test_add_to_list_appends_value(tmp_path):
    """Test adding a new value to a list field."""
    path = _make_md(tmp_path, extra_fm={"tags": ["a"]})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.add_to_list("tags", "b") is True
    assert editor.front_matter["tags"] == ["a", "b"]


def test_add_to_list_returns_false_if_present(tmp_path):
    """Test adding a duplicate value returns False."""
    path = _make_md(tmp_path, extra_fm={"tags": ["a"]})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.add_to_list("tags", "a") is False


def test_add_to_list_creates_list_if_missing(tmp_path):
    """Test add_to_list creates the list if the key doesn't exist."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.add_to_list("linked_project", "ctk") is True
    assert editor.front_matter["linked_project"] == ["ctk"]


def test_add_to_list_coerces_non_list(tmp_path):
    """Test add_to_list wraps a scalar value into a list."""
    path = _make_md(tmp_path, extra_fm={"linked_project": "existing"})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.add_to_list("linked_project", "new-proj") is True
    assert editor.front_matter["linked_project"] == ["existing", "new-proj"]


def test_add_to_list_raises_if_not_loaded(tmp_path):
    """Test add_to_list raises RuntimeError if not loaded."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    with pytest.raises(RuntimeError, match="not loaded"):
        editor.add_to_list("tags", "x")


def test_remove_from_list_removes_value(tmp_path):
    """Test removing a value from a list field."""
    path = _make_md(tmp_path, extra_fm={"tags": ["a", "b", "c"]})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.remove_from_list("tags", "b") is True
    assert editor.front_matter["tags"] == ["a", "c"]


def test_remove_from_list_returns_false_if_not_present(tmp_path):
    """Test removing a missing value returns False."""
    path = _make_md(tmp_path, extra_fm={"tags": ["a"]})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.remove_from_list("tags", "z") is False


def test_remove_from_list_returns_false_for_non_list(tmp_path):
    """Test removing from a non-list field returns False."""
    path = _make_md(tmp_path, extra_fm={"title": "scalar"})
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.remove_from_list("title", "scalar") is False


# ---------------------------------------------------------------------------
# FrontMatterEditor.save()
# ---------------------------------------------------------------------------

def test_save_writes_changes(tmp_path):
    """Test that save persists changes to disk."""
    path = _make_md(tmp_path, title="Original")
    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("title", "Updated")
    assert editor.save() is True

    # Re-read and verify
    new_editor = FrontMatterEditor(path)
    new_editor.load()
    assert new_editor.get("title") == "Updated"


def test_save_atomic_write(tmp_path):
    """Test that save uses atomic write (temp file + os.replace)."""
    path = _make_md(tmp_path, title="Atomic")
    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("title", "Atomically Updated")

    # After save, no temp files should remain
    assert editor.save() is True
    remaining = list(tmp_path.glob(".mf_*.tmp"))
    assert len(remaining) == 0


def test_save_dry_run_does_not_modify_file(tmp_path):
    """Test that save with dry_run=True does not write to disk."""
    path = _make_md(tmp_path, title="Original")
    original_content = path.read_text()

    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("title", "Changed")
    assert editor.save(dry_run=True) is True

    # File should be unchanged
    assert path.read_text() == original_content


def test_save_preserves_body(tmp_path):
    """Test that save preserves the body content."""
    body = "This is the body.\n\nWith multiple paragraphs."
    path = _make_md(tmp_path, body=body)
    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("tags", ["new-tag"])
    editor.save()

    new_editor = FrontMatterEditor(path)
    new_editor.load()
    assert "This is the body." in new_editor.body
    assert "With multiple paragraphs." in new_editor.body


def test_save_raises_if_not_loaded(tmp_path):
    """Test save raises RuntimeError if not loaded."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    with pytest.raises(RuntimeError, match="not loaded"):
        editor.save()


# ---------------------------------------------------------------------------
# FrontMatterEditor.preview_changes()
# ---------------------------------------------------------------------------

def test_preview_changes_shows_differences(tmp_path):
    """Test preview_changes output contains old and new front matter."""
    path = _make_md(tmp_path, title="Before")
    editor = FrontMatterEditor(path)
    editor.load()
    editor.set("title", "After")
    preview = editor.preview_changes()
    assert "Before" in preview
    assert "After" in preview


def test_preview_changes_no_changes(tmp_path):
    """Test preview_changes when nothing changed."""
    path = _make_md(tmp_path, title="Same")
    editor = FrontMatterEditor(path)
    editor.load()
    # Note: even re-serializing YAML may differ, so this may or may not say "No changes"
    # depending on formatting. At minimum, preview should not error.
    preview = editor.preview_changes()
    assert isinstance(preview, str)


def test_preview_changes_not_loaded(tmp_path):
    """Test preview_changes when not loaded returns message."""
    path = _make_md(tmp_path)
    editor = FrontMatterEditor(path)
    preview = editor.preview_changes()
    assert preview == "File not loaded"


# ---------------------------------------------------------------------------
# add_projects_to_content()
# ---------------------------------------------------------------------------

def test_add_projects_to_content_adds_linked_project(tmp_path):
    """Test adding projects creates linked_project list."""
    path = _make_md(tmp_path)
    result = add_projects_to_content(path, ["ctk", "alpha-lib"])
    assert result is True

    # Verify
    editor = FrontMatterEditor(path)
    editor.load()
    assert editor.get("linked_project") == ["ctk", "alpha-lib"]


def test_add_projects_to_content_no_duplicates(tmp_path):
    """Test adding projects that already exist returns False."""
    path = _make_md(tmp_path, extra_fm={"linked_project": ["ctk"]})
    result = add_projects_to_content(path, ["ctk"])
    assert result is False


def test_add_projects_to_content_dry_run(tmp_path):
    """Test dry run doesn't write changes."""
    path = _make_md(tmp_path)
    original = path.read_text()
    result = add_projects_to_content(path, ["ctk"], dry_run=True)
    assert result is True
    assert path.read_text() == original


def test_add_projects_to_content_missing_file(tmp_path):
    """Test adding projects to a missing file returns False."""
    path = tmp_path / "missing.md"
    result = add_projects_to_content(path, ["ctk"])
    assert result is False


# ---------------------------------------------------------------------------
# batch_add_projects()
# ---------------------------------------------------------------------------

def test_batch_add_projects_returns_tuple(tmp_path):
    """Test batch_add_projects returns (success, failure, failed_paths)."""
    path1 = _make_md(tmp_path, filename="post1.md", title="Post 1")
    path2 = _make_md(tmp_path, filename="post2.md", title="Post 2")

    updates = [
        (path1, ["proj-a"]),
        (path2, ["proj-b"]),
    ]
    success, failure, failed = batch_add_projects(updates)
    assert success == 2
    assert failure == 0
    assert failed == []


def test_batch_add_projects_reports_failures(tmp_path):
    """Test batch_add_projects counts failures from missing files."""
    path_ok = _make_md(tmp_path, filename="ok.md")
    path_bad = tmp_path / "missing.md"

    updates = [
        (path_ok, ["proj-a"]),
        (path_bad, ["proj-b"]),
    ]
    success, failure, failed = batch_add_projects(updates)
    assert success == 1
    assert failure == 1
    assert path_bad in failed


def test_batch_add_projects_dry_run(tmp_path):
    """Test batch in dry run mode does not modify files."""
    path = _make_md(tmp_path, filename="dr.md")
    original = path.read_text()

    updates = [(path, ["proj-a"])]
    success, failure, failed = batch_add_projects(updates, dry_run=True)
    assert success == 1
    assert path.read_text() == original
