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
        cross_conservation: Optional list of cross-conserved position dicts

    Returns:
        SVG content as string
    """
    # Layout parameters
    margin_left = 200
    margin_top = 50
    margin_bottom = 50
    margin_right = 100
    max_line_length = 600
    row_gap = 15  # padding between rows

    # Secondary structure track parameters
    has_ss = any(a.get('secondary_structure') for a in alignments)
    ss_track_offset = 5
    ss_track_height = 12

    has_cross = bool(cross_conservation)

    # Calculate max sequence length from all alignments
    max_length = max((a['length'] for a in alignments), default=400)

    # --- Pre-compute label positions and per-row metrics ---
    row_info = []
    for alignment in alignments:
        alignment_length = alignment['length']
        if alignment_length == 0:
            row_info.append(None)
            continue
        line_length = (alignment_length / max_length) * max_line_length
        positioned = position_labels_smartly(alignment['conserved'], alignment_length, line_length)
        max_level = max((p['y_level'] for p in positioned), default=0) if positioned else 0
        scale = line_length / alignment_length

        # Space above the line: base offset (15) + stacked levels (25 each) + position number (8)
        label_above = 23 + max_level * 25
        label_above = max(label_above, 30)  # minimum headroom

        # Space below the line: SS track + scale markers
        ss_data = alignment.get('secondary_structure')
        marker_y_offset = (ss_track_offset + ss_track_height + 2) if ss_data else 0
        below = marker_y_offset + 18  # 18px for scale marker text

        row_info.append({
            'positioned': positioned,
            'line_length': line_length,
            'scale': scale,
            'alignment_length': alignment_length,
            'label_above': label_above,
            'below': below,
        })

    # --- Calculate y position of each row's horizontal line ---
    y_bases = []
    for idx in range(len(alignments)):
        ri = row_info[idx]
        if ri is None:
            y_bases.append(0)
            continue
        if idx == 0:
            y_bases.append(margin_top + ri['label_above'])
        else:
            prev_below = row_info[idx - 1]['below'] if row_info[idx - 1] else 30
            y_bases.append(y_bases[idx - 1] + prev_below + row_gap + ri['label_above'])

    # --- Legend sizing ---
    legend_rows = (1 if has_ss else 0) + (1 if has_cross else 0)
    legend_height = legend_rows * 25

    # --- SVG dimensions ---
    last_idx = len(alignments) - 1
    last_below = row_info[last_idx]['below'] if row_info[last_idx] else 30
    content_bottom = y_bases[last_idx] + last_below
    svg_height = content_bottom + (legend_height + 15 if legend_height else 0) + margin_bottom
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

    # --- Draw each alignment ---
    for idx, alignment in enumerate(alignments):
        ri = row_info[idx]
        if ri is None:
            continue

        line_y = y_bases[idx]
        line_length = ri['line_length']
        scale = ri['scale']
        alignment_length = ri['alignment_length']

        # Alignment name
        dwg.add(dwg.text(
            alignment['name'],
            insert=(margin_left - 10, line_y + 5),
            text_anchor='end',
            font_size='14px',
            fill='black'
        ))

        # Horizontal line representing the sequence
        dwg.add(dwg.line(
            start=(margin_left, line_y),
            end=(margin_left + line_length, line_y),
            stroke='black',
            stroke_width=2
        ))

        # Conserved residue labels (pre-computed)
        for pos_data in ri['positioned']:
            x_pos = margin_left + (pos_data['position'] * scale) + pos_data['x_offset']
            y_level = pos_data['y_level']
            y_pos = line_y - 15 - (y_level * 25)

            residue = pos_data['residue']
            position = pos_data['position']
            color = get_color(residue)

            # Vertical tick mark
            dwg.add(dwg.line(
                start=(x_pos, line_y),
                end=(x_pos, y_pos + 5),
                stroke=color,
                stroke_width=1.5
            ))

            # Position number on top
            dwg.add(dwg.text(
                str(position),
                insert=(x_pos, y_pos - 8),
                text_anchor='middle',
                font_size='8px',
                fill=color
            ))

            # Residue letter
            dwg.add(dwg.text(
                residue,
                insert=(x_pos, y_pos),
                text_anchor='middle',
                font_size='12px',
                font_weight='bold',
                fill=color
            ))

        # Secondary structure track
        ss_data = alignment.get('secondary_structure')
        if ss_data:
            y_center = line_y + ss_track_offset + ss_track_height / 2
            amplitude = ss_track_height / 2 - 2

            for segment in ss_data:
                seg_start = segment['start']
                seg_end = segment['end']
                ss_type = segment['ss3']

                x_start = margin_left + ((seg_start - 0.5) * scale)
                x_end = margin_left + ((seg_end + 0.5) * scale)

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

        # Scale markers (every 50 positions)
        marker_y_offset = (ss_track_offset + ss_track_height + 2) if ss_data else 0
        for pos in range(0, alignment_length + 1, 50):
            x_pos = margin_left + (pos * scale)
            if x_pos <= margin_left + line_length:
                dwg.add(dwg.line(
                    start=(x_pos, line_y + marker_y_offset),
                    end=(x_pos, line_y + marker_y_offset + 5),
                    stroke='gray',
                    stroke_width=1
                ))
                if pos > 0:
                    dwg.add(dwg.text(
                        str(pos),
                        insert=(x_pos, line_y + marker_y_offset + 18),
                        text_anchor='middle',
                        font_size='10px',
                        fill='gray'
                    ))

    # --- Cross-conservation connecting lines ---
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

                dwg.add(dwg.line(
                    start=(x_i, y_bases[i]),
                    end=(x_next, y_bases[i + 1]),
                    stroke=color,
                    stroke_width=1,
                    stroke_opacity=0.4,
                    stroke_dasharray='3,3'
                ))

    # --- Legend (SS + cross-conservation only) ---
    if legend_rows > 0:
        current_legend_y = content_bottom + 25

        if has_ss:
            mini_w = 30
            mini_h = 12
            label_gap = 35
            item_gap = 80
            offset = 0

            _draw_helix(dwg,
                         margin_left + offset,
                         margin_left + offset + mini_w,
                         current_legend_y - 2, mini_h / 2 - 2, 10)
            dwg.add(dwg.text('Helix',
                             insert=(margin_left + offset + label_gap, current_legend_y + 2),
                             font_size='12px', fill='black'))
            offset += item_gap

            _draw_sheet(dwg,
                        margin_left + offset,
                        margin_left + offset + mini_w,
                        current_legend_y - 2, mini_h)
            dwg.add(dwg.text('Sheet',
                             insert=(margin_left + offset + label_gap, current_legend_y + 2),
                             font_size='12px', fill='black'))
            offset += item_gap

            _draw_coil(dwg,
                       margin_left + offset,
                       margin_left + offset + mini_w,
                       current_legend_y - 2)
            dwg.add(dwg.text('Coil',
                             insert=(margin_left + offset + label_gap, current_legend_y + 2),
                             font_size='12px', fill='black'))

            current_legend_y += 25

        if has_cross:
            dwg.add(dwg.line(
                start=(margin_left, current_legend_y - 2),
                end=(margin_left + 30, current_legend_y - 2),
                stroke='gray',
                stroke_width=1,
                stroke_opacity=0.4,
                stroke_dasharray='3,3'
            ))
            dwg.add(dwg.text(
                'Conserved across all groups',
                insert=(margin_left + 35, current_legend_y + 2),
                font_size='12px',
                fill='black'
            ))

    return dwg.tostring()
