from Bio import SeqIO
from collections import Counter

def analyze_alignment(fasta_path, threshold):
    """
    Analyze a protein alignment and identify conserved positions.

    Args:
        fasta_path: Path to FASTA alignment file
        threshold: Conservation threshold (0-100)

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

    # First sequence is the representative
    representative = str(sequences[0].seq)
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
