from routes.session import session_bp
from routes.analysis import analysis_bp
from routes.pdb import pdb_bp


def register_blueprints(app):
    app.register_blueprint(session_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(pdb_bp)
