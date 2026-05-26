import os
from flask import Flask, render_template, send_from_directory
import session_store


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

    @app.route('/')
    def landing():
        return render_template('landing.html')

    @app.route('/app')
    def index():
        return render_template('index.html')

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/example-data')
    def example_data():
        return send_from_directory(
            os.path.join(app.root_path, 'example_data'),
            'globins_example.zip',
            as_attachment=True
        )

    from routes import register_blueprints
    register_blueprints(app)

    session_store.start_cleanup_thread()

    return app


app = create_app()

if __name__ == '__main__':
    # Start debugpy listener inside the reloader child only — the parent
    # supervisor process doesn't serve requests, and binding the port twice
    # would fail on reload.
    if os.environ.get('DEBUGPY') == '1' and os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        import debugpy
        debugpy.listen(('0.0.0.0', 5678))
        print('debugpy listening on 0.0.0.0:5678', flush=True)

    app.run(debug=True, host='0.0.0.0', port=5001)
