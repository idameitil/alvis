import pytest
from conservation import analyze_alignment, analyze_cross_conservation


class TestAnalyzeAlignment:
    def test_fully_conserved(self, tmp_fasta):
        """3 identical sequences at threshold=100 → all positions detected."""
        fasta = ">s1\nACDE\n>s2\nACDE\n>s3\nACDE\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=100)
        assert length == 4
        assert len(positions) == 4
        residues = [p['residue'] for p in positions]
        assert residues == ['A', 'C', 'D', 'E']

    def test_below_threshold(self, tmp_fasta):
        """2/3 match at threshold=80 → not detected (66.7% < 80%)."""
        fasta = ">s1\nA\n>s2\nA\n>s3\nX\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=80)
        assert length == 1
        assert positions == []

    def test_at_threshold_boundary(self, tmp_fasta):
        """2/3 match at threshold=66 → detected (66.7% >= 66)."""
        fasta = ">s1\nA\n>s2\nA\n>s3\nX\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=66)
        assert length == 1
        assert len(positions) == 1
        assert positions[0]['residue'] == 'A'
        assert positions[0]['conservation'] == pytest.approx(66.67, abs=0.1)

    def test_gaps_count_against_conservation(self, tmp_fasta):
        """Gaps in non-representative seqs reduce the conservation percentage."""
        # 2 out of 3 have 'A', one has gap → 66.7%
        fasta = ">s1\nA\n>s2\nA\n>s3\n-\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=80)
        assert positions == []

    def test_ungapped_position_mapping(self, tmp_fasta):
        """Representative has gaps → position is correctly 1-indexed skipping gaps."""
        # Representative: -A-C → ungapped positions: A=1, C=2
        fasta = ">s1\n-A-C\n>s2\n-A-C\n>s3\n-A-C\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=100)
        assert length == 2
        pos_nums = [p['position'] for p in positions]
        assert pos_nums == [1, 2]

    def test_empty_alignment(self, tmp_fasta):
        """Empty FASTA file → returns ([], 0)."""
        path = tmp_fasta("")
        positions, length = analyze_alignment(path, threshold=50)
        assert positions == []
        assert length == 0

    def test_gap_in_representative_skipped(self, tmp_fasta):
        """If representative has gap at a conserved column, it's skipped."""
        # Column 1: s1='-', s2='A', s3='A' → conserved 'A' at 66.7%
        # but representative (s1) has gap → should be skipped
        fasta = ">s1\n-B\n>s2\nAB\n>s3\nAB\n"
        path = tmp_fasta(fasta)
        positions, length = analyze_alignment(path, threshold=60)
        # Only position for 'B' should be detected, not the gap column
        residues = [p['residue'] for p in positions]
        assert 'A' not in residues
        assert 'B' in residues


class TestCrossConservation:
    def test_basic_cross_conservation(self, tmp_path):
        """Two groups, all.fasta fully conserved → positions map correctly."""
        # group1 rep = seq1, group2 rep = seq4
        # all.fasta: all 6 seqs have identical aligned sequence
        all_content = (
            ">seq1\nACDE\n"
            ">seq2\nACDE\n"
            ">seq3\nACDE\n"
            ">seq4\nACDE\n"
            ">seq5\nACDE\n"
            ">seq6\nACDE\n"
        )
        all_path = str(tmp_path / "all.fasta")
        with open(all_path, 'w') as f:
            f.write(all_content)

        rep_ids = [
            ("group1.fasta", "seq1"),
            ("group2.fasta", "seq4"),
        ]
        result = analyze_cross_conservation(all_path, rep_ids, threshold=100)
        assert len(result) == 4
        # Each entry should map both groups
        for entry in result:
            assert "group1.fasta" in entry['positions']
            assert "group2.fasta" in entry['positions']

    def test_cross_conservation_gap_skip(self, tmp_path):
        """Representative has gap at conserved column → that entry excluded."""
        all_content = (
            ">seq1\n-CDE\n"
            ">seq2\nACDE\n"
            ">seq3\nACDE\n"
            ">seq4\nACDE\n"
        )
        all_path = str(tmp_path / "all.fasta")
        with open(all_path, 'w') as f:
            f.write(all_content)

        rep_ids = [
            ("group1.fasta", "seq1"),
            ("group2.fasta", "seq4"),
        ]
        result = analyze_cross_conservation(all_path, rep_ids, threshold=50)
        # Column 0 is conserved but seq1 has gap → should be excluded
        positions_col0 = [e for e in result if e['positions'].get('group2.fasta') == 1]
        assert len(positions_col0) == 0
