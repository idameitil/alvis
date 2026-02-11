# ALVIS Codebase Health Assessment & Recommendations

## Executive Summary

ALVIS is a Flask-based web application for visualizing conserved residues across protein sequence alignments. The core pipeline (ZIP upload → FASTA parsing → conservation analysis → SVG generation) is **fully functional and well-architected**. Database persistence (Phase 2) is complete. The next major feature — showing secondary structure from PDB/DSSP on the representative proteins — requires new backend processing, UI changes for PDB upload, and SVG modifications.

---

## Component Health Report

### 1. Conservation Analysis (`conservation.py`) — Healthy

- Correct column-by-column conservation calculation using BioPython
- Handles gapped alignments properly, returning **ungapped positions** (critical: these map directly to PDB residue numbering)
- Robust multi-encoding file reading
- Validates alignment consistency (equal-length sequences)
- First sequence used as representative — straightforward convention

**One concern**: the conservation percentage divides by non-gap count, not total sequence count. This means a column where 3 of 100 sequences have residues and all 3 match will show 100% conservation. This is a design choice, but worth being aware of.

### 2. SVG Generator (`svg_generator.py`) — Healthy

- Smart label positioning algorithm avoids overlap by stacking vertically
- Proportional line scaling across multiple alignments
- Color scheme groups amino acids by chemical properties
- Scale markers every 50 residues

**Relevant for DSSP integration**: the SVG currently draws one horizontal line per alignment with conserved residue ticks above it. Secondary structure will need to be rendered either as colored segments along the line, or as a parallel track (helix/sheet/coil annotations). The generator's structure supports this — each alignment is drawn in a `row_height`-sized band with room for additions.

### 3. Flask Application (`app.py`) — Healthy

- Clean route structure: `/upload`, `/generate`, `/cleanup`, `/projects/*`
- Proper temp directory lifecycle management
- Good error handling with cleanup on failure

**Security note**: `temp_dir` is sent to the client and accepted back verbatim — a path traversal risk in production. Not blocking for development, but should be addressed before deployment (use session-based temp dir tracking instead).

### 4. Database Layer (`models/` + `services/`) — Healthy

- SQLAlchemy models with proper relationships and cascading deletes
- Service layer cleanly separates DB operations from route handlers
- Schema is extensible for new tables (PDB structures, secondary structure data)

### 5. Frontend (`templates/index.html` + `static/style.css`) — Healthy

- Vanilla JS single-page app, no framework dependencies
- Step-by-step workflow (Upload → Configure → Generate → Results)
- XSS protection via `escapeHtml()`
- Modal dialogs for project management
- Professional styling with consistent theme

### 6. Configuration & Dependencies — Healthy

- `requirements.txt` has pinned versions, minimal dependency set
- `.env`-based configuration with dev/prod separation
- 50MB upload limit is reasonable

### 7. Tests — Missing

- No test files exist anywhere in the project
- No pytest configuration

### 8. PDB/DSSP Integration — Not Started

- Mentioned as Phase 3 in `PHASE2_IMPLEMENTATION.md` but no code exists

---

## Recommended Steps for PDB/DSSP Secondary Structure Feature

### Step 1: Add DSSP dependency and PDB parsing backend

**What**: Create a new module (e.g., `structure.py`) that:
- Accepts a PDB file path
- Runs DSSP (via BioPython's `Bio.PDB.DSSP` interface) to extract secondary structure
- Returns per-residue secondary structure assignments (H=helix, E=sheet, C=coil, etc.)
- Maps DSSP 8-state codes to 3-state (Helix/Sheet/Coil) for visualization simplicity

**Dependencies to add**:
- `dssp` — the DSSP binary must be installed on the system (via `conda install dssp`, `brew install dssp`, or compiled from source). BioPython's `DSSP` module calls it as a subprocess.
- BioPython already includes `Bio.PDB.DSSP` and `Bio.PDB.PDBParser`, so no new Python packages are strictly needed. However, consider adding `mkdssp` as a documented system dependency.

**Key design decision**: DSSP requires the actual DSSP executable installed on the server. An alternative is to pre-compute secondary structure and accept DSSP output files directly, but running DSSP server-side is more user-friendly.

### Step 2: Add PDB upload to the workflow

**What**: Modify the upload flow so users can provide PDB files for representative proteins:
- After FASTA ZIP upload, show a second upload step where users associate PDB files with specific alignments
- Each alignment's representative (first sequence) can optionally have a PDB file
- PDB files should be uploaded individually or in a second ZIP
- Store PDB files in the temp directory alongside FASTA files

**Backend changes** (`app.py`):
- New route `POST /upload-pdb` or extend `/upload` to accept PDB files
- Validate PDB files parse correctly (using `Bio.PDB.PDBParser`)
- Return mapping of alignment → PDB file

**Frontend changes** (`index.html`):
- Add a step between threshold configuration and generation where users can upload PDB files per alignment
- Allow skipping (secondary structure is optional per alignment)
- Show which alignments have PDB files associated

### Step 3: Integrate DSSP into the generation pipeline

**What**: Modify `/generate` to optionally run DSSP when PDB files are provided:
- For each alignment with an associated PDB, run DSSP
- Extract secondary structure for the representative sequence
- Pass secondary structure data alongside conservation data to the SVG generator

**Key challenge — residue numbering alignment**:
- Conservation analysis returns ungapped positions (1-indexed)
- PDB residue numbering may not start at 1 and may have insertion codes
- Need a mapping step: representative sequence positions → PDB residue numbers
- Approach: extract the sequence from the PDB file, align it to the FASTA representative, and build a position map. Or require that the PDB chain matches the representative sequence directly.

### Step 4: Modify SVG generation to show secondary structure

**What**: Add secondary structure visualization to the SVG:
- Draw a colored band along each alignment's horizontal line showing helix (e.g., red/pink rectangles or wavy line), sheet (yellow arrows or rectangles), and coil (thin line or gray)
- This goes below the conservation ticks, using the space between the line and the scale markers
- Add secondary structure elements to the legend

**Suggested visual approach**:
- Below each alignment's main line, draw a thin colored bar:
  - Helix (H): red/magenta rectangles or traditional helix cartoon
  - Sheet (E): yellow/gold rectangles or arrow shapes
  - Coil (C): thin gray line (or leave empty)
- This keeps the conservation ticks above and structure below, avoiding visual clutter
- Increase `row_height` from 100 to ~130 to accommodate the extra track

### Step 5: Extend the database schema (optional, for persistence)

**What**: If you want to save secondary structure data with projects:
- Add a `Structure` model linked to `Alignment` (one-to-one)
- Fields: `pdb_filename`, `chain_id`, `secondary_structure_string` (compact representation like "HHHHHCCCEEEEEECCCHHHH")
- Add a `SecondaryStructureSegment` model or store as JSON

This step is optional — you could regenerate from PDB on reload, but storing avoids needing PDB files after the initial run.

### Step 6: Handle edge cases

- **No PDB provided**: secondary structure track simply not shown for that alignment (current behavior preserved)
- **PDB/sequence mismatch**: warn user if PDB sequence doesn't match FASTA representative
- **Multi-chain PDBs**: let user select which chain corresponds to the representative
- **Missing residues in PDB**: some residues may lack coordinates; show gaps in the secondary structure track

---

## Priority Order

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| 1 | Backend DSSP module (`structure.py`) | Medium | Core enabler |
| 2 | PDB upload route + frontend step | Medium | User-facing |
| 3 | SVG secondary structure rendering | Medium | Visual payoff |
| 4 | Residue numbering alignment (FASTA↔PDB) | High | Correctness |
| 5 | Database schema extension | Low | Persistence |
| 6 | Edge case handling + validation | Medium | Robustness |

Steps 1-3 can be developed somewhat in parallel. Step 4 (residue mapping) is the most technically tricky part and should be designed carefully upfront.

---

## Other Observations

- **Testing**: There are no tests. Before adding a complex feature like DSSP, consider adding at least unit tests for `conservation.py` and `svg_generator.py` — these are pure functions that are easy to test and will catch regressions as the codebase evolves.
- **Security**: The `temp_dir` path is exposed to the client. Track session temp directories server-side (e.g., in Flask session or a dict keyed by session ID) instead.
- **DSSP alternatives**: If installing the DSSP binary is problematic for deployment, consider using `mkdssp` (the modern rewrite), or accepting pre-computed secondary structure files (`.dssp` format) as an alternative input.
