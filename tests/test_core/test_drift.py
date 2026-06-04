from pathlib import Path

from mf.core.drift import RenderFinding, check_render_drift


class FakeRenderer:
    """In-memory Renderer for testing the engine without real generators."""

    section = "fake"

    def __init__(self, root: Path, pages: dict[str, str | None]):
        # pages: slug -> rendered text, or None for "not renderable"
        self._root = root
        self._pages = pages

    def iter_slugs(self):
        return list(self._pages)

    def existing_slugs(self):
        return [p.name for p in self._root.iterdir() if (p / "index.md").exists()] if self._root.exists() else []

    def hugo_path(self, slug):
        return self._root / slug / "index.md"

    def render_page(self, slug):
        return self._pages.get(slug)


def _write_page(root: Path, slug: str, text: str) -> None:
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(text, encoding="utf-8")


def _status_for(findings, slug):
    return next(f.status for f in findings if f.slug == slug)


def test_current_when_disk_matches_render(tmp_path):
    text = '---\ntitle: "A"\n---\n\nbody\n'
    _write_page(tmp_path, "a", text)
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": text}))
    assert _status_for(findings, "a") == "current"


def test_current_ignores_frontmatter_key_order_and_whitespace(tmp_path):
    on_disk = '---\nb: 2\na: 1\n---\n\nbody\n'
    rendered = '---\na: 1\nb: 2\n---\n\nbody\n'
    _write_page(tmp_path, "a", on_disk)
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": rendered}))
    assert _status_for(findings, "a") == "current"


def test_stale_when_body_differs(tmp_path):
    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nold body\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nnew body\n'}))
    assert _status_for(findings, "a") == "stale"


def test_missing_when_renderable_but_no_page(tmp_path):
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nbody\n'}))
    assert _status_for(findings, "a") == "missing"


def test_orphan_when_page_on_disk_unknown_to_renderer(tmp_path):
    _write_page(tmp_path, "ghost", '---\ntitle: "Ghost"\n---\n\nbody\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {}))
    assert _status_for(findings, "ghost") == "orphan"


def test_orphan_when_known_but_not_renderable_and_on_disk(tmp_path):
    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nbody\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": None}))
    assert _status_for(findings, "a") == "orphan"


def test_findings_are_render_finding_instances(tmp_path):
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": "---\n---\n\nx\n"}))
    assert all(isinstance(f, RenderFinding) for f in findings)


def test_dry_run_preview_uses_create_update_skip_verbs(tmp_path, capsys):
    from rich.console import Console

    from mf.core.drift import print_dry_run_preview

    _write_page(tmp_path, "stale", '---\ntitle: "x"\n---\n\nold\n')
    _write_page(tmp_path, "current", '---\ntitle: "x"\n---\n\nsame\n')
    _write_page(tmp_path, "ghost", '---\ntitle: "x"\n---\n\northan\n')
    renderer = FakeRenderer(
        tmp_path,
        {
            "stale": '---\ntitle: "x"\n---\n\nnew\n',
            "current": '---\ntitle: "x"\n---\n\nsame\n',
            "new": '---\ntitle: "x"\n---\n\nbody\n',
        },
    )
    print_dry_run_preview(renderer, console=Console())
    out = capsys.readouterr().out
    assert "would update" in out
    assert "would create" in out
    assert "would skip:" in out
    assert "would skip (orphan)" in out


def test_run_diff_command_unknown_slug_exits(tmp_path):
    import pytest
    from rich.console import Console

    from mf.core.drift import run_diff_command

    with pytest.raises(SystemExit):
        run_diff_command(FakeRenderer(tmp_path, {}), console=Console(), slug="nope")


def test_print_drift_report_lists_drift_rows():
    import io

    from rich.console import Console

    from mf.core.drift import RenderFinding, print_drift_report

    buf = io.StringIO()
    console = Console(file=buf, width=200)
    findings = [
        RenderFinding("a", "current"),
        RenderFinding("b", "stale", "generate would update"),
        RenderFinding("c", "missing", "generate would create"),
    ]
    print_drift_report(findings, section="fake", console=console)
    out = buf.getvalue()
    assert "b" in out and "stale" in out
    assert "c" in out and "missing" in out


def test_print_drift_report_all_current_says_so():
    import io

    from rich.console import Console

    from mf.core.drift import RenderFinding, print_drift_report

    buf = io.StringIO()
    console = Console(file=buf, width=200)
    print_drift_report([RenderFinding("a", "current")], section="fake", console=console)
    assert "all pages current" in buf.getvalue()


def test_print_render_diff_shows_added_and_removed_lines(tmp_path):
    import io

    from rich.console import Console

    from mf.core.drift import print_render_diff

    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nold line\n')
    renderer = FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nnew line\n'})
    buf = io.StringIO()
    print_render_diff(renderer, "a", Console(file=buf, width=200))
    out = buf.getvalue()
    assert "old line" in out
    assert "new line" in out


def test_run_diff_command_full_emits_diff_for_stale(tmp_path):
    import io

    from rich.console import Console

    from mf.core.drift import run_diff_command

    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nold\n')
    renderer = FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nnew\n'})
    buf = io.StringIO()
    run_diff_command(renderer, console=Console(file=buf, width=200), full=True)
    out = buf.getvalue()
    assert "stale" in out
    assert "new" in out
