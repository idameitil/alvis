import os
import re
import zipfile
import tempfile
import urllib.request
import urllib.error
from flask import Flask, render_template, request, jsonify, send_from_directory
from Bio import SeqIO, SeqUtils
from Bio.PDB import PDBParser
from conservation import analyze_alignment, analyze_cross_conservation
from svg_generator import generate_svg
from structure import run_dssp, get_ss_segments, align_pdb_to_fasta, remap_ss_segments
import session_store

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/example-data')
def example_data():
    """Serve the example globins ZIP file"""
    return send_from_directory(
        os.path.join(app.root_path, 'example_data'),
        'globins_example.zip',
        as_attachment=True
    )

FASTA_EXTENSIONS = ('.fasta', '.fa', '.faa', '.fas')

@app.route('/upload', methods=['POST'])
def upload():
    """Handle ZIP or single FASTA upload"""
    session_store.cleanup_expired()

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    is_zip = file.filename.lower().endswith('.zip')
    is_fasta = file.filename.lower().endswith(FASTA_EXTENSIONS)

    if not is_zip and not is_fasta:
        return jsonify({'error': 'File must be a ZIP archive or a FASTA file (.fasta, .fa, .faa, .fas)'}), 400

    # Create temp directory for this session
    temp_dir = tempfile.mkdtemp()

    if is_fasta:
        # Single FASTA file — save directly
        fasta_filename = file.filename
        fasta_path = os.path.join(temp_dir, fasta_filename)
        file.save(fasta_path)

        token = session_store.create(temp_dir)
        return jsonify({
            'session_token': token,
            'fasta_files': [fasta_filename]
        })

    # ZIP file — existing logic
    zip_path = os.path.join(temp_dir, 'upload.zip')
    file.save(zip_path)

    # Extract and find FASTA files
    fasta_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Find all FASTA files (common extensions)
        for root, dirs, files in os.walk(temp_dir):
            # Skip macOS metadata directories
            dirs[:] = [d for d in dirs if d not in ['__MACOSX', '.DS_Store']]

            for filename in files:
                # Skip system/hidden files
                if filename.startswith('.') or filename.startswith('._'):
                    continue

                if filename.endswith(FASTA_EXTENSIONS):
                    # Store relative path from temp_dir
                    rel_path = os.path.relpath(os.path.join(root, filename), temp_dir)
                    fasta_files.append(rel_path)

        # Detect all.fasta (cross-conservation reference) and separate it
        all_fasta = None
        group_files = []
        for f in fasta_files:
            basename_no_ext = os.path.splitext(os.path.basename(f))[0]
            if basename_no_ext.lower() == 'all':
                all_fasta = f
            else:
                group_files.append(f)
        fasta_files = group_files

        if not fasta_files:
            import shutil
            shutil.rmtree(temp_dir)
            return jsonify({'error': 'No FASTA files found in ZIP'}), 400

        token = session_store.create(temp_dir)

        response = {
            'session_token': token,
            'fasta_files': sorted(fasta_files)
        }
        if all_fasta:
            response['all_fasta'] = all_fasta

        return jsonify(response)

    except zipfile.BadZipFile:
        import shutil
        shutil.rmtree(temp_dir)
        return jsonify({'error': 'Invalid ZIP file'}), 400

def _parse_pdb_chains(pdb_path):
    """Parse a PDB file and return list of chain dicts with id, num_residues, and sequence."""
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("protein", pdb_path)
    model = structure[0]
    chains = []
    for chain in model.get_chains():
        residues = [r for r in chain.get_residues() if r.id[0] == ' ']
        seq = ''.join(SeqUtils.seq1(r.get_resname()) for r in residues)
        chains.append({
            'id': chain.id,
            'num_residues': len(residues),
            'sequence': seq
        })
    return chains


def _find_representative_index(fasta_path, pdb_sequence):
    """Find which FASTA sequence best matches the PDB chain sequence.
    Uses local pairwise alignment scoring to handle offset homologs.
    Returns the 0-based index, or 0 if no good match."""
    from Bio.Align import PairwiseAligner

    sequences = list(SeqIO.parse(fasta_path, 'fasta'))
    pdb_upper = pdb_sequence.upper()
    best_index = 0
    best_score = -1

    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5

    for i, seq in enumerate(sequences):
        ungapped = str(seq.seq).replace('-', '').upper()
        # Fast path: substring match (identical or truncated)
        if pdb_upper in ungapped or ungapped in pdb_upper:
            return i
        alignments = aligner.align(ungapped, pdb_upper)
        if alignments:
            score = alignments[0].score
            if score > best_score:
                best_score = score
                best_index = i

    return best_index

@app.route('/upload-pdb', methods=['POST'])
def upload_pdb():
    """Handle PDB file upload for a specific alignment"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    token = request.form.get('session_token')

    temp_dir = session_store.get_temp_dir(token) if token else None
    if not temp_dir:
        return jsonify({'error': 'Invalid session'}), 400

    if not file.filename.endswith('.pdb'):
        return jsonify({'error': 'File must be a PDB file (.pdb)'}), 400

    # Save PDB to a pdb/ subdirectory in temp_dir
    pdb_dir = os.path.join(temp_dir, 'pdb')
    os.makedirs(pdb_dir, exist_ok=True)

    pdb_filename = file.filename
    pdb_path = os.path.join(pdb_dir, pdb_filename)
    file.save(pdb_path)

    try:
        chains = _parse_pdb_chains(pdb_path)
    except Exception as e:
        os.remove(pdb_path)
        return jsonify({'error': f'Failed to parse PDB file: {str(e)}'}), 400

    if not chains:
        os.remove(pdb_path)
        return jsonify({'error': 'No protein chains found in PDB file'}), 400

    return jsonify({
        'pdb_filename': pdb_filename,
        'chains': chains
    })

@app.route('/fetch-pdb', methods=['POST'])
def fetch_pdb():
    """Fetch a PDB file from RCSB by its 4-character ID."""
    data = request.json
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    token = data.get('session_token')
    pdb_id = data.get('pdb_id', '').strip()

    temp_dir = session_store.get_temp_dir(token) if token else None
    if not temp_dir:
        return jsonify({'error': 'Invalid session'}), 400

    # Strict validation: exactly 4 alphanumeric characters
    if not re.fullmatch(r'[A-Za-z0-9]{4}', pdb_id):
        return jsonify({'error': 'PDB ID must be exactly 4 alphanumeric characters'}), 400

    pdb_id_upper = pdb_id.upper()
    pdb_filename = f'{pdb_id_upper}.pdb'

    pdb_dir = os.path.join(temp_dir, 'pdb')
    os.makedirs(pdb_dir, exist_ok=True)
    pdb_path = os.path.join(pdb_dir, pdb_filename)

    # Download from RCSB
    url = f'https://files.rcsb.org/download/{pdb_id_upper}.pdb'
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            pdb_data = response.read()
        with open(pdb_path, 'wb') as f:
            f.write(pdb_data)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({'error': f'PDB ID "{pdb_id_upper}" not found on RCSB'}), 404
        return jsonify({'error': f'RCSB returned HTTP {e.code}'}), 502
    except urllib.error.URLError as e:
        return jsonify({'error': f'Network error fetching PDB: {e.reason}'}), 502
    except Exception as e:
        return jsonify({'error': f'Failed to download PDB: {str(e)}'}), 500

    try:
        chains = _parse_pdb_chains(pdb_path)
    except Exception as e:
        os.remove(pdb_path)
        return jsonify({'error': f'Failed to parse downloaded PDB: {str(e)}'}), 400

    if not chains:
        os.remove(pdb_path)
        return jsonify({'error': 'No protein chains found in downloaded PDB'}), 400

    return jsonify({
        'pdb_filename': pdb_filename,
        'chains': chains
    })

@app.route('/generate', methods=['POST'])
def generate():
    """Generate SVG from alignment files with specified thresholds"""
    data = request.json
    token = data.get('session_token')
    thresholds = data.get('thresholds', {})
    pdb_files = data.get('pdb_files', {})  # {fasta_file: {pdb_filename, chain_id}}
    all_fasta = data.get('all_fasta')
    cross_threshold = data.get('cross_threshold', 95)

    temp_dir = session_store.get_temp_dir(token) if token else None
    if not temp_dir:
        return jsonify({'error': 'Invalid session'}), 400

    try:
        # Analyze each alignment
        alignments = []
        alignment_info = []
        rep_indices = {}  # fasta_file -> representative index
        for fasta_file, threshold in thresholds.items():
            file_path = os.path.join(temp_dir, fasta_file)
            if os.path.exists(file_path):
                try:
                    # Determine representative index: match PDB chain if provided
                    rep_index = 0
                    pdb_info = pdb_files.get(fasta_file)
                    if pdb_info and pdb_info.get('chain_sequence'):
                        rep_index = _find_representative_index(
                            file_path, pdb_info['chain_sequence']
                        )
                    rep_indices[fasta_file] = rep_index

                    conserved_positions, seq_length = analyze_alignment(
                        file_path, threshold, representative_index=rep_index
                    )

                    # Read sequences once for num_sequences and representative
                    with open(file_path, 'r') as f:
                        seqs = list(SeqIO.parse(f, 'fasta'))
                    num_sequences = len(seqs)
                    rep_seq_record = seqs[rep_index] if rep_index < len(seqs) else seqs[0]

                    alignment_data = {
                        'name': os.path.basename(fasta_file),
                        'conserved': conserved_positions,
                        'length': seq_length,
                        'threshold': threshold,
                        'num_sequences': num_sequences
                    }

                    # Build per-alignment info for the response
                    info = {
                        'name': os.path.basename(fasta_file),
                        'num_sequences': num_sequences,
                    }

                    # Run DSSP if PDB provided for this alignment
                    if pdb_info:
                        info['representative'] = rep_seq_record.id
                        pdb_path = os.path.join(temp_dir, 'pdb', pdb_info['pdb_filename'])
                        chain_id = pdb_info.get('chain_id')
                        if os.path.exists(pdb_path):
                            try:
                                residues = run_dssp(pdb_path, chain_id=chain_id)
                                segments = get_ss_segments(residues)

                                # Map PDB positions to FASTA representative positions
                                rep_seq = str(rep_seq_record.seq).replace('-', '')
                                pdb_to_fasta, _ = align_pdb_to_fasta(residues, rep_seq)
                                remapped = remap_ss_segments(segments, pdb_to_fasta, seq_length)
                                alignment_data['secondary_structure'] = remapped
                                alignment_data['ss_length'] = len(residues)

                                mapped_count = len(pdb_to_fasta)
                                coverage = mapped_count / seq_length * 100 if seq_length else 0
                                info['pdb_coverage'] = f'{coverage:.1f}%'
                                info['pdb_mapped'] = f'{mapped_count} / {seq_length} positions'

                                # Warn if DSSP resolved very few residues
                                if coverage < 10:
                                    alignment_data['ss_warning'] = (
                                        f"DSSP resolved only {len(residues)} residues "
                                        f"({mapped_count} mapped to alignment). "
                                        f"The PDB may lack backbone coordinates for most residues."
                                    )
                            except Exception as e:
                                print(f"DSSP warning for {fasta_file}: {e}")
                                # Non-fatal: continue without secondary structure

                    alignment_info.append(info)
                    alignments.append(alignment_data)
                except Exception as e:
                    return jsonify({'error': f'Error processing {fasta_file}: {str(e)}'}), 400

        # Cross-conservation analysis if all.fasta was provided
        cross_positions = None
        if all_fasta:
            all_fasta_path = os.path.join(temp_dir, all_fasta)
            if os.path.exists(all_fasta_path):
                try:
                    representative_ids = []
                    for fasta_file in thresholds.keys():
                        file_path = os.path.join(temp_dir, fasta_file)
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
                            all_fasta_path, representative_ids, cross_threshold
                        )
                except Exception as e:
                    print(f"Cross-conservation warning: {e}")
                    # Non-fatal: continue without cross-conservation

        # Generate SVG
        svg_content = generate_svg(alignments, cross_conservation=cross_positions)

        # Collect warnings
        warnings = [a['ss_warning'] for a in alignments if a.get('ss_warning')]

        response = {
            'svg': svg_content,
            'success': True,
            'alignment_info': alignment_info
        }
        if warnings:
            response['warnings'] = warnings

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Cleanup session and its temp directory"""
    data = request.json
    token = data.get('session_token')

    if token:
        session_store.remove(token)

    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
