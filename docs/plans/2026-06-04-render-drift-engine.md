# Render-Drift Engine

**Status:** Draft. Design approved 2026-06-04; pre-implementation.
**Author:** Alexander Towell
**Scope:** First slice only (frontmatter lift + drift engine + render/write split for the four projection modules). Follow-on slices are listed at the end and are out of scope for this spec.
**Related:** `docs/plans/2026-05-08-git-automation.md` (deferred); the `series diff` / `series sync` subsystem this generalizes from.

## Goal

Give every projection module (papers, projects, packages, publications) a uniform, read-only answer to one question: **"What would `generate` change if I ran it right now?"**

Today only `series` can inspect drift between its source of truth and its Hugo output. The four projection modules regenerate blindly: no preview, no `diff`, no `audit`. This slice closes that gap with a single shared engine rather than four bespoke implementations.

## Problem

mf's identity is `Source -> Database -> Hugo`, where databases are truth and Hugo pages are derived artifacts. A derived artifact can fall out of date with truth in two ways:

1. the database (or upstream source) changed and `generate` was not re-run, or
2. the generator logic or template changed and pages were not regenerated.

Either way the published site silently diverges from truth. `series` already detects its analogue of this through `series diff`, but it does so with machinery (ownership tiers, two write authorities) that does not apply to the other modules. Meanwhile four different result types already express the idea "here is a discrepancy and how bad it is": `AuditFinding`, `PostDiff`, `IntegrityIssue`, and papers' `stale` / `no_hash` / `missing` staleness categories. The shape is shared; the spellings are not.

A naive generalization would try to lift the series ownership model onto every module. That is the wrong move. A survey of all five modules confirms **only series has two write authorities**. Papers, projects, packages, and publications are strict one-way projections (`Hugo = render(DB, source)`), with no preserved regions and no merge. For them the equivalence is simply `on_disk == render(entry)`, and `generate` is the remedy for any difference.

## Non-goals (this slice)

- No generated-vs-preserved regions, ownership tiers, or merge for the projection modules. They are strictly disposable outputs (confirmed with the user).
- No persisted per-page hash state. Commit `f27431c` removed a noisy hash-based staleness check from `series audit`; re-introducing stored hashes would repeat that mistake. Drift is computed live by re-rendering.
- No coverage of projects' create-once section stubs, projects' branch-bundle auxiliary files, or projects' `hide -> rmtree` deletion path. The first slice compares the single primary page per slug.
- No changes to `series` post syncing. Series posts keep `series diff`; only the optional, later series landing page would use this engine.
- No top-level `mf status` rollup and no migration of `audit` / `integrity` onto the shared spine. Those are follow-on slices.

## Architecture

### The equivalence we check

For a projection module, a Hugo page is current iff its on-disk content is semantically equal to what the generator would produce now from the stored entry (and any source files). "Semantically equal" means: parse both sides into `(frontmatter_dict, body_text)` and require the dicts to be equal and the bodies to be equal.

Textual comparison of rendered YAML against on-disk YAML is explicitly rejected: key ordering, quoting, and trailing-whitespace differences would manufacture false drift, the same noise that motivated removing the staleness check in `f27431c`.

### `core/frontmatter.py` (lifted primitives)

The generic frontmatter helpers currently in `src/mf/series/frontmatter.py` are not series-specific and move to `src/mf/core/frontmatter.py`:

- `parse_post(path) -> (dict, str)` (parse an index.md file)
- `parse_text(text) -> (dict, str)` (new; parse an in-memory rendered string)
- `compute_body_hash(path) -> str`
- `frontmatter_equal(a, b) -> bool`

The series-specific layer stays in `src/mf/series/frontmatter.py` and imports the primitives from core: `DEFAULT_BLOG_OWNED`, `DEFAULT_SHARED`, `get_ownership_sets`, `classify_field`, `FrontmatterFieldDiff`, `compare_frontmatter`. Existing `mf.series.frontmatter` imports continue to work by re-exporting the moved names from the series module, so callers and tests are not broken.

### `core/drift.py` (the engine)

A new module providing the protocol, the finding type, the check, and one report renderer.

**Renderer protocol** mirrors the `FieldDatabase` adapter seam in `core/field_ops.py`: the module supplies the binding, core supplies the mechanism.

```python
@runtime_checkable
class Renderer(Protocol):
    section: str                                         # "papers", for messages
    def iter_slugs(self) -> Iterable[str]: ...           # slugs generate would produce pages for
    def hugo_path(self, slug: str) -> Path: ...          # primary page location
    def render_page(self, slug: str) -> str | None: ...  # text generate would write; None if unrenderable
```

`render_page` returns the exact text the generator would write for the primary page, or `None` when the slug cannot be rendered (for example, a paper whose source artifacts are missing).

**Finding type:**

```python
@dataclass
class RenderFinding:
    slug: str
    status: str        # current | stale | missing | orphan
    detail: str = ""
```

Status semantics:

- `current`: page exists and is semantically equal to `render_page`.
- `stale`: page exists and differs (generate would overwrite).
- `missing`: `render_page` is not None and no page exists (generate would create).
- `orphan`: a page exists on disk whose slug is not in `iter_slugs`, or whose `render_page` is None (generate would not produce it). Reported as informational; `integrity check` remains the authority on orphans, and the two must agree.

**The check:**

```python
def check_render_drift(renderer: Renderer) -> list[RenderFinding]: ...
```

For each slug from `iter_slugs`, render and compare against `hugo_path`. Then scan the section directory for pages whose slug is unknown to the renderer and report them as `orphan`. Comparison uses `core.frontmatter.parse_text` / `parse_post` for semantic equality.

A single Rich report renderer prints the findings table and is reused by both CLI doors below.

### Determinism prerequisite

`check_render_drift` is only meaningful if `render_page` is a pure function of the stored entry plus source files, with no wall-clock reads. Three generators currently violate this with a "use now if absent" date fallback:

- `packages/generator.py:52`: `entry.data.get("date_added") or date.today().isoformat()`
- `papers/generator.py:200-203`: file `mtime` when no date is set
- `projects/generator.py:137-138,190`: `datetime.now(...)` when GitHub `created_at` is absent (rare; the cache normally supplies a stable `created_at`)

`publications` is already deterministic (date comes from the required `PubEntry.date`).

Mechanism: pinning happens in `generate`, never in `diff`. When `generate` must synthesize a date for an entry that lacks one, it writes the synthesized value back into the entry (`db.update(slug, date=...)`) before rendering, so every subsequent render and diff reads a stable stored value. Diff stays strictly read-only.

Transitional behavior: an entry that has never been generated since this change, and that lacks a stored date, may report as `stale` until its next `generate` pins the date. This self-heals on the next generate and affects only date-less entries. No separate backfill command is required; a stable date is the correct behavior regardless.

### Per-module render/write split

Each generator is split into a pure `render_page(slug) -> str | None` (no writes, no wall clock) and the existing write path, which calls the renderer and then writes. Verified current state and target:

| Module | Current | Target | Effort |
|--------|---------|--------|--------|
| publications | already split: `pub_to_frontmatter` + `generate_publication_content(fm) -> str` | thin `Renderer` wrapping the existing pair | trivial |
| packages | `generate_package_content` builds a string then writes | extract the string builder into `render_page`; write path calls it; pin date on `generate` | easy |
| papers | `generate_paper_content` reads HTML/PDF, writes a thumbnail, then writes index.md | `render_page` performs reads only and returns text; thumbnail generation stays in the write path; pin date | medium |
| projects | `generate_project_frontmatter` is pure; `generate_project_content` merges cache and overrides, rewrites README urls, writes primary page plus create-once stubs | `render_page` returns the primary page (frontmatter + readme); stubs, branch extras, and hide-delete stay in the write path and are out of scope for drift | medium |

### CLI surface: one engine, two doors

1. **Enriched `generate --dry-run`.** Today each module's dry-run prints "would write: path". It becomes "would create | update | skip: path", driven by `check_render_drift`, so dry-run finally reports what changes rather than just where.
2. **`mf <module> diff [slug]`** (new, read-only). Prints the `RenderFinding` table; with a slug or a `--full` flag, prints a unified diff for stale pages, reusing the diff rendering already written for `series diff`. Read-only commands may not write under any branch (house rule).

Both doors call the same `check_render_drift`. No new persisted state.

## Files touched

New:

- `src/mf/core/frontmatter.py` (lifted primitives)
- `src/mf/core/drift.py` (Renderer protocol, RenderFinding, check_render_drift, report renderer)
- `tests/test_core/test_drift.py`, `tests/test_core/test_frontmatter.py`

Modified:

- `src/mf/series/frontmatter.py` (re-export primitives from core; keep the ownership layer)
- `src/mf/{papers,projects,packages,publications}/generator.py` (render/write split, drop wall-clock fallbacks)
- `src/mf/{papers,projects,packages,publications}/commands.py` (enrich `generate --dry-run`; add `diff` subcommand; keep lazy imports inside command bodies)
- the `generate` paths that pin synthesized dates

## Test plan

- Pure `render_page` unit tests per module (no disk needed for the render half).
- `check_render_drift`: one case each for current, stale, missing, and orphan, via a fake Renderer plus at least one real module.
- Determinism test: call `render_page` twice for the same entry and assert byte-identical output (guards the wall-clock regression).
- Semantic-equality test: reorder frontmatter keys and reflow whitespace on disk, then assert the status stays `current`.
- Regression: existing `tests/test_series/` stay green after the frontmatter lift (the re-export keeps `mf.series.frontmatter` imports valid).
- CLI: `generate --dry-run` reports create / update / skip; `diff` is read-only (assert no file writes occur).

## Sequencing (build order)

1. Lift primitives to `core/frontmatter.py`; re-export from `series/frontmatter.py`; run series tests green. (Piece 0)
2. Add `core/drift.py` with `Renderer`, `RenderFinding`, `check_render_drift`, and the report renderer, tested against a fake Renderer. (Piece 1)
3. Wire publications first (already split) as the reference Renderer; add its `diff` and enriched dry-run. (Piece 2a)
4. packages, then papers, then projects: split render/write, drop wall-clock fallbacks (pin dates), wire `diff` and dry-run. (Piece 2b through 2d)

## Open questions

- Orphan reporting overlaps with `integrity check`. For this slice, `diff` reports orphans informationally and must agree with integrity. A later slice may make integrity consume `check_render_drift` so there is a single orphan authority.
- Projects' primary page is `index.md` or `_index.md` depending on `rich_project`. `hugo_path` resolves which one. If both exist on disk (a prior mode switch left a stale file), that is itself drift the slice should surface as a finding rather than silently pick one.

## Follow-on slices (not this spec)

- Piece 3: top-level `mf status` aggregating drift across all modules into one dashboard.
- Piece 4: re-express `series audit`, `series diff`, and `integrity check` on the shared `core/drift` finding and report spine, collapsing the four discrepancy dataclasses into one.
- Optional: the series landing page as a Renderer, so series joins the same engine for its one projected page.
