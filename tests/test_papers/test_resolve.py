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
