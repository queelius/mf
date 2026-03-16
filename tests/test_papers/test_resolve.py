"""Tests for artifact path resolution."""

from pathlib import Path

import pytest

from mf.core.database import PaperEntry


class TestPaperEntryArtifactProperties:
    """Tests for html_dir and pdf_file_source properties on PaperEntry."""

    def test_html_dir_returns_value(self):
        entry = PaperEntry(slug="test", data={"html_dir": "custom_html"})
        assert entry.html_dir == "custom_html"

    def test_html_dir_returns_none_when_absent(self):
        entry = PaperEntry(slug="test", data={})
        assert entry.html_dir is None

    def test_pdf_file_source_returns_value(self):
        entry = PaperEntry(slug="test", data={"pdf_file_source": "output.pdf"})
        assert entry.pdf_file_source == "output.pdf"

    def test_pdf_file_source_returns_none_when_absent(self):
        entry = PaperEntry(slug="test", data={})
        assert entry.pdf_file_source is None

    def test_source_format_accepts_pdf(self):
        entry = PaperEntry(slug="test", data={"source_format": "pdf"})
        assert entry.source_format == "pdf"


from mf.papers.processor import ArtifactPaths, resolve_artifact_paths


class TestResolveArtifactPaths:
    """Tests for convention-based artifact path resolution."""

    def test_tex_defaults(self, tmp_path):
        """tex format: html_paper/ dir and {stem}.pdf."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html/>")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path == pdf_file

    def test_tex_html_missing(self, tmp_path):
        """tex format: no html_paper/ dir returns None for html_dir."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path == pdf_file

    def test_tex_pdf_missing(self, tmp_path):
        """tex format: no {stem}.pdf returns None for pdf_path."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html/>")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path is None

    def test_tex_custom_stem(self, tmp_path):
        """tex format uses actual stem, not hardcoded 'paper'."""
        tex_file = tmp_path / "cipher_maps.tex"
        tex_file.write_text(r"\documentclass{article}")
        pdf_file = tmp_path / "cipher_maps.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="cipher-maps", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.pdf_path == pdf_file
        assert result.html_dir is None

    def test_pdf_format(self, tmp_path):
        """pdf format: source IS the PDF, no HTML."""
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(pdf_file),
            "source_format": "pdf",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path == pdf_file

    def test_pregenerated_format(self, tmp_path):
        """pregenerated format: source parent is HTML dir, glob for PDF."""
        html_dir = tmp_path / "output"
        html_dir.mkdir()
        index = html_dir / "index.html"
        index.write_text("<html/>")
        pdf_file = html_dir / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(index),
            "source_format": "pregenerated",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path == pdf_file

    def test_pregenerated_no_pdf(self, tmp_path):
        """pregenerated format: no PDF in dir returns None for pdf_path."""
        html_dir = tmp_path / "output"
        html_dir.mkdir()
        index = html_dir / "index.html"
        index.write_text("<html/>")

        entry = PaperEntry(slug="test", data={
            "source_path": str(index),
            "source_format": "pregenerated",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path is None

    def test_override_html_dir(self, tmp_path):
        """html_dir override takes precedence over convention."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        custom_html = tmp_path / "my_html"
        custom_html.mkdir()
        (custom_html / "index.html").write_text("<html/>")

        entry = PaperEntry(slug="test", data={
            "source_path": str(tex_file),
            "html_dir": "my_html",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == custom_html

    def test_override_pdf_file_source(self, tmp_path):
        """pdf_file_source override takes precedence over convention."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        custom_pdf = tmp_path / "build" / "output.pdf"
        custom_pdf.parent.mkdir()
        custom_pdf.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(tex_file),
            "pdf_file_source": "build/output.pdf",
        })
        result = resolve_artifact_paths(entry)

        assert result.pdf_path == custom_pdf

    def test_no_source_path_returns_empty(self):
        """Entry with no source_path returns empty ArtifactPaths."""
        entry = PaperEntry(slug="test", data={})
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path is None


from mf.papers.processor import ingest_paper


class TestIngestPaper:
    """Tests for ingest_paper orchestration."""

    def _make_tex_paper(self, tmp_path, mock_site_root):
        """Create a tex paper with built artifacts."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html>paper</html>")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf content")

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("test-paper", {
            "title": "Test Paper",
            "source_path": str(tex_file),
        })
        db.save()
        return tex_file

    def test_ingest_copies_artifacts(self, tmp_path, mock_site_root):
        """Ingest copies HTML and PDF to /static/latex/{slug}/."""
        self._make_tex_paper(tmp_path, mock_site_root)

        result = ingest_paper("test-paper")

        assert result is True
        target = mock_site_root / "static" / "latex" / "test-paper"
        assert (target / "index.html").exists()
        assert (target / "paper.pdf").exists()

    def test_ingest_updates_source_hash(self, tmp_path, mock_site_root):
        """Ingest updates source_hash in DB."""
        self._make_tex_paper(tmp_path, mock_site_root)

        ingest_paper("test-paper")

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        entry = db.get("test-paper")
        assert entry.source_hash is not None
        assert entry.last_generated is not None

    def test_ingest_skips_unchanged(self, tmp_path, mock_site_root):
        """Ingest skips when source hash unchanged (unless --force)."""
        self._make_tex_paper(tmp_path, mock_site_root)

        ingest_paper("test-paper")
        result = ingest_paper("test-paper")
        assert result is True

    def test_ingest_force_overrides_hash_check(self, tmp_path, mock_site_root):
        """Ingest with force=True always copies."""
        self._make_tex_paper(tmp_path, mock_site_root)

        ingest_paper("test-paper")
        result = ingest_paper("test-paper", force=True)
        assert result is True

    def test_ingest_not_found(self, mock_site_root):
        """Ingest returns False for nonexistent slug."""
        result = ingest_paper("nonexistent")
        assert result is False

    def test_ingest_no_source_path(self, mock_site_root):
        """Ingest returns False when entry has no source_path."""
        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("no-source", {"title": "No Source"})
        db.save()

        result = ingest_paper("no-source")
        assert result is False

    def test_ingest_source_file_missing(self, mock_site_root):
        """Ingest returns False when source file doesn't exist on disk."""
        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("bad-path", {
            "title": "Bad Path",
            "source_path": "/nonexistent/paper.tex",
        })
        db.save()

        result = ingest_paper("bad-path")
        assert result is False

    def test_ingest_no_artifacts(self, tmp_path, mock_site_root):
        """Ingest returns False when no artifacts found."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("empty", {
            "title": "Empty",
            "source_path": str(tex_file),
        })
        db.save()

        result = ingest_paper("empty")
        assert result is False

    def test_ingest_dry_run(self, tmp_path, mock_site_root):
        """Dry run doesn't copy or update DB."""
        self._make_tex_paper(tmp_path, mock_site_root)

        result = ingest_paper("test-paper", dry_run=True)

        assert result is True
        target = mock_site_root / "static" / "latex" / "test-paper"
        assert not target.exists()
