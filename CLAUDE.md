# Alvis — Protein Alignment Conservation Analyzer

## What this is

A Flask web app that visualizes conserved residues across protein
sequence alignments. The user uploads a ZIP of FASTA alignment files,
configures conservation thresholds, optionally adds PDB files for
secondary structure, and gets an SVG diagram.

## How to run

```bash
# Docker (preferred)
docker compose up

# Local
source venv/bin/activate
python app.py          # → http://localhost:5000
```

## Running tests

```bash
docker compose run --rm web python -m pytest tests/ -v
```

## Tech stack

- **Backend:** Flask (Python 3.9) with `create_app()` factory, BioPython (SeqIO, PDB/DSSP)
- **Frontend:** Single-page vanilla JS (`static/app.js`) + HTML template
- **SVG:** Generated server-side with `svgwrite`
- **Storage:** Temp directories for uploaded files, in-memory session store (no database)

## Architecture

```
app.py                     Flask app factory (create_app), serves index + example data

models/
  types.py                 Dataclasses: ChainInfo, PdbInfo, GroupConfig
  session.py               Session dataclass — owns temp dir, FASTA/PDB file ops, config
  analysis.py              build_result(session) — orchestrates conservation + DSSP + SVG

routes/
  __init__.py              register_blueprints(app) — wires all blueprints
  session.py               REST endpoints for session lifecycle, FASTA upload, PDB upload
  analysis.py              GET /session/<id>/result — triggers analysis, returns SVG
  pdb.py                   POST /fetch-pdb — downloads PDB from RCSB by ID

conservation.py            analyze_alignment() + analyze_cross_conservation()
svg_generator.py           generate_svg() — builds SVG with svgwrite
structure.py               DSSP: run_dssp(), get_ss_segments(), align_pdb_to_fasta(), remap_ss_segments()
session_store.py           Thread-safe in-memory store: create/get/remove/cleanup_expired

templates/index.html       HTML shell (no inline JS)
static/app.js              All client-side logic (upload, PDB, generate, results)
static/style.css           All styles
```

## API (resource-oriented)

```
POST   /session                      → create empty session → {id, groups, ...}
POST   /session/<id>/fasta           → upload ZIP or single FASTA → session dict
DELETE /session/<id>/fasta/<name>    → remove a FASTA file → session dict
POST   /session/<id>/pdb             → upload PDB file → {pdb_filename, chains}
DELETE /session/<id>/pdb/<name>      → remove PDB file → session dict
PATCH  /session/<id>                 → set thresholds, chain_assignments, cross_threshold
GET    /session/<id>/result          → run analysis → {svg, alignment_info, warnings?}
DELETE /session/<id>                 → cleanup temp dir + session

POST   /fetch-pdb                    → {session_id, pdb_id} → fetch from RCSB → {pdb_filename, chains}
GET    /example-data                 → serves globins_example.zip
```

## Key concepts

### Session model (`models/session.py`)

The `Session` dataclass owns the temp directory and all file operations:
- `add_fasta_zip()` / `add_fasta_file()` / `add_fasta_content()` — ingest FASTA data
- `add_pdb()` / `add_pdb_from_bytes()` — save and parse PDB files via `parse_pdb_chains()`
- `update_config()` — set per-group thresholds and PDB chain assignments
- `cleanup()` — delete temp directory

Each group FASTA file maps to a `GroupConfig` (threshold + optional `PdbInfo`).

### Analysis pipeline (`models/analysis.py`)

`build_result(session)` orchestrates the full pipeline:
1. For each group: find representative (PDB-aligned or first seq), run `analyze_alignment()`
2. Parse FASTA for sequence count and representative record
3. If PDB assigned: run DSSP, align PDB to FASTA, remap SS segments
4. If `all.fasta` present: run `analyze_cross_conservation()` across all groups
5. Generate SVG via `generate_svg()`

Representative selection uses pairwise local alignment to find the FASTA
sequence best matching the PDB chain (`_find_representative_index()`).

### Conservation analysis (`conservation.py`)

- `analyze_alignment(path, threshold, representative_index)` — for each column,
  counts the most common residue. If count/total >= threshold, it's conserved.
  Returns conserved positions as ungapped coordinates in the representative sequence.

- `analyze_cross_conservation(all_fasta_path, representative_ids, threshold)`
  — same idea on `all.fasta`. Maps conserved columns to ungapped positions
  in each group's representative.

### Cross-conservation (`all.fasta`)

When the uploaded ZIP contains a file named `all.fasta` (basename `all`,
any FASTA extension), it's a combined alignment of all groups. The app:
1. Separates it from group files during upload
2. Finds conserved columns across all sequences
3. Maps those columns to each group representative's ungapped position
4. Draws dashed connecting lines between adjacent SVG rows

### SVG layout (`svg_generator.py`)

- Each alignment is a horizontal line with colored tick marks for conserved residues
- Labels stack into vertical levels to avoid overlap (`position_labels_smartly`)
- Row spacing is dynamic — computed from max label stacking height per alignment
- Secondary structure (helix/sheet/coil) draws below each line if PDB provided
- Cross-conservation lines are dashed, semi-transparent, colored by residue type
- Uses ClustalX-inspired color scheme for amino acid residues

### Structure mapping (`structure.py`)

- `run_dssp()` — extracts per-residue secondary structure from PDB
- `get_ss_segments()` — merges consecutive residues into H/E/C segments
- `align_pdb_to_fasta()` — maps PDB positions to FASTA positions via
  substring match (fast path) or pairwise alignment (fallback)
- `remap_ss_segments()` — translates PDB-coordinate segments to FASTA
  coordinates, filling gaps with 'U' (uncovered) segments

## Conventions

- The first sequence in each group FASTA is the "representative" (unless PDB
  chain alignment picks a better match)
- Conservation = `count_of_most_common / total_sequences` (gaps count against)
- Ungapped position = count of non-gap characters up to and including a column (1-indexed)
- FASTA files tried with encodings: utf-8, latin-1, cp1252, iso-8859-1
- macOS metadata (`__MACOSX`, `._*`) filtered during ZIP extraction
- Non-fatal errors (DSSP, cross-conservation) are logged and skipped — SVG still generates
- Python 3.9 in Docker — use `from __future__ import annotations` for `str | None` syntax
- `templates/about.html` documents the tool, biological significance, and methodology —
  update it when refactoring features, changing workflows, or altering analysis logic
