import re
import urllib.request
import urllib.error

from flask import Blueprint, request, jsonify

import session_store

pdb_bp = Blueprint('pdb', __name__)


@pdb_bp.route('/fetch-pdb', methods=['POST'])
def fetch_pdb():
    """Fetch a PDB file from RCSB by its 4-character ID."""
    data = request.json
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    token = data.get('session_id')
    pdb_id = data.get('pdb_id', '').strip()

    session = session_store.get(token) if token else None
    if not session:
        return jsonify({'error': 'Invalid session'}), 400

    if not re.fullmatch(r'[A-Za-z0-9]{4}', pdb_id):
        return jsonify({'error': 'PDB ID must be exactly 4 alphanumeric characters'}), 400

    pdb_id_upper = pdb_id.upper()
    pdb_filename = f'{pdb_id_upper}.pdb'

    url = f'https://files.rcsb.org/download/{pdb_id_upper}.pdb'
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            pdb_data = response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({'error': f'PDB ID "{pdb_id_upper}" not found on RCSB'}), 404
        return jsonify({'error': f'RCSB returned HTTP {e.code}'}), 502
    except urllib.error.URLError as e:
        return jsonify({'error': f'Network error fetching PDB: {e.reason}'}), 502
    except Exception as e:
        return jsonify({'error': f'Failed to download PDB: {str(e)}'}), 500

    try:
        chains = session.add_pdb_from_bytes(pdb_filename, pdb_data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({
        'pdb_filename': pdb_filename,
        'chains': [c.to_dict() for c in chains],
    })
