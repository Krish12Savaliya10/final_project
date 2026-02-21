"""General helper utilities."""

import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import current_app
from werkzeug.utils import secure_filename

from core.india_geo import is_point_in_india

from core.db import execute_db, query_db


DOC_FIELD_LABELS = {
    "identity_proof_path": "Identity KYC",
    "business_proof_path": "Main Business Document",
    "property_proof_path": "Property Proof",
    "vehicle_proof_path": "Vehicle Proof",
    "driver_verification_path": "Driver Verification",
    "bank_proof_path": "Bank Proof",
    "address_proof_path": "Address Proof",
    "operational_photo_path": "Operational Photos",
}

ROLE_BASE_DOCUMENTS = {
    "organizer": [
        "business_proof_path",
    ],
    "hotel_provider": [
        "business_proof_path",
    ],
    "admin": [
        "identity_proof_path",
        "business_proof_path",
        "bank_proof_path",
        "address_proof_path",
    ],
}

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def save_upload(file_obj, folder=None):
    if not file_obj or not file_obj.filename:
        return None
    filename = secure_filename(file_obj.filename)
    if not filename:
        return None

    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    final_name = f"{stamp}_{filename}"

    destination = folder or current_app.config["UPLOAD_FOLDER"]
    os.makedirs(destination, exist_ok=True)
    file_path = os.path.join(destination, final_name)
    file_obj.save(file_path)
    return final_name


def normalize_role(raw_role):
    role_map = {
        "traveler": "customer",
        "customer": "customer",
        "organizer": "organizer",
        "admin": "admin",
        # Legacy provider role is merged into hotel_provider.
        "provider": "hotel_provider",
        "hotel_provider": "hotel_provider",
        "hotel": "hotel_provider",
        "hotel and resort providers": "hotel_provider",
        "service_provider": "hotel_provider",
    }
    return role_map.get((raw_role or "").strip().lower(), "customer")


def normalize_provider_category(raw_category):
    text = (raw_category or "").strip().lower()
    if text in {"hotel", "hotels", "resort", "hotel/resort", "hotel & resort"}:
        return "Hotel"
    if text in {"guide", "guides", "tour_guide"}:
        return "Guides"
    if text in {"food", "catering"}:
        return "Food"
    return ""


def get_onboarding_document_requirements(role, provider_category=None):
    normalized_role = normalize_role(role)
    if normalized_role == "hotel_provider":
        provider_category = "Hotel"

    required_fields = list(ROLE_BASE_DOCUMENTS.get(normalized_role, []))

    seen = set()
    ordered = []
    for field in required_fields:
        if field in seen:
            continue
        seen.add(field)
        ordered.append({"field": field, "label": DOC_FIELD_LABELS.get(field, field)})
    return ordered


def is_allowed_document_filename(filename):
    text = (filename or "").strip().lower()
    if "." not in text:
        return False
    ext = text.rsplit(".", 1)[1]
    return ext in ALLOWED_DOCUMENT_EXTENSIONS


def is_allowed_image_filename(filename):
    text = (filename or "").strip().lower()
    if "." not in text:
        return False
    ext = text.rsplit(".", 1)[1]
    return ext in ALLOWED_IMAGE_EXTENSIONS


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_decimal(value, default=None):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return default


def parse_date(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_valid_email(email):
    text = (email or "").strip().lower()
    if not text:
        return False
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", text))


def is_valid_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    return len(digits) == 10


def normalize_phone(phone):
    return re.sub(r"\D", "", phone or "")


def is_valid_pincode(pincode):
    return bool(re.match(r"^\d{6}$", (pincode or "").strip()))


def is_non_negative_amount(value):
    val = to_decimal(value, None)
    return val is not None and val >= Decimal("0")




def is_within_india_bounds(lat, lng):
    """Return True if the given latitude/longitude point lies within India.

    This is a thin wrapper around :func:`core.india_geo.is_point_in_india` that
    accepts string inputs and gracefully handles bad data. Other parts of the
    application import ``is_within_india_bounds`` from ``core.helpers`` so
    keeping the helper here avoids a circular import in route modules.
    """

    try:
        return is_point_in_india(lat, lng)
    except Exception:
        # In case of unexpected value types just treat as out of bounds.
        return False


def update_room_inventory_for_provider(room_type_id, new_available, provider_user_id, note=None):
    room_row = query_db(
        """
        SELECT rt.id, rt.available_rooms, rt.total_rooms
        FROM hotel_room_types rt
        JOIN services s ON s.id=rt.service_id
        WHERE rt.id=%s AND s.provider_id=%s
        """,
        (room_type_id, provider_user_id),
        one=True,
    )
    if not room_row:
        return False, "Room type not found."

    old_available = int(room_row["available_rooms"] or 0)
    total_rooms = int(room_row["total_rooms"] or 0)
    new_available = max(0, min(new_available, total_rooms))

    execute_db(
        "UPDATE hotel_room_types SET available_rooms=%s WHERE id=%s",
        (new_available, room_type_id),
    )
    execute_db(
        """
        INSERT INTO hotel_room_inventory_logs(room_type_id, changed_by, old_available, new_available, note)
        VALUES(%s,%s,%s,%s,%s)
        """,
        (room_type_id, provider_user_id, old_available, new_available, note or None),
    )
    return True, "Room availability updated."



# -----------------------------------------------------------------------------
# geographical helpers
# -----------------------------------------------------------------------------

# common misspellings and variants of state names that appear in our data
_STATE_CORRECTIONS = {
    # user-supplied typos
    "gujrat": "Gujarat",
    "tamilnadu": "Tamil Nadu",
    "tamil nadu": "Tamil Nadu",
    "utarpradesh": "Uttar Pradesh",
    "uttar pradesh": "Uttar Pradesh",
    "bangal": "West Bengal",
    "bengal": "West Bengal",
    # alternative forms
    "jammu and kashmir": "Jammu & Kashmir",
    "jamun and kashmir": "Jammu & Kashmir",
    "jamu and kashmir": "Jammu & Kashmir",
    "jammu & kashmir": "Jammu & Kashmir",
    "andman nikobar": "Andaman and Nicobar Islands",
    "adman nikobar": "Andaman and Nicobar Islands",
    "andaman nicobar": "Andaman and Nicobar Islands",
    "andaman and nicobar": "Andaman and Nicobar Islands",
}

def normalize_state_name(raw_state: str) -> str:
    """Return a cleaned, canonical state/union territory name.

    The project ingest scripts and the web UI sometimes receive creative
    spellings or concatenated forms ("Utarpradesh", "Tamilnadu", etc.).
    This helper will translate a handful of common variants to the
    correct official name so that geocoding and database lookups behave
    consistently.  If the passed string is empty or unrecognised it is
    returned stripped but otherwise unchanged.
    """
    if not raw_state:
        return ""
    text = raw_state.strip().lower()
    fixed = _STATE_CORRECTIONS.get(text)
    if fixed:
        return fixed
    # fall back to a capitalised form of the original if nothing matches
    return raw_state.strip()
