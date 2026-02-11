import math
import svgwrite
from io import StringIO

# Color scheme for amino acids
COLOR_SCHEME = {
    'G': (255, 0, 255), 'Y': (255, 0, 255), 'S': (255, 0, 255),
    'T': (255, 0, 255), 'N': (255, 0, 255), 'C': (255, 0, 255), 'Q': (255, 0, 255),
    'V': (70, 156, 118), 'I': (70, 156, 118), 'L': (70, 156, 118),
    'P': (70, 156, 118), 'F': (70, 156, 118), 'M': (70, 156, 118),
    'W': (70, 156, 118), 'A': (70, 156, 118),
    'H': (255, 140, 0),
    'D': (192, 0, 0), 'E': (192, 0, 0),
    'K': (0, 0, 255), 'R': (0, 0, 255)
}

# Secondary structure colors (fill, outline)
SS_FILL = {
    'H': 'rgb(230,90,90)',    # helix — coral red
    'E': 'rgb(240,195,50)',   # sheet — gold
    'C': 'rgb(180,180,180)',  # coil  — light gray
}
SS_STROKE = {
    'H': 'rgb(180,60,60)',    # helix outline
    'E': 'rgb(190,150,30)',   # sheet outline
}

def get_color(residue):
    """Get RGB color for a residue"""
    color = COLOR_SCHEME.get(residue.upper(), (128, 128, 128))  # Default gray
    return f'rgb({color[0]},{color[1]},{color[2]})'

def _draw_helix(dwg, x_start, x_end, y_center, amplitude, scale):
    """Draw alpha helix as a filled sinusoidal ribbon."""
    seg_length = x_end - x_start
    if seg_length < 1:
        return

    ribbon_half = 1.5  # half the ribbon thickness
    period = max(3.6 * scale, 14)  # one wave per helix turn, min 14px
    num_samples = min(max(int(seg_length), 20), 300)

    top_points = []
    bottom_points = []

    for i in range(num_samples + 1):
        frac = i / num_samples
        x = x_start + frac * seg_length
        phase = 2 * math.pi * (frac * seg_length) / period
        wave = math.sin(phase) * amplitude
        top_points.append((x, y_center + wave - ribbon_half))
        bottom_points.append((x, y_center + wave + ribbon_half))

    # Closed path: top edge forward, bottom edge backward
    d = f"M {top_points[0][0]:.1f},{top_points[0][1]:.1f}"
    for x, y in top_points[1:]:
        d += f" L {x:.1f},{y:.1f}"
    for x, y in reversed(bottom_points):
        d += f" L {x:.1f},{y:.1f}"
    d += " Z"

    dwg.add(dwg.path(
        d=d,
        fill=SS_FILL['H'],
        stroke=SS_STROKE['H'],
        stroke_width=0.5
    ))


def _draw_sheet(dwg, x_start, x_end, y_center, height):
    """Draw beta sheet as an arrow polygon."""
    seg_length = x_end - x_start
    if seg_length < 1:
        return

    body_height = height * 0.5
    head_height = height
    head_length = min(8, seg_length * 0.35)
    body_end = x_end - head_length

    if body_end <= x_start:
        # Very short segment: just draw a triangle
        points = [
            (x_start, y_center - head_height / 2),
            (x_end, y_center),
            (x_start, y_center + head_height / 2),
        ]
    else:
        points = [
            (x_start,  y_center - body_height / 2),
            (body_end,  y_center - body_height / 2),
            (body_end,  y_center - head_height / 2),
            (x_end,     y_center),
            (body_end,  y_center + head_height / 2),
            (body_end,  y_center + body_height / 2),
            (x_start,   y_center + body_height / 2),
        ]

    dwg.add(dwg.polygon(
        points=points,
        fill=SS_FILL['E'],
        stroke=SS_STROKE['E'],
        stroke_width=0.5
    ))


def _draw_coil(dwg, x_start, x_end, y_center):
    """Draw coil/loop as a thin line."""
    if x_end - x_start < 1:
        return
    dwg.add(dwg.line(
        start=(x_start, y_center),
        end=(x_end, y_center),
        stroke=SS_FILL['C'],
        stroke_width=1.5
    ))


def position_labels_smartly(conserved_positions, alignment_length, line_length_pixels, min_spacing=25):
    """
    Position labels to avoid overlap by moving them horizontally and vertically.

    Args:
        conserved_positions: List of conserved position dicts
        alignment_length: Length of this specific alignment (in residues)
        line_length_pixels: Actual pixel length of the line being drawn
        min_spacing: Minimum horizontal spacing between labels

    Returns:
        List of dicts with added 'x_offset' and 'y_level' keys
    """
    if not conserved_positions:
        return []

    # Calculate scale (pixels per sequence position)
    scale = line_length_pixels / alignment_length

    # Sort by position
    positions = sorted(conserved_positions, key=lambda x: x['position'])

    # Track occupied x positions at each y level
    levels = [[]]  # List of lists, each containing occupied x ranges

    positioned = []

    for pos_data in positions:
        x_pos = pos_data['position'] * scale
        label_width = min_spacing  # Approximate width needed for label

        # Find a level where this label fits
        level = 0
        placed = False

        while not placed:
            # Ensure level exists
            if level >= len(levels):
                levels.append([])

            # Check if this position overlaps with any existing label at this level
            overlaps = False
            for occupied_start, occupied_end in levels[level]:
                if not (x_pos + label_width < occupied_start or x_pos > occupied_end):
                    overlaps = True
                    break

            if not overlaps:
                # Place at this level
                levels[level].append((x_pos, x_pos + label_width))
                positioned.append({
                    **pos_data,
                    'x_offset': 0,  # No horizontal offset needed with levels
                    'y_level': level
                })
                placed = True
            else:
                level += 1

    return positioned

def generate_svg(alignments, cross_conservation=None):
    """
    Generate SVG visualization of conserved residues.

    Args:
        alignments: List of dicts with 'name', 'conserved', and 'length' keys

    Returns:
        SVG content as string
    """
    # Layout parameters
    margin_left = 200
    margin_top = 50
    margin_bottom = 50
    margin_right = 100  # Increased to prevent right-side clipping of labels
    max_line_length = 600  # Maximum line length in pixels
    label_height = 60  # Space above line for labels

    # Secondary structure track parameters
    has_ss = any(a.get('secondary_structure') for a in alignments)
    ss_track_offset = 5       # pixels below the main line
    ss_track_height = 12      # height of SS shapes
    ss_extra_space = 22 if has_ss else 0  # extra vertical space per row when SS present
    row_height = 100 + ss_extra_space

    # Calculate max sequence length from all alignments
    max_length = max((a['length'] for a in alignments), default=400)

    # Legend needs extra rows for SS and/or cross-conservation
    has_cross = bool(cross_conservation)
    legend_extra = (25 if has_ss else 0) + (25 if has_cross else 0)

    # Calculate dimensions
    svg_height = margin_top + (len(alignments) * row_height) + margin_bottom + legend_extra
    svg_width = margin_left + max_line_length + margin_right

    # Create SVG
    dwg = svgwrite.Drawing(size=(svg_width, svg_height))

    # Add title
    dwg.add(dwg.text(
        'Protein Alignment Conservation',
        insert=(svg_width / 2, 30),
        text_anchor='middle',
        font_size='20px',
        font_weight='bold',
        fill='black'
    ))

    # Draw each alignment
    for idx, alignment in enumerate(alignments):
        y_base = margin_top + (idx * row_height)

        # Get this alignment's actual length
        alignment_length = alignment['length']

        # Skip if alignment length is zero (should not happen, but safety check)
        if alignment_length == 0:
            continue

        # Calculate this alignment's line length proportional to max
        line_length = (alignment_length / max_length) * max_line_length

        # Draw alignment name
        dwg.add(dwg.text(
            alignment['name'],
            insert=(margin_left - 10, y_base + 5),
            text_anchor='end',
            font_size='14px',
            fill='black'
        ))

        # Draw horizontal line representing the sequence
        line_y = y_base
        dwg.add(dwg.line(
            start=(margin_left, line_y),
            end=(margin_left + line_length, line_y),
            stroke='black',
            stroke_width=2
        ))

        # Position conserved residue labels
        positioned = position_labels_smartly(alignment['conserved'], alignment_length, line_length)

        # Draw conserved residues - scale based on this alignment's length
        scale = line_length / alignment_length

        for pos_data in positioned:
            x_pos = margin_left + (pos_data['position'] * scale) + pos_data['x_offset']
            y_level = pos_data['y_level']
            y_pos = line_y - 15 - (y_level * 25)  # Stack vertically (more space for number on top)

            residue = pos_data['residue']
            position = pos_data['position']
            color = get_color(residue)

            # Draw vertical tick mark
            dwg.add(dwg.line(
                start=(x_pos, line_y),
                end=(x_pos, y_pos + 5),
                stroke=color,
                stroke_width=1.5
            ))

            # Draw position number on top (small)
            dwg.add(dwg.text(
                str(position),
                insert=(x_pos, y_pos - 8),
                text_anchor='middle',
                font_size='8px',
                fill=color
            ))

            # Draw residue letter below (larger, bold)
            dwg.add(dwg.text(
                residue,
                insert=(x_pos, y_pos),
                text_anchor='middle',
                font_size='12px',
                font_weight='bold',
                fill=color
            ))

        # Draw secondary structure track if available
        ss_data = alignment.get('secondary_structure')
        if ss_data:
            y_center = line_y + ss_track_offset + ss_track_height / 2
            amplitude = ss_track_height / 2 - 2  # helix wave amplitude

            for segment in ss_data:
                seg_start = segment['start']
                seg_end = segment['end']
                ss_type = segment['ss3']

                # Map positions to pixels (center on residue positions)
                x_start = margin_left + ((seg_start - 0.5) * scale)
                x_end = margin_left + ((seg_end + 0.5) * scale)

                # Clip to line boundaries
                x_start = max(x_start, margin_left)
                x_end = min(x_end, margin_left + line_length)
                if x_end - x_start <= 0:
                    continue

                if ss_type == 'H':
                    _draw_helix(dwg, x_start, x_end, y_center, amplitude, scale)
                elif ss_type == 'E':
                    _draw_sheet(dwg, x_start, x_end, y_center, ss_track_height)
                else:
                    _draw_coil(dwg, x_start, x_end, y_center)

        # Draw scale markers (every 50 positions)
        # Shift down when SS track is present for this alignment
        marker_y_offset = (ss_track_offset + ss_track_height + 2) if ss_data else 0
        for pos in range(0, alignment_length + 1, 50):
            x_pos = margin_left + (pos * scale)
            if x_pos <= margin_left + line_length:
                # Small tick below line
                dwg.add(dwg.line(
                    start=(x_pos, line_y + marker_y_offset),
                    end=(x_pos, line_y + marker_y_offset + 5),
                    stroke='gray',
                    stroke_width=1
                ))
                # Position label
                if pos > 0:
                    dwg.add(dwg.text(
                        str(pos),
                        insert=(x_pos, line_y + marker_y_offset + 18),
                        text_anchor='middle',
                        font_size='10px',
                        fill='gray'
                    ))

    # Draw cross-conservation connecting lines between adjacent rows
    if has_cross:
        global_scale = max_line_length / max_length

        for entry in cross_conservation:
            positions = entry['positions']
            color = get_color(entry['residue'])

            for i in range(len(alignments) - 1):
                name_i = alignments[i]['name']
                name_next = alignments[i + 1]['name']

                if name_i not in positions or name_next not in positions:
                    continue

                x_i = margin_left + positions[name_i] * global_scale
                x_next = margin_left + positions[name_next] * global_scale

                y_i = margin_top + i * row_height
                y_next = margin_top + (i + 1) * row_height

                dwg.add(dwg.line(
                    start=(x_i, y_i),
                    end=(x_next, y_next),
                    stroke=color,
                    stroke_width=1,
                    stroke_opacity=0.4,
                    stroke_dasharray='3,3'
                ))

    # Add legend
    legend_x = margin_left
    legend_y = svg_height - 30 - legend_extra

    # Residue color legend
    legend_groups = [
        ('GYSTNCP', (255, 0, 255)),
        ('VILPFMWA', (70, 156, 118)),
        ('H', (255, 140, 0)),
        ('DE', (192, 0, 0)),
        ('KR', (0, 0, 255))
    ]

    offset = 0
    for residues, color in legend_groups:
        color_str = f'rgb({color[0]},{color[1]},{color[2]})'

        # Color box
        dwg.add(dwg.rect(
            insert=(legend_x + offset, legend_y - 10),
            size=(15, 15),
            fill=color_str
        ))

        # Residue labels
        dwg.add(dwg.text(
            residues,
            insert=(legend_x + offset + 20, legend_y + 2),
            font_size='12px',
            fill='black'
        ))

        offset += len(residues) * 10 + 40

    # Secondary structure legend (second row, only if any alignment has SS)
    if has_ss:
        ss_legend_y = legend_y + 25
        mini_w = 30     # width of each mini shape
        mini_h = 12     # height
        label_gap = 35  # space from shape start to label
        item_gap = 80   # total space per legend item
        offset = 0

        # Mini helix
        _draw_helix(dwg,
                     legend_x + offset,
                     legend_x + offset + mini_w,
                     ss_legend_y - 2, mini_h / 2 - 2, 10)
        dwg.add(dwg.text('Helix',
                         insert=(legend_x + offset + label_gap, ss_legend_y + 2),
                         font_size='12px', fill='black'))
        offset += item_gap

        # Mini sheet arrow
        _draw_sheet(dwg,
                    legend_x + offset,
                    legend_x + offset + mini_w,
                    ss_legend_y - 2, mini_h)
        dwg.add(dwg.text('Sheet',
                         insert=(legend_x + offset + label_gap, ss_legend_y + 2),
                         font_size='12px', fill='black'))
        offset += item_gap

        # Mini coil line
        _draw_coil(dwg,
                   legend_x + offset,
                   legend_x + offset + mini_w,
                   ss_legend_y - 2)
        dwg.add(dwg.text('Coil',
                         insert=(legend_x + offset + label_gap, ss_legend_y + 2),
                         font_size='12px', fill='black'))

    # Cross-conservation legend
    if has_cross:
        cross_legend_y = legend_y + (25 if has_ss else 0) + 25
        dwg.add(dwg.line(
            start=(legend_x, cross_legend_y - 2),
            end=(legend_x + 30, cross_legend_y - 2),
            stroke='gray',
            stroke_width=1,
            stroke_opacity=0.4,
            stroke_dasharray='3,3'
        ))
        dwg.add(dwg.text(
            'Conserved across all groups',
            insert=(legend_x + 35, cross_legend_y + 2),
            font_size='12px',
            fill='black'
        ))

    return dwg.tostring()
