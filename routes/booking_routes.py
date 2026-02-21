from decimal import Decimal
from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import json
import math
import os
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from flask import abort, flash, redirect, render_template, request, session, url_for

from core.auth import login_required
from core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from core.db import execute_db, get_db, query_db
from core.helpers import is_within_india_bounds, parse_date, save_upload, to_int


def _haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dphi / 2) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


ID_PROOF_TYPES = [
    "Aadhaar Card",
    "Passport",
    "Driving License",
    "Voter ID",
    "PAN Card",
    "Government ID",
]
ALLOWED_ID_PROOF_EXTENSIONS = {".pdf", ".jpg", ".jpeg"}


def _is_allowed_id_proof_filename(filename):
    ext = os.path.splitext((filename or "").strip())[1].lower()
    return ext in ALLOWED_ID_PROOF_EXTENSIONS


def register_routes(app):
    @app.route("/booking/<int:tour_id>", methods=["GET", "POST"])
    def booking(tour_id):
        tour = query_db(
            """
            SELECT
                t.*,
                (
                    SELECT COALESCE(SUM(b2.pax_count), 0)
                    FROM bookings b2
                    WHERE b2.tour_id=t.id AND b2.status IN ('pending', 'paid')
                ) + (
                    SELECT COALESCE(SUM(eb.pax_count), 0)
                    FROM organizer_external_bookings eb
                    WHERE eb.tour_id=t.id
                ) AS booked_pax,
                ps.state_name AS pickup_state_name,
                pc.city_name AS pickup_city_name,
                ds.state_name AS drop_state_name,
                dc.city_name AS drop_city_name
            FROM tours t
            LEFT JOIN states ps ON ps.id=t.pickup_state_id
            LEFT JOIN cities pc ON pc.id=t.pickup_city_id
            LEFT JOIN states ds ON ds.id=t.drop_state_id
            LEFT JOIN cities dc ON dc.id=t.drop_city_id
            WHERE t.id=%s
            """,
            (tour_id,),
            one=True,
        )
        if not tour:
            abort(404)

        itinerary = query_db(
            """
            SELECT ti.day_number, ms.spot_name, ms.image_url, ms.photo_source, ms.latitude, ms.longitude
            FROM tour_itinerary ti
            JOIN master_spots ms ON ms.id=ti.spot_id
            WHERE ti.tour_id=%s
            ORDER BY ti.day_number ASC, ti.order_sequence ASC, ti.id ASC
            """,
            (tour_id,),
        )
        try:
            city_schedules = query_db(
                """
                SELECT
                    tcs.city_id,
                    c.city_name,
                    s.state_name,
                    tcs.arrival_datetime,
                    tcs.departure_datetime,
                    tcs.note,
                    tcs.sequence_no
                FROM tour_city_schedules tcs
                JOIN cities c ON c.id=tcs.city_id
                LEFT JOIN states s ON s.id=c.state_id
                WHERE tcs.tour_id=%s
                ORDER BY tcs.sequence_no ASC, tcs.id ASC
                """,
                (tour_id,),
            )
        except Exception:
            city_schedules = []
        total_distance_km = 0.0
        prev_lat = None
        prev_lng = None
        for item in itinerary:
            lat = item.get("latitude")
            lng = item.get("longitude")
            if not is_within_india_bounds(lat, lng):
                lat = None
                lng = None
                item["latitude"] = None
                item["longitude"] = None
            leg_km = None
            if lat is not None and lng is not None and prev_lat is not None and prev_lng is not None:
                try:
                    leg_km = _haversine_km(prev_lat, prev_lng, lat, lng)
                    total_distance_km += leg_km
                except (TypeError, ValueError):
                    leg_km = None
            item["leg_distance_km"] = round(leg_km, 1) if leg_km is not None else None
            if lat is not None and lng is not None:
                prev_lat = lat
                prev_lng = lng
        total_distance_km = round(total_distance_km, 1)
        current_user_id = session.get("user_id")
        existing = None
        if current_user_id:
            existing = query_db(
                """
                SELECT * FROM bookings
                WHERE user_id=%s AND tour_id=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (current_user_id, tour_id),
                one=True,
            )
        linked_hotel_rows = query_db(
            """
            SELECT
                svc.id AS service_id,
                svc.description AS service_description,
                hp.*,
                c.city_name,
                s.state_name
            FROM tour_service_links tsl
            JOIN hotel_profiles hp ON hp.service_id=tsl.service_id
            JOIN services svc ON svc.id=tsl.service_id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE tsl.tour_id=%s
              AND tsl.service_kind='Hotel'
            ORDER BY hp.star_rating DESC, hp.hotel_name
            """,
            (tour_id,),
        )
        try:
            hotel_stay_rows = query_db(
                """
                SELECT
                    ths.service_id,
                    ths.check_in_date,
                    ths.check_out_date,
                    ths.nights,
                    ths.stay_notes
                FROM tour_hotel_stays ths
                WHERE ths.tour_id=%s
                ORDER BY ths.check_in_date ASC, ths.id ASC
                """,
                (tour_id,),
            )
        except Exception:
            hotel_stay_rows = []

        def to_date(value):
            if value is None:
                return None
            if hasattr(value, "year") and hasattr(value, "month"):
                return value
            text = str(value).strip()
            if not text:
                return None
            return parse_date(text[:10])

        tour_start = to_date(tour.get("start_date"))
        tour_end = to_date(tour.get("end_date"))
        fallback_check_out = (tour_end + timedelta(days=1)) if tour_end else None
        if tour_start and not fallback_check_out:
            fallback_check_out = tour_start + timedelta(days=1)

        stay_range_by_hotel = {}
        stays_by_hotel = {}
        for row in hotel_stay_rows:
            sid = to_int(row.get("service_id"), 0)
            if sid <= 0:
                continue
            check_in = to_date(row.get("check_in_date"))
            check_out = to_date(row.get("check_out_date"))
            if not check_in or not check_out or check_in >= check_out:
                continue
            stays_by_hotel.setdefault(sid, []).append(
                {
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "nights": to_int(row.get("nights"), (check_out - check_in).days),
                    "stay_notes": row.get("stay_notes"),
                }
            )
            if sid not in stay_range_by_hotel:
                stay_range_by_hotel[sid] = [check_in, check_out]
            else:
                stay_range_by_hotel[sid][0] = min(stay_range_by_hotel[sid][0], check_in)
                stay_range_by_hotel[sid][1] = max(stay_range_by_hotel[sid][1], check_out)

        linked_hotel_ids = [to_int(h.get("service_id"), 0) for h in linked_hotel_rows if to_int(h.get("service_id"), 0) > 0]
        hotel_image_rows = []
        hotel_price_rows = []
        if linked_hotel_ids:
            placeholders = ", ".join(["%s"] * len(linked_hotel_ids))
            hotel_image_rows = query_db(
                f"""
                SELECT service_id, image_url, image_title, is_cover, sort_order, id
                FROM hotel_images
                WHERE service_id IN ({placeholders})
                ORDER BY service_id ASC, is_cover DESC, sort_order ASC, id ASC
                """,
                tuple(linked_hotel_ids),
            )
            hotel_price_rows = query_db(
                f"""
                SELECT service_id, COALESCE(MIN(base_price), 0) AS from_price
                FROM hotel_room_types
                WHERE service_id IN ({placeholders})
                GROUP BY service_id
                """,
                tuple(linked_hotel_ids),
            )

        hotel_images_by_service = {}
        for img in hotel_image_rows:
            sid = to_int(img.get("service_id"), 0)
            if sid <= 0:
                continue
            hotel_images_by_service.setdefault(sid, []).append(img)

        hotel_price_by_service = {}
        for row in hotel_price_rows:
            sid = to_int(row.get("service_id"), 0)
            if sid <= 0:
                continue
            hotel_price_by_service[sid] = float(row.get("from_price") or 0)

        linked_hotels = []
        hotel_map = {}
        for hotel in linked_hotel_rows:
            sid = to_int(hotel.get("service_id"), 0)
            if sid <= 0:
                continue
            if not is_within_india_bounds(hotel.get("latitude"), hotel.get("longitude")):
                hotel["latitude"] = None
                hotel["longitude"] = None
            if sid not in stays_by_hotel and tour_start and fallback_check_out and fallback_check_out > tour_start:
                default_nights = (fallback_check_out - tour_start).days
                stays_by_hotel[sid] = [
                    {
                        "check_in_date": tour_start,
                        "check_out_date": fallback_check_out,
                        "nights": default_nights,
                        "stay_notes": "Stay schedule follows tour dates.",
                    }
                ]
                stay_range_by_hotel[sid] = [tour_start, fallback_check_out]
            hotel_images = hotel_images_by_service.get(sid, [])
            hotel["images"] = hotel_images
            hotel["cover_image"] = hotel_images[0]["image_url"] if hotel_images else None
            hotel["from_price"] = hotel_price_by_service.get(sid, 0.0)
            hotel["stay_plans"] = stays_by_hotel.get(sid, [])
            hotel["room_types"] = []
            hotel["total_available_rooms"] = 0
            hotel_map[sid] = hotel
            linked_hotels.append(hotel)

        hotel_room_rows = []
        if linked_hotel_ids:
            placeholders = ", ".join(["%s"] * len(linked_hotel_ids))
            hotel_room_rows = query_db(
                f"""
                SELECT
                    rt.id AS room_type_id,
                    rt.service_id,
                    rt.room_type_name,
                    rt.max_guests,
                    rt.base_price,
                    rt.total_rooms,
                    rt.available_rooms
                FROM hotel_room_types rt
                WHERE rt.service_id IN ({placeholders})
                ORDER BY rt.base_price ASC, rt.id ASC
                """,
                tuple(linked_hotel_ids),
            )

        for room in hotel_room_rows:
            sid = to_int(room.get("service_id"), 0)
            room_type_id = to_int(room.get("room_type_id"), 0)
            if sid <= 0 or room_type_id <= 0 or sid not in hotel_map:
                continue
            stay_range = stay_range_by_hotel.get(sid)
            stay_check_in = stay_range[0] if stay_range else None
            stay_check_out = stay_range[1] if stay_range else None

            overlap_rooms = 0
            if stay_check_in and stay_check_out:
                overlap_row = query_db(
                    """
                    SELECT COALESCE(SUM(rooms_booked), 0) AS overlapping_rooms
                    FROM hotel_bookings
                    WHERE room_type_id=%s
                      AND status='confirmed'
                      AND check_in_date < %s
                      AND check_out_date > %s
                    """,
                    (room_type_id, stay_check_out, stay_check_in),
                    one=True,
                ) or {}
                overlap_rooms = max(0, to_int(overlap_row.get("overlapping_rooms"), 0))
            base_available_rooms = max(0, to_int(room.get("available_rooms"), 0))
            current_available = max(0, base_available_rooms - overlap_rooms)
            room["currently_available"] = current_available
            room["stay_check_in"] = stay_check_in
            room["stay_check_out"] = stay_check_out
            hotel_map[sid]["room_types"].append(room)
            hotel_map[sid]["total_available_rooms"] += current_available

        room_options_by_hotel = {}
        room_options_flat = []
        room_option_lookup = {}
        hotel_included_price = {}
        for hotel in linked_hotels:
            sid = to_int(hotel.get("service_id"), 0)
            if sid <= 0:
                continue
            base_prices = [Decimal(str(r.get("base_price") or 0)) for r in hotel.get("room_types", [])]
            hotel_included_price[sid] = min(base_prices) if base_prices else Decimal("0.00")

        for hotel in linked_hotels:
            sid = to_int(hotel.get("service_id"), 0)
            room_options_by_hotel[str(sid)] = []
            for room in hotel.get("room_types", []):
                stay_nights = 1
                stay_check_in = room.get("stay_check_in")
                stay_check_out = room.get("stay_check_out")
                if stay_check_in and stay_check_out:
                    try:
                        stay_nights = max(1, int((stay_check_out - stay_check_in).days))
                    except Exception:
                        stay_nights = 1

                base_price_dec = Decimal(str(room.get("base_price") or 0))
                included_base_dec = hotel_included_price.get(sid, Decimal("0.00"))
                extra_per_night_dec = max(base_price_dec - included_base_dec, Decimal("0.00"))
                extra_per_room_total_dec = extra_per_night_dec * Decimal(stay_nights)

                room_option = {
                    "hotel_service_id": sid,
                    "hotel_name": hotel.get("hotel_name"),
                    "room_type_id": to_int(room.get("room_type_id"), 0),
                    "room_type_name": room.get("room_type_name"),
                    "max_guests": to_int(room.get("max_guests"), 0),
                    "base_price": float(base_price_dec),
                    "included_base_price": float(included_base_dec),
                    "extra_per_night": float(extra_per_night_dec),
                    "stay_nights": stay_nights,
                    "extra_per_room_total": float(extra_per_room_total_dec),
                    "available": to_int(room.get("currently_available"), 0),
                    "stay_check_in": stay_check_in,
                    "stay_check_out": stay_check_out,
                }
                room_options_by_hotel[str(sid)].append(room_option)
                room_options_flat.append(room_option)
                rid = to_int(room_option.get("room_type_id"), 0)
                if rid > 0:
                    room_option_lookup[rid] = room_option
        linked_guides = query_db(
            """
            SELECT
                s.id AS service_id,
                s.service_name,
                s.description,
                s.price,
                c.city_name,
                st.state_name
            FROM tour_service_links tsl
            JOIN services s ON s.id=tsl.service_id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
            WHERE tsl.tour_id=%s
              AND tsl.service_kind='Guides'
            ORDER BY s.service_name
            """,
            (tour_id,),
        )
        existing_room_request = None
        if existing and to_int(existing.get("room_type_id"), 0) > 0:
            existing_room_request = {
                "hotel_service_id": to_int(existing.get("room_hotel_service_id"), 0) or None,
                "room_type_id": to_int(existing.get("room_type_id"), 0),
                "rooms_requested": max(1, to_int(existing.get("room_rooms_requested"), 1)),
                "note": (existing.get("room_note") or "").strip() or None,
            }
        existing_travelers = []
        if existing:
            try:
                existing_travelers = query_db(
                    """
                    SELECT full_name, age, id_proof_type, id_proof_number, contact_number
                    FROM booking_travelers
                    WHERE booking_id=%s
                    ORDER BY id ASC
                    """,
                    (existing["id"],),
                )
            except Exception:
                existing_travelers = []
        booking_id_defaults = {
            "id_proof_type": (existing.get("id_proof_type") or "").strip() if existing else "",
            "id_proof_number": (existing.get("id_proof_number") or "").strip() if existing else "",
            "id_proof_file_path": (existing.get("id_proof_file_path") or "").strip() if existing else "",
        }

        if request.method == "POST":
            if not current_user_id:
                flash("Please login to join this tour.")
                return redirect(url_for("login", next=url_for("booking", tour_id=tour_id)))

            if existing and existing["status"] == "paid":
                flash("This tour is already booked and paid.")
                return redirect(url_for("booking", tour_id=tour_id))

            if (tour.get("tour_status") or "open").lower() != "open":
                flash("This tour is not open for booking.")
                return redirect(url_for("booking", tour_id=tour_id))

            pax_count = max(1, to_int(request.form.get("pax_count"), 1))
            max_group_size = to_int(tour.get("max_group_size"), 0)
            current_booked = to_int(tour.get("booked_pax"), 0)
            existing_pax = to_int(existing.get("pax_count"), 1) if existing else 0
            projected_booked = current_booked - existing_pax + pax_count
            if max_group_size and projected_booked > max_group_size:
                flash("Tour is full or seats are not available for selected group size.")
                return redirect(url_for("booking", tour_id=tour_id))

            traveler_names = request.form.getlist("traveler_full_name[]")
            traveler_ages = request.form.getlist("traveler_age[]")
            traveler_id_types = request.form.getlist("traveler_id_proof_type[]")
            traveler_id_numbers = request.form.getlist("traveler_id_proof_number[]")
            traveler_contacts = request.form.getlist("traveler_contact[]")
            traveler_rows = []
            for idx in range(pax_count):
                full_name = (traveler_names[idx] if idx < len(traveler_names) else "").strip()
                age = to_int(traveler_ages[idx] if idx < len(traveler_ages) else None, -1)
                id_type = (traveler_id_types[idx] if idx < len(traveler_id_types) else "").strip()
                id_number = (traveler_id_numbers[idx] if idx < len(traveler_id_numbers) else "").strip()
                contact = (traveler_contacts[idx] if idx < len(traveler_contacts) else "").strip()

                if not full_name or len(full_name) > 120:
                    flash(f"Traveler #{idx + 1} name is required (max 120 chars).")
                    return redirect(url_for("booking", tour_id=tour_id))
                if age < 0 or age > 120:
                    flash(f"Traveler #{idx + 1} age must be between 0 and 120.")
                    return redirect(url_for("booking", tour_id=tour_id))
                if id_type and len(id_type) > 50:
                    flash("ID proof type is too long.")
                    return redirect(url_for("booking", tour_id=tour_id))
                if id_type and id_type not in ID_PROOF_TYPES:
                    flash(f"Traveler #{idx + 1} ID proof type is invalid.")
                    return redirect(url_for("booking", tour_id=tour_id))
                if id_number and len(id_number) > 120:
                    flash("ID proof number is too long.")
                    return redirect(url_for("booking", tour_id=tour_id))
                if contact and len(contact) > 20:
                    flash("Traveler contact number is too long.")
                    return redirect(url_for("booking", tour_id=tour_id))
                traveler_rows.append(
                    {
                        "full_name": full_name,
                        "age": age,
                        "id_proof_type": id_type or None,
                        "id_proof_number": id_number or None,
                        "contact_number": contact or None,
                        "is_child": 1 if age < 12 else 0,
                    }
                )

            booking_id_proof_type = (request.form.get("booking_id_proof_type") or "").strip()
            booking_id_proof_number = (request.form.get("booking_id_proof_number") or "").strip()
            booking_id_proof_file = request.files.get("booking_id_proof_file")
            existing_id_file_path = (booking_id_defaults.get("id_proof_file_path") or "").strip()
            booking_id_file_path = existing_id_file_path

            if not booking_id_proof_type or len(booking_id_proof_type) > 50:
                flash("Select a valid ID proof type for tour booking.")
                return redirect(url_for("booking", tour_id=tour_id))
            if booking_id_proof_type not in ID_PROOF_TYPES:
                flash("Selected ID proof type is invalid.")
                return redirect(url_for("booking", tour_id=tour_id))
            if not booking_id_proof_number or len(booking_id_proof_number) > 120:
                flash("Valid ID proof number is required (max 120 chars).")
                return redirect(url_for("booking", tour_id=tour_id))
            if booking_id_proof_file and booking_id_proof_file.filename:
                if not _is_allowed_id_proof_filename(booking_id_proof_file.filename):
                    flash("Tour ID proof file must be PDF or JPG.")
                    return redirect(url_for("booking", tour_id=tour_id))
                saved_doc_name = save_upload(booking_id_proof_file, app.config["DOC_UPLOAD_FOLDER"])
                if not saved_doc_name:
                    flash("Unable to upload ID proof file. Try again.")
                    return redirect(url_for("booking", tour_id=tour_id))
                booking_id_file_path = saved_doc_name
            if not booking_id_file_path:
                flash("Upload ID proof document (PDF/JPG) for tour booking.")
                return redirect(url_for("booking", tour_id=tour_id))

            individual_guide = 1 if request.form.get("need_individual_guide") else 0
            selected_guide_id = request.form.get("guide_service_id")
            guide_note = request.form.get("guide_note", "").strip()
            selected_room_type_id = to_int(request.form.get("room_type_id"), 0)
            rooms_requested = 1
            room_note = request.form.get("room_note", "").strip()
            if len(guide_note) > 255:
                flash("Guide request note is too long.")
                return redirect(url_for("booking", tour_id=tour_id))
            if len(room_note) > 255:
                flash("Room request note is too long.")
                return redirect(url_for("booking", tour_id=tour_id))
            room_selection_required = bool(linked_hotels and room_options_flat)
            need_room_allocation = 1 if room_selection_required else 0
            if room_selection_required and selected_room_type_id <= 0:
                flash("Please select a room type from fixed tour hotels.")
                return redirect(url_for("booking", tour_id=tour_id))

            guide_service_id = None
            try:
                if selected_guide_id:
                    candidate = int(selected_guide_id)
                    if any(int(g["service_id"]) == candidate for g in linked_guides):
                        guide_service_id = candidate
            except (TypeError, ValueError):
                guide_service_id = None

            hotel_service_id = None
            room_type_id = None
            rooms_requested_to_store = 1
            room_note_to_store = None
            if need_room_allocation:
                selected_room_option = room_option_lookup.get(selected_room_type_id)
                if not selected_room_option:
                    flash("Selected room type is invalid for this fixed tour.")
                    return redirect(url_for("booking", tour_id=tour_id))
                selected_hotel_service_id = to_int(selected_room_option.get("hotel_service_id"), 0)
                hotel_choice = hotel_map.get(selected_hotel_service_id)
                if not hotel_choice:
                    flash("Selected hotel is not available for this fixed tour.")
                    return redirect(url_for("booking", tour_id=tour_id))
                if to_int(selected_room_option.get("available"), 0) < rooms_requested:
                    flash("Selected room is not available for this tour stay.")
                    return redirect(url_for("booking", tour_id=tour_id))

                stay_check_in = selected_room_option.get("stay_check_in")
                stay_check_out = selected_room_option.get("stay_check_out")
                if not stay_check_in or not stay_check_out:
                    flash("Room stay dates are not configured for this hotel.")
                    return redirect(url_for("booking", tour_id=tour_id))

                db = get_db()
                cur = db.cursor(dictionary=True)
                cur.execute(
                    """
                    SELECT available_rooms
                    FROM hotel_room_types
                    WHERE id=%s AND service_id=%s
                    FOR UPDATE
                    """,
                    (selected_room_type_id, selected_hotel_service_id),
                )
                locked_room = cur.fetchone()
                if not locked_room:
                    db.rollback()
                    cur.close()
                    db.close()
                    flash("Selected room type is invalid.")
                    return redirect(url_for("booking", tour_id=tour_id))

                cur.execute(
                    """
                    SELECT COALESCE(SUM(rooms_booked), 0) AS overlapping_rooms
                    FROM hotel_bookings
                    WHERE room_type_id=%s
                      AND status='confirmed'
                      AND check_in_date < %s
                      AND check_out_date > %s
                    """,
                    (selected_room_type_id, stay_check_out, stay_check_in),
                )
                overlap_row = cur.fetchone() or {}
                overlap_rooms = max(0, to_int(overlap_row.get("overlapping_rooms"), 0))
                base_available = max(0, to_int(locked_room.get("available_rooms"), 0))
                current_available = max(0, base_available - overlap_rooms)
                if current_available < rooms_requested:
                    db.rollback()
                    cur.close()
                    db.close()
                    flash("Selected room is not available now. Please choose a different room type.")
                    return redirect(url_for("booking", tour_id=tour_id))
                db.commit()
                cur.close()
                db.close()
                hotel_service_id = selected_hotel_service_id
                room_type_id = selected_room_type_id
                rooms_requested_to_store = rooms_requested
                room_note_to_store = room_note or None

            booking_id = None
            if existing and existing["status"] == "pending":
                booking_id = existing["id"]
                execute_db(
                    """
                    UPDATE bookings
                    SET
                        pax_count=%s,
                        id_proof_type=%s,
                        id_proof_number=%s,
                        id_proof_file_path=%s,
                        guide_service_id=%s,
                        guide_individual_requested=%s,
                        guide_note=%s,
                        room_hotel_service_id=%s,
                        room_type_id=%s,
                        room_rooms_requested=%s,
                        room_note=%s
                    WHERE id=%s AND user_id=%s
                    """,
                    (
                        pax_count,
                        booking_id_proof_type,
                        booking_id_proof_number,
                        booking_id_file_path,
                        guide_service_id,
                        individual_guide,
                        guide_note or None,
                        hotel_service_id,
                        room_type_id,
                        rooms_requested_to_store,
                        room_note_to_store,
                        booking_id,
                        current_user_id,
                    ),
                )
            else:
                booking_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                booking_id = execute_db(
                    """
                    INSERT INTO bookings(
                        user_id,tour_id,pax_count,date,status,id_proof_type,id_proof_number,id_proof_file_path,
                        guide_service_id,guide_individual_requested,guide_note,
                        room_hotel_service_id,room_type_id,room_rooms_requested,room_note
                    )
                    VALUES(%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        current_user_id,
                        tour_id,
                        pax_count,
                        booking_date,
                        booking_id_proof_type,
                        booking_id_proof_number,
                        booking_id_file_path,
                        guide_service_id,
                        individual_guide,
                        guide_note or None,
                        hotel_service_id,
                        room_type_id,
                        rooms_requested_to_store,
                        room_note_to_store,
                    ),
                )

            try:
                execute_db("DELETE FROM booking_travelers WHERE booking_id=%s", (booking_id,))
                for traveler in traveler_rows:
                    execute_db(
                        """
                        INSERT INTO booking_travelers(
                            booking_id, full_name, age, id_proof_type, id_proof_number, contact_number, is_child
                        )
                        VALUES(%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            booking_id,
                            traveler["full_name"],
                            traveler["age"],
                            traveler["id_proof_type"],
                            traveler["id_proof_number"],
                            traveler["contact_number"],
                            traveler["is_child"],
                        ),
                    )
            except Exception:
                flash("Unable to store traveler details right now.")
                return redirect(url_for("booking", tour_id=tour_id))
            if max_group_size:
                next_status = "full" if projected_booked >= max_group_size else "open"
                execute_db("UPDATE tours SET tour_status=%s WHERE id=%s", (next_status, tour_id))
            return redirect(url_for("payment", booking_id=booking_id))

        max_group_size = to_int(tour.get("max_group_size"), 0)
        booked_pax = to_int(tour.get("booked_pax"), 0)
        remaining_slots = max(0, max_group_size - booked_pax) if max_group_size else None
        tour_is_full = (max_group_size and booked_pax >= max_group_size) or (tour.get("tour_status") == "full")
        min_group_size = max(1, to_int(tour.get("min_group_size"), 6) or 6)

        return render_template(
            "booking.html",
            tour=tour,
            itinerary=itinerary,
            city_schedules=city_schedules,
            linked_hotels=linked_hotels,
            linked_guides=linked_guides,
            room_options_by_hotel=room_options_by_hotel,
            room_options_flat=room_options_flat,
            existing_room_request=existing_room_request,
            readonly=bool(existing and existing["status"] == "paid"),
            booking_id=existing["id"] if existing and existing["status"] == "paid" else None,
            remaining_slots=remaining_slots,
            tour_is_full=tour_is_full,
            min_group_size=min_group_size,
            projected_booked=booked_pax,
            total_distance_km=total_distance_km,
            existing_travelers=existing_travelers,
            id_proof_types=ID_PROOF_TYPES,
            booking_id_defaults=booking_id_defaults,
        )

    @app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
    @login_required
    def payment(booking_id):
        def create_razorpay_order(amount_rupees, receipt):
            if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
                return None, "Razorpay keys not configured."
            payload = {
                "amount": int(amount_rupees * 100),  # paise
                "currency": "INR",
                "receipt": receipt[:40],
                "payment_capture": 1,
            }
            auth_raw = f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode("utf-8")
            auth_header = "Basic " + base64.b64encode(auth_raw).decode("ascii")
            req = urlrequest.Request(
                "https://api.razorpay.com/v1/orders",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": auth_header,
                },
                method="POST",
            )
            try:
                with urlrequest.urlopen(req, timeout=12) as resp:
                    body = resp.read().decode("utf-8")
                order_obj = json.loads(body)
                return order_obj, None
            except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
                return None, "Unable to create Razorpay order."

        def verify_razorpay_signature(order_id, payment_id, signature):
            if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
                return False
            if not (order_id and payment_id and signature):
                return False
            message = f"{order_id}|{payment_id}".encode("utf-8")
            expected = hmac.new(
                RAZORPAY_KEY_SECRET.encode("utf-8"),
                message,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)

        booking = query_db(
            """
            SELECT b.*, t.title, t.price, t.start_date, t.departure_datetime, t.return_datetime, t.child_price_percent
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            WHERE b.id=%s AND b.user_id=%s
            """,
            (booking_id, session["user_id"]),
            one=True,
        )
        if not booking:
            abort(404)

        if booking["status"] == "paid":
            return redirect(url_for("invoice", booking_id=booking_id))

        unit_price = Decimal(str(booking["price"] or 0))
        pax_count = max(1, to_int(booking.get("pax_count"), 1))
        child_price_percent = Decimal(str(booking.get("child_price_percent") or 100))
        child_multiplier = max(Decimal("0"), min(Decimal("1"), child_price_percent / Decimal("100")))
        traveler_rows = query_db(
            """
            SELECT age, is_child
            FROM booking_travelers
            WHERE booking_id=%s
            """,
            (booking_id,),
        )
        if traveler_rows:
            child_count = sum(1 for tr in traveler_rows if to_int(tr.get("is_child"), 0) or to_int(tr.get("age"), 0) < 12)
            child_count = max(0, min(child_count, len(traveler_rows)))
            adult_count = max(0, len(traveler_rows) - child_count)
        else:
            child_count = 0
            adult_count = pax_count

        adult_total = unit_price * Decimal(adult_count)
        child_total = unit_price * child_multiplier * Decimal(child_count)
        base_price = (adult_total + child_total).quantize(Decimal("0.01"))

        room_upgrade_details = {}
        room_upgrade_charge = Decimal("0.00")
        room_req = query_db(
            """
            SELECT
                b.room_hotel_service_id AS hotel_service_id,
                b.room_type_id,
                b.room_rooms_requested AS rooms_requested,
                rt.room_type_name,
                rt.base_price AS selected_room_base_price
            FROM bookings b
            JOIN hotel_room_types rt ON rt.id=b.room_type_id AND rt.service_id=b.room_hotel_service_id
            WHERE b.id=%s
            LIMIT 1
            """,
            (booking_id,),
            one=True,
        )
        if room_req:
            hotel_service_id = to_int(room_req.get("hotel_service_id"), 0)
            rooms_requested = max(1, to_int(room_req.get("rooms_requested"), 1))
            selected_base_price = Decimal(str(room_req.get("selected_room_base_price") or 0))
            included_row = query_db(
                """
                SELECT COALESCE(MIN(base_price), 0) AS included_room_base_price
                FROM hotel_room_types
                WHERE service_id=%s
                """,
                (hotel_service_id,),
                one=True,
            ) or {}
            included_base_price = Decimal(str(included_row.get("included_room_base_price") or 0))
            nights_row = query_db(
                """
                SELECT COALESCE(SUM(nights), 0) AS stay_nights
                FROM tour_hotel_stays
                WHERE tour_id=%s AND service_id=%s
                """,
                (booking.get("tour_id"), hotel_service_id),
                one=True,
            ) or {}
            stay_nights = max(1, to_int(nights_row.get("stay_nights"), 0))
            extra_per_night = max(selected_base_price - included_base_price, Decimal("0.00"))
            room_upgrade_charge = (extra_per_night * Decimal(rooms_requested) * Decimal(stay_nights)).quantize(
                Decimal("0.01")
            )
            room_upgrade_details = {
                "room_type_name": room_req.get("room_type_name") or "Selected Room",
                "rooms_requested": rooms_requested,
                "stay_nights": stay_nights,
                "extra_per_night": extra_per_night.quantize(Decimal("0.01")),
                "included_room_base_price": included_base_price.quantize(Decimal("0.01")),
                "selected_room_base_price": selected_base_price.quantize(Decimal("0.01")),
                "charge": room_upgrade_charge,
            }

        amount_to_pay = (base_price + room_upgrade_charge).quantize(Decimal("0.01"))

        razorpay_available = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
        razorpay_order = None
        razorpay_error = None
        if razorpay_available:
            razorpay_order, razorpay_error = create_razorpay_order(
                amount_to_pay,
                receipt=f"booking-{booking_id}-u{session['user_id']}",
            )

        if request.method == "POST":
            payment_provider = (request.form.get("payment_provider") or "manual").strip().lower()
            if payment_provider not in {"manual", "razorpay"}:
                flash("Invalid payment provider.")
                return redirect(url_for("payment", booking_id=booking_id))
            if razorpay_available and payment_provider != "razorpay":
                flash("Please complete payment using Razorpay checkout.")
                return redirect(url_for("payment", booking_id=booking_id))
            if payment_provider == "razorpay":
                order_id = (request.form.get("razorpay_order_id") or "").strip()
                payment_id = (request.form.get("razorpay_payment_id") or "").strip()
                signature = (request.form.get("razorpay_signature") or "").strip()
                if not verify_razorpay_signature(order_id, payment_id, signature):
                    flash("Payment verification failed. Please try again.")
                    return redirect(url_for("payment", booking_id=booking_id))

            existing_payment = query_db(
                "SELECT id FROM payments WHERE booking_id=%s AND paid=1 ORDER BY id DESC LIMIT 1",
                (booking_id,),
                one=True,
            )
            admin_commission = (amount_to_pay * Decimal("0.01")).quantize(Decimal("0.01"))
            organizer_earning = (amount_to_pay - admin_commission).quantize(Decimal("0.01"))
            if not existing_payment:
                execute_db(
                    """
                    INSERT INTO payments(
                        booking_id, amount, admin_commission, organizer_earning, payment_provider, paid
                    )
                    VALUES(%s,%s,%s,%s,%s,1)
                    """,
                    (booking_id, amount_to_pay, admin_commission, organizer_earning, payment_provider),
                )
            execute_db("UPDATE bookings SET status='paid' WHERE id=%s", (booking_id,))
            flash("Payment successful. Your booking is confirmed.")
            return redirect(url_for("invoice", booking_id=booking_id))

        extra_charges = max(amount_to_pay - base_price, Decimal("0.00"))
        return render_template(
            "payment.html",
            booking=booking,
            base_price=base_price,
            unit_price=unit_price,
            pax_count=pax_count,
            adult_count=adult_count,
            child_count=child_count,
            child_price_percent=child_price_percent,
            extra_charges=extra_charges,
            room_upgrade_details=room_upgrade_details,
            amount_to_pay=amount_to_pay,
            razorpay_available=razorpay_available,
            razorpay_order=razorpay_order,
            razorpay_key_id=RAZORPAY_KEY_ID,
            razorpay_error=razorpay_error,
        )

    @app.route("/invoice/<int:booking_id>")
    @login_required
    def invoice(booking_id):
        booking = query_db(
            """
            SELECT b.*, t.title, t.price, t.start_date, t.departure_datetime, t.return_datetime
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            WHERE b.id=%s AND b.user_id=%s
            """,
            (booking_id, session["user_id"]),
            one=True,
        )
        if not booking:
            abort(404)
        if booking["status"] != "paid":
            flash("Complete payment to generate invoice.")
            return redirect(url_for("payment", booking_id=booking_id))
        return render_template("invoice.html", booking=booking)

    @app.route("/mybookings")
    @login_required
    def mybookings():
        bookings = query_db(
            """
            SELECT b.*, t.title, t.price, t.start_date, t.departure_datetime, t.return_datetime
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            WHERE b.user_id=%s
            ORDER BY b.id DESC
            """,
            (session["user_id"],),
        )
        return render_template("mybookings.html", bookings=bookings)
