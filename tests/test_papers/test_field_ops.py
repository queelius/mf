"""Tests for mf.papers.field_ops -- paper-specific field operations."""

import json
import pytest

from mf.papers.field_ops import (
    PAPERS_SCHEMA,
    modify_paper_list_field,
    set_paper_field,
    unset_paper_field,
    validate_paper_field,
)
from mf.core.field_ops import FieldType


# ---------------------------------------------------------------------------
# Schema completeness
# ---------------------------------------------------------------------------


class TestPapersSchema:
    def test_has_core_fields(self):
        for field in ("title", "date", "abstract", "year"):
            assert field in PAPERS_SCHEMA, f"Missing core field: {field}"

    def test_has_author_fields(self):
        assert "authors" in PAPERS_SCHEMA
        assert "advisors" in PAPERS_SCHEMA
        assert PAPERS_SCHEMA["authors"].field_type == FieldType.STRING_LIST

    def test_has_classification_fields(self):
        for field in ("tags", "category", "stars", "featured"):
            assert field in PAPERS_SCHEMA, f"Missing classification field: {field}"

    def test_has_publication_fields(self):
        for field in ("status", "venue", "publication_type", "doi", "arxiv_id"):
            assert field in PAPERS_SCHEMA, f"Missing publication field: {field}"

    def test_has_link_fields(self):
        for field in ("github_url", "project_url", "related_posts"):
            assert field in PAPERS_SCHEMA, f"Missing link field: {field}"

    def test_has_file_path_fields(self):
        for field in ("pdf_path", "html_path", "cite_path"):
            assert field in PAPERS_SCHEMA, f"Missing path field: {field}"

    def test_has_source_fields(self):
        assert "source_path" in PAPERS_SCHEMA
        assert "source_format" in PAPERS_SCHEMA

    def test_stars_constraints(self):
        s = PAPERS_SCHEMA["stars"]
        assert s.min_val == 0
        assert s.max_val == 5

    def test_status_choices(self):
        s = PAPERS_SCHEMA["status"]
        assert s.choices is not None
        assert "published" in s.choices
        assert "preprint" in s.choices

    def test_publication_type_choices(self):
        s = PAPERS_SCHEMA["publication_type"]
        assert "conference" in s.choices
        assert "thesis" in s.choices

    def test_source_format_choices(self):
        s = PAPERS_SCHEMA["source_format"]
        assert "tex" in s.choices
        assert "pregenerated" in s.choices

    def test_zenodo_fields_excluded(self):
        """Zenodo fields should NOT be in the user-settable schema."""
        for field in ("zenodo_doi", "zenodo_url", "zenodo_deposit_id",
                       "zenodo_registered_at", "zenodo_concept_doi", "zenodo_version"):
            assert field not in PAPERS_SCHEMA, f"Zenodo field should be excluded: {field}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidatePaperField:
    def test_valid_stars(self):
        assert validate_paper_field("stars", 3) == []

    def test_invalid_stars(self):
        errors = validate_paper_field("stars", 10)
        assert errors

    def test_valid_status(self):
        assert validate_paper_field("status", "published") == []

    def test_invalid_status(self):
        errors = validate_paper_field("status", "bogus")
        assert any("not a valid choice" in e for e in errors)

    def test_unknown_field(self):
        errors = validate_paper_field("nonexistent", "x")
        assert any("Unknown field" in e for e in errors)


# ---------------------------------------------------------------------------
# set / unset / modify using real PaperDatabase
# ---------------------------------------------------------------------------


@pytest.fixture
def paper_db(tmp_path):
    """Create a PaperDatabase with test data."""
    from mf.core.database import PaperDatabase

    db_path = tmp_path / "paper_db.json"
    data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "test-paper": {
            "title": "Test Paper",
            "stars": 3,
            "tags": ["stats", "ml"],
            "status": "preprint",
        },
    }
    db_path.write_text(json.dumps(data, indent=2))
    db = PaperDatabase(db_path)
    db.load()
    return db


class TestSetPaperField:
    def test_set_simple(self, paper_db):
        result = set_paper_field(paper_db, "test-paper", "stars", 5)
        assert result.old_value == 3
        assert result.new_value == 5
        entry = paper_db.get("test-paper")
        assert entry.data["stars"] == 5

    def test_set_new_field(self, paper_db):
        result = set_paper_field(paper_db, "test-paper", "venue", "NeurIPS")
        assert result.old_value is None
        assert result.new_value == "NeurIPS"

    def test_set_creates_entry(self, paper_db):
        result = set_paper_field(paper_db, "new-paper", "stars", 4)
        assert result.old_value is None
        entry = paper_db.get("new-paper")
        assert entry.data["stars"] == 4


class TestUnsetPaperField:
    def test_unset_field(self, paper_db):
        result = unset_paper_field(paper_db, "test-paper", "stars")
        assert result.old_value == 3
        assert "stars" not in paper_db.get("test-paper").data

    def test_unset_nonexistent_paper_raises(self, paper_db):
        with pytest.raises(KeyError, match="Paper not found"):
            unset_paper_field(paper_db, "nope", "stars")

    def test_unset_absent_field(self, paper_db):
        result = unset_paper_field(paper_db, "test-paper", "venue")
        assert result.old_value is None


class TestModifyPaperListField:
    def test_add_tags(self, paper_db):
        result = modify_paper_list_field(paper_db, "test-paper", "tags", add=["ai"])
        assert "ai" in result.new_value
        assert "stats" in result.new_value

    def test_remove_tags(self, paper_db):
        result = modify_paper_list_field(paper_db, "test-paper", "tags", remove=["ml"])
        assert "ml" not in result.new_value
        assert "stats" in result.new_value

    def test_replace_tags(self, paper_db):
        result = modify_paper_list_field(paper_db, "test-paper", "tags", replace=["a", "b"])
        assert result.new_value == ["a", "b"]
