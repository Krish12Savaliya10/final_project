"""Application configuration."""

import os


SECRET_KEY = os.getenv("SECRET_KEY", "tourgen-secret-key")
UPLOAD_FOLDER = "static/uploads"
DOC_UPLOAD_FOLDER = "static/uploads/documents"
SPOT_UPLOAD_FOLDER = "static/uploads/spots"

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "root"),
    "database": os.getenv("MYSQL_DATABASE", "tourgen_db"),
    "port": int(os.getenv("MYSQL_PORT", "8889")),
}

MYSQL_UNIX_SOCKET = (os.getenv("MYSQL_UNIX_SOCKET") or "").strip()
if MYSQL_UNIX_SOCKET:
    MYSQL_CONFIG.pop("host", None)
    MYSQL_CONFIG.pop("port", None)
    MYSQL_CONFIG["unix_socket"] = MYSQL_UNIX_SOCKET
