import os
import zipfile
import tempfile
from flask import Flask, render_template, request, jsonify, send_from_directory
from Bio import SeqIO
from conservation import analyze_alignment, analyze_cross_conservation
from svg_generator import generate_svg
from structure import run_dssp, get_ss_segments, map_ss_to_sequence
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

@app.route('/upload', methods=['POST'])
def upload():
    """Handle ZIP upload and extract FASTA file names"""
    session_store.cleanup_expired()

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith('.zip'):
        return jsonify({'error': 'File must be a ZIP archive'}), 400

    # Create temp directory for this session
    temp_dir = tempfile.mkdtemp()
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

                if filename.endswith(('.fasta', '.fa', '.faa', '.fas')):
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

    # Parse PDB to get available chains
    try:
        from Bio.PDB import PDBParser
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("protein", pdb_path)
        model = structure[0]
        chains = []
        for chain in model.get_chains():
            num_residues = sum(1 for r in chain.get_residues()
                              if r.id[0] == ' ')  # standard residues only
            chains.append({'id': chain.id, 'num_residues': num_residues})
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
        for fasta_file, threshold in thresholds.items():
            file_path = os.path.join(temp_dir, fasta_file)
            if os.path.exists(file_path):
                try:
                    conserved_positions, seq_length = analyze_alignment(file_path, threshold)

                    # Count sequences in file
                    with open(file_path, 'r') as f:
                        num_sequences = sum(1 for _ in SeqIO.parse(f, 'fasta'))

                    alignment_data = {
                        'name': os.path.basename(fasta_file),
                        'conserved': conserved_positions,
                        'length': seq_length,
                        'threshold': threshold,
                        'num_sequences': num_sequences
                    }

                    # Run DSSP if PDB provided for this alignment
                    pdb_info = pdb_files.get(fasta_file)
                    if pdb_info:
                        pdb_path = os.path.join(temp_dir, 'pdb', pdb_info['pdb_filename'])
                        chain_id = pdb_info.get('chain_id')
                        if os.path.exists(pdb_path):
                            try:
                                residues = run_dssp(pdb_path, chain_id=chain_id)
                                segments = get_ss_segments(residues)

                                # Map PDB positions to FASTA representative positions
                                with open(file_path, 'r') as f:
                                    rep_seq = str(list(SeqIO.parse(f, 'fasta'))[0].seq).replace('-', '')
                                offset = map_ss_to_sequence(residues, rep_seq)
                                for seg in segments:
                                    seg['start'] += offset
                                    seg['end'] += offset

                                alignment_data['secondary_structure'] = segments
                                alignment_data['ss_length'] = len(residues)
                            except Exception as e:
                                print(f"DSSP warning for {fasta_file}: {e}")
                                # Non-fatal: continue without secondary structure

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
                            with open(file_path, 'r') as f:
                                first_seq = next(SeqIO.parse(f, 'fasta'), None)
                            if first_seq:
                                representative_ids.append(
                                    (os.path.basename(fasta_file), first_seq.id)
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

        return jsonify({
            'svg': svg_content,
            'success': True
        })

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
