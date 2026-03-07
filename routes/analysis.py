from flask import Blueprint, jsonify

import session_store
from models.analysis import build_result

analysis_bp = Blueprint('analysis', __name__)


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
    except Exception as e:
        return jsonify({'error': str(e)}), 500
