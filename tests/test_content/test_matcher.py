"""Tests for the ProjectMatcher and related classes."""

import json

import pytest

from mf.content.matcher import Match, MatchType, ProjectMatcher
from mf.content.scanner import ContentItem


# ---------------------------------------------------------------------------
# MatchType tests
# ---------------------------------------------------------------------------

def test_match_type_values():
    """Test that MatchType enum has the expected members."""
    assert MatchType.GITHUB_URL.value == "github_url"
    assert MatchType.EXACT_SLUG.value == "exact_slug"
    assert MatchType.PROJECT_TITLE.value == "project_title"
    assert MatchType.FUZZY.value == "fuzzy"
    assert MatchType.TAG_OVERLAP.value == "tag_overlap"
    assert MatchType.INTERNAL_LINK.value == "internal_link"


# ---------------------------------------------------------------------------
# Match tests
# ---------------------------------------------------------------------------

def test_match_sort_by_confidence_descending():
    """Test that Match sorts by confidence in descending order."""
    item = ContentItem(path="/f", slug="s", content_type="post", front_matter={})
    m_high = Match(
        content_item=item, project_slug="a",
        match_type=MatchType.GITHUB_URL, confidence=1.0, evidence="url",
    )
    m_low = Match(
        content_item=item, project_slug="b",
        match_type=MatchType.FUZZY, confidence=0.5, evidence="fuzzy",
    )
    # __lt__ is inverted for descending sort
    assert m_high < m_low  # higher confidence sorts first
    sorted_matches = sorted([m_low, m_high])
    assert sorted_matches[0].confidence == 1.0


# ---------------------------------------------------------------------------
# ProjectMatcher._word_match tests
# ---------------------------------------------------------------------------

def _make_matcher(mock_site_root):
    """Helper to build a matcher without loading projects."""
    return ProjectMatcher(site_root=mock_site_root)


def test_word_match_basic(mock_site_root):
    """Test basic word boundary matching."""
    matcher = _make_matcher(mock_site_root)
    assert matcher._word_match("ctk", "The ctk library is useful.") is True
    assert matcher._word_match("ctk", "something-ctk-else") is True
    assert matcher._word_match("ctk", "notkere") is False


def test_word_match_start_and_end(mock_site_root):
    """Test word match at start and end of string."""
    matcher = _make_matcher(mock_site_root)
    assert matcher._word_match("ctk", "ctk is great") is True
    assert matcher._word_match("ctk", "great ctk") is True


def test_word_match_case_insensitive(mock_site_root):
    """Test that word matching is case insensitive."""
    matcher = _make_matcher(mock_site_root)
    assert matcher._word_match("CTK", "The ctk library") is True
    assert matcher._word_match("ctk", "The CTK library") is True


def test_word_match_with_special_chars(mock_site_root):
    """Test word match with regex special characters in the needle."""
    matcher = _make_matcher(mock_site_root)
    # e.g., project name with a dot like "likelihood.model"
    assert matcher._word_match("likelihood.model", "about likelihood.model here") is True


def test_word_match_underscore_separator(mock_site_root):
    """Test word boundary matching with underscore separators."""
    matcher = _make_matcher(mock_site_root)
    assert matcher._word_match("ctk", "use_ctk_lib") is True


# ---------------------------------------------------------------------------
# ProjectMatcher._check_match tests
# ---------------------------------------------------------------------------

def test_check_match_github_url(mock_site_root):
    """Test matching by GitHub URL in body."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={},
        body="See https://github.com/queelius/ctk for details.",
    )
    project = {
        "slug": "ctk", "title": "CTK", "tags": [],
        "github_url": "github.com/queelius/ctk",
    }
    match = matcher._check_match(item, "ctk", project)
    assert match is not None
    assert match.match_type == MatchType.GITHUB_URL
    assert match.confidence == 1.0


def test_check_match_internal_link(mock_site_root):
    """Test matching by internal link to project page."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={},
        body="See the [project page](/projects/ctk/) for more.",
    )
    project = {
        "slug": "ctk", "title": "CTK", "tags": [],
        "github_url": "github.com/queelius/ctk",
    }
    match = matcher._check_match(item, "ctk", project)
    assert match is not None
    assert match.match_type == MatchType.INTERNAL_LINK
    assert match.confidence == 0.95


def test_check_match_project_title(mock_site_root):
    """Test matching by project title appearing in content."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "Exploring Algebraic Types"},
        body="The algebraic-mle library helps with maximum likelihood.",
    )
    project = {
        "slug": "algebraic-mle", "title": "algebraic-mle",
        "tags": [], "github_url": "github.com/queelius/algebraic-mle",
    }
    match = matcher._check_match(item, "algebraic-mle", project)
    assert match is not None
    # Could be EXACT_SLUG or PROJECT_TITLE depending on length
    assert match.match_type in (MatchType.PROJECT_TITLE, MatchType.EXACT_SLUG)


def test_check_match_exact_slug(mock_site_root):
    """Test matching by exact slug mention in text."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-about-stuff", content_type="post",
        front_matter={"title": "My Post"},
        body="I used foobar-lib to build this.",
    )
    project = {
        "slug": "foobar-lib", "title": "Foobar Library",
        "tags": [], "github_url": "github.com/queelius/foobar-lib",
    }
    match = matcher._check_match(item, "foobar-lib", project)
    assert match is not None
    assert match.match_type == MatchType.EXACT_SLUG


def test_check_match_slug_in_title_boosted(mock_site_root):
    """Test that slug appearing in title gets a confidence boost."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "Introducing foobar-lib"},
        body="Nothing here.",
    )
    project = {
        "slug": "foobar-lib", "title": "Foobar Library",
        "tags": [], "github_url": "github.com/queelius/foobar-lib",
    }
    match = matcher._check_match(item, "foobar-lib", project)
    assert match is not None
    assert match.confidence > ProjectMatcher.CONFIDENCE[MatchType.EXACT_SLUG]


def test_check_match_tag_overlap(mock_site_root):
    """Test matching by tag overlap (>=2 shared tags)."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "Unrelated Title", "tags": ["python", "testing", "ci"]},
        body="Body without slug or url.",
    )
    project = {
        "slug": "xyzzy-project", "title": "Xyzzy",
        "tags": ["python", "testing", "deploy"],
        "github_url": "github.com/queelius/xyzzy-project",
    }
    match = matcher._check_match(item, "xyzzy-project", project)
    assert match is not None
    assert match.match_type == MatchType.TAG_OVERLAP


def test_check_match_tag_overlap_requires_two(mock_site_root):
    """Test that a single shared tag is not enough for a match."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "Unrelated", "tags": ["python"]},
        body="No slug or url.",
    )
    project = {
        "slug": "xyzzy-project", "title": "Xyzzy",
        "tags": ["python"], "github_url": "github.com/queelius/xyzzy-project",
    }
    match = matcher._check_match(item, "xyzzy-project", project)
    assert match is None


def test_check_match_skips_already_linked(mock_site_root):
    """Test that content already linked to the project returns None."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"linked_project": ["ctk"]},
        body="https://github.com/queelius/ctk",
    )
    project = {
        "slug": "ctk", "title": "CTK", "tags": [],
        "github_url": "github.com/queelius/ctk",
    }
    match = matcher._check_match(item, "ctk", project)
    assert match is None


def test_check_match_short_slug_ignored(mock_site_root):
    """Test that slugs shorter than MIN_SLUG_LENGTH don't match by slug."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "My Post"},
        body="Just the word ab here.",
    )
    project = {
        "slug": "ab", "title": "AB",
        "tags": [], "github_url": "github.com/queelius/ab",
    }
    match = matcher._check_match(item, "ab", project)
    # Should not match by slug or title (both too short)
    assert match is None


def test_check_match_no_match(mock_site_root):
    """Test that completely unrelated content returns None."""
    matcher = _make_matcher(mock_site_root)
    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "Cooking Recipes", "tags": ["food"]},
        body="Today I made spaghetti bolognese.",
    )
    project = {
        "slug": "foobar-lib", "title": "Foobar Library",
        "tags": ["python", "testing"],
        "github_url": "github.com/queelius/foobar-lib",
    }
    match = matcher._check_match(item, "foobar-lib", project)
    assert match is None


# ---------------------------------------------------------------------------
# ProjectMatcher confidence thresholds
# ---------------------------------------------------------------------------

def test_confidence_ordering():
    """Test that confidence values are ordered logically."""
    assert ProjectMatcher.CONFIDENCE[MatchType.GITHUB_URL] >= ProjectMatcher.CONFIDENCE[MatchType.INTERNAL_LINK]
    assert ProjectMatcher.CONFIDENCE[MatchType.INTERNAL_LINK] >= ProjectMatcher.CONFIDENCE[MatchType.EXACT_SLUG]
    assert ProjectMatcher.CONFIDENCE[MatchType.EXACT_SLUG] >= ProjectMatcher.CONFIDENCE[MatchType.PROJECT_TITLE]
    assert ProjectMatcher.CONFIDENCE[MatchType.PROJECT_TITLE] >= ProjectMatcher.CONFIDENCE[MatchType.FUZZY]
    assert ProjectMatcher.CONFIDENCE[MatchType.FUZZY] >= ProjectMatcher.CONFIDENCE[MatchType.TAG_OVERLAP]


# ---------------------------------------------------------------------------
# Integration-level test with mock projects DB
# ---------------------------------------------------------------------------

def test_matcher_match_content_integration(mock_site_root):
    """Integration test: match_content uses loaded projects."""
    # Set up projects DB and cache so _load_projects works
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "_example": {},
        "alpha-lib": {
            "title": "Alpha Library",
            "tags": ["python"],
        },
    }
    cache_data = {
        "alpha-lib": {"name": "Alpha Library", "topics": ["python"]},
    }
    (mock_site_root / ".mf" / "projects_db.json").write_text(json.dumps(db_data))
    (mock_site_root / ".mf" / "cache" / "projects.json").write_text(json.dumps(cache_data))

    matcher = ProjectMatcher(site_root=mock_site_root)

    item = ContentItem(
        path="/f", slug="post-1", content_type="post",
        front_matter={"title": "About Alpha Library"},
        body="The alpha-lib project is a useful python tool.",
    )
    matches = matcher.match_content(item, threshold=0.5)
    assert len(matches) >= 1
    assert matches[0].project_slug == "alpha-lib"


def test_matcher_get_project_slugs(mock_site_root):
    """Test that get_project_slugs returns slugs from DB."""
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "_example": {},
        "proj-a": {"title": "A"},
        "proj-b": {"title": "B"},
    }
    cache_data = {}
    (mock_site_root / ".mf" / "projects_db.json").write_text(json.dumps(db_data))
    (mock_site_root / ".mf" / "cache" / "projects.json").write_text(json.dumps(cache_data))

    matcher = ProjectMatcher(site_root=mock_site_root)
    slugs = matcher.get_project_slugs()
    assert "proj-a" in slugs
    assert "proj-b" in slugs


def test_matcher_hidden_projects_excluded(mock_site_root):
    """Test that hidden projects are excluded from matching."""
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "_example": {},
        "visible-proj": {"title": "Visible"},
        "hidden-proj": {"title": "Hidden", "hide": True},
    }
    cache_data = {}
    (mock_site_root / ".mf" / "projects_db.json").write_text(json.dumps(db_data))
    (mock_site_root / ".mf" / "cache" / "projects.json").write_text(json.dumps(cache_data))

    matcher = ProjectMatcher(site_root=mock_site_root)
    slugs = matcher.get_project_slugs()
    assert "visible-proj" in slugs
    assert "hidden-proj" not in slugs
