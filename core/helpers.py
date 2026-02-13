"""General helper utilities."""

import os
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from core.db import execute_db, query_db


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
        "provider": "provider",
        "service_provider": "provider",
    }
    return role_map.get((raw_role or "").strip().lower(), "customer")


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
