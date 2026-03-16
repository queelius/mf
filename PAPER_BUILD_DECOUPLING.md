# Paper Build Decoupling

## Status: Complete

### Completed
1. **paper_db.json updated** — 6 deleted entries removed (alea, alga, langcalc, likelihood.model.series.md, reliability-series-sys-model-sel, weibull-series-model-selection), 9 source paths fixed for moved repos
2. **Makefiles created** — 22 new Makefiles in paper repos with `pdf` and `html` targets, 8 existing Makefiles updated with `html` target
3. **Resolved moves**:
   - oblivious-computing papers → trapdoor-computing/papers/
   - known-plaintext-attack-ts → ~/github/papers/ (was in oblivious-computing)
   - mdrelax → ~/github/papers/mdrelax/
   - reliability-estimation-in-series-systems → latex/paper.tex (subdir move)
   - cipher-maps → trapdoor-computing/papers/cipher-maps-unified/
   - encrypted-search-ob-types → trapdoor-computing/papers/encrypted-search/
4. **mf package changes** — removed build logic from processor.py (generate_html, generate_pdf, process_paper, find_tex_files, run_command), replaced `process` → `ingest` and `sync` → `status` commands, removed tex2any/pdflatex dependencies, added `resolve_artifact_paths` for convention-based artifact discovery, removed tex-only staleness guard so all formats are hash-checked

### Remaining
5. **Update ORCHESTRATION.md** to reflect new flow

## Architecture

### Before
```
mf papers process paper.tex
  → mf calls tex2any → HTML
  → mf calls pdflatex → PDF
  → mf copies to /static/latex/{slug}/
  → mf updates paper_db.json
```

### After
```
# Developer builds in paper repo:
cd ~/github/papers/my-paper/paper
make html pdf

# mf just ingests pre-built artifacts:
mf papers ingest my-paper

# mf detects staleness (but doesn't build):
mf papers status
```

### Makefile Convention
Each paper repo has a `Makefile` in the directory containing the `.tex` file:
```makefile
TEX = paper.tex
STEM = $(basename $(TEX))
HTMLDIR = html_paper

pdf: $(STEM).pdf
html: $(HTMLDIR)/index.html

$(STEM).pdf: $(TEX)
    pdflatex ... && bibtex ... && pdflatex ... && pdflatex ...

$(HTMLDIR)/index.html: $(TEX)
    tex2html $(TEX) -o $(HTMLDIR)
```

`html_paper/` is used instead of `html/` to avoid conflicts with existing directories.

### paper_db.json Fields
- `source_path` — path to main .tex file (used for hash-based staleness)
- `pdf_path` — where to find the built PDF (relative to Hugo static)
- `html_path` — where to find the built HTML (relative to Hugo static)
- `source_hash` — SHA256 of source .tex for change detection

### mf Commands
- `mf papers status` — check which papers are stale/missing/up-to-date (replaces `sync`)
- `mf papers ingest <slug>` — copy pre-built artifacts to Hugo static (replaces `process`)
- `mf papers generate` — regenerate Hugo content pages from database
- `mf papers list/show/set/unset/tag/feature` — unchanged

## What gets deleted from mf
- `generate_html()` — the tex2any invocation
- `generate_pdf()` — the pdflatex orchestration (5-pass pdflatex + bibtex)
- tex2any-footer-config meta tag parsing in metadata.py
- Auto-rebuild in sync (now just reports staleness)

## What stays in mf
- `copy_to_static()` — copies pre-built output to Hugo static dir
- `backup_existing_paper()` — backup before overwriting
- `metadata.py` — extract metadata from HTML/PDF (standard meta tags only)
- `generator.py` — generate Hugo content from metadata
- Staleness detection via source hash
- Database management, slug handling, all the content plumbing
- CITATION.cff parsing, Zenodo integration

## Benefits
- **mf is simpler.** Content registry, not a build system.
- **Papers own their builds.** Different papers can use different tools/engines.
- **Reproducible builds.** Makefile is in the paper repo.
- **No tex2any/tex2html dependency in mf.** One less tool to install.
- **Standard Unix pattern.** `make` builds, a separate tool registers.
