# Cross-conservation connecting lines — implementation plan

## Goal

When the user includes an `all.fasta` in their ZIP, the program:

1. Runs conservation analysis on `all.fasta` — a **new multiple sequence
   alignment** of every sequence from every group
2. Finds columns where >= 95% of all sequences share the same residue
3. For each conserved column, determines the ungapped position in each
   group's representative (by counting non-gap characters in that
   representative's row within all.fasta)
4. Draws connecting lines in the SVG between adjacent rows at those
   positions

## How it works visually

```
  groupA.fasta   ──── R ──────── K ──── D ────────
                      │          │      │
  groupB.fasta   ────── R ────── K ──── D ──────
                        │        │      │
  groupC.fasta   ──── R ──────── K ────── D ────
```

If Arg, Lys, and Asp are conserved at >= 95% in all.fasta, thin colored
lines connect their positions between adjacent rows. Lines are vertical
when the ungapped positions match, diagonal when they differ (because
each representative has its own gap pattern within all.fasta).

## Why position mapping is simple

`all.fasta` is a single alignment that already contains every sequence,
including each group's representative. A conserved column is just a
column index. To find where that column falls on a group's SVG row:

- Look at the representative's row in all.fasta
- Count non-gap characters up to and including that column
- That count is the ungapped position, which is the same coordinate
  system the individual group rows already use

```
all.fasta column:     1234567890123456...
>rep_A                MVHLTPEEK--SAVTA...
                      ^^^^^^^^^^  ^^^^
                      ungapped:   1234567890  1213
                                              ^ column 15 → ungapped pos 13

>rep_B                MVHLT-EEKSAVT-AL...
                      ^^^^^  ^^^^^^^^ ^
                      ungapped: 12345 678910111213 14
                                                   ^ column 15 → ungapped pos 14
```

No sequence matching or pairwise alignment is needed. The representatives
are already rows in all.fasta — we just need to know which sequence ID
in all.fasta corresponds to each group's representative.

## Data flow

```
ZIP upload
 ├── groupA.fasta  → per-group conservation + SS  → row in SVG
 ├── groupB.fasta  → per-group conservation + SS  → row in SVG
 ├── groupC.fasta  → per-group conservation + SS  → row in SVG
 └── all.fasta     → find conserved columns across all sequences
                        ↓
                   for each conserved column, count ungapped positions
                   in each representative's row within all.fasta
                        ↓
                   connecting lines between adjacent SVG rows
```

## Implementation steps

### Step 1 — Detect all.fasta during upload

In the `/upload` route, when scanning the ZIP for FASTA files:

- If any file is named `all.fasta` (or `all.fa`, `all.faa`, `all.fas`),
  separate it from the group files
- Return it as a distinct field in the response: `all_fasta: "all.fasta"`
- It does **not** appear in the group file list, does not get a threshold
  input, and does not get its own SVG row

### Step 2 — Frontend changes

Minimal:

- Store `sessionData.all_fasta` from the upload response
- In the threshold step, show a note: "Cross-conservation enabled
  (all.fasta detected)" with an optional threshold input (default 95%)
- Pass `all_fasta` and `cross_threshold` to `/generate`

No new workflow step needed — it is automatic when all.fasta is in the ZIP.

### Step 3 — New analysis function in conservation.py

```python
def analyze_cross_conservation(all_fasta_path, representative_ids, threshold=95):
    """
    Find columns conserved across ALL sequences in a combined alignment,
    and map them to ungapped positions in each group's representative.

    Args:
        all_fasta_path: path to all.fasta (the combined alignment)
        representative_ids: ordered list of (group_fasta_name, seq_id)
            seq_id is the FASTA header of that group's representative
        threshold: conservation percentage

    Returns:
        list of dicts, one per conserved column:
        {
            'residue': 'R',
            'conservation': 98.5,
            'positions': {
                'groupA.fasta': 13,   # ungapped pos in rep A
                'groupB.fasta': 14,   # ungapped pos in rep B
                'groupC.fasta': 13,   # ungapped pos in rep C
            }
        }
        Only includes entries where every representative has a non-gap
        residue at that column.
    """
```

Logic:

1. Parse all.fasta, store every sequence indexed by ID
2. Look up each representative by ID
3. For each alignment column:
   a. Collect residues from every sequence in all.fasta
   b. Skip gap-only columns
   c. Count the most common residue across ALL sequences
   d. conservation = count / total_sequences * 100
   e. If conservation >= threshold:
      - Check each representative's character at this column
      - If any representative has a gap, skip this column
      - Otherwise, for each representative count non-gap characters
        up to and including this column → that is the ungapped position
      - Record the position

### Step 4 — Identifying representatives

For each group, the representative is the first sequence in the group's
FASTA file. In `/generate`, before calling the cross-conservation
analysis:

- Read the first sequence from each group file → get its ID (header)
- Pass these IDs to `analyze_cross_conservation()`
- The function looks them up by ID in all.fasta
- If an ID is not found, that group is skipped with a warning

### Step 5 — Backend wiring in app.py

In the `/generate` route, after processing all individual alignments:

```
if all_fasta in request:
    representative_ids = []
    for each group fasta_file:
        read first sequence → get its header ID
        representative_ids.append((group_name, seq_id))

    cross_positions = analyze_cross_conservation(
        all_fasta_path, representative_ids, cross_threshold
    )

    svg_content = generate_svg(alignments, cross_conservation=cross_positions)
```

### Step 6 — SVG rendering in svg_generator.py

Modify `generate_svg()` to accept an optional `cross_conservation` list.

For each cross-conserved position:
- For each pair of adjacent rows (row i, row i+1):
  - Look up the ungapped position for each row's group in `positions`
  - Compute x coordinates: `x = margin_left + ungapped_pos * scale`
  - Draw a line from (x_i, bottom of row i) to (x_i+1, top of row i+1)
- Color: use `get_color(residue)` so the connecting line color matches
  the residue type
- Style: thin (1px), semi-transparent (`stroke-opacity: 0.4`),
  dashed (`stroke-dasharray: 3,3`)
- Lines pass through the space between rows (below row i's scale
  markers, above row i+1's labels)

### Step 7 — Legend

Add a legend entry when cross-conservation lines are present:
a small dashed line sample labeled "Conserved across all groups".

## Edge cases

| Case | Handling |
|------|----------|
| Representative ID not found in all.fasta | Skip that group for cross-conservation, print warning |
| Representative has a gap at a conserved column | Skip that column entirely (no partial lines) |
| Many conserved positions | Low opacity (0.4) prevents visual clutter |
| all.fasta not in ZIP | Feature not activated, no UI change, no connecting lines |
| Sequences in all.fasta not matching groups exactly | Fine — conservation is computed over all sequences in all.fasta regardless |

## Files changed

| File | Change |
|------|--------|
| `app.py` | Detect all.fasta in `/upload`, gather representative IDs and run cross-conservation in `/generate` |
| `conservation.py` | New `analyze_cross_conservation()` function |
| `svg_generator.py` | Draw connecting lines between adjacent rows, add legend entry |
| `templates/index.html` | Store `all_fasta`, show note when detected, pass cross-threshold to backend |
