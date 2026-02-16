"""
Zenodo API client for DOI registration.

Zenodo is a research data repository that provides DOIs for research outputs.
This module handles creating deposits, uploading metadata and files, and publishing.

API Documentation: https://developers.zenodo.org/

Usage:
    client = ZenodoClient(api_token="your-token", sandbox=False)

    # Create a deposit
    deposit = client.create_deposit()

    # Upload metadata
    client.upload_metadata(deposit["id"], metadata)

    # Upload file
    client.upload_file(deposit["id"], "/path/to/paper.pdf")

    # Publish (get DOI)
    result = client.publish(deposit["id"])
"""

from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests
from rich.console import Console

console = Console()


class ZenodoError(Exception):
    """Base exception for Zenodo API errors."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class ZenodoAuthError(ZenodoError):
    """Authentication error with Zenodo API."""
    pass


class ZenodoValidationError(ZenodoError):
    """Validation error in metadata or request."""
    pass


@dataclass
class ZenodoDeposit:
    """Represents a Zenodo deposit (draft or published)."""

    id: int
    doi: str | None  # Version DOI
    doi_url: str | None
    record_url: str | None
    state: str  # "unsubmitted", "inprogress", "done"
    submitted: bool
    metadata: dict[str, Any]
    conceptdoi: str | None = None  # Concept DOI (points to latest version)
    conceptrecid: int | None = None  # Concept record ID (for creating new versions)
    version: str | None = None  # Version string

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ZenodoDeposit:
        """Create from Zenodo API response."""
        links: dict[str, Any] = data.get("links", {})
        meta: dict[str, Any] = data.get("metadata", {})
        return cls(
            id=int(data["id"]),
            doi=data.get("doi"),
            doi_url=data.get("doi_url"),
            record_url=links.get("record_html"),
            state=str(data.get("state", "unsubmitted")),
            submitted=bool(data.get("submitted", False)),
            metadata=meta,
            conceptdoi=data.get("conceptdoi"),
            conceptrecid=data.get("conceptrecid"),
            version=data.get("metadata", {}).get("version"),
        )


@dataclass
class ZenodoRecord:
    """Represents a published Zenodo record from the public search API."""

    id: int
    doi: str | None
    doi_url: str | None
    conceptdoi: str | None
    title: str
    creators: list[dict[str, str]]
    version: str | None
    record_url: str | None

    @classmethod
    def from_search_hit(cls, hit: dict[str, Any]) -> ZenodoRecord:
        """Create from a search API hit object.

        Args:
            hit: A single entry from the /records/ API hits array.
        """
        metadata: dict[str, Any] = hit.get("metadata", {})
        hit_links: dict[str, Any] = hit.get("links", {})
        return cls(
            id=int(hit["id"]),
            doi=hit.get("doi"),
            doi_url=hit.get("doi_url"),
            conceptdoi=hit.get("conceptdoi"),
            title=str(metadata.get("title", "")),
            creators=list(metadata.get("creators", [])),
            version=metadata.get("version"),
            record_url=hit_links.get("html"),
        )


def _extract_last_name(author: Any) -> str:
    """Extract a normalized last name from various author formats.

    Handles:
        - str: "Alex Towell" -> "towell"
        - dict with "name" key: {"name": "Towell, Alex"} -> "towell"
    """
    name = author.get("name", "") if isinstance(author, dict) else str(author)
    name = name.strip()
    if not name:
        return ""
    # Handle "Last, First" format
    if "," in name:
        return name.split(",")[0].strip().lower()
    # Handle "First Last" format
    parts = name.split()
    return parts[-1].lower() if parts else ""


def compute_match_score(
    paper_title: str,
    paper_authors: list[Any],
    record_title: str,
    record_creators: list[dict[str, str]],
) -> float:
    """Compute a match confidence score between a paper and a Zenodo record.

    Uses title similarity (70% weight) and author name overlap (30% weight).

    Args:
        paper_title: Title from local paper database
        paper_authors: Authors list (strings or dicts with "name" key)
        record_title: Title from Zenodo record
        record_creators: Creators from Zenodo record (dicts with "name" key)

    Returns:
        Float between 0.0 and 1.0
    """
    # Title similarity (70% weight)
    title_score = SequenceMatcher(
        None,
        paper_title.lower().strip(),
        record_title.lower().strip(),
    ).ratio()

    # Author overlap (30% weight)
    paper_last_names = {_extract_last_name(a) for a in paper_authors}
    paper_last_names.discard("")
    record_last_names = {_extract_last_name(c) for c in record_creators}
    record_last_names.discard("")

    if paper_last_names and record_last_names:
        overlap = paper_last_names & record_last_names
        union = paper_last_names | record_last_names
        author_score = len(overlap) / len(union) if union else 0.0
    elif not paper_last_names and not record_last_names:
        # Both empty — don't penalize
        author_score = 1.0
    else:
        author_score = 0.0

    return 0.7 * title_score + 0.3 * author_score


# Mapping from paper categories to Zenodo upload types
CATEGORY_TO_UPLOAD_TYPE: dict[str, tuple[str, str | None]] = {
    # (upload_type, publication_type)
    "research paper": ("publication", "article"),
    "conference paper": ("publication", "conferencepaper"),
    "technical report": ("publication", "technicalnote"),
    "white paper": ("publication", "technicalnote"),
    "Master's Thesis": ("publication", "thesis"),
    "PhD Thesis": ("publication", "thesis"),
    "thesis": ("publication", "thesis"),
    "preprint": ("publication", "preprint"),
    "journal article": ("publication", "article"),
    "R package": ("software", None),
    "Python package": ("software", None),
    "software": ("software", None),
    "library": ("software", None),
    "tool": ("software", None),
    "novel": ("publication", "other"),
    "short story": ("publication", "other"),
    "essay": ("publication", "other"),
    "dataset": ("dataset", None),
    "poster": ("poster", None),
    "presentation": ("presentation", None),
}


def map_paper_to_zenodo_metadata(paper_entry: Any, paper_slug: str) -> dict[str, Any]:
    """Map paper database entry to Zenodo metadata format.

    Args:
        paper_entry: PaperEntry from the database
        paper_slug: Paper slug for reference

    Returns:
        Dictionary with Zenodo metadata format
    """
    data = paper_entry.data

    # Determine upload type based on category
    category = str(data.get("category", "research paper"))
    upload_type, publication_type = CATEGORY_TO_UPLOAD_TYPE.get(
        category, ("publication", "other")
    )

    # Build creators list (Zenodo format)
    creators = []
    for author in paper_entry.authors:
        if isinstance(author, dict):
            creator = {"name": author.get("name", "Unknown")}
            if "affiliation" in author:
                creator["affiliation"] = author["affiliation"]
            if "orcid" in author:
                creator["orcid"] = author["orcid"]
        else:
            # Simple string author
            creator = {"name": str(author)}
        creators.append(creator)

    if not creators:
        creators = [{"name": "Alex Towell"}]  # Default author

    # Build metadata
    metadata: dict[str, Any] = {
        "title": data.get("title", paper_slug),
        "upload_type": upload_type,
        "creators": creators,
        "access_right": "open",
        "license": data.get("license", "cc-by-4.0"),
    }

    # Add publication type if applicable
    if publication_type:
        metadata["publication_type"] = publication_type

    # Description (abstract)
    if abstract := data.get("abstract"):
        metadata["description"] = abstract
    else:
        metadata["description"] = f"Research paper: {data.get('title', paper_slug)}"

    # Publication date
    if date_raw := data.get("date"):
        # Zenodo expects YYYY-MM-DD format
        date_str = str(date_raw)
        if len(date_str) >= 10:
            metadata["publication_date"] = date_str[:10]
        else:
            metadata["publication_date"] = date_str
    else:
        metadata["publication_date"] = datetime.now().strftime("%Y-%m-%d")

    # Keywords (tags)
    if tags := data.get("tags"):
        metadata["keywords"] = tags

    # Related identifiers
    related = []

    # GitHub URL
    if github_url := data.get("github_url"):
        related.append({
            "identifier": github_url,
            "relation": "isSupplementTo",
            "resource_type": "software",
        })

    # External URL
    if ext_url := data.get("external_url"):
        related.append({
            "identifier": ext_url,
            "relation": "isIdenticalTo",
        })

    # ArXiv ID
    if arxiv_id := data.get("arxiv_id"):
        related.append({
            "identifier": f"arXiv:{arxiv_id}",
            "relation": "isIdenticalTo",
            "scheme": "arxiv",
        })

    if related:
        metadata["related_identifiers"] = related

    # References (if we have cite_path or other citations)
    # Note: Zenodo supports references but they need to be in specific format

    # Contributors (advisors for theses)
    if advisors := data.get("advisors"):
        contributors = []
        for advisor in advisors:
            if isinstance(advisor, dict):
                contributors.append({
                    "name": advisor.get("name", "Unknown"),
                    "type": "Supervisor",
                    "affiliation": advisor.get("affiliation", ""),
                })
            else:
                contributors.append({
                    "name": str(advisor),
                    "type": "Supervisor",
                })
        if contributors:
            metadata["contributors"] = contributors

    # Notes
    notes = []
    if venue := data.get("venue"):
        notes.append(f"Published in: {venue}")
    if (status := data.get("status")) and status != "published":
        notes.append(f"Status: {status}")
    if notes:
        metadata["notes"] = " | ".join(notes)

    return metadata


class ZenodoClient:
    """Client for interacting with Zenodo API."""

    PRODUCTION_URL = "https://zenodo.org/api"
    SANDBOX_URL = "https://sandbox.zenodo.org/api"

    def __init__(self, api_token: str, sandbox: bool = False):
        """Initialize Zenodo client.

        Args:
            api_token: Zenodo API token
            sandbox: Use sandbox.zenodo.org for testing
        """
        self.api_token = api_token
        self.sandbox = sandbox
        self.base_url = self.SANDBOX_URL if sandbox else self.PRODUCTION_URL
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_token}",
        })

    # Retry config for 429 rate-limit responses
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2.0  # seconds; doubles each retry

    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        """Make a request to Zenodo API.

        Automatically retries on 429 (rate limit) with exponential backoff.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            json_data: JSON body data
            files: Files to upload
            data: Form data

        Returns:
            JSON response data

        Raises:
            ZenodoError: On API errors
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(1 + self.MAX_RETRIES):
            try:
                response = self._session.request(
                    method,
                    url,
                    json=json_data,
                    files=files,
                    data=data,
                )
            except requests.RequestException as e:
                raise ZenodoError(f"Request failed: {e}") from e

            # Retry on 429 rate limit
            if response.status_code == 429 and attempt < self.MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = self.RETRY_BACKOFF_BASE * (2 ** attempt)
                else:
                    wait = self.RETRY_BACKOFF_BASE * (2 ** attempt)
                console.print(
                    f"[yellow]Rate limited, retrying in {wait:.0f}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})...[/yellow]"
                )
                time.sleep(wait)
                continue

            break  # Not a 429, or exhausted retries

        # Handle authentication errors
        if response.status_code == 401:
            raise ZenodoAuthError(
                "Invalid or expired API token",
                status_code=401,
            )

        # Handle validation errors
        if response.status_code == 400:
            try:
                error_data = response.json()
            except Exception:
                error_data = {"message": response.text}

            raise ZenodoValidationError(
                f"Validation error: {error_data.get('message', error_data)}",
                status_code=400,
                response=error_data,
            )

        # Handle other errors
        if not response.ok:
            try:
                error_data = response.json()
                message = error_data.get("message", response.text)
            except Exception:
                message = response.text

            raise ZenodoError(
                f"API error ({response.status_code}): {message}",
                status_code=response.status_code,
            )

        # Handle empty responses
        if response.status_code == 204 or not response.content:
            return {}

        try:
            result: dict[str, Any] = response.json()
            return result
        except json.JSONDecodeError:
            return {"raw": response.text}

    def test_connection(self) -> bool:
        """Test API connection and authentication.

        Returns:
            True if connection successful
        """
        try:
            # Try to list deposits (requires valid auth)
            self._request("GET", "/deposit/depositions?size=1")
            return True
        except ZenodoAuthError:
            return False
        except ZenodoError as e:
            console.print(f"[yellow]Warning: Connection test returned error: {e}[/yellow]")
            return False

    def search_records(self, query: str, size: int = 10, page: int = 1) -> list[dict]:
        """Search published Zenodo records via GET /records/.

        This uses the public search API (works with or without auth).

        Args:
            query: Elasticsearch query string (e.g., 'title:"My Paper"')
            size: Number of results per page (max 100 with auth)
            page: Page number (1-indexed)

        Returns:
            List of raw hit dicts from the API
        """
        params = urllib.parse.urlencode({"q": query, "size": size, "page": page})
        data = self._request("GET", f"/records/?{params}")
        if isinstance(data, dict):
            hits_outer: dict[str, Any] = data.get("hits", {})
            hits_list: list[dict] = hits_outer.get("hits", [])  # type: ignore[assignment]
            return hits_list
        return []

    def create_deposit(self) -> ZenodoDeposit:
        """Create a new deposit (draft).

        Returns:
            ZenodoDeposit object
        """
        data = self._request("POST", "/deposit/depositions", json_data={})
        return ZenodoDeposit.from_api_response(data)

    def get_deposit(self, deposit_id: int) -> ZenodoDeposit:
        """Get an existing deposit.

        Args:
            deposit_id: Deposit ID

        Returns:
            ZenodoDeposit object
        """
        data = self._request("GET", f"/deposit/depositions/{deposit_id}")
        return ZenodoDeposit.from_api_response(data)

    def update_metadata(self, deposit_id: int, metadata: dict[str, Any]) -> ZenodoDeposit:
        """Update deposit metadata.

        Args:
            deposit_id: Deposit ID
            metadata: Zenodo metadata dictionary

        Returns:
            Updated ZenodoDeposit object
        """
        data = self._request(
            "PUT",
            f"/deposit/depositions/{deposit_id}",
            json_data={"metadata": metadata},
        )
        return ZenodoDeposit.from_api_response(data)

    def upload_file(
        self,
        deposit_id: int,
        file_path: Path | str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to a deposit.

        Args:
            deposit_id: Deposit ID
            file_path: Path to file
            filename: Override filename (defaults to file's name)

        Returns:
            File upload response
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ZenodoError(f"File not found: {file_path}")

        filename = filename or file_path.name

        # Get the bucket URL from deposit
        deposit = self.get_deposit(deposit_id)
        bucket_url = deposit.metadata.get("bucket")

        if bucket_url:
            # New API: Upload directly to bucket
            with open(file_path, "rb") as f:
                response = self._session.put(
                    f"{bucket_url}/{filename}",
                    data=f,
                )
            if not response.ok:
                raise ZenodoError(f"File upload failed: {response.text}")
            result: dict[str, Any] = response.json()
            return result
        else:
            # Legacy API: Use files endpoint
            with open(file_path, "rb") as f:
                return self._request(
                    "POST",
                    f"/deposit/depositions/{deposit_id}/files",
                    files={"file": (filename, f)},
                    data={"name": filename},
                )

    def list_files(self, deposit_id: int) -> list[dict[str, Any]]:
        """List files in a deposit.

        Args:
            deposit_id: Deposit ID

        Returns:
            List of file metadata
        """
        data = self._request("GET", f"/deposit/depositions/{deposit_id}/files")
        return data if isinstance(data, list) else []

    def delete_file(self, deposit_id: int, file_id: str) -> None:
        """Delete a file from a deposit.

        Args:
            deposit_id: Deposit ID
            file_id: File ID
        """
        self._request("DELETE", f"/deposit/depositions/{deposit_id}/files/{file_id}")

    def publish(self, deposit_id: int) -> ZenodoDeposit:
        """Publish a deposit (assign DOI).

        WARNING: This action is irreversible. Once published, a deposit
        cannot be deleted (only new versions can be created).

        Args:
            deposit_id: Deposit ID

        Returns:
            Published ZenodoDeposit with DOI
        """
        data = self._request("POST", f"/deposit/depositions/{deposit_id}/actions/publish")
        return ZenodoDeposit.from_api_response(data)

    def discard(self, deposit_id: int) -> None:
        """Discard an unpublished deposit.

        Args:
            deposit_id: Deposit ID
        """
        self._request("POST", f"/deposit/depositions/{deposit_id}/actions/discard")

    def new_version(self, deposit_id: int) -> ZenodoDeposit:
        """Create a new version of an existing deposit.

        This creates a draft for a new version while keeping the same
        concept DOI. The existing files are copied to the new draft.

        Args:
            deposit_id: Existing deposit ID (any version)

        Returns:
            New draft ZenodoDeposit
        """
        data = self._request("POST", f"/deposit/depositions/{deposit_id}/actions/newversion")
        # The response contains a link to the new draft
        draft_url = data.get("links", {}).get("latest_draft")
        if draft_url:
            # Fetch the actual draft
            response = self._session.get(draft_url)
            if response.ok:
                return ZenodoDeposit.from_api_response(response.json())
        return ZenodoDeposit.from_api_response(data)

    def edit(self, deposit_id: int) -> ZenodoDeposit:
        """Unlock a published deposit for editing (creates new version draft).

        Args:
            deposit_id: Published deposit ID

        Returns:
            Unlocked ZenodoDeposit in edit mode
        """
        data = self._request("POST", f"/deposit/depositions/{deposit_id}/actions/edit")
        return ZenodoDeposit.from_api_response(data)

    def list_deposits(
        self,
        status: str | None = None,
        size: int = 100,
    ) -> list[ZenodoDeposit]:
        """List deposits.

        Args:
            status: Filter by status ("draft", "published")
            size: Number of results

        Returns:
            List of deposits
        """
        params = f"?size={size}"
        if status:
            params += f"&status={status}"

        data = self._request("GET", f"/deposit/depositions{params}")

        if isinstance(data, list):
            return [ZenodoDeposit.from_api_response(d) for d in data]
        return []


def get_zenodo_client(config: dict[str, Any]) -> ZenodoClient | None:
    """Get a Zenodo client from config.

    Args:
        config: Configuration dict (expects zenodo.api_token)

    Returns:
        ZenodoClient or None if not configured
    """
    zenodo_config: dict[str, Any] = config.get("zenodo", {})
    api_token = zenodo_config.get("api_token")

    if not api_token:
        return None

    sandbox = bool(zenodo_config.get("sandbox", False))
    return ZenodoClient(api_token=str(api_token), sandbox=sandbox)


def is_eligible_for_zenodo(paper_entry: Any, min_stars: int = 3) -> bool:
    """Check if a paper is eligible for Zenodo registration.

    Args:
        paper_entry: PaperEntry from database
        min_stars: Minimum star rating (default 3)

    Returns:
        True if eligible
    """
    # Already has DOI from Zenodo
    if (doi := paper_entry.doi) and "zenodo" in doi.lower():
        return False

    # Check star rating
    stars = int(paper_entry.data.get("stars", 0))
    return stars >= min_stars


def find_paper_pdf(paper_entry: Any, static_dir: Path) -> Path | None:
    """Find the PDF file for a paper.

    Args:
        paper_entry: PaperEntry from database
        static_dir: Path to static/ directory

    Returns:
        Path to PDF or None if not found
    """
    # Try pdf_path from database
    if pdf_path_raw := paper_entry.pdf_path:
        # Remove leading slash if present
        pdf_path: str = str(pdf_path_raw).lstrip("/")
        full_path = static_dir / pdf_path
        if full_path.exists():
            return full_path

    # Try standard locations in static/latex/{slug}/
    slug = paper_entry.slug
    latex_dir = static_dir / "latex" / slug

    if latex_dir.exists():
        # Look for PDFs
        pdfs: list[Path] = list(latex_dir.glob("*.pdf"))
        if pdfs:
            # Prefer main.pdf or {slug}.pdf
            for pdf in pdfs:
                if pdf.name in ("main.pdf", f"{slug}.pdf"):
                    return pdf
            return pdfs[0]

    # Try publications directory (for theses etc.)
    pub_dir = static_dir / "publications" / slug
    if pub_dir.exists():
        pub_pdfs: list[Path] = list(pub_dir.glob("*.pdf"))
        if pub_pdfs:
            return pub_pdfs[0]

    return None
