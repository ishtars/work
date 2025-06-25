from flask import Flask
from caozuo.comment_viewer import bp as comments_bp
from caozuo.add_search_triples import bp as triples_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = 'test_secret_key'
    app.register_blueprint(comments_bp, url_prefix='/comments')
    app.register_blueprint(triples_bp, url_prefix='/triples')
    return app


if __name__ == '__main__':
    create_app().run(debug=True)
