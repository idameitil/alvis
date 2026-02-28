from Bio import SeqIO
from collections import Counter

def analyze_alignment(fasta_path, threshold, representative_index=0):
    """
    Analyze a protein alignment and identify conserved positions.

    Args:
        fasta_path: Path to FASTA alignment file
        threshold: Conservation threshold (0-100)
        representative_index: 0-based index of the representative sequence (default: first)

    Returns:
        Tuple of (conserved_positions, sequence_length):
        - conserved_positions: List of dicts with conserved position info
        - sequence_length: Actual ungapped length of representative sequence
    """
    # Read all sequences from alignment
    # Try different encodings to handle various file formats
    sequences = None
    for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
        try:
            with open(fasta_path, 'r', encoding=encoding) as f:
                sequences = list(SeqIO.parse(f, "fasta"))
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if sequences is None:
        raise ValueError(f"Could not read {fasta_path} with any supported encoding")

    if not sequences:
        return [], 0

    # Select the representative sequence
    rep_idx = min(representative_index, len(sequences) - 1)
    representative = str(sequences[rep_idx].seq)
    num_sequences = len(sequences)
    alignment_length = len(representative)

    # Calculate ungapped length of representative
    ungapped_length = len(representative.replace('-', ''))

    # Validate that representative sequence is not empty or all gaps
    if ungapped_length == 0:
        raise ValueError(f"Invalid alignment in {fasta_path}: first sequence is empty or contains only gaps")

    # Check all sequences have same length (proper alignment)
    for seq in sequences:
        if len(seq.seq) != alignment_length:
            raise ValueError(f"Alignment error in {fasta_path}: sequences have different lengths")

    conserved_positions = []

    # Analyze each column in the alignment
    for pos in range(alignment_length):
        # Get all residues at this position
        column = [str(seq.seq[pos]).upper() for seq in sequences]

        # Skip gap-only columns
        non_gap_residues = [r for r in column if r != '-']
        if not non_gap_residues:
            continue

        # Count residue frequencies
        residue_counts = Counter(non_gap_residues)
        most_common_residue, count = residue_counts.most_common(1)[0]

        # Calculate conservation percentage (as fraction of total sequences, not just non-gap)
        conservation = (count / num_sequences) * 100

        # Check if meets threshold
        if conservation >= threshold:
            # Get residue from representative sequence
            rep_residue = representative[pos].upper()

            # Skip if it's a gap in representative
            if rep_residue == '-':
                continue

            # Calculate position in ungapped representative sequence
            ungapped_position = len(representative[:pos+1].replace('-', ''))

            conserved_positions.append({
                'position': ungapped_position,
                'residue': rep_residue,
                'conservation': conservation
            })

    return conserved_positions, ungapped_length


def analyze_cross_conservation(all_fasta_path, representative_ids, threshold=95):
    """
    Find columns conserved across ALL sequences in a combined alignment,
    and map them to ungapped positions in each group's representative.

    Args:
        all_fasta_path: path to all.fasta (the combined alignment)
        representative_ids: ordered list of (group_fasta_name, seq_id)
            seq_id is the FASTA header of that group's representative
        threshold: conservation percentage (0-100)

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
    # Read all sequences from the combined alignment
    sequences = None
    for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
        try:
            with open(all_fasta_path, 'r', encoding=encoding) as f:
                sequences = list(SeqIO.parse(f, "fasta"))
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if sequences is None:
        raise ValueError(f"Could not read {all_fasta_path} with any supported encoding")

    if not sequences:
        return []

    # Index sequences by ID for representative lookup
    seq_by_id = {seq.id: str(seq.seq) for seq in sequences}

    num_sequences = len(sequences)
    alignment_length = len(sequences[0].seq)

    # Validate alignment length consistency
    for seq in sequences:
        if len(seq.seq) != alignment_length:
            raise ValueError(
                f"Alignment error in {all_fasta_path}: sequences have different lengths"
            )

    # Look up each representative in the combined alignment
    rep_seqs = {}  # group_name -> sequence string from all.fasta
    missing = []
    for group_name, seq_id in representative_ids:
        if seq_id in seq_by_id:
            rep_seqs[group_name] = seq_by_id[seq_id]
        else:
            missing.append((group_name, seq_id))

    if missing:
        for group_name, seq_id in missing:
            print(f"Cross-conservation warning: representative '{seq_id}' "
                  f"for {group_name} not found in all.fasta")

    if not rep_seqs:
        return []

    # Analyze each column
    conserved = []
    for col in range(alignment_length):
        # Collect residues from every sequence
        column = [str(seq.seq[col]).upper() for seq in sequences]

        non_gap = [r for r in column if r != '-']
        if not non_gap:
            continue

        residue_counts = Counter(non_gap)
        most_common_residue, count = residue_counts.most_common(1)[0]
        conservation = (count / num_sequences) * 100

        if conservation < threshold:
            continue

        # Check each representative at this column — skip if any has a gap
        positions = {}
        skip = False
        for group_name, rep_seq in rep_seqs.items():
            residue = rep_seq[col].upper()
            if residue == '-':
                skip = True
                break
            # Ungapped position = count of non-gap chars up to and including this column
            ungapped_pos = len(rep_seq[:col + 1].replace('-', ''))
            positions[group_name] = ungapped_pos

        if skip:
            continue

        conserved.append({
            'residue': most_common_residue,
            'conservation': conservation,
            'positions': positions,
        })

    return conserved
