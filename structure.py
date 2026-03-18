"""
PDB secondary structure mapped onto FASTA alignment coordinates.

Pipeline:
  1. run_dssp()          — extract per-residue H/E/C from a PDB file
  2. get_ss_segments()   — merge consecutive residues into segments
  3. align_pdb_to_fasta() — build bidirectional position mapping (PDB <-> FASTA)
  4. remap_ss_segments() — translate segments into FASTA coordinates
"""
import os

from Bio.PDB import PDBParser, MMCIFParser
from Bio.PDB.DSSP import DSSP
from Bio.Align import PairwiseAligner


# DSSP 8-state to 3-state mapping
DSSP_TO_3STATE = {
    'H': 'H',  # alpha-helix
    'G': 'H',  # 3_10-helix
    'I': 'H',  # pi-helix
    'E': 'E',  # beta-strand
    'B': 'E',  # beta-bridge
    'T': 'C',  # turn
    'S': 'C',  # bend
    '-': 'C',  # none
}


# ---------------------------------------------------------------------------
# 1. Extract per-residue secondary structure
# ---------------------------------------------------------------------------

def run_dssp(pdb_path, chain_id=None):
    """Run DSSP on a PDB file and return per-residue secondary structure.

    Returns a list of dicts, one per residue:
        position  — 1-indexed sequential number within the chain
        resname   — one-letter amino acid code
        ss8       — DSSP 8-state code (H, G, I, E, B, T, S, -)
        ss3       — simplified 3-state (H=helix, E=sheet, C=coil)
    """
    if not os.path.exists(pdb_path):
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")

    if pdb_path.lower().endswith('.cif'):
        parser = MMCIFParser(QUIET=True)
    else:
        parser = PDBParser(QUIET=True)
    model = parser.get_structure("protein", pdb_path)[0]

    available_chains = [c.id for c in model.get_chains()]
    if not available_chains:
        raise ValueError(f"No chains found in {pdb_path}")

    if chain_id is None:
        chain_id = available_chains[0]
    elif chain_id not in available_chains:
        raise ValueError(
            f"Chain '{chain_id}' not found in {pdb_path}. "
            f"Available: {', '.join(available_chains)}"
        )

    try:
        dssp = DSSP(model, pdb_path, dssp="mkdssp")
    except Exception as e:
        raise RuntimeError(
            f"DSSP failed on {pdb_path}: {e}. "
            f"Ensure mkdssp is installed and in PATH."
        )

    residues = []
    seq_pos = 0
    for dssp_key in dssp.keys():
        dssp_chain, _ = dssp_key
        if dssp_chain != chain_id:
            continue

        seq_pos += 1
        aa = dssp[dssp_key][1]   # one-letter amino acid
        ss8 = dssp[dssp_key][2]  # 8-state secondary structure

        if aa == 'X':  # non-standard residue
            continue

        residues.append({
            'position': seq_pos,
            'resname': aa,
            'ss8': ss8,
            'ss3': DSSP_TO_3STATE.get(ss8, 'C'),
        })

    if not residues:
        raise ValueError(f"No residues found for chain '{chain_id}' in {pdb_path}")

    return residues


# ---------------------------------------------------------------------------
# 2. Merge residues into contiguous segments
# ---------------------------------------------------------------------------

def get_ss_segments(residues):
    """Group consecutive residues with the same SS type into segments.

    Returns a list of dicts:
        start — first position (1-indexed)
        end   — last position (1-indexed)
        ss3   — 'H', 'E', or 'C'
    """
    if not residues:
        return []

    segments = []
    current_ss = residues[0]['ss3']
    start = residues[0]['position']

    for i in range(1, len(residues)):
        if residues[i]['ss3'] != current_ss:
            segments.append({'start': start, 'end': residues[i - 1]['position'], 'ss3': current_ss})
            current_ss = residues[i]['ss3']
            start = residues[i]['position']

    segments.append({'start': start, 'end': residues[-1]['position'], 'ss3': current_ss})
    return segments


# ---------------------------------------------------------------------------
# 3. Build bidirectional position mapping (PDB <-> FASTA)
# ---------------------------------------------------------------------------

def _make_local_aligner():
    """Shared aligner config used by align_pdb_to_fasta."""
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5
    return aligner


def align_pdb_to_fasta(residues, fasta_sequence):
    """Map each PDB residue position to its corresponding FASTA ungapped position.

    The PDB chain may cover only a domain, have missing residues, or differ
    slightly from the FASTA sequence. This tries fast substring matching
    first, then falls back to pairwise local alignment.

    Returns (pdb_to_fasta, fasta_to_pdb) — two dicts of 1-indexed positions.
    """
    pdb_seq = ''.join(r['resname'] for r in residues).upper()
    fasta_upper = fasta_sequence.upper()

    pdb_to_fasta = {}
    fasta_to_pdb = {}

    def _record(pdb_pos, fasta_pos):
        pdb_to_fasta[pdb_pos] = fasta_pos
        fasta_to_pdb[fasta_pos] = pdb_pos

    # Fast path: PDB is a substring of FASTA (most common case)
    idx = fasta_upper.find(pdb_seq)
    if idx >= 0:
        for i, r in enumerate(residues):
            _record(r['position'], idx + i + 1)
        return pdb_to_fasta, fasta_to_pdb

    # Fast path: FASTA is a substring of PDB (PDB is longer)
    idx = pdb_seq.find(fasta_upper)
    if idx >= 0:
        for i in range(len(fasta_upper)):
            _record(residues[idx + i]['position'], i + 1)
        return pdb_to_fasta, fasta_to_pdb

    # Fallback: pairwise local alignment
    aligner = _make_local_aligner()
    alignments = aligner.align(fasta_upper, pdb_seq)
    if not alignments:
        return pdb_to_fasta, fasta_to_pdb

    # aligned[0] = FASTA blocks, aligned[1] = PDB blocks
    # Each block is a (start, end) tuple — 0-indexed, half-open
    best = alignments[0]
    for fasta_block, pdb_block in zip(best.aligned[0], best.aligned[1]):
        fasta_start, fasta_end = fasta_block
        pdb_start, _ = pdb_block
        for j in range(fasta_end - fasta_start):
            _record(residues[pdb_start + j]['position'], fasta_start + j + 1)

    return pdb_to_fasta, fasta_to_pdb


# ---------------------------------------------------------------------------
# 4. Translate PDB-coordinate segments into FASTA coordinates
# ---------------------------------------------------------------------------

def remap_ss_segments(segments, pdb_to_fasta, fasta_length):
    """Remap SS segments from PDB coordinates to FASTA coordinates.

    Positions not covered by the PDB mapping get type 'U' (uncovered).

    Returns a list of segment dicts in FASTA coordinates:
        start — first FASTA position (1-indexed)
        end   — last FASTA position (1-indexed)
        ss3   — 'H', 'E', 'C', or 'U'
    """
    if fasta_length == 0:
        return []

    # Scatter: assign an SS type to each FASTA position that has a PDB mapping
    fasta_ss = {}
    for seg in segments:
        for pdb_pos in range(seg['start'], seg['end'] + 1):
            fasta_pos = pdb_to_fasta.get(pdb_pos)
            if fasta_pos is not None:
                fasta_ss[fasta_pos] = seg['ss3']

    # Gather: walk FASTA positions and merge consecutive same-type into segments
    result = []
    current_type = fasta_ss.get(1, 'U')
    start = 1

    for pos in range(2, fasta_length + 1):
        ss = fasta_ss.get(pos, 'U')
        if ss != current_type:
            result.append({'start': start, 'end': pos - 1, 'ss3': current_type})
            current_type = ss
            start = pos

    result.append({'start': start, 'end': fasta_length, 'ss3': current_type})
    return result
