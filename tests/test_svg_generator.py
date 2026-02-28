import xml.etree.ElementTree as ET
from svg_generator import position_labels_smartly, generate_svg


class TestPositionLabelsSmart:
    def test_no_conserved_positions(self):
        result = position_labels_smartly([], alignment_length=100, line_length_pixels=600)
        assert result == []

    def test_non_overlapping_labels(self):
        """Widely spaced positions should all be at level 0."""
        positions = [
            {'position': 10, 'residue': 'A', 'conservation': 100},
            {'position': 50, 'residue': 'C', 'conservation': 100},
            {'position': 90, 'residue': 'D', 'conservation': 100},
        ]
        result = position_labels_smartly(positions, alignment_length=100, line_length_pixels=600)
        assert len(result) == 3
        assert all(p['y_level'] == 0 for p in result)

    def test_overlapping_labels_stacked(self):
        """Close positions should get stacked to different levels."""
        positions = [
            {'position': 10, 'residue': 'A', 'conservation': 100},
            {'position': 11, 'residue': 'C', 'conservation': 100},
            {'position': 12, 'residue': 'D', 'conservation': 100},
        ]
        result = position_labels_smartly(positions, alignment_length=100, line_length_pixels=600)
        levels = {p['y_level'] for p in result}
        # At least 2 different levels needed since labels are ~25px wide and positions are 6px apart
        assert len(levels) > 1


class TestGenerateSvg:
    def test_smoke_test(self):
        """Given 2 alignments, output is valid XML with expected SVG elements."""
        alignments = [
            {
                'name': 'group1.fasta',
                'conserved': [
                    {'position': 5, 'residue': 'A', 'conservation': 100},
                    {'position': 15, 'residue': 'K', 'conservation': 95},
                ],
                'length': 100,
            },
            {
                'name': 'group2.fasta',
                'conserved': [
                    {'position': 10, 'residue': 'D', 'conservation': 90},
                ],
                'length': 80,
            },
        ]
        svg_str = generate_svg(alignments)

        # Should be valid XML
        root = ET.fromstring(svg_str)
        assert root.tag.endswith('svg')

        # Should contain text elements with residue letters and group names
        all_text = ET.tostring(root, encoding='unicode')
        assert 'group1.fasta' in all_text
        assert 'group2.fasta' in all_text
        assert '>A<' in all_text
        assert '>K<' in all_text
        assert '>D<' in all_text

    def test_with_cross_conservation(self):
        """Cross-conservation lines produce dashed stroke elements."""
        alignments = [
            {
                'name': 'group1.fasta',
                'conserved': [{'position': 5, 'residue': 'A', 'conservation': 100}],
                'length': 100,
            },
            {
                'name': 'group2.fasta',
                'conserved': [{'position': 5, 'residue': 'A', 'conservation': 100}],
                'length': 100,
            },
        ]
        cross = [
            {
                'residue': 'A',
                'conservation': 100,
                'positions': {'group1.fasta': 5, 'group2.fasta': 5},
            }
        ]
        svg_str = generate_svg(alignments, cross_conservation=cross)
        assert 'stroke-dasharray' in svg_str
