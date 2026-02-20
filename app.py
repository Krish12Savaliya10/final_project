import os

from flask import Flask

from core.config import (
    DOC_UPLOAD_FOLDER,
    GOOGLE_MAPS_API_KEY,
    SECRET_KEY,
    SPOT_UPLOAD_FOLDER,
    UPLOAD_FOLDER,
)
from core.db import ensure_runtime_schema
from routes import register_all_routes


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["DOC_UPLOAD_FOLDER"] = DOC_UPLOAD_FOLDER
    app.config["SPOT_UPLOAD_FOLDER"] = SPOT_UPLOAD_FOLDER

    try:
        ensure_runtime_schema()
    except Exception as exc:
        # Keep app boot resilient even if DB is temporarily unavailable.
        print(f"[schema-warning] Could not ensure runtime schema: {exc}")

    @app.context_processor
    def inject_google_maps_key():
        return dict(google_maps_api_key=GOOGLE_MAPS_API_KEY)
    register_all_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["DOC_UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["SPOT_UPLOAD_FOLDER"], exist_ok=True)
    app.run(debug=True, port=5001)
