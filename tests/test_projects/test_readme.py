"""Tests for mf.projects.readme — relative URL rewriting in GitHub READMEs."""

import pytest

from mf.projects.readme import rewrite_readme_urls


REPO_URL = "https://github.com/user/test-repo"
BRANCH = "main"


# -- Inline link tests --

class TestInlineLinks:
    """Tests for [text](url) rewriting."""

    def test_relative_path(self):
        md = "[API](docs/api.md)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[API](https://github.com/user/test-repo/blob/main/docs/api.md)"

    def test_dot_slash_prefix(self):
        md = "[Guide](./docs/guide.md)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[Guide](https://github.com/user/test-repo/blob/main/docs/guide.md)"

    def test_link_with_title(self):
        md = '[Guide](docs/guide.md "The Guide")'
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == '[Guide](https://github.com/user/test-repo/blob/main/docs/guide.md "The Guide")'

    def test_directory_link_uses_tree(self):
        md = "[Docs](docs/)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[Docs](https://github.com/user/test-repo/tree/main/docs/)"

    def test_license_link(self):
        md = "[License](LICENSE)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[License](https://github.com/user/test-repo/blob/main/LICENSE)"

    def test_nested_path(self):
        md = "[Config](src/config/default.yaml)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[Config](https://github.com/user/test-repo/blob/main/src/config/default.yaml)"


# -- Image tests --

class TestImages:
    """Tests for ![alt](url) rewriting to raw.githubusercontent.com."""

    def test_relative_image(self):
        md = "![Logo](images/logo.png)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "![Logo](https://raw.githubusercontent.com/user/test-repo/main/images/logo.png)"

    def test_dot_slash_image(self):
        md = "![Icon](./assets/icon.svg)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "![Icon](https://raw.githubusercontent.com/user/test-repo/main/assets/icon.svg)"

    def test_image_with_title(self):
        md = '![Logo](logo.png "Project Logo")'
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == '![Logo](https://raw.githubusercontent.com/user/test-repo/main/logo.png "Project Logo")'

    def test_absolute_image_unchanged(self):
        md = "![Badge](https://img.shields.io/badge/test-passing-green)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == md


# -- Skip cases --

class TestSkipCases:
    """URLs that should NOT be rewritten."""

    @pytest.mark.parametrize("md", [
        "[Site](https://example.com)",
        "[Site](http://example.com)",
        "[Site](//cdn.example.com/file.js)",
    ])
    def test_absolute_urls_unchanged(self, md):
        assert rewrite_readme_urls(md, REPO_URL, BRANCH) == md

    def test_anchor_unchanged(self):
        md = "[Section](#installation)"
        assert rewrite_readme_urls(md, REPO_URL, BRANCH) == md

    def test_mailto_unchanged(self):
        md = "[Email](mailto:user@example.com)"
        assert rewrite_readme_urls(md, REPO_URL, BRANCH) == md

    def test_data_uri_unchanged(self):
        md = "![Dot](data:image/png;base64,ABC123)"
        assert rewrite_readme_urls(md, REPO_URL, BRANCH) == md


# -- Badge pattern (nested image+link) --

class TestBadgePattern:
    """Badge: [![Badge](https://...)](relative-url)."""

    def test_badge_with_relative_link(self):
        md = "[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        # The image URL (absolute) stays the same; the outer link (relative) is rewritten
        assert "https://img.shields.io/badge/license-MIT-blue" in result
        assert "https://github.com/user/test-repo/blob/main/LICENSE" in result

    def test_badge_with_absolute_link(self):
        md = "[![CI](https://img.shields.io/badge/ci-passing-green)](https://github.com/user/test-repo/actions)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == md


# -- Reference-style definitions --

class TestReferenceDefinitions:
    """Tests for [ref]: url rewriting."""

    def test_simple_refdef(self):
        md = "[docs]: docs/api.md"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[docs]: https://github.com/user/test-repo/blob/main/docs/api.md"

    def test_refdef_with_title(self):
        md = '[docs]: docs/api.md "API Docs"'
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == '[docs]: https://github.com/user/test-repo/blob/main/docs/api.md "API Docs"'

    def test_refdef_absolute_unchanged(self):
        md = "[site]: https://example.com"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == md

    def test_refdef_directory(self):
        md = "[examples]: examples/"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert result == "[examples]: https://github.com/user/test-repo/tree/main/examples/"


# -- Mixed content --

class TestMixedContent:
    """Tests with multiple URL types in a single document."""

    def test_mixed_links_and_images(self):
        md = (
            "# Project\n\n"
            "![Logo](logo.png)\n\n"
            "See the [docs](docs/) and [license](LICENSE).\n\n"
            "Visit [homepage](https://example.com).\n"
        )
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)

        assert "raw.githubusercontent.com/user/test-repo/main/logo.png" in result
        assert "github.com/user/test-repo/tree/main/docs/" in result
        assert "github.com/user/test-repo/blob/main/LICENSE" in result
        assert "[homepage](https://example.com)" in result

    def test_multiple_links_on_same_line(self):
        md = "[A](a.md) and [B](b.md)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert "blob/main/a.md" in result
        assert "blob/main/b.md" in result


# -- Edge cases --

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_content(self):
        assert rewrite_readme_urls("", REPO_URL, BRANCH) == ""

    def test_no_links(self):
        md = "# Hello\n\nJust text, no links."
        assert rewrite_readme_urls(md, REPO_URL, BRANCH) == md

    def test_empty_html_url(self):
        md = "[Link](docs/api.md)"
        assert rewrite_readme_urls(md, "", BRANCH) == md

    def test_custom_branch(self):
        md = "[Link](docs/api.md)"
        result = rewrite_readme_urls(md, REPO_URL, "develop")
        assert result == "[Link](https://github.com/user/test-repo/blob/develop/docs/api.md)"

    def test_trailing_slash_on_html_url(self):
        md = "[Link](docs/api.md)"
        result = rewrite_readme_urls(md, REPO_URL + "/", BRANCH)
        assert result == "[Link](https://github.com/user/test-repo/blob/main/docs/api.md)"

    def test_none_default_branch_falls_back(self):
        """If default_branch is None or empty, fall back to 'main'."""
        md = "[Link](docs/api.md)"
        result = rewrite_readme_urls(md, REPO_URL, "")
        assert "blob/main/docs/api.md" in result

        result2 = rewrite_readme_urls(md, REPO_URL, None)
        assert "blob/main/docs/api.md" in result2

    def test_empty_alt_text(self):
        md = "![](logo.png)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert "raw.githubusercontent.com/user/test-repo/main/logo.png" in result

    def test_empty_link_text(self):
        md = "[](docs/api.md)"
        result = rewrite_readme_urls(md, REPO_URL, BRANCH)
        assert "blob/main/docs/api.md" in result
