"""Tests for PubEntry and PubsDatabase."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_pub_data():
    return {
        "title": "Test Paper",
        "authors": [{"name": "Alex Towell", "email": "lex@metafunctor.com"}],
        "date": "2026-04-08",
        "status": "draft",
        "type": "conference paper",
        "abstract": "A test abstract.",
        "tags": ["testing"],
        "artifacts": {"pdf": "/latex/test/paper.pdf"},
        "timeline": [{"date": "2026-04-08", "event": "created", "note": "Test"}],
    }


class TestPubEntry:
    def test_create_from_dict(self, sample_pub_data):
        from mf.publications.database import PubEntry

        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        assert entry.slug == "test-paper"
        assert entry.title == "Test Paper"
        assert entry.status == "draft"
        assert entry.type == "conference paper"
        assert entry.artifacts.get("pdf") == "/latex/test/paper.pdf"

    def test_to_dict_roundtrip(self, sample_pub_data):
        from mf.publications.database import PubEntry

        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        data = entry.to_dict()
        assert data["title"] == "Test Paper"
        assert data["status"] == "draft"
        assert data["artifacts"]["pdf"] == "/latex/test/paper.pdf"

    def test_missing_required_field_raises(self):
        from mf.publications.database import PubEntry

        with pytest.raises(ValueError, match="title"):
            PubEntry.from_dict("bad", {"status": "draft", "type": "preprint"})

    def test_invalid_status_raises(self, sample_pub_data):
        from mf.publications.database import PubEntry

        sample_pub_data["status"] = "banana"
        with pytest.raises(ValueError, match="status"):
            PubEntry.from_dict("test", sample_pub_data)

    def test_invalid_type_raises(self, sample_pub_data):
        from mf.publications.database import PubEntry

        sample_pub_data["type"] = "manga"
        with pytest.raises(ValueError, match="type"):
            PubEntry.from_dict("test", sample_pub_data)


class TestPubsDatabase:
    def test_load_empty(self, tmp_path):
        from mf.publications.database import PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        assert len(db) == 0

    def test_set_and_get(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        db.set(entry)
        assert db.get("test-paper") is not None
        assert db.get("test-paper").title == "Test Paper"

    def test_save_and_reload(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db_path = tmp_path / "pubs_db.json"
        db = PubsDatabase(db_path)
        db.load()
        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        db.set(entry)
        db.save()

        db2 = PubsDatabase(db_path)
        db2.load()
        assert len(db2) == 1
        assert db2.get("test-paper").title == "Test Paper"

    def test_remove(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        db.set(PubEntry.from_dict("test-paper", sample_pub_data))
        assert len(db) == 1
        db.remove("test-paper")
        assert len(db) == 0

    def test_iter(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        db.set(PubEntry.from_dict("paper-a", sample_pub_data))
        db.set(PubEntry.from_dict("paper-b", sample_pub_data))
        slugs = list(db)
        assert "paper-a" in slugs
        assert "paper-b" in slugs

    def test_validate_on_set_rejects_bad_entry(self, tmp_path):
        from mf.publications.database import PubEntry

        with pytest.raises(ValueError):
            PubEntry.from_dict("bad", {"status": "draft", "type": "preprint"})
