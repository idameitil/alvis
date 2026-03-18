import os
from flask import Flask, render_template, send_from_directory
import session_store


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

    @app.route('/')
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
    app.run(debug=True, port=5000)
