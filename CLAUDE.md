# Alvis — Protein Alignment Conservation Analyzer

## What this is

A Flask web app that visualizes conserved residues across protein
sequence alignments. The user uploads a ZIP of FASTA alignment files,
configures conservation thresholds, optionally adds PDB files for
secondary structure, and gets an SVG diagram.

## How to run

```bash
source venv/bin/activate
python app.py          # → http://localhost:5000
```

Or `./run.sh` (creates venv + installs deps + runs).

## Tech stack

- **Backend:** Flask (Python 3.9), BioPython (SeqIO, PDB/DSSP)
- **Frontend:** Single-page vanilla JS in `templates/index.html`
- **SVG:** Generated server-side with `svgwrite`
- **Storage:** Temp directories for uploaded files, in-memory session tokens (no database)

## File map

```
app.py                 Flask routes — the entire backend API
conservation.py        analyze_alignment() + analyze_cross_conservation()
svg_generator.py       generate_svg() — builds the SVG with svgwrite
structure.py           DSSP wrapper: run_dssp(), get_ss_segments(), map_ss_to_sequence()
templates/index.html   The full UI (HTML + inline JS)
static/style.css       All styles
requirements.txt       Python dependencies
session_store.py       In-memory session token store (opaque tokens → temp dirs)
```

## Request flow

```
POST /upload         ZIP file → extract → list FASTA files, detect all.fasta
                     Returns: {session_token, fasta_files, all_fasta?}

POST /upload-pdb     PDB file for one alignment → parse chains
                     Form data: session_token, fasta_file, file
                     Returns: {pdb_filename, chains}

POST /generate       {session_token, thresholds, pdb_files, all_fasta?, cross_threshold?}
                     → analyze each group alignment (conservation.py)
                     → read first seq from each group for representative IDs
                     → run DSSP if PDB provided (structure.py)
                     → cross-conservation analysis if all.fasta present
                     → generate SVG (svg_generator.py)
                     Returns: {svg}

POST /cleanup        {session_token} → delete temp directory + session
```

## Key concepts

### Conservation analysis (`conservation.py`)

- `analyze_alignment(path, threshold)` — for each column in a FASTA
  alignment, counts the most common residue. If count/total >= threshold,
  it's conserved. Returns conserved positions as ungapped coordinates in
  the first (representative) sequence.

- `analyze_cross_conservation(all_fasta_path, representative_ids, threshold)`
  — same idea but on `all.fasta`, a combined alignment of all groups.
  Maps conserved columns to ungapped positions in each group's
  representative. Returns a list of `{residue, conservation, positions}`
  dicts where `positions` maps group names to ungapped positions.

### Cross-conservation (`all.fasta`)

When the uploaded ZIP contains a file named `all.fasta` (basename `all`,
any FASTA extension), it's treated as a combined alignment of every
sequence across all groups. The app:
1. Separates it from the group files during upload
2. Finds conserved columns across all sequences
3. Maps those columns to each group representative's ungapped position
4. Draws dashed connecting lines between adjacent SVG rows

The position mapping works because each group's representative is a row
in `all.fasta` — counting non-gap characters up to a column gives the
ungapped position, which is the same coordinate system the per-group
rows use.

### SVG layout (`svg_generator.py`)

- Each alignment is a horizontal line with colored tick marks above for
  conserved residues (labeled with residue letter + position number)
- Labels stack into multiple vertical levels to avoid overlap
  (`position_labels_smartly`)
- Row spacing is dynamic — computed from the max label stacking height
  per alignment
- Secondary structure (helix/sheet/coil) draws below each line if a PDB
  was provided
- Cross-conservation lines are dashed, semi-transparent, colored by
  residue type, drawn between adjacent rows

### Amino acid color scheme

| Color | Residues |
|-------|----------|
| Magenta `(255,0,255)` | G Y S T N C Q (polar/small) |
| Green `(70,156,118)` | V I L P F M W A (hydrophobic) |
| Orange `(255,140,0)` | H (histidine) |
| Red `(192,0,0)` | D E (acidic) |
| Blue `(0,0,255)` | K R (basic) |

## Pending work

### Known issue: redundant FASTA reads

Each group FASTA file is read 3-4 times during `/generate`:
1. `analyze_alignment()` — full parse
2. Count sequences — re-parse
3. DSSP mapping — re-parse for representative sequence
4. Cross-conservation — re-parse for representative ID

`analyze_alignment()` should return richer results (num_sequences,
rep_id, rep_seq) to eliminate reads 2-4.

## Conventions

- The first sequence in each group FASTA file is the "representative"
- Conservation is computed as `count_of_most_common / total_sequences`
  (gaps count against conservation)
- Ungapped position = count of non-gap characters up to and including
  a column (1-indexed)
- FASTA files are tried with multiple encodings: utf-8, latin-1,
  cp1252, iso-8859-1
- macOS metadata (`__MACOSX`, `._*` files) is filtered during ZIP
  extraction
- Non-fatal errors (DSSP failures, cross-conservation failures) are
  logged and skipped — the SVG still generates
