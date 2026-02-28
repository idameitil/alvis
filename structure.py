"""
Secondary structure extraction from PDB files using DSSP.
"""
import os
from Bio.PDB import PDBParser
from Bio.PDB.DSSP import DSSP


# DSSP 8-state to 3-state mapping
DSSP_TO_3STATE = {
    'H': 'H',  # alpha-helix
    'G': 'H',  # 3_10-helix → helix
    'I': 'H',  # pi-helix → helix
    'E': 'E',  # beta-strand
    'B': 'E',  # beta-bridge → sheet
    'T': 'C',  # turn → coil
    'S': 'C',  # bend → coil
    '-': 'C',  # none → coil
}


def run_dssp(pdb_path, chain_id=None):
    """
    Run DSSP on a PDB file and return per-residue secondary structure.

    Args:
        pdb_path: Path to PDB file
        chain_id: Chain to extract (default: first chain found)

    Returns:
        List of dicts with keys:
          - position: residue number (1-indexed, sequential)
          - resname: one-letter amino acid code
          - ss8: DSSP 8-state code (H, G, I, E, B, T, S, -)
          - ss3: simplified 3-state code (H=helix, E=sheet, C=coil)

    Raises:
        FileNotFoundError: if PDB file doesn't exist
        ValueError: if chain_id not found or PDB has no protein chains
        RuntimeError: if DSSP execution fails
    """
    if not os.path.exists(pdb_path):
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("protein", pdb_path)
    model = structure[0]

    # Resolve chain
    available_chains = [c.id for c in model.get_chains()]
    if not available_chains:
        raise ValueError(f"No chains found in {pdb_path}")

    if chain_id is None:
        chain_id = available_chains[0]
    elif chain_id not in available_chains:
        raise ValueError(
            f"Chain '{chain_id}' not found in {pdb_path}. "
            f"Available chains: {', '.join(available_chains)}"
        )

    # Run DSSP
    try:
        dssp = DSSP(model, pdb_path, dssp="mkdssp")
    except Exception as e:
        raise RuntimeError(
            f"DSSP failed on {pdb_path}: {e}. "
            f"Ensure mkdssp is installed and in PATH."
        )

    # Extract secondary structure for the target chain
    residues = []
    seq_pos = 0
    for dssp_key in dssp.keys():
        dssp_chain, dssp_resid = dssp_key
        if dssp_chain != chain_id:
            continue

        seq_pos += 1
        data = dssp[dssp_key]
        aa = data[1]       # one-letter amino acid
        ss8 = data[2]      # 8-state secondary structure

        # Skip non-standard residues marked as 'X'
        if aa == 'X':
            continue

        residues.append({
            'position': seq_pos,
            'resname': aa,
            'ss8': ss8,
            'ss3': DSSP_TO_3STATE.get(ss8, 'C'),
        })

    if not residues:
        raise ValueError(
            f"No residues found for chain '{chain_id}' in {pdb_path}"
        )

    return residues


def get_ss_segments(residues):
    """
    Convert per-residue secondary structure into contiguous segments.

    Args:
        residues: list of dicts from run_dssp()

    Returns:
        List of dicts with keys:
          - start: first position in segment (1-indexed)
          - end: last position in segment (1-indexed)
          - ss3: 'H', 'E', or 'C'
    """
    if not residues:
        return []

    segments = []
    current_ss = residues[0]['ss3']
    start = residues[0]['position']

    for i in range(1, len(residues)):
        r = residues[i]
        if r['ss3'] != current_ss:
            segments.append({
                'start': start,
                'end': residues[i - 1]['position'],
                'ss3': current_ss,
            })
            current_ss = r['ss3']
            start = r['position']

    # Final segment
    segments.append({
        'start': start,
        'end': residues[-1]['position'],
        'ss3': current_ss,
    })

    return segments


def align_pdb_to_fasta(residues, fasta_sequence):
    """
    Build per-residue position mappings between PDB chain and FASTA sequence.

    Uses substring matching (fast path) or pairwise local alignment (fallback)
    to map each PDB residue position to the corresponding FASTA ungapped position.

    Args:
        residues: list of dicts from run_dssp() (each has 'resname', 'position')
        fasta_sequence: ungapped representative sequence from FASTA

    Returns:
        (pdb_to_fasta, fasta_to_pdb) — two dicts mapping 1-indexed positions
        bidirectionally. Empty dicts if no alignment found.
    """
    pdb_seq = ''.join(r['resname'] for r in residues)
    fasta_upper = fasta_sequence.upper()
    pdb_upper = pdb_seq.upper()

    pdb_to_fasta = {}
    fasta_to_pdb = {}

    # Fast path: PDB sequence is a substring of FASTA
    idx = fasta_upper.find(pdb_upper)
    if idx >= 0:
        for i, r in enumerate(residues):
            pdb_pos = r['position']
            fasta_pos = idx + i + 1  # 1-indexed
            pdb_to_fasta[pdb_pos] = fasta_pos
            fasta_to_pdb[fasta_pos] = pdb_pos
        return pdb_to_fasta, fasta_to_pdb

    # Fast path: FASTA sequence is a substring of PDB
    idx = pdb_upper.find(fasta_upper)
    if idx >= 0:
        for i in range(len(fasta_upper)):
            pdb_pos = residues[idx + i]['position']
            fasta_pos = i + 1  # 1-indexed
            pdb_to_fasta[pdb_pos] = fasta_pos
            fasta_to_pdb[fasta_pos] = pdb_pos
        return pdb_to_fasta, fasta_to_pdb

    # Fallback: pairwise local alignment
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5

    alignments = aligner.align(fasta_upper, pdb_upper)
    if not alignments:
        return pdb_to_fasta, fasta_to_pdb

    best = alignments[0]
    # aligned[0] = FASTA blocks, aligned[1] = PDB blocks
    # Each block is a list of (start, end) tuples (0-indexed, half-open)
    for fasta_block, pdb_block in zip(best.aligned[0], best.aligned[1]):
        fasta_start, fasta_end = fasta_block
        pdb_start, pdb_end = pdb_block
        block_len = fasta_end - fasta_start
        for j in range(block_len):
            pdb_pos = residues[pdb_start + j]['position']
            fasta_pos = fasta_start + j + 1  # 1-indexed
            pdb_to_fasta[pdb_pos] = fasta_pos
            fasta_to_pdb[fasta_pos] = pdb_pos

    return pdb_to_fasta, fasta_to_pdb


def remap_ss_segments(segments, pdb_to_fasta, fasta_length):
    """
    Remap secondary structure segments from PDB coordinates to FASTA coordinates,
    filling unmapped FASTA positions with 'U' (uncovered) segments.

    Args:
        segments: list of segment dicts from get_ss_segments() (PDB coordinates)
        pdb_to_fasta: dict mapping PDB positions to FASTA positions
        fasta_length: length of the ungapped FASTA sequence

    Returns:
        List of segment dicts in FASTA coordinates, with 'U' type for uncovered regions.
    """
    # Build per-FASTA-position SS type from PDB segments
    fasta_ss = {}
    for seg in segments:
        for pdb_pos in range(seg['start'], seg['end'] + 1):
            fasta_pos = pdb_to_fasta.get(pdb_pos)
            if fasta_pos is not None:
                fasta_ss[fasta_pos] = seg['ss3']

    # Walk all FASTA positions and merge consecutive same-type into segments
    if fasta_length == 0:
        return []

    result = []
    current_type = fasta_ss.get(1, 'U')
    start = 1

    for pos in range(2, fasta_length + 1):
        ss = fasta_ss.get(pos, 'U')
        if ss != current_type:
            result.append({'start': start, 'end': pos - 1, 'ss3': current_type})
            current_type = ss
            start = pos

    # Final segment
    result.append({'start': start, 'end': fasta_length, 'ss3': current_type})

    return result


def map_ss_to_sequence(residues, fasta_sequence):
    """
    Find where PDB residues map onto the FASTA representative sequence.

    The PDB may cover only a domain of the full protein. This function finds
    the offset so that SS positions align with the correct FASTA positions.

    Args:
        residues: list of dicts from run_dssp() (each has 'resname')
        fasta_sequence: ungapped representative sequence from FASTA

    Returns:
        Offset such that: fasta_position = pdb_position + offset
        (both 1-indexed). Returns 0 if sequences already match.
    """
    pdb_seq = ''.join(r['resname'] for r in residues)
    fasta_upper = fasta_sequence.upper()
    pdb_upper = pdb_seq.upper()

    # Fast path: exact substring match
    idx = fasta_upper.find(pdb_upper)
    if idx >= 0:
        return idx

    # Fallback: local pairwise alignment (handles mutations, missing residues)
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5

    alignments = aligner.align(fasta_upper, pdb_upper)
    if alignments:
        best = alignments[0]
        # aligned[0] = target (fasta) blocks, aligned[1] = query (pdb) blocks
        fasta_start = best.aligned[0][0][0]  # 0-indexed start in fasta
        pdb_start = best.aligned[1][0][0]    # 0-indexed start in pdb
        return fasta_start - pdb_start

    return 0


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python structure.py <pdb_file> [chain_id]")
        print()
        print("Example:")
        print("  python structure.py 1ubq.pdb A")
        sys.exit(1)

    pdb_file = sys.argv[1]
    chain = sys.argv[2] if len(sys.argv) > 2 else None

    residues = run_dssp(pdb_file, chain_id=chain)

    # Print per-residue table
    print(f"{'Pos':>4}  {'AA':>2}  {'SS8':>3}  {'SS3':>3}")
    print("-" * 18)
    for r in residues:
        print(f"{r['position']:>4}  {r['resname']:>2}  {r['ss8']:>3}  {r['ss3']:>3}")

    # Print segments
    print()
    segments = get_ss_segments(residues)
    print("Secondary structure segments:")
    for seg in segments:
        label = {'H': 'Helix', 'E': 'Sheet', 'C': 'Coil'}[seg['ss3']]
        print(f"  {label:5s}  {seg['start']:>4} - {seg['end']:>4}")

    # Print compact string
    ss_string = ''.join(r['ss3'] for r in residues)
    print(f"\nCompact: {ss_string}")
    print(f"Length:  {len(residues)} residues")
