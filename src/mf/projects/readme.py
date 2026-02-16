"""Rewrite relative URLs in GitHub README content to absolute GitHub URLs.

When importing README.md from a GitHub repo, relative URLs (e.g., ./docs/api.md,
images/logo.png) break because the files don't exist in the Hugo site. This module
transforms those URLs to point back to the GitHub repository.

Rules:
- Regular links → github.com/{owner}/{repo}/blob/{branch}/{path}
- Directory links (trailing /) → github.com/{owner}/{repo}/tree/{branch}/{path}
- Images → raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
- Absolute URLs, anchors, mailto:, data: URIs → unchanged
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


def rewrite_readme_urls(
    content: str,
    html_url: str,
    default_branch: str = "main",
) -> str:
    """Rewrite relative URLs in README markdown to absolute GitHub URLs.

    Args:
        content: Raw README markdown content.
        html_url: GitHub repo HTML URL (e.g., https://github.com/owner/repo).
        default_branch: Default branch name (e.g., "main" or "master").

    Returns:
        Content with relative URLs replaced by absolute GitHub URLs.
    """
    if not content or not html_url:
        return content

    # Normalize: strip trailing slash from html_url
    html_url = html_url.rstrip("/")
    default_branch = default_branch or "main"

    # Extract owner/repo from html_url for raw.githubusercontent.com
    parsed = urlparse(html_url)
    # path is like /owner/repo
    owner_repo = parsed.path.lstrip("/")

    def _make_absolute(path: str, is_image: bool) -> str:
        """Build an absolute GitHub URL from a relative path."""
        # Strip leading ./
        path = re.sub(r"^\./", "", path)

        if is_image:
            return f"https://raw.githubusercontent.com/{owner_repo}/{default_branch}/{path}"

        # Directory links (trailing /) use /tree/
        if path.endswith("/"):
            return f"{html_url}/tree/{default_branch}/{path}"

        # Regular file links use /blob/
        return f"{html_url}/blob/{default_branch}/{path}"

    def _is_relative(url: str) -> bool:
        """Check if a URL is relative (should be rewritten)."""
        # Skip empty
        if not url:
            return False
        # Skip anchors
        if url.startswith("#"):
            return False
        # Skip absolute URLs (http://, https://, //, etc.)
        if re.match(r"^https?://", url) or url.startswith("//"):
            return False
        # Skip mailto: and data: URIs
        return not re.match(
            r"^(mailto:|data:|tel:|ftp:|javascript:)", url, re.IGNORECASE
        )

    def _rewrite_image(m: re.Match[str]) -> str:
        """Rewrite an image URL: ![alt](url "title")."""
        alt = m.group(1)
        url = m.group(2)
        title = m.group(3) or ""
        if _is_relative(url):
            url = _make_absolute(url, is_image=True)
        title_part = f' "{title}"' if title else ""
        return f"![{alt}]({url}{title_part})"

    def _rewrite_link(m: re.Match[str]) -> str:
        """Rewrite a link URL: [text](url "title")."""
        text = m.group(1)
        url = m.group(2)
        title = m.group(3) or ""
        if _is_relative(url):
            url = _make_absolute(url, is_image=False)
        title_part = f' "{title}"' if title else ""
        return f"[{text}]({url}{title_part})"

    def _rewrite_refdef(m: re.Match[str]) -> str:
        """Rewrite a reference definition: [ref]: url "title"."""
        label = m.group(1)
        url = m.group(2)
        title = m.group(3) or ""
        if _is_relative(url):
            url = _make_absolute(url, is_image=False)
        title_part = f' "{title}"' if title else ""
        return f"[{label}]: {url}{title_part}"

    # Pattern for images: ![alt](url) or ![alt](url "title")
    # The url group stops at ) or space-before-title
    img_pattern = r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)'

    # Pattern for inline links (not images): [text](url) or [text](url "title")
    # Negative lookbehind to avoid matching images.
    # Text group allows one level of nested brackets for badge patterns
    # like [![Badge](https://...)](LICENSE)
    _nested_text = r'[^\[\]]*(?:\[[^\[\]]*\](?:\([^)]*\))?[^\[\]]*)*'
    link_pattern = rf'(?<!!)\[({_nested_text})\]\(([^)\s]+)(?:\s+"([^"]*)")?\)'

    # Pattern for reference definitions: [label]: url or [label]: url "title"
    refdef_pattern = r'^\[([^\]]+)\]:\s+(\S+)(?:\s+"([^"]*)")?$'

    # Process in order: images first, then links, then reference definitions
    content = re.sub(img_pattern, _rewrite_image, content)
    content = re.sub(link_pattern, _rewrite_link, content)
    content = re.sub(refdef_pattern, _rewrite_refdef, content, flags=re.MULTILINE)

    return content
