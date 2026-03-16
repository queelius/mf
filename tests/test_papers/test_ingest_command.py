"""Tests for ingest and status CLI commands."""

from unittest.mock import patch

from click.testing import CliRunner

from mf.papers.commands import papers


class TestIngestCommand:
    """Tests for mf papers ingest CLI."""

    @patch("mf.papers.processor.ingest_paper")
    def test_ingest_calls_ingest_paper(self, mock_ingest, mock_site_root):
        mock_ingest.return_value = True
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest", "my-paper"])

        assert result.exit_code == 0
        mock_ingest.assert_called_once_with("my-paper", force=False, dry_run=False)

    @patch("mf.papers.processor.ingest_paper")
    def test_ingest_with_force(self, mock_ingest, mock_site_root):
        mock_ingest.return_value = True
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest", "my-paper", "--force"])

        assert result.exit_code == 0
        mock_ingest.assert_called_once_with("my-paper", force=True, dry_run=False)

    def test_ingest_requires_slug(self, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest"])
        assert result.exit_code != 0


class TestStatusCommand:
    """Tests for mf papers status CLI."""

    @patch("mf.papers.sync.paper_status")
    def test_status_calls_paper_status(self, mock_status, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["status"])

        assert result.exit_code == 0
        mock_status.assert_called_once_with(slug=None)

    @patch("mf.papers.sync.paper_status")
    def test_status_with_slug(self, mock_status, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["status", "--slug", "my-paper"])

        assert result.exit_code == 0
        mock_status.assert_called_once_with(slug="my-paper")


class TestPaperStatusFunction:
    """Integration tests for paper_status function."""

    def test_paper_status_not_found(self, mock_site_root, capsys):
        from mf.papers.sync import paper_status
        paper_status(slug="nonexistent")

    def test_paper_status_up_to_date(self, tmp_path, mock_site_root):
        from mf.core.database import PaperDatabase
        from mf.core.crypto import compute_file_hash
        from mf.papers.sync import paper_status

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        h = compute_file_hash(tex_file)

        db = PaperDatabase()
        db.load()
        db.set("up-paper", {
            "title": "Up",
            "source_path": str(tex_file),
            "source_hash": h,
        })
        db.save()

        paper_status(slug="up-paper")

    def test_paper_status_all(self, mock_site_root):
        from mf.papers.sync import paper_status
        paper_status(slug=None)
