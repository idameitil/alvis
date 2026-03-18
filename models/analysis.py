from __future__ import annotations
import os
from dataclasses import dataclass, field

from Bio import SeqIO
from Bio.Align import PairwiseAligner

from conservation import analyze_alignment, analyze_cross_conservation
from svg_generator import generate_svg
from structure import run_dssp, get_ss_segments, align_pdb_to_fasta, remap_ss_segments


MIN_PDB_IDENTITY = 0.90   # 90 % sequence identity over aligned region
MIN_PDB_COVERAGE = 30     # at least 30 aligned positions


def _alignment_identity(seq_a, seq_b, alignment):
    """Compute (identical_count, aligned_length) from a pairwise alignment."""
    identical = 0
    aligned = 0
    for a_block, b_block in zip(alignment.aligned[0], alignment.aligned[1]):
        length = a_block[1] - a_block[0]
        for j in range(length):
            aligned += 1
            if seq_a[a_block[0] + j] == seq_b[b_block[0] + j]:
                identical += 1
    return identical, aligned


def find_representative_index(fasta_path, pdb_sequence,
                              min_identity=MIN_PDB_IDENTITY,
                              min_coverage=MIN_PDB_COVERAGE):
    """Find which FASTA sequence best matches the PDB chain sequence.

    Returns a dict with keys:
        index            — 0-based sequence index (None if no good match)
        identity         — fraction of identical residues in aligned region
        aligned_length   — number of aligned positions
        warning          — string if no sequence passed thresholds, else None
    """
    sequences = list(SeqIO.parse(fasta_path, 'fasta'))
    pdb_upper = pdb_sequence.upper()

    best = {'index': None, 'identity': 0.0, 'aligned_length': 0, 'warning': None}

    # Fast path: exact substring match
    for i, seq in enumerate(sequences):
        ungapped = str(seq.seq).replace('-', '').upper()
        if pdb_upper in ungapped or ungapped in pdb_upper:
            overlap = min(len(pdb_upper), len(ungapped))
            return {'index': i, 'identity': 1.0, 'aligned_length': overlap, 'warning': None}

    # Pairwise local alignment
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5

    for i, seq in enumerate(sequences):
        ungapped = str(seq.seq).replace('-', '').upper()
        alignments = aligner.align(ungapped, pdb_upper)
        if not alignments:
            continue
        identical, aligned = _alignment_identity(ungapped, pdb_upper, alignments[0])
        if aligned == 0:
            continue
        identity = identical / aligned
        if identity > best['identity'] or (
            identity == best['identity'] and aligned > best['aligned_length']
        ):
            best = {'index': i, 'identity': identity, 'aligned_length': aligned, 'warning': None}

    # Apply thresholds
    if best['index'] is None or best['identity'] < min_identity or best['aligned_length'] < min_coverage:
        pct = best['identity'] * 100
        best['warning'] = (
            f"No FASTA sequence matched the PDB chain well enough "
            f"(best: {pct:.0f}% identity over {best['aligned_length']} positions; "
            f"need \u2265{min_identity*100:.0f}% over \u2265{min_coverage}). "
            f"PDB assignment ignored."
        )
        best['index'] = None

    return best


@dataclass
class AlignmentResult:
    name: str
    num_sequences: int
    length: int
    threshold: float
    representative: str
    conserved: list
    secondary_structure: list | None = None
    pdb_coverage: str | None = None
    pdb_mapped: str | None = None
    warnings: list = field(default_factory=list)

    def to_dict(self):
        d = {
            'name': self.name,
            'num_sequences': self.num_sequences,
            'length': self.length,
            'threshold': self.threshold,
            'representative': self.representative,
            'conserved': self.conserved,
        }
        if self.secondary_structure is not None:
            d['secondary_structure'] = self.secondary_structure
        if self.pdb_coverage is not None:
            d['pdb_coverage'] = self.pdb_coverage
        if self.pdb_mapped is not None:
            d['pdb_mapped'] = self.pdb_mapped
        if self.warnings:
            d['warnings'] = self.warnings
        return d


@dataclass
class AnalysisResult:
    session_id: str
    alignments: list[AlignmentResult]
    alignment_info: list[dict]
    cross_conservation: list | None
    svg: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        response = {
            'svg': self.svg,
            'success': True,
            'alignment_info': self.alignment_info,
        }
        if self.warnings:
            response['warnings'] = self.warnings
        return response


def build_result(session) -> AnalysisResult:
    """Run conservation analysis and SVG generation for a session.

    This is the orchestration logic previously in the /generate route handler.
    """
    alignments = []
    alignment_info = []
    rep_indices = {}
    warnings_list = []

    for fasta_file, group in sorted(session.groups.items()):
        file_path = os.path.join(session.temp_dir, fasta_file)
        if not os.path.exists(file_path):
            continue

        threshold = group.threshold
        pdb_info = group.pdb

        # Determine representative index: manual override > PDB match > default (0)
        rep_index = group.representative_index
        pdb_identity = None
        if rep_index is None and pdb_info and pdb_info.chain_sequence:
            match = find_representative_index(file_path, pdb_info.chain_sequence)
            if match['warning']:
                warnings_list.append(f"{os.path.basename(fasta_file)}: {match['warning']}")
                pdb_info = None  # skip DSSP for this group
            else:
                rep_index = match['index']
                pdb_identity = match['identity']
                if pdb_identity < 1.0:
                    pct = pdb_identity * 100
                    warnings_list.append(
                        f"{os.path.basename(fasta_file)}: PDB chain matched sequence "
                        f"#{rep_index + 1} with {pct:.1f}% identity over "
                        f"{match['aligned_length']} positions (not a perfect match)."
                    )
        if rep_index is None:
            rep_index = 0
        rep_indices[fasta_file] = rep_index

        conserved_positions, seq_length = analyze_alignment(
            file_path, threshold, representative_index=rep_index
        )

        # Read sequences for num_sequences and representative record
        with open(file_path, 'r') as f:
            seqs = list(SeqIO.parse(f, 'fasta'))
        num_sequences = len(seqs)
        rep_seq_record = seqs[rep_index] if rep_index < len(seqs) else seqs[0]

        alignment_data = {
            'name': group.display_name or os.path.basename(fasta_file),
            'conserved': conserved_positions,
            'length': seq_length,
            'threshold': threshold,
            'num_sequences': num_sequences,
        }

        info = {
            'name': group.display_name or os.path.basename(fasta_file),
            'num_sequences': num_sequences,
        }

        # Run DSSP if PDB provided
        if pdb_info:
            info['representative'] = rep_seq_record.id
            if pdb_identity is not None:
                info['pdb_identity'] = f'{pdb_identity * 100:.1f}%'
            pdb_path = os.path.join(session.temp_dir, 'pdb', pdb_info.filename)
            chain_id = pdb_info.chain_id
            if os.path.exists(pdb_path):
                try:
                    residues = run_dssp(pdb_path, chain_id=chain_id)
                    segments = get_ss_segments(residues)

                    rep_seq = str(rep_seq_record.seq).replace('-', '')
                    pdb_to_fasta, _ = align_pdb_to_fasta(residues, rep_seq)
                    remapped = remap_ss_segments(segments, pdb_to_fasta, seq_length)
                    alignment_data['secondary_structure'] = remapped
                    alignment_data['ss_length'] = len(residues)

                    mapped_count = len(pdb_to_fasta)
                    coverage = mapped_count / seq_length * 100 if seq_length else 0
                    info['pdb_coverage'] = f'{coverage:.1f}%'
                    info['pdb_mapped'] = f'{mapped_count} / {seq_length} positions'

                    if coverage < 10:
                        alignment_data['ss_warning'] = (
                            f"DSSP resolved only {len(residues)} residues "
                            f"({mapped_count} mapped to alignment). "
                            f"The PDB may lack backbone coordinates for most residues."
                        )
                except Exception as e:
                    print(f"DSSP warning for {fasta_file}: {e}")

        alignment_info.append(info)
        alignments.append(alignment_data)

    # Cross-conservation analysis
    cross_positions = None
    if session.all_fasta:
        all_fasta_path = os.path.join(session.temp_dir, session.all_fasta)
        if os.path.exists(all_fasta_path):
            try:
                representative_ids = []
                for fasta_file in sorted(session.groups.keys()):
                    file_path = os.path.join(session.temp_dir, fasta_file)
                    if os.path.exists(file_path):
                        rep_index = rep_indices.get(fasta_file, 0)
                        with open(file_path, 'r') as f:
                            seqs = list(SeqIO.parse(f, 'fasta'))
                        rep_record = seqs[rep_index] if rep_index < len(seqs) else seqs[0]
                        representative_ids.append(
                            (os.path.basename(fasta_file), rep_record.id)
                        )

                if representative_ids:
                    cross_positions = analyze_cross_conservation(
                        all_fasta_path, representative_ids, session.cross_threshold
                    )
            except Exception as e:
                print(f"Cross-conservation warning: {e}")

    # Generate SVG
    svg_content = generate_svg(alignments, cross_conservation=cross_positions)

    # Collect warnings
    warnings = warnings_list + [a['ss_warning'] for a in alignments if a.get('ss_warning')]

    return AnalysisResult(
        session_id=session.id,
        alignments=[],  # could populate AlignmentResult objects if needed later
        alignment_info=alignment_info,
        cross_conservation=cross_positions,
        svg=svg_content,
        warnings=warnings,
    )
