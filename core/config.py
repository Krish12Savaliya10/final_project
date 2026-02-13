"""Application configuration."""

SECRET_KEY = "tourgen-secret-key"
UPLOAD_FOLDER = "static/uploads"
DOC_UPLOAD_FOLDER = "static/uploads/documents"

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "tourgen_db",
    "port": 8889,
}
