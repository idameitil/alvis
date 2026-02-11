import os
import zipfile
import tempfile
import shutil
from flask import Flask, render_template, request, jsonify
from conservation import analyze_alignment
from svg_generator import generate_svg
from structure import run_dssp, get_ss_segments, map_ss_to_sequence
from config import Config
from models.database import db
from services import project_service

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Initialize database
db.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/debug/db-test')
def db_test():
    """Test database connection"""
    try:
        from models.models import Project
        count = Project.query.count()
        return jsonify({
            'status': 'ok',
            'connection': 'working',
            'project_count': count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/projects', methods=['GET'])
def get_projects():
    """Get list of recent projects"""
    try:
        limit = request.args.get('limit', 10, type=int)
        projects = project_service.get_recent_projects(limit=limit)
        return jsonify({'projects': projects})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/projects/<int:project_id>', methods=['GET'])
def get_project(project_id):
    """Get a specific project with all data"""
    try:
        project_data = project_service.get_project_by_id(project_id)
        if not project_data:
            return jsonify({'error': 'Project not found'}), 404
        return jsonify(project_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/projects/create', methods=['POST'])
def create_project():
    """Create a new project"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')

        if not name:
            return jsonify({'error': 'Project name is required'}), 400

        project = project_service.create_project(name, description)
        return jsonify(project.to_dict()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete a project"""
    try:
        success = project_service.delete_project(project_id)
        if not success:
            return jsonify({'error': 'Project not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    """Handle ZIP upload and extract FASTA file names"""
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

        if not fasta_files:
            shutil.rmtree(temp_dir)
            return jsonify({'error': 'No FASTA files found in ZIP'}), 400

        return jsonify({
            'temp_dir': temp_dir,
            'fasta_files': sorted(fasta_files)
        })

    except zipfile.BadZipFile:
        shutil.rmtree(temp_dir)
        return jsonify({'error': 'Invalid ZIP file'}), 400

@app.route('/upload-pdb', methods=['POST'])
def upload_pdb():
    """Handle PDB file upload for a specific alignment"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    temp_dir = request.form.get('temp_dir')
    fasta_file = request.form.get('fasta_file')

    if not temp_dir or not os.path.exists(temp_dir):
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
    temp_dir = data.get('temp_dir')
    thresholds = data.get('thresholds', {})
    pdb_files = data.get('pdb_files', {})  # {fasta_file: {pdb_filename, chain_id}}
    project_id = data.get('project_id')  # Optional: save to project

    if not temp_dir or not os.path.exists(temp_dir):
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
                    from Bio import SeqIO
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
                    shutil.rmtree(temp_dir)
                    return jsonify({'error': f'Error processing {fasta_file}: {str(e)}'}), 400

        # Generate SVG
        svg_content = generate_svg(alignments)

        # Save to database if project_id provided
        if project_id:
            try:
                project_service.save_project_data(project_id, alignments, svg_content)
                print(f"Successfully saved project {project_id} to database")
                # Only cleanup if saved to database
                shutil.rmtree(temp_dir)
            except Exception as e:
                # Return error if save fails
                print(f"Error: Failed to save project data: {e}")
                return jsonify({'error': f'Failed to save project: {str(e)}'}), 500

        # Return SVG content as JSON
        return jsonify({
            'svg': svg_content,
            'success': True,
            'project_id': project_id,
            'temp_dir': temp_dir if not project_id else None
        })

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Cleanup temp directory if user cancels"""
    data = request.json
    temp_dir = data.get('temp_dir')

    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
