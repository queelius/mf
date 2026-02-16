"""Tests for Zenodo integration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mf.papers.zenodo import (
    CATEGORY_TO_UPLOAD_TYPE,
    ZenodoClient,
    ZenodoDeposit,
    ZenodoError,
    ZenodoAuthError,
    ZenodoRecord,
    ZenodoValidationError,
    compute_match_score,
    find_paper_pdf,
    is_eligible_for_zenodo,
    map_paper_to_zenodo_metadata,
)


# -----------------------------------------------------------------------------
# ZenodoDeposit tests
# -----------------------------------------------------------------------------


class TestZenodoDeposit:
    """Tests for ZenodoDeposit dataclass."""

    def test_from_api_response_minimal(self):
        """Test creating deposit from minimal API response."""
        data = {
            "id": 12345,
            "state": "unsubmitted",
            "submitted": False,
        }
        deposit = ZenodoDeposit.from_api_response(data)

        assert deposit.id == 12345
        assert deposit.state == "unsubmitted"
        assert deposit.submitted is False
        assert deposit.doi is None
        assert deposit.conceptdoi is None

    def test_from_api_response_full(self):
        """Test creating deposit from full API response."""
        data = {
            "id": 12345,
            "doi": "10.5281/zenodo.12345",
            "doi_url": "https://doi.org/10.5281/zenodo.12345",
            "conceptdoi": "10.5281/zenodo.12344",
            "conceptrecid": 12344,
            "state": "done",
            "submitted": True,
            "links": {
                "record_html": "https://zenodo.org/record/12345",
            },
            "metadata": {
                "title": "Test Paper",
                "version": "1",
            },
        }
        deposit = ZenodoDeposit.from_api_response(data)

        assert deposit.id == 12345
        assert deposit.doi == "10.5281/zenodo.12345"
        assert deposit.doi_url == "https://doi.org/10.5281/zenodo.12345"
        assert deposit.conceptdoi == "10.5281/zenodo.12344"
        assert deposit.conceptrecid == 12344
        assert deposit.state == "done"
        assert deposit.submitted is True
        assert deposit.version == "1"


# -----------------------------------------------------------------------------
# ZenodoClient tests
# -----------------------------------------------------------------------------


class TestZenodoClient:
    """Tests for ZenodoClient class."""

    def test_init_production(self):
        """Test client initialization for production."""
        client = ZenodoClient(api_token="test-token", sandbox=False)
        assert client.base_url == "https://zenodo.org/api"
        assert client.sandbox is False

    def test_init_sandbox(self):
        """Test client initialization for sandbox."""
        client = ZenodoClient(api_token="test-token", sandbox=True)
        assert client.base_url == "https://sandbox.zenodo.org/api"
        assert client.sandbox is True

    @patch("requests.Session.request")
    def test_create_deposit(self, mock_request):
        """Test creating a new deposit."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "state": "unsubmitted",
            "submitted": False,
            "metadata": {},
        }
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        deposit = client.create_deposit()

        assert deposit.id == 12345
        assert deposit.state == "unsubmitted"

    @patch("requests.Session.request")
    def test_auth_error(self, mock_request):
        """Test handling of authentication errors."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="bad-token", sandbox=True)
        with pytest.raises(ZenodoAuthError):
            client.create_deposit()

    @patch("requests.Session.request")
    def test_validation_error(self, mock_request):
        """Test handling of validation errors."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "message": "Invalid metadata",
        }
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        with pytest.raises(ZenodoValidationError) as exc_info:
            client.create_deposit()
        assert "Invalid metadata" in str(exc_info.value)

    @patch("requests.Session.request")
    def test_test_connection_success(self, mock_request):
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        assert client.test_connection() is True

    @patch("requests.Session.request")
    def test_test_connection_failure(self, mock_request):
        """Test failed connection test."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="bad-token", sandbox=True)
        assert client.test_connection() is False

    @patch("mf.papers.zenodo.time.sleep")
    @patch("requests.Session.request")
    def test_retries_on_429(self, mock_request, mock_sleep):
        """Test that 429 rate limit triggers retry with backoff."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.ok = False
        rate_limit_response.headers = {"Retry-After": "3"}
        rate_limit_response.text = "30 per 1 minute"

        success_response = MagicMock()
        success_response.ok = True
        success_response.status_code = 200
        success_response.content = b'{"hits":{"hits":[]}}'
        success_response.json.return_value = {"hits": {"hits": []}}

        # First call returns 429, second succeeds
        mock_request.side_effect = [rate_limit_response, success_response]

        client = ZenodoClient(api_token="test-token", sandbox=True)
        results = client.search_records("test query")

        assert results == []
        assert mock_request.call_count == 2
        # Should have slept for the Retry-After value
        mock_sleep.assert_called_once_with(3.0)

    @patch("mf.papers.zenodo.time.sleep")
    @patch("requests.Session.request")
    def test_429_exhausts_retries(self, mock_request, mock_sleep):
        """Test that exhausting retries on 429 raises ZenodoError."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.ok = False
        rate_limit_response.headers = {}
        rate_limit_response.text = "30 per 1 minute"
        rate_limit_response.json.return_value = {"message": "30 per 1 minute"}

        # All calls return 429
        mock_request.return_value = rate_limit_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        with pytest.raises(ZenodoError, match="429"):
            client.search_records("test query")

        # 1 initial + 3 retries = 4 total
        assert mock_request.call_count == 4
        assert mock_sleep.call_count == 3


# -----------------------------------------------------------------------------
# Metadata mapping tests
# -----------------------------------------------------------------------------


class TestMetadataMapping:
    """Tests for paper to Zenodo metadata mapping."""

    def test_category_mapping_research_paper(self):
        """Test mapping for research paper category."""
        upload_type, pub_type = CATEGORY_TO_UPLOAD_TYPE["research paper"]
        assert upload_type == "publication"
        assert pub_type == "article"

    def test_category_mapping_thesis(self):
        """Test mapping for thesis category."""
        upload_type, pub_type = CATEGORY_TO_UPLOAD_TYPE["Master's Thesis"]
        assert upload_type == "publication"
        assert pub_type == "thesis"

    def test_category_mapping_software(self):
        """Test mapping for software category."""
        upload_type, pub_type = CATEGORY_TO_UPLOAD_TYPE["Python package"]
        assert upload_type == "software"
        assert pub_type is None

    def test_map_paper_minimal(self):
        """Test mapping paper with minimal data."""
        paper = MagicMock()
        paper.data = {
            "title": "Test Paper",
        }
        paper.authors = []

        metadata = map_paper_to_zenodo_metadata(paper, "test-paper")

        assert metadata["title"] == "Test Paper"
        assert metadata["upload_type"] == "publication"
        assert metadata["access_right"] == "open"
        assert len(metadata["creators"]) == 1  # Default author

    def test_map_paper_full(self):
        """Test mapping paper with full data."""
        paper = MagicMock()
        paper.data = {
            "title": "Full Test Paper",
            "abstract": "This is an abstract",
            "date": "2024-01-15",
            "category": "conference paper",
            "tags": ["machine-learning", "ai"],
            "github_url": "https://github.com/test/repo",
            "venue": "Test Conference 2024",
        }
        paper.authors = [
            {"name": "Alice Author", "affiliation": "University"},
            {"name": "Bob Coauthor"},
        ]

        metadata = map_paper_to_zenodo_metadata(paper, "full-test")

        assert metadata["title"] == "Full Test Paper"
        assert metadata["description"] == "This is an abstract"
        assert metadata["publication_date"] == "2024-01-15"
        assert metadata["upload_type"] == "publication"
        assert metadata["publication_type"] == "conferencepaper"
        assert metadata["keywords"] == ["machine-learning", "ai"]
        assert len(metadata["creators"]) == 2
        assert metadata["creators"][0]["name"] == "Alice Author"
        assert metadata["creators"][0]["affiliation"] == "University"
        assert "Test Conference 2024" in metadata.get("notes", "")

    def test_map_paper_with_advisors(self):
        """Test mapping thesis with advisors."""
        paper = MagicMock()
        paper.data = {
            "title": "My Thesis",
            "category": "Master's Thesis",
            "advisors": [
                {"name": "Dr. Advisor", "affiliation": "University"},
            ],
        }
        paper.authors = [{"name": "Student Name"}]

        metadata = map_paper_to_zenodo_metadata(paper, "thesis")

        assert "contributors" in metadata
        assert len(metadata["contributors"]) == 1
        assert metadata["contributors"][0]["name"] == "Dr. Advisor"
        assert metadata["contributors"][0]["type"] == "Supervisor"


# -----------------------------------------------------------------------------
# Eligibility tests
# -----------------------------------------------------------------------------


class TestEligibility:
    """Tests for paper eligibility checking."""

    def test_eligible_with_high_stars(self):
        """Test paper with high stars is eligible."""
        paper = MagicMock()
        paper.data = {"stars": 4}
        paper.doi = None

        assert is_eligible_for_zenodo(paper, min_stars=3) is True

    def test_not_eligible_with_low_stars(self):
        """Test paper with low stars is not eligible."""
        paper = MagicMock()
        paper.data = {"stars": 2}
        paper.doi = None

        assert is_eligible_for_zenodo(paper, min_stars=3) is False

    def test_not_eligible_already_on_zenodo(self):
        """Test paper already on Zenodo is not eligible."""
        paper = MagicMock()
        paper.data = {"stars": 5}
        paper.doi = "10.5281/zenodo.12345"

        assert is_eligible_for_zenodo(paper, min_stars=3) is False

    def test_eligible_with_non_zenodo_doi(self):
        """Test paper with non-Zenodo DOI is eligible."""
        paper = MagicMock()
        paper.data = {"stars": 4}
        paper.doi = "10.1109/EXAMPLE.2024"

        assert is_eligible_for_zenodo(paper, min_stars=3) is True


# -----------------------------------------------------------------------------
# PDF finding tests
# -----------------------------------------------------------------------------


class TestFindPaperPdf:
    """Tests for finding paper PDFs."""

    def test_find_from_pdf_path(self, tmp_path):
        """Test finding PDF from explicit path."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        pdf = static_dir / "latex" / "test" / "main.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_text("fake pdf")

        paper = MagicMock()
        paper.slug = "test"
        paper.pdf_path = "/latex/test/main.pdf"

        result = find_paper_pdf(paper, static_dir)
        assert result == pdf

    def test_find_from_latex_dir(self, tmp_path):
        """Test finding PDF from standard latex directory."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        pdf = static_dir / "latex" / "test-paper" / "test-paper.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_text("fake pdf")

        paper = MagicMock()
        paper.slug = "test-paper"
        paper.pdf_path = None

        result = find_paper_pdf(paper, static_dir)
        assert result == pdf

    def test_not_found(self, tmp_path):
        """Test when no PDF exists."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        paper = MagicMock()
        paper.slug = "missing"
        paper.pdf_path = None

        result = find_paper_pdf(paper, static_dir)
        assert result is None

    def test_find_from_publications_dir(self, tmp_path):
        """Test finding PDF from publications directory."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        pdf = static_dir / "publications" / "thesis" / "thesis.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_text("fake pdf")

        paper = MagicMock()
        paper.slug = "thesis"
        paper.pdf_path = None

        result = find_paper_pdf(paper, static_dir)
        assert result == pdf


# -----------------------------------------------------------------------------
# PaperEntry zenodo properties tests
# -----------------------------------------------------------------------------


class TestPaperEntryZenodo:
    """Tests for PaperEntry zenodo properties."""

    def test_zenodo_properties_empty(self):
        """Test zenodo properties when not set."""
        from mf.core.database import PaperEntry

        entry = PaperEntry(slug="test", data={})

        assert entry.zenodo_deposit_id is None
        assert entry.zenodo_doi is None
        assert entry.zenodo_url is None
        assert entry.zenodo_concept_doi is None
        assert entry.zenodo_version == 1
        assert entry.has_zenodo() is False

    def test_zenodo_properties_set(self):
        """Test zenodo properties when set."""
        from mf.core.database import PaperEntry

        entry = PaperEntry(slug="test", data={
            "zenodo_deposit_id": 12345,
            "zenodo_doi": "10.5281/zenodo.12345",
            "zenodo_url": "https://zenodo.org/record/12345",
            "zenodo_concept_doi": "10.5281/zenodo.12344",
            "zenodo_version": 2,
        })

        assert entry.zenodo_deposit_id == 12345
        assert entry.zenodo_doi == "10.5281/zenodo.12345"
        assert entry.zenodo_url == "https://zenodo.org/record/12345"
        assert entry.zenodo_concept_doi == "10.5281/zenodo.12344"
        assert entry.zenodo_version == 2
        assert entry.has_zenodo() is True

    def test_set_zenodo_registration(self):
        """Test setting zenodo registration."""
        from mf.core.database import PaperEntry

        entry = PaperEntry(slug="test", data={})
        entry.set_zenodo_registration(
            deposit_id=12345,
            doi="10.5281/zenodo.12345",
            url="https://zenodo.org/record/12345",
            concept_doi="10.5281/zenodo.12344",
            version=1,
        )

        assert entry.zenodo_deposit_id == 12345
        assert entry.zenodo_doi == "10.5281/zenodo.12345"
        assert entry.zenodo_concept_doi == "10.5281/zenodo.12344"
        assert entry.zenodo_registered_at is not None

    def test_stars_property(self):
        """Test stars property."""
        from mf.core.database import PaperEntry

        entry_no_stars = PaperEntry(slug="test", data={})
        assert entry_no_stars.stars == 0

        entry_with_stars = PaperEntry(slug="test", data={"stars": 4})
        assert entry_with_stars.stars == 4


# -----------------------------------------------------------------------------
# ZenodoRecord tests
# -----------------------------------------------------------------------------


class TestZenodoRecord:
    """Tests for ZenodoRecord dataclass."""

    def test_from_search_hit(self):
        """Test parsing a full API search hit."""
        hit = {
            "id": 99999,
            "doi": "10.5281/zenodo.99999",
            "doi_url": "https://doi.org/10.5281/zenodo.99999",
            "conceptdoi": "10.5281/zenodo.99998",
            "links": {"html": "https://zenodo.org/record/99999"},
            "metadata": {
                "title": "Exposition of Masked Fill-in Models",
                "creators": [
                    {"name": "Towell, Alex"},
                    {"name": "Smith, Jane"},
                ],
                "version": "1.0",
            },
        }
        record = ZenodoRecord.from_search_hit(hit)

        assert record.id == 99999
        assert record.doi == "10.5281/zenodo.99999"
        assert record.doi_url == "https://doi.org/10.5281/zenodo.99999"
        assert record.conceptdoi == "10.5281/zenodo.99998"
        assert record.title == "Exposition of Masked Fill-in Models"
        assert len(record.creators) == 2
        assert record.creators[0]["name"] == "Towell, Alex"
        assert record.version == "1.0"
        assert record.record_url == "https://zenodo.org/record/99999"

    def test_from_search_hit_minimal(self):
        """Test parsing a search hit with missing optional fields."""
        hit = {
            "id": 11111,
            "metadata": {
                "title": "Minimal Record",
            },
        }
        record = ZenodoRecord.from_search_hit(hit)

        assert record.id == 11111
        assert record.doi is None
        assert record.doi_url is None
        assert record.conceptdoi is None
        assert record.title == "Minimal Record"
        assert record.creators == []
        assert record.version is None
        assert record.record_url is None


# -----------------------------------------------------------------------------
# compute_match_score tests
# -----------------------------------------------------------------------------


class TestComputeMatchScore:
    """Tests for compute_match_score function."""

    def test_exact_match(self):
        """Exact title + authors should produce score close to 1.0."""
        score = compute_match_score(
            paper_title="Exposition of Masked Fill-in Models",
            paper_authors=["Alex Towell"],
            record_title="Exposition of Masked Fill-in Models",
            record_creators=[{"name": "Towell, Alex"}],
        )
        assert score > 0.95

    def test_no_match(self):
        """Completely unrelated title and authors should score low."""
        score = compute_match_score(
            paper_title="Exposition of Masked Fill-in Models",
            paper_authors=["Alex Towell"],
            record_title="Introduction to Quantum Computing for Beginners",
            record_creators=[{"name": "Doe, John"}],
        )
        assert score < 0.5

    def test_partial_title_match(self):
        """Similar titles with different authors → intermediate score."""
        score = compute_match_score(
            paper_title="Algebraic Hashing for Content-Addressable Storage",
            paper_authors=["Alex Towell"],
            record_title="Algebraic Hashing: A Content-Addressable Approach",
            record_creators=[{"name": "Towell, Alex"}],
        )
        # Should be moderate-to-high because title is similar and author matches
        assert 0.5 < score < 1.0

    def test_no_authors(self):
        """Missing authors on both sides should not penalize score."""
        score = compute_match_score(
            paper_title="Same Title Exactly",
            paper_authors=[],
            record_title="Same Title Exactly",
            record_creators=[],
        )
        # 0.7 * 1.0 (exact title) + 0.3 * 1.0 (both empty) = 1.0
        assert score > 0.95

    def test_dict_authors(self):
        """Authors as dicts with 'name' key should work."""
        score = compute_match_score(
            paper_title="Test Paper",
            paper_authors=[{"name": "Alice Author"}, {"name": "Bob Coauthor"}],
            record_title="Test Paper",
            record_creators=[{"name": "Author, Alice"}, {"name": "Coauthor, Bob"}],
        )
        assert score > 0.95

    def test_one_side_no_authors(self):
        """One side with authors and other without should reduce score."""
        score = compute_match_score(
            paper_title="Same Title",
            paper_authors=["Alex Towell"],
            record_title="Same Title",
            record_creators=[],
        )
        # 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert abs(score - 0.7) < 0.05


# -----------------------------------------------------------------------------
# ZenodoClient search_records tests
# -----------------------------------------------------------------------------


class TestSearchRecords:
    """Tests for ZenodoClient.search_records method."""

    @patch("requests.Session.request")
    def test_search_records_success(self, mock_request):
        """Successful search returns parsed hits."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"hits":{"hits":[{"id":1}]}}'
        mock_response.json.return_value = {
            "hits": {
                "total": 1,
                "hits": [
                    {
                        "id": 99999,
                        "doi": "10.5281/zenodo.99999",
                        "metadata": {"title": "Found Paper"},
                    }
                ],
            }
        }
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        results = client.search_records('title:"Found Paper"')

        assert len(results) == 1
        assert results[0]["id"] == 99999

    @patch("requests.Session.request")
    def test_search_records_empty(self, mock_request):
        """No results returns empty list."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"hits":{"hits":[]}}'
        mock_response.json.return_value = {
            "hits": {"total": 0, "hits": []},
        }
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        results = client.search_records('title:"Nonexistent Paper"')

        assert results == []

    @patch("requests.Session.request")
    def test_search_records_api_error(self, mock_request):
        """API error raises ZenodoError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}
        mock_response.text = "Internal Server Error"
        mock_request.return_value = mock_response

        client = ZenodoClient(api_token="test-token", sandbox=True)
        with pytest.raises(ZenodoError):
            client.search_records("broken query")


# -----------------------------------------------------------------------------
# CLI import command tests
# -----------------------------------------------------------------------------


def _make_search_hit(
    record_id: int = 99999,
    doi: str = "10.5281/zenodo.99999",
    title: str = "Test Paper",
    creators: list | None = None,
) -> dict:
    """Helper to create a Zenodo search API hit."""
    return {
        "id": record_id,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}",
        "conceptdoi": f"10.5281/zenodo.{record_id - 1}",
        "links": {"html": f"https://zenodo.org/record/{record_id}"},
        "metadata": {
            "title": title,
            "creators": creators or [{"name": "Towell, Alex"}],
        },
    }


class TestZenodoImportCommand:
    """Tests for the 'mf papers zenodo import' CLI command."""

    @pytest.fixture
    def mock_db_and_client(self, tmp_path, monkeypatch):
        """Set up a mock paper database and Zenodo client."""
        from mf.core import config

        # Set up site root
        mf_dir = tmp_path / ".mf"
        mf_dir.mkdir()
        (mf_dir / "backups" / "papers").mkdir(parents=True)

        db_data = {
            "_comment": "Test",
            "_schema_version": "2.0",
            "test-paper": {
                "title": "Test Paper on Algebraic Hashing",
                "authors": ["Alex Towell"],
                "category": "research paper",
                "stars": 4,
            },
            "registered-paper": {
                "title": "Already Registered Paper",
                "authors": ["Alex Towell"],
                "zenodo_doi": "10.5281/zenodo.11111",
                "zenodo_url": "https://zenodo.org/record/11111",
                "zenodo_deposit_id": 11111,
            },
        }
        db_path = mf_dir / "paper_db.json"
        db_path.write_text(json.dumps(db_data, indent=2))

        # Config file with zenodo token
        config_path = mf_dir / "config.yaml"
        config_path.write_text("zenodo:\n  api_token: fake-token\n  sandbox: true\n")

        config.get_site_root.cache_clear()
        monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

        return tmp_path

    def test_import_single_paper(self, mock_db_and_client):
        """Import zenodo fields for a single paper."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        hit = _make_search_hit(
            record_id=99999,
            doi="10.5281/zenodo.99999",
            title="Test Paper on Algebraic Hashing",
            creators=[{"name": "Towell, Alex"}],
        )

        mock_client = MagicMock()
        mock_client.search_records.return_value = [hit]

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(papers, ["zenodo", "import", "test-paper"], obj=MagicMock(dry_run=False))

        assert result.exit_code == 0, result.output
        assert "Imported" in result.output
        assert "10.5281/zenodo.99999" in result.output

    def test_import_dry_run(self, mock_db_and_client):
        """Dry run should not save database."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        hit = _make_search_hit(title="Test Paper on Algebraic Hashing")

        mock_client = MagicMock()
        mock_client.search_records.return_value = [hit]

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(
                papers, ["zenodo", "import", "test-paper"],
                obj=MagicMock(dry_run=True),
            )

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output or "dry" in result.output.lower()

    def test_import_no_match(self, mock_db_and_client):
        """Reports when no Zenodo record found."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        mock_client = MagicMock()
        mock_client.search_records.return_value = []

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(papers, ["zenodo", "import", "test-paper"], obj=MagicMock(dry_run=False))

        assert result.exit_code == 0, result.output
        assert "No match" in result.output or "no match" in result.output.lower()

    def test_import_already_registered(self, mock_db_and_client):
        """Skips papers that already have zenodo_doi."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        mock_client = MagicMock()

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(
                papers, ["zenodo", "import", "registered-paper"],
                obj=MagicMock(dry_run=False),
            )

        assert result.exit_code == 0, result.output
        assert "already registered" in result.output.lower()
        # Client should not have been asked to search
        mock_client.search_records.assert_not_called()

    def test_import_json_output(self, mock_db_and_client):
        """--json outputs candidates without importing."""
        import re

        from click.testing import CliRunner

        from mf.papers.commands import papers

        hit = _make_search_hit(
            record_id=99999,
            doi="10.5281/zenodo.99999",
            title="Test Paper on Algebraic Hashing",
        )

        mock_client = MagicMock()
        mock_client.search_records.return_value = [hit]

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(
                papers, ["zenodo", "import", "--all", "--json"],
                obj=MagicMock(dry_run=False),
            )

        assert result.exit_code == 0, result.output
        # Strip ANSI escape codes from Rich output
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        # Find the JSON array in the output (may have console prefix text)
        json_start = clean.find("[")
        assert json_start >= 0, f"No JSON array found in output: {clean!r}"
        output_json = json.loads(clean[json_start:])
        assert isinstance(output_json, list)
        # Only test-paper should be in results (registered-paper is skipped)
        assert len(output_json) == 1
        assert output_json[0]["slug"] == "test-paper"
        assert len(output_json[0]["candidates"]) == 1

    def test_import_no_slug_and_no_all(self, mock_db_and_client):
        """Should error when neither slug nor --all provided."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        runner = CliRunner()
        result = runner.invoke(
            papers, ["zenodo", "import"],
            obj=MagicMock(dry_run=False),
        )

        assert result.exit_code != 0

    def test_import_paper_not_found(self, mock_db_and_client):
        """Should error when slug doesn't exist in database."""
        from click.testing import CliRunner

        from mf.papers.commands import papers

        mock_client = MagicMock()

        with patch("mf.papers.commands._get_zenodo_client", return_value=(mock_client, True)):
            runner = CliRunner()
            result = runner.invoke(
                papers, ["zenodo", "import", "nonexistent"],
                obj=MagicMock(dry_run=False),
            )

        assert result.exit_code != 0
