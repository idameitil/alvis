from flask import Blueprint, jsonify

import session_store
from models.analysis import build_result

analysis_bp = Blueprint('analysis', __name__)

# Exceptions caused by bad user input (malformed files, invalid config, etc.)
_CLIENT_ERRORS = (ValueError, FileNotFoundError, IndexError, KeyError)


@analysis_bp.route('/session/<session_id>/result', methods=['GET'])
def get_result(session_id):
    """Run conservation analysis and return SVG + metadata."""
    session = session_store.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 404

    if not session.groups:
        return jsonify({'error': 'No FASTA files in session'}), 400

    try:
        result = build_result(session)
        return jsonify(result.to_dict())
    except _CLIENT_ERRORS as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
