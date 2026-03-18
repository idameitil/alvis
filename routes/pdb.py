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

    MAX_PDB_SIZE = 10 * 1024 * 1024  # 10 MB

    url = f'https://files.rcsb.org/download/{pdb_id_upper}.pdb'
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            pdb_data = response.read(MAX_PDB_SIZE + 1)
            if len(pdb_data) > MAX_PDB_SIZE:
                return jsonify({'error': 'PDB file exceeds 10 MB size limit'}), 400
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

    result = {
        'pdb_filename': pdb_filename,
        'chains': [c.to_dict() for c in chains],
    }

    fasta_filename = data.get('fasta_filename')
    if fasta_filename and fasta_filename in session.groups and chains:
        try:
            match = session.suggest_representative(
                fasta_filename, chains[0].sequence
            )
            result['suggested_representative'] = match['index']
            if match['warning']:
                result['pdb_match_warning'] = match['warning']
            if match['identity'] is not None and match['identity'] > 0:
                result['pdb_identity'] = f"{match['identity'] * 100:.1f}%"
                if match['index'] is not None and match['identity'] < 1.0:
                    result['pdb_match_warning'] = (
                        f"Matched with {match['identity'] * 100:.1f}% identity "
                        f"over {match['aligned_length']} positions (not a perfect match)."
                    )
        except Exception:
            pass

    return jsonify(result)
