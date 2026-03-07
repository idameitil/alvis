from flask import Blueprint, request, jsonify

import session_store
from models.session import Session, FASTA_EXTENSIONS

session_bp = Blueprint('session', __name__)


@session_bp.route('/session', methods=['POST'])
def create_session():
    """Create a new empty session."""
    session_store.cleanup_expired()
    session = Session.create_new(session_id='')
    session_store.create(session)
    return jsonify(session.to_dict())


@session_bp.route('/session/<session_id>/fasta', methods=['POST'])
def add_fasta(session_id):
    """Add FASTA file(s) to a session.

    Accepts multipart (file) or JSON {name, content}.
    Optional form field or JSON key `role`: "group" (default) or "cross".
    """
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    # JSON body: paste-in FASTA content
    if request.is_json:
        data = request.json
        name = data.get('name')
        content = data.get('content')
        role = data.get('role', 'group')
        if not name or not content:
            return jsonify({'error': 'JSON body must have "name" and "content"'}), 400
        if not name.lower().endswith(FASTA_EXTENSIONS):
            return jsonify({'error': f'Filename must end with {FASTA_EXTENSIONS}'}), 400
        try:
            if role == 'cross':
                session.add_cross_fasta_content(name, content)
            else:
                session.add_fasta_content(name, content)
        except Exception as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(session.to_dict())

    # Multipart file upload
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    role = request.form.get('role', 'group')
    filename = file.filename
    is_zip = filename.lower().endswith('.zip')
    is_fasta = filename.lower().endswith(FASTA_EXTENSIONS)

    if not is_zip and not is_fasta:
        return jsonify({
            'error': 'File must be a ZIP archive or a FASTA file (.fasta, .fa, .faa, .fas)'
        }), 400

    try:
        if is_zip:
            session.add_fasta_zip(file)
        elif role == 'cross':
            session.add_cross_fasta_file(filename, file)
        else:
            session.add_fasta_file(filename, file)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify(session.to_dict())


@session_bp.route('/session/<session_id>/fasta/<path:name>', methods=['DELETE'])
def remove_fasta(session_id, name):
    """Remove a FASTA file from the session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    try:
        session.remove_fasta(name)
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify(session.to_dict())


@session_bp.route('/session/<session_id>/fasta/<path:name>/sequences', methods=['GET'])
def list_sequences(session_id, name):
    """List sequence IDs in a FASTA file (for representative selection)."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    try:
        sequences = session.list_sequences(name)
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify({'sequences': sequences})


@session_bp.route('/session/<session_id>/pdb', methods=['POST'])
def add_pdb(session_id):
    """Upload a PDB file for the session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename.endswith('.pdb'):
        return jsonify({'error': 'File must be a PDB file (.pdb)'}), 400

    try:
        chains = session.add_pdb(file.filename, file)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({
        'pdb_filename': file.filename,
        'chains': [c.to_dict() for c in chains],
    })


@session_bp.route('/session/<session_id>/pdb/<path:name>', methods=['DELETE'])
def remove_pdb(session_id, name):
    """Remove a PDB file from the session."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    session.remove_pdb(name)
    return jsonify(session.to_dict())


@session_bp.route('/session/<session_id>', methods=['PATCH'])
def update_session(session_id):
    """Update session configuration (thresholds, chain assignments, etc.)."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    data = request.json or {}
    session.update_config(
        thresholds=data.get('thresholds'),
        chain_assignments=data.get('chain_assignments'),
        cross_threshold=data.get('cross_threshold'),
        representative_indices=data.get('representative_indices'),
    )
    return jsonify(session.to_dict())


@session_bp.route('/session/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete a session and its temp directory."""
    session_store.remove(session_id)
    return jsonify({'status': 'ok'})
