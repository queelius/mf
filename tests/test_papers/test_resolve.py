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
