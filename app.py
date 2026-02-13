import os

from flask import Flask

from core.bootstrap import ensure_hotel_tables, ensure_support_tables, ensure_tour_tables, ensure_transport_tables
from core.config import DOC_UPLOAD_FOLDER, SECRET_KEY, UPLOAD_FOLDER
from routes import register_all_routes


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["DOC_UPLOAD_FOLDER"] = DOC_UPLOAD_FOLDER

    register_all_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["DOC_UPLOAD_FOLDER"], exist_ok=True)
    ensure_support_tables()
    ensure_hotel_tables()
    ensure_transport_tables()
    ensure_tour_tables()
    app.run(debug=True, port=5001)
