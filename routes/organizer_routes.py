import base64
import csv
import io
import os
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.db import execute_db, get_db, query_db
from core.helpers import (
    is_allowed_image_filename,
    is_within_india_bounds,
    is_non_negative_amount,
    is_valid_latitude,
    is_valid_longitude,
    is_valid_phone,
    parse_date,
    save_upload,
    to_int,
)


def _to_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime_local(value):
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fig_to_base64(fig):
    buff = BytesIO()
    fig.tight_layout()
    fig.savefig(buff, format="png", dpi=120, bbox_inches="tight")
    buff.seek(0)
    encoded = base64.b64encode(buff.read()).decode("utf-8")
    buff.close()
    return encoded


def _normalize_local_spot_image(image_value, upload_folder, spot_folder):
    text = (image_value or "").strip()
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text

    normalized = text.replace("\\", "/").lstrip("/")
    if normalized.lower().startswith("static/uploads/"):
        normalized = normalized[len("static/uploads/") :]
    elif normalized.lower().startswith("uploads/"):
        normalized = normalized[len("uploads/") :]

    if "/" not in normalized and normalized.lower() != "demo.jpg":
        spot_path = os.path.join(spot_folder, normalized)
        upload_path = os.path.join(upload_folder, normalized)
        if os.path.isfile(spot_path):
            return f"spots/{normalized}"
        if os.path.isfile(upload_path):
            return normalized

    return normalized


def _build_organizer_charts(tours, bookings):
    charts = {"tours_by_month": None, "booking_status": None, "travel_mode": None}
    error = None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return charts, "Matplotlib not available in environment."

    try:
        month_counts = Counter()
        for row in tours:
            dt = _to_date(row.get("start_date"))
            if not dt:
                continue
            month_counts[dt.strftime("%b %Y")] += 1

        if month_counts:
            labels = sorted(
                month_counts.keys(),
                key=lambda s: datetime.strptime(s, "%b %Y"),
            )
            values = [month_counts[k] for k in labels]
            fig, ax = plt.subplots(figsize=(6.4, 3.2))
            ax.bar(labels, values, color="#2563eb")
            ax.set_title("Tours By Month")
            ax.set_ylabel("Tours")
            ax.tick_params(axis="x", rotation=30)
            charts["tours_by_month"] = _fig_to_base64(fig)
            plt.close(fig)

        status_counts = Counter([(b.get("status") or "unknown").capitalize() for b in bookings])
        if status_counts:
            labels = list(status_counts.keys())
            values = list(status_counts.values())
            fig, ax = plt.subplots(figsize=(4.6, 3.2))
            ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=140)
            ax.set_title("Booking Status Split")
            charts["booking_status"] = _fig_to_base64(fig)
            plt.close(fig)

        mode_counts = Counter([(t.get("travel_mode") or "Not Set") for t in tours])
        if mode_counts:
            labels = list(mode_counts.keys())
            values = list(mode_counts.values())
            fig, ax = plt.subplots(figsize=(6.4, 3.2))
            ax.barh(labels, values, color="#16a34a")
            ax.set_title("Travel Mode Distribution")
            ax.set_xlabel("Tours")
            charts["travel_mode"] = _fig_to_base64(fig)
            plt.close(fig)
    except Exception:
        error = "Unable to generate charts from current data."

    return charts, error


def register_routes(app):
    @app.route("/organizer", methods=["GET", "POST"])
    @login_required
    @role_required("organizer")
    def organizer_dashboard():
        if request.method == "POST":
            action = request.form.get("action", "").strip()

            if action == "add_city":
                state_id = to_int(request.form.get("state_id"), 0)
                city_name = request.form.get("city_name", "").strip()
                if state_id and city_name and len(city_name) <= 100:
                    state_ok = query_db("SELECT id FROM states WHERE id=%s", (state_id,), one=True)
                    if not state_ok:
                        flash("Invalid state selected.")
                        return redirect(url_for("organizer_dashboard"))
                    execute_db(
                        "INSERT INTO cities(state_id, city_name) VALUES(%s,%s)",
                        (state_id, city_name),
                    )
                    flash("City added.")
                else:
                    flash("Invalid city details.")

            elif action == "add_spot":
                city_id = to_int(request.form.get("city_id"), 0)
                spot_name = request.form.get("spot_name", "").strip()
                latitude = (
                    request.form.get("latitude")
                    or request.form.get("letitude")
                    or request.form.get("lattitude")
                    or ""
                ).strip()
                longitude = (
                    request.form.get("longitude")
                    or request.form.get("longtitude")
                    or request.form.get("logitutide")
                    or ""
                ).strip()
                external_image_url = (
                    request.form.get("external_image_url")
                    or request.form.get("image_url")
                    or request.form.get("image")
                    or ""
                ).strip()
                spot_details = (
                    request.form.get("spot_details")
                    or request.form.get("details")
                    or request.form.get("description")
                    or ""
                ).strip()
                image_file = request.files.get("spot_image")
                if image_file and image_file.filename and not is_allowed_image_filename(image_file.filename):
                    flash("Spot image must be a JPG, JPEG, PNG, or WEBP file.")
                    return redirect(url_for("organizer_dashboard"))
                if not city_id or not spot_name or len(spot_name) > 100:
                    flash("City and valid spot name are required.")
                    return redirect(url_for("organizer_dashboard"))
                city_ok = query_db("SELECT id FROM cities WHERE id=%s", (city_id,), one=True)
                if not city_ok:
                    flash("Invalid city selected.")
                    return redirect(url_for("organizer_dashboard"))
                has_lat = bool(latitude)
                has_lng = bool(longitude)
                if has_lat != has_lng:
                    flash("Enter both latitude and longitude together, or leave both blank.")
                    return redirect(url_for("organizer_dashboard"))
                if latitude and not is_valid_latitude(latitude):
                    flash("Latitude must be between -90 and 90.")
                    return redirect(url_for("organizer_dashboard"))
                if longitude and not is_valid_longitude(longitude):
                    flash("Longitude must be between -180 and 180.")
                    return redirect(url_for("organizer_dashboard"))
                if has_lat and has_lng and not is_within_india_bounds(latitude, longitude):
                    flash("Spot coordinates must be inside India.")
                    return redirect(url_for("organizer_dashboard"))
                if external_image_url and not external_image_url.lower().startswith(("http://", "https://")):
                    flash("External image URL must start with http:// or https://")
                    return redirect(url_for("organizer_dashboard"))
                if len(spot_details) > 2000:
                    flash("Spot details must be 2000 characters or less.")
                    return redirect(url_for("organizer_dashboard"))
                if city_id and spot_name:
                    image_name = None
                    if image_file and image_file.filename:
                        image_name = save_upload(image_file, app.config["SPOT_UPLOAD_FOLDER"])
                        if not image_name:
                            flash("Unable to upload spot image.")
                            return redirect(url_for("organizer_dashboard"))
                    uploaded_image_path = f"spots/{image_name}" if image_name else ""
                    final_image = external_image_url or uploaded_image_path or "demo.jpg"
                    photo_source = "external_url" if external_image_url else "local_file"
                    execute_db(
                        """
                        INSERT INTO spot_change_requests(
                            organizer_id, request_type, status, city_id, spot_name,
                            image_url, photo_source, latitude, longitude, spot_details
                        )
                        VALUES(%s,'add_spot','pending',%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            session["user_id"],
                            city_id,
                            spot_name,
                            final_image,
                            photo_source,
                            latitude or None,
                            longitude or None,
                            spot_details or None,
                        ),
                    )
                    flash("Spot request submitted. Admin approval is required before it appears in database.")

            elif action == "add_spots_csv":
                csv_file = request.files.get("spots_csv")
                default_city_id = to_int(request.form.get("default_city_id"), 0)
                if not csv_file or not csv_file.filename:
                    flash("Please upload a CSV file.")
                    return redirect(url_for("organizer_dashboard"))
                if not csv_file.filename.lower().endswith(".csv"):
                    flash("Only CSV file is allowed.")
                    return redirect(url_for("organizer_dashboard"))
                if default_city_id:
                    city_ok = query_db("SELECT id FROM cities WHERE id=%s", (default_city_id,), one=True)
                    if not city_ok:
                        flash("Invalid default city selected.")
                        return redirect(url_for("organizer_dashboard"))

                try:
                    text_stream = io.TextIOWrapper(csv_file.stream, encoding="utf-8-sig")
                    reader = csv.DictReader(text_stream)
                except Exception:
                    flash("Unable to read CSV file.")
                    return redirect(url_for("organizer_dashboard"))

                db = get_db()
                cur = db.cursor(dictionary=True)
                inserted = 0
                updated = 0
                skipped = 0

                states = query_db("SELECT id, state_name FROM states")
                state_map = {str(s["id"]): s["id"] for s in states}
                state_map.update({(s["state_name"] or "").strip().lower(): s["id"] for s in states})

                cities = query_db("SELECT id, state_id, city_name FROM cities")
                city_key_map = {}
                city_id_map = {}
                for c in cities:
                    city_id_map[str(c["id"])] = c["id"]
                    city_key = ((c["city_name"] or "").strip().lower(), int(c["state_id"] or 0))
                    city_key_map[city_key] = c["id"]

                def resolve_state_id(raw_state):
                    from core.helpers import normalize_state_name
                    if not raw_state:
                        return 0
                    cleaned = normalize_state_name(raw_state)
                    return int(state_map.get(cleaned.strip().lower()) or state_map.get(str(cleaned)) or 0)

                def resolve_city_id(raw_city_id, raw_city_name, raw_state):
                    if raw_city_id and str(raw_city_id).isdigit():
                        cid = city_id_map.get(str(int(raw_city_id)))
                        if cid:
                            return cid
                    if raw_city_name:
                        state_resolved = resolve_state_id(raw_state)
                        key = ((raw_city_name or "").strip().lower(), state_resolved)
                        cid = city_key_map.get(key)
                        if cid:
                            return cid
                        if state_resolved:
                            cur.execute(
                                "INSERT INTO cities(state_id, city_name) VALUES(%s,%s)",
                                (state_resolved, raw_city_name.strip()),
                            )
                            cid = cur.lastrowid
                            city_id_map[str(cid)] = cid
                            city_key_map[((raw_city_name or "").strip().lower(), state_resolved)] = cid
                            return cid
                    return default_city_id if default_city_id else 0

                def csv_value(row_data, *keys):
                    for key in keys:
                        value = row_data.get(key)
                        if value is None:
                            continue
                        text = str(value).strip()
                        if text:
                            return text
                    return ""

                for row in reader:
                    spot_name = csv_value(row, "spot_name", "spot", "place_name")
                    if not spot_name:
                        skipped += 1
                        continue

                    raw_city_id = csv_value(row, "city_id")
                    raw_city_name = csv_value(row, "city_name", "city")
                    raw_state = csv_value(row, "state_name", "state_id", "state")
                    city_id = resolve_city_id(
                        raw_city_id,
                        raw_city_name,
                        raw_state,
                    )
                    if not city_id:
                        skipped += 1
                        continue

                    image_url = (
                        csv_value(
                            row,
                            "image_file",
                            "image_url",
                            "image",
                            "images",
                            "photo",
                            "photo_url",
                            "img",
                        )
                        or "demo.jpg"
                    )
                    image_url = _normalize_local_spot_image(
                        image_url,
                        app.config["UPLOAD_FOLDER"],
                        app.config["SPOT_UPLOAD_FOLDER"],
                    )
                    photo_source = "external_url" if image_url.lower().startswith(("http://", "https://")) else "local_file"
                    latitude = csv_value(row, "latitude", "lat", "letitude", "lattitude") or None
                    longitude = csv_value(row, "longitude", "longtitude", "logitutide", "lng", "lon") or None
                    spot_details = (
                        csv_value(row, "spot_details", "details", "description", "spot_description", "about") or None
                    )
                    has_lat = bool(latitude)
                    has_lng = bool(longitude)
                    if has_lat != has_lng:
                        skipped += 1
                        continue
                    if latitude and not is_valid_latitude(latitude):
                        skipped += 1
                        continue
                    if longitude and not is_valid_longitude(longitude):
                        skipped += 1
                        continue
                    if has_lat and has_lng and not is_within_india_bounds(latitude, longitude):
                        skipped += 1
                        continue

                    cur.execute(
                        "SELECT id FROM master_spots WHERE city_id=%s AND spot_name=%s LIMIT 1",
                        (city_id, spot_name),
                    )
                    existing = cur.fetchone()
                    if existing:
                        cur.execute(
                            """
                            UPDATE master_spots
                            SET image_url=%s, photo_source=%s, latitude=%s, longitude=%s, spot_details=%s
                            WHERE id=%s
                            """,
                            (image_url, photo_source, latitude, longitude, spot_details, existing["id"]),
                        )
                        updated += 1
                    else:
                        cur.execute(
                            """
                            INSERT INTO master_spots(spot_name,image_url,photo_source,city_id,latitude,longitude,spot_details)
                            VALUES(%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (spot_name, image_url, photo_source, city_id, latitude, longitude, spot_details),
                        )
                        inserted += 1

                db.commit()
                cur.close()
                db.close()
                flash(f"CSV import completed. Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}")

            elif action == "update_spot_image":
                spot_id = to_int(request.form.get("spot_id"), 0)
                external_image_url = (request.form.get("external_image_url") or "").strip()
                image_file = request.files.get("spot_image")

                if spot_id <= 0:
                    flash("Invalid spot selected for image update.")
                    return redirect(url_for("organizer_dashboard"))

                spot_exists = query_db(
                    "SELECT id, spot_name, city_id FROM master_spots WHERE id=%s",
                    (spot_id,),
                    one=True,
                )
                if not spot_exists:
                    flash("Selected spot was not found.")
                    return redirect(url_for("organizer_dashboard"))

                final_image = ""
                photo_source = "local_file"
                if image_file and image_file.filename:
                    if not is_allowed_image_filename(image_file.filename):
                        flash("Spot image must be a JPG, JPEG, PNG, or WEBP file.")
                        return redirect(url_for("organizer_dashboard"))
                    image_name = save_upload(image_file, app.config["SPOT_UPLOAD_FOLDER"])
                    if not image_name:
                        flash("Unable to upload spot image file.")
                        return redirect(url_for("organizer_dashboard"))
                    final_image = f"spots/{image_name}"
                elif external_image_url:
                    if not external_image_url.lower().startswith(("http://", "https://")):
                        flash("External image URL must start with http:// or https://")
                        return redirect(url_for("organizer_dashboard"))
                    final_image = external_image_url
                    photo_source = "external_url"
                else:
                    flash("Upload a spot image or provide an external image URL.")
                    return redirect(url_for("organizer_dashboard"))

                execute_db(
                    """
                    INSERT INTO spot_change_requests(
                        organizer_id, request_type, status, spot_id, city_id, spot_name,
                        image_url, photo_source
                    )
                    VALUES(%s,'update_spot_image','pending',%s,%s,%s,%s,%s)
                    """,
                    (
                        session["user_id"],
                        spot_id,
                        to_int(spot_exists.get("city_id"), 0) or None,
                        spot_exists.get("spot_name") or "",
                        final_image,
                        photo_source,
                    ),
                )
                flash("Spot image change request submitted. Admin approval is required.")

            elif action == "add_external_booking":
                tour_id = to_int(request.form.get("tour_id"), 0)
                traveler_name = (request.form.get("traveler_name") or "").strip()
                contact_number = (request.form.get("contact_number") or "").strip()
                pax_count = max(1, to_int(request.form.get("pax_count"), 1))
                amount_text = (request.form.get("amount_received") or "0").strip() or "0"
                notes = (request.form.get("notes") or "").strip()

                if tour_id <= 0:
                    flash("Select a valid tour for manual booking.")
                    return redirect(url_for("organizer_dashboard"))
                tour_row = query_db(
                    "SELECT id, max_group_size FROM tours WHERE id=%s AND organizer_id=%s",
                    (tour_id, session["user_id"]),
                    one=True,
                )
                if not tour_row:
                    flash("Invalid tour selected.")
                    return redirect(url_for("organizer_dashboard"))
                if not traveler_name or len(traveler_name) > 120:
                    flash("Traveler name is required (max 120 chars).")
                    return redirect(url_for("organizer_dashboard"))
                if contact_number and not is_valid_phone(contact_number):
                    flash("Contact number must be a valid 10-digit mobile number.")
                    return redirect(url_for("organizer_dashboard"))
                if len(notes) > 255:
                    flash("Booking notes must be 255 characters or less.")
                    return redirect(url_for("organizer_dashboard"))
                if not is_non_negative_amount(amount_text):
                    flash("Manual booking amount must be non-negative.")
                    return redirect(url_for("organizer_dashboard"))

                amount = Decimal(amount_text)
                admin_commission = (amount * Decimal("0.01")).quantize(Decimal("0.01"))
                organizer_earning = (amount - admin_commission).quantize(Decimal("0.01"))
                execute_db(
                    """
                    INSERT INTO organizer_external_bookings(
                        organizer_id, tour_id, traveler_name, contact_number, pax_count,
                        amount_received, admin_commission, organizer_earning, notes
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        session["user_id"],
                        tour_id,
                        traveler_name,
                        contact_number or None,
                        pax_count,
                        amount,
                        admin_commission,
                        organizer_earning,
                        notes or None,
                    ),
                )

                total_booked_row = query_db(
                    """
                    SELECT
                        COALESCE(
                            (
                                SELECT SUM(b.pax_count)
                                FROM bookings b
                                WHERE b.tour_id=%s AND b.status IN ('pending', 'paid')
                            ),
                            0
                        ) + COALESCE(
                            (
                                SELECT SUM(eb.pax_count)
                                FROM organizer_external_bookings eb
                                WHERE eb.tour_id=%s
                            ),
                            0
                        ) AS total_booked
                    """,
                    (tour_id, tour_id),
                    one=True,
                ) or {}
                max_group_size = to_int(tour_row.get("max_group_size"), 0)
                total_booked = to_int(total_booked_row.get("total_booked"), 0)
                if max_group_size:
                    next_status = "full" if total_booked >= max_group_size else "open"
                    execute_db(
                        "UPDATE tours SET tour_status=%s WHERE id=%s AND organizer_id=%s",
                        (next_status, tour_id, session["user_id"]),
                    )

                flash("Manual booking saved and analytics updated.")

            elif action == "update_tour_image":
                tour_id = to_int(request.form.get("tour_id"), 0)
                if tour_id <= 0:
                    flash("Invalid tour selected for image update.")
                    return redirect(url_for("organizer_dashboard"))

                owned_tour = query_db(
                    "SELECT id FROM tours WHERE id=%s AND organizer_id=%s",
                    (tour_id, session["user_id"]),
                    one=True,
                )
                if not owned_tour:
                    flash("Tour not found for this organizer.")
                    return redirect(url_for("organizer_dashboard"))

                image_file = request.files.get("tour_image")
                if image_file and image_file.filename and not is_allowed_image_filename(image_file.filename):
                    flash("Tour image must be a JPG, JPEG, PNG, or WEBP file.")
                    return redirect(url_for("organizer_dashboard"))
                image_name = save_upload(image_file, app.config["UPLOAD_FOLDER"])
                if not image_name:
                    flash("Please upload a valid image file to update the tour.")
                    return redirect(url_for("organizer_dashboard"))

                execute_db(
                    "UPDATE tours SET image_path=%s WHERE id=%s AND organizer_id=%s",
                    (image_name, tour_id, session["user_id"]),
                )
                flash("Tour image updated successfully.")

            elif action == "add_tour":
                title = request.form.get("title", "").strip()
                description = request.form.get("description", "").strip()
                price = (request.form.get("price", "0") or "0").strip()
                start_point = request.form.get("start_point", "").strip()
                end_point = request.form.get("end_point", "").strip()
                start_date = (request.form.get("start_date") or "").strip()
                end_date = (request.form.get("end_date") or "").strip()
                travel_mode = request.form.get("travel_mode", "").strip()
                food_plan = request.form.get("food_plan", "").strip()
                transport_details = request.form.get("transport_details", "").strip()
                hotel_notes = request.form.get("hotel_notes", "").strip()
                inclusions = request.form.get("inclusions", "").strip()
                exclusions = request.form.get("exclusions", "").strip()
                pickup_state_id = to_int(request.form.get("pickup_state_id"), 0) or None
                pickup_city_id = to_int(request.form.get("pickup_city_id"), 0) or None
                drop_state_id = to_int(request.form.get("drop_state_id"), 0) or None
                drop_city_id = to_int(request.form.get("drop_city_id"), 0) or None
                max_group_size = to_int(request.form.get("max_group_size"), 0) or None
                min_group_size = to_int(
                    request.form.get("start_min_people") or request.form.get("min_group_size"),
                    6,
                ) or 6
                terms_conditions = request.form.get("terms_conditions", "").strip()
                child_price_percent_text = (request.form.get("child_price_percent") or "100").strip() or "100"
                departure_datetime_raw = (request.form.get("departure_datetime") or "").strip()
                return_datetime_raw = (request.form.get("return_datetime") or "").strip()
                difficulty_level = request.form.get("difficulty_level", "").strip()
                linked_hotels = request.form.getlist("linked_hotels[]")
                linked_guides = request.form.getlist("linked_guides[]")
                tour_image_file = request.files.get("tour_image")
                if tour_image_file and tour_image_file.filename and not is_allowed_image_filename(tour_image_file.filename):
                    flash("Tour image must be a JPG, JPEG, PNG, or WEBP file.")
                    return redirect(url_for("organizer_dashboard"))
                image_name = save_upload(tour_image_file, app.config["UPLOAD_FOLDER"]) or "demo.jpg"
                day_numbers = request.form.getlist("day_numbers[]")
                spots = request.form.getlist("spots[]")
                hotel_stay_service_ids = request.form.getlist("hotel_stay_service_ids[]")
                hotel_stay_check_ins = request.form.getlist("hotel_stay_check_ins[]")
                hotel_stay_check_outs = request.form.getlist("hotel_stay_check_outs[]")
                hotel_stay_notes = request.form.getlist("hotel_stay_notes[]")
                schedule_city_ids = request.form.getlist("schedule_city_ids[]")
                schedule_arrivals = request.form.getlist("schedule_arrivals[]")
                schedule_departures = request.form.getlist("schedule_departures[]")
                schedule_notes = request.form.getlist("schedule_notes[]")

                if not (title and start_point and end_point and start_date and end_date):
                    flash("All required tour fields must be filled.")
                    return redirect(url_for("organizer_dashboard"))
                if not (pickup_state_id and pickup_city_id and drop_state_id and drop_city_id):
                    flash("Pickup and drop state/city are required.")
                    return redirect(url_for("organizer_dashboard"))
                if len(title) > 255 or len(start_point) > 255 or len(end_point) > 255:
                    flash("Tour title or point name is too long.")
                    return redirect(url_for("organizer_dashboard"))
                if len(description) > 5000:
                    flash("Tour description is too long.")
                    return redirect(url_for("organizer_dashboard"))
                if len(transport_details) > 255:
                    flash("Transport details should be 255 characters or less.")
                    return redirect(url_for("organizer_dashboard"))
                if len(hotel_notes) > 2000 or len(inclusions) > 2000 or len(exclusions) > 2000 or len(terms_conditions) > 4000:
                    flash("One of the detail fields is too long.")
                    return redirect(url_for("organizer_dashboard"))
                if not is_non_negative_amount(price):
                    flash("Tour price must be a valid non-negative number.")
                    return redirect(url_for("organizer_dashboard"))
                start_dt = parse_date(start_date)
                end_dt = parse_date(end_date)
                if not start_dt or not end_dt:
                    flash("Invalid tour dates.")
                    return redirect(url_for("organizer_dashboard"))
                if start_dt >= end_dt:
                    flash("Start date must be earlier than end date.")
                    return redirect(url_for("organizer_dashboard"))
                if not max_group_size or max_group_size < 1:
                    flash("Max group size must be at least 1.")
                    return redirect(url_for("organizer_dashboard"))
                if min_group_size < 1:
                    flash("Minimum people to start tour must be at least 1.")
                    return redirect(url_for("organizer_dashboard"))
                if not is_non_negative_amount(child_price_percent_text):
                    flash("Child price percent must be a valid non-negative number.")
                    return redirect(url_for("organizer_dashboard"))
                try:
                    child_price_percent = Decimal(child_price_percent_text)
                except (InvalidOperation, TypeError):
                    flash("Invalid child price percent.")
                    return redirect(url_for("organizer_dashboard"))
                if child_price_percent > Decimal("100"):
                    flash("Child price percent cannot exceed 100.")
                    return redirect(url_for("organizer_dashboard"))

                departure_datetime = _parse_datetime_local(departure_datetime_raw)
                return_datetime = _parse_datetime_local(return_datetime_raw)
                if departure_datetime_raw and not departure_datetime:
                    flash("Invalid departure date/time.")
                    return redirect(url_for("organizer_dashboard"))
                if return_datetime_raw and not return_datetime:
                    flash("Invalid return date/time.")
                    return redirect(url_for("organizer_dashboard"))
                if departure_datetime and return_datetime and departure_datetime >= return_datetime:
                    flash("Return date/time must be after departure date/time.")
                    return redirect(url_for("organizer_dashboard"))

                if not query_db("SELECT id FROM states WHERE id=%s", (pickup_state_id,), one=True):
                    flash("Invalid pickup state.")
                    return redirect(url_for("organizer_dashboard"))
                if not query_db("SELECT id FROM states WHERE id=%s", (drop_state_id,), one=True):
                    flash("Invalid drop state.")
                    return redirect(url_for("organizer_dashboard"))
                pickup_city = query_db(
                    "SELECT id, state_id FROM cities WHERE id=%s",
                    (pickup_city_id,),
                    one=True,
                )
                if not pickup_city:
                    flash("Invalid pickup city.")
                    return redirect(url_for("organizer_dashboard"))
                drop_city = query_db(
                    "SELECT id, state_id FROM cities WHERE id=%s",
                    (drop_city_id,),
                    one=True,
                )
                if not drop_city:
                    flash("Invalid drop city.")
                    return redirect(url_for("organizer_dashboard"))
                if int(pickup_city["state_id"]) != pickup_state_id:
                    flash("Pickup city does not belong to selected pickup state.")
                    return redirect(url_for("organizer_dashboard"))
                if int(drop_city["state_id"]) != drop_state_id:
                    flash("Drop city does not belong to selected drop state.")
                    return redirect(url_for("organizer_dashboard"))

                allowed_state_ids = {pickup_state_id, drop_state_id}
                total_days = (end_dt - start_dt).days + 1

                itinerary_rows = []
                for idx, spot_id_raw in enumerate(spots):
                    spot_id = to_int(spot_id_raw, 0)
                    if not spot_id:
                        continue
                    day_num = max(1, to_int(day_numbers[idx] if idx < len(day_numbers) else 1, 1))
                    if day_num > total_days:
                        flash(f"Itinerary day must be between 1 and {total_days}.")
                        return redirect(url_for("organizer_dashboard"))
                    itinerary_rows.append((spot_id, day_num, idx + 1))
                if not itinerary_rows:
                    flash("Add at least one valid itinerary spot.")
                    return redirect(url_for("organizer_dashboard"))

                itinerary_spot_ids = sorted({row[0] for row in itinerary_rows})
                spot_placeholders = ", ".join(["%s"] * len(itinerary_spot_ids))
                spot_rows = query_db(
                    f"""
                    SELECT
                        ms.id,
                        ms.spot_name,
                        c.id AS city_id,
                        c.city_name,
                        s.id AS state_id,
                        s.state_name
                    FROM master_spots ms
                    JOIN cities c ON c.id=ms.city_id
                    JOIN states s ON s.id=c.state_id
                    WHERE ms.id IN ({spot_placeholders})
                    """,
                    tuple(itinerary_spot_ids),
                )
                spot_map = {int(s["id"]): s for s in spot_rows}
                if len(spot_map) != len(itinerary_spot_ids):
                    flash("One or more selected spots are invalid.")
                    return redirect(url_for("organizer_dashboard"))
                for spot_id, _, _ in itinerary_rows:
                    spot = spot_map[spot_id]
                    if int(spot["state_id"]) not in allowed_state_ids:
                        flash(
                            f"Spot '{spot['spot_name']}' is outside selected pickup/drop states. "
                            "Please use relevant spots only."
                        )
                        return redirect(url_for("organizer_dashboard"))

                def parse_service_ids(raw_list):
                    return sorted({to_int(v, 0) for v in raw_list if to_int(v, 0) > 0})

                hotel_ids = parse_service_ids(linked_hotels)
                guide_ids = parse_service_ids(linked_guides)
                transport_ids = []

                def validate_service_ids(service_ids, expected_type, label):
                    if not service_ids:
                        return service_ids
                    placeholders = ", ".join(["%s"] * len(service_ids))
                    rows = query_db(
                        f"""
                        SELECT s.id, s.service_type, c.state_id
                        FROM services s
                        LEFT JOIN cities c ON c.id=s.city_id
                        WHERE s.id IN ({placeholders})
                        """,
                        tuple(service_ids),
                    )
                    row_map = {int(r["id"]): r for r in rows}
                    if len(row_map) != len(service_ids):
                        flash(f"Invalid {label} selection found.")
                        return None
                    for sid in service_ids:
                        row = row_map[sid]
                        if row["service_type"] != expected_type:
                            flash(f"Invalid {label} type selected.")
                            return None
                        state_id = row.get("state_id")
                        if state_id and int(state_id) not in allowed_state_ids:
                            flash(f"{label} must belong to pickup/drop states.")
                            return None
                    return service_ids

                hotel_ids = validate_service_ids(hotel_ids, "Hotel", "Hotel")
                if hotel_ids is None:
                    return redirect(url_for("organizer_dashboard"))
                guide_ids = validate_service_ids(guide_ids, "Guides", "Guide")
                if guide_ids is None:
                    return redirect(url_for("organizer_dashboard"))
                if not transport_details:
                    flash("Add transport details for this tour.")
                    return redirect(url_for("organizer_dashboard"))

                hotel_stays = []
                max_checkout = end_dt + timedelta(days=1)
                stay_row_count = max(
                    len(hotel_stay_service_ids),
                    len(hotel_stay_check_ins),
                    len(hotel_stay_check_outs),
                    len(hotel_stay_notes),
                )
                for idx in range(stay_row_count):
                    service_id = to_int(hotel_stay_service_ids[idx] if idx < len(hotel_stay_service_ids) else 0, 0)
                    check_in_raw = (hotel_stay_check_ins[idx] if idx < len(hotel_stay_check_ins) else "").strip()
                    check_out_raw = (hotel_stay_check_outs[idx] if idx < len(hotel_stay_check_outs) else "").strip()
                    note = (hotel_stay_notes[idx] if idx < len(hotel_stay_notes) else "").strip()

                    if not service_id and not check_in_raw and not check_out_raw and not note:
                        continue
                    if not service_id or not check_in_raw or not check_out_raw:
                        flash("Each night-stay row needs hotel, check-in, and check-out dates.")
                        return redirect(url_for("organizer_dashboard"))
                    if service_id not in hotel_ids:
                        flash("Night-stay hotel must be selected in linked hotels.")
                        return redirect(url_for("organizer_dashboard"))
                    check_in = parse_date(check_in_raw)
                    check_out = parse_date(check_out_raw)
                    if not check_in or not check_out:
                        flash("Invalid hotel stay dates.")
                        return redirect(url_for("organizer_dashboard"))
                    if check_in >= check_out:
                        flash("Hotel stay check-out must be after check-in.")
                        return redirect(url_for("organizer_dashboard"))
                    if check_in < start_dt or check_out > max_checkout:
                        flash("Hotel stay dates must fall inside the tour duration.")
                        return redirect(url_for("organizer_dashboard"))
                    nights = (check_out - check_in).days
                    hotel_stays.append((service_id, check_in, check_out, nights, note[:255] if note else None))

                if hotel_ids and not hotel_stays:
                    flash("Add at least one detailed hotel night-stay row for linked hotel(s).")
                    return redirect(url_for("organizer_dashboard"))

                city_schedule_rows = []
                schedule_row_count = max(
                    len(schedule_city_ids),
                    len(schedule_arrivals),
                    len(schedule_departures),
                    len(schedule_notes),
                )
                for idx in range(schedule_row_count):
                    city_id = to_int(schedule_city_ids[idx] if idx < len(schedule_city_ids) else 0, 0)
                    arrival_raw = (schedule_arrivals[idx] if idx < len(schedule_arrivals) else "").strip()
                    departure_raw = (schedule_departures[idx] if idx < len(schedule_departures) else "").strip()
                    note = (schedule_notes[idx] if idx < len(schedule_notes) else "").strip()
                    if not city_id and not arrival_raw and not departure_raw and not note:
                        continue
                    if not city_id or not arrival_raw or not departure_raw:
                        flash("Each city schedule row requires city, arrival and departure datetime.")
                        return redirect(url_for("organizer_dashboard"))
                    city_row = query_db(
                        "SELECT id, state_id FROM cities WHERE id=%s",
                        (city_id,),
                        one=True,
                    )
                    if not city_row:
                        flash("Invalid city in schedule.")
                        return redirect(url_for("organizer_dashboard"))
                    if to_int(city_row.get("state_id"), 0) not in allowed_state_ids:
                        flash("Scheduled cities must belong to pickup/drop states.")
                        return redirect(url_for("organizer_dashboard"))
                    arrival_dt = _parse_datetime_local(arrival_raw)
                    departure_dt = _parse_datetime_local(departure_raw)
                    if not arrival_dt or not departure_dt:
                        flash("Invalid city schedule datetime.")
                        return redirect(url_for("organizer_dashboard"))
                    if arrival_dt >= departure_dt:
                        flash("In city schedule, departure must be after arrival.")
                        return redirect(url_for("organizer_dashboard"))
                    city_schedule_rows.append(
                        (
                            city_id,
                            arrival_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            departure_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            idx + 1,
                            note[:255] if note else None,
                        )
                    )

                db = get_db()
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO tours(
                        organizer_id,tour_status,title,description,price,start_date,end_date,start_point,end_point,image_path,
                        travel_mode,food_plan,transport_details,hotel_notes,inclusions,exclusions,
                        pickup_state_id,pickup_city_id,drop_state_id,drop_city_id,max_group_size,min_group_size,
                        terms_conditions,child_price_percent,departure_datetime,return_datetime,difficulty_level
                    )
                    VALUES(%s,'open',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        session["user_id"],
                        title,
                        description,
                        price,
                        start_date,
                        end_date,
                        start_point,
                        end_point,
                        image_name,
                        travel_mode or None,
                        food_plan or None,
                        transport_details or None,
                        hotel_notes or None,
                        inclusions or None,
                        exclusions or None,
                        pickup_state_id,
                        pickup_city_id,
                        drop_state_id,
                        drop_city_id,
                        max_group_size,
                        min_group_size,
                        terms_conditions or None,
                        child_price_percent,
                        departure_datetime.strftime("%Y-%m-%d %H:%M:%S") if departure_datetime else None,
                        return_datetime.strftime("%Y-%m-%d %H:%M:%S") if return_datetime else None,
                        difficulty_level or None,
                    ),
                )
                tour_id = cur.lastrowid

                for spot_id, day_num, seq in itinerary_rows:
                    cur.execute(
                        """
                        INSERT INTO tour_itinerary(tour_id, spot_id, order_sequence, day_number)
                        VALUES(%s,%s,%s,%s)
                        """,
                        (tour_id, int(spot_id), seq, day_num),
                    )

                for sid in hotel_ids:
                    cur.execute(
                        """
                        INSERT IGNORE INTO tour_service_links(tour_id, service_id, service_kind)
                        VALUES(%s,%s,'Hotel')
                        """,
                        (tour_id, sid),
                    )
                for sid in guide_ids:
                    cur.execute(
                        """
                        INSERT IGNORE INTO tour_service_links(tour_id, service_id, service_kind)
                        VALUES(%s,%s,'Guides')
                        """,
                        (tour_id, sid),
                    )
                for sid in transport_ids:
                    cur.execute(
                        """
                        INSERT IGNORE INTO tour_service_links(tour_id, service_id, service_kind)
                        VALUES(%s,%s,'Transport')
                        """,
                        (tour_id, sid),
                    )

                if hotel_stays:
                    cur.execute("SHOW TABLES LIKE 'tour_hotel_stays'")
                    if not cur.fetchone():
                        db.rollback()
                        cur.close()
                        db.close()
                        flash("Hotel stay table not found. Restart app once to apply latest schema.")
                        return redirect(url_for("organizer_dashboard"))
                    for service_id, check_in, check_out, nights, stay_note in hotel_stays:
                        cur.execute(
                            """
                            INSERT INTO tour_hotel_stays(
                                tour_id, service_id, check_in_date, check_out_date, nights, stay_notes
                            )
                            VALUES(%s,%s,%s,%s,%s,%s)
                            """,
                            (tour_id, service_id, check_in, check_out, nights, stay_note),
                        )

                if city_schedule_rows:
                    for city_id, arrival_dt, departure_dt, sequence_no, schedule_note in city_schedule_rows:
                        cur.execute(
                            """
                            INSERT INTO tour_city_schedules(
                                tour_id, city_id, arrival_datetime, departure_datetime, sequence_no, note
                            )
                            VALUES(%s,%s,%s,%s,%s,%s)
                            """,
                            (tour_id, city_id, arrival_dt, departure_dt, sequence_no, schedule_note),
                        )

                db.commit()
                cur.close()
                db.close()
                flash("Tour published with detailed itinerary, stay plan and schedule.")

            elif action == "update_tour_status":
                tour_id = to_int(request.form.get("tour_id"), 0)
                new_status = (request.form.get("tour_status") or "").strip().lower()
                if tour_id <= 0 or new_status not in {"open", "full", "closed"}:
                    flash("Invalid tour status.")
                    return redirect(url_for("organizer_dashboard"))
                execute_db(
                    "UPDATE tours SET tour_status=%s WHERE id=%s AND organizer_id=%s",
                    (new_status, tour_id, session["user_id"]),
                )
                flash("Tour status updated.")

            return redirect(url_for("organizer_dashboard"))

        tours = query_db(
            """
            SELECT
                t.*,
                (
                    SELECT COALESCE(SUM(b.pax_count), 0)
                    FROM bookings b
                    WHERE b.tour_id=t.id AND b.status IN ('pending', 'paid')
                ) + (
                    SELECT COALESCE(SUM(eb.pax_count), 0)
                    FROM organizer_external_bookings eb
                    WHERE eb.tour_id=t.id
                ) AS booked_pax,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Transport'
                ) AS linked_transport_count
            FROM tours t
            WHERE t.organizer_id=%s
            ORDER BY t.id DESC
            """,
            (session["user_id"],),
        )
        bookings = query_db(
            """
            SELECT b.*, u.full_name, t.title
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            JOIN tours t ON t.id=b.tour_id
            WHERE t.organizer_id=%s
            ORDER BY b.id DESC
            """,
            (session["user_id"],),
        )
        external_bookings = query_db(
            """
            SELECT
                eb.id,
                eb.tour_id,
                t.title,
                eb.traveler_name,
                eb.contact_number,
                eb.pax_count,
                eb.amount_received,
                eb.admin_commission,
                eb.organizer_earning,
                eb.notes,
                eb.created_at
            FROM organizer_external_bookings eb
            JOIN tours t ON t.id=eb.tour_id
            WHERE eb.organizer_id=%s
            ORDER BY eb.id DESC
            LIMIT 100
            """,
            (session["user_id"],),
        )
        states = query_db("SELECT * FROM states ORDER BY state_name")
        cities = query_db(
            """
            SELECT c.*, s.state_name
            FROM cities c
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name
            """
        )
        spots = query_db(
            """
            SELECT
                ms.id AS spot_id,
                ms.spot_name,
                ms.image_url,
                ms.photo_source,
                ms.latitude,
                ms.longitude,
                c.id AS city_id,
                c.city_name,
                s.id AS state_id,
                s.state_name
            FROM master_spots ms
            JOIN cities c ON c.id=ms.city_id
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name, ms.spot_name
            """
        )
        spot_requests = query_db(
            """
            SELECT
                r.id,
                r.request_type,
                r.status,
                r.spot_id,
                r.city_id,
                r.spot_name,
                r.image_url,
                r.photo_source,
                r.latitude,
                r.longitude,
                r.spot_details,
                r.admin_note,
                r.created_at,
                r.reviewed_at,
                c.city_name,
                s.state_name
            FROM spot_change_requests r
            LEFT JOIN cities c ON c.id=r.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE r.organizer_id=%s
            ORDER BY r.id DESC
            LIMIT 100
            """,
            (session["user_id"],),
        )
        hotel_options = query_db(
            """
            SELECT
                svc.id AS service_id,
                hp.hotel_name,
                c.id AS city_id,
                c.city_name,
                s.id AS state_id,
                s.state_name
            FROM services svc
            JOIN hotel_profiles hp ON hp.service_id=svc.id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE svc.service_type='Hotel'
              AND COALESCE(hp.listing_status, 'active')='active'
            ORDER BY s.state_name, c.city_name, hp.hotel_name
            """
        )
        guide_options = query_db(
            """
            SELECT
                svc.id AS service_id,
                svc.service_name,
                svc.description,
                svc.price,
                c.id AS city_id,
                c.city_name,
                s.id AS state_id,
                s.state_name
            FROM services svc
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE svc.service_type='Guides'
            ORDER BY s.state_name, c.city_name, svc.service_name
            """
        )
        transport_options = []
        payment_profit_rows = query_db(
            """
            SELECT
                t.id AS tour_id,
                COALESCE(SUM(p.organizer_earning), 0) AS organizer_profit,
                COALESCE(SUM(p.admin_commission), 0) AS admin_commission
            FROM payments p
            JOIN bookings b ON b.id=p.booking_id
            JOIN tours t ON t.id=b.tour_id
            WHERE p.paid=1 AND t.organizer_id=%s
            GROUP BY t.id
            """,
            (session["user_id"],),
        )
        external_profit_rows = query_db(
            """
            SELECT
                eb.tour_id,
                COALESCE(SUM(eb.organizer_earning), 0) AS organizer_profit,
                COALESCE(SUM(eb.admin_commission), 0) AS admin_commission
            FROM organizer_external_bookings eb
            WHERE eb.organizer_id=%s
            GROUP BY eb.tour_id
            """,
            (session["user_id"],),
        )
        profit_by_tour = {}
        for row in payment_profit_rows:
            tid = to_int(row.get("tour_id"), 0)
            if tid <= 0:
                continue
            profit_by_tour[tid] = {
                "organizer_profit": Decimal(str(row.get("organizer_profit") or 0)),
                "admin_commission": Decimal(str(row.get("admin_commission") or 0)),
            }
        for row in external_profit_rows:
            tid = to_int(row.get("tour_id"), 0)
            if tid <= 0:
                continue
            current = profit_by_tour.setdefault(
                tid,
                {"organizer_profit": Decimal("0.00"), "admin_commission": Decimal("0.00")},
            )
            current["organizer_profit"] += Decimal(str(row.get("organizer_profit") or 0))
            current["admin_commission"] += Decimal(str(row.get("admin_commission") or 0))

        total_profit = Decimal("0.00")
        total_admin_commission = Decimal("0.00")
        booking_stats_by_tour = {}
        for t in tours:
            tid = to_int(t.get("id"), 0)
            if tid <= 0:
                continue
            booking_stats_by_tour[tid] = {
                "internal_booking_count": 0,
                "internal_pax": 0,
                "paid_booking_count": 0,
                "paid_pax": 0,
                "external_booking_count": 0,
                "external_pax": 0,
            }

        for b in bookings:
            tid = to_int(b.get("tour_id"), 0)
            if tid not in booking_stats_by_tour:
                continue
            pax = max(0, to_int(b.get("pax_count"), 0))
            status = (b.get("status") or "").strip().lower()
            stats = booking_stats_by_tour[tid]
            stats["internal_booking_count"] += 1
            stats["internal_pax"] += pax
            if status == "paid":
                stats["paid_booking_count"] += 1
                stats["paid_pax"] += pax

        for eb in external_bookings:
            tid = to_int(eb.get("tour_id"), 0)
            if tid not in booking_stats_by_tour:
                continue
            pax = max(0, to_int(eb.get("pax_count"), 0))
            stats = booking_stats_by_tour[tid]
            stats["external_booking_count"] += 1
            stats["external_pax"] += pax

        tour_booking_summaries = []
        for t in tours:
            tid = to_int(t.get("id"), 0)
            booking_stats = booking_stats_by_tour.get(
                tid,
                {
                    "internal_booking_count": 0,
                    "internal_pax": 0,
                    "paid_booking_count": 0,
                    "paid_pax": 0,
                    "external_booking_count": 0,
                    "external_pax": 0,
                },
            )
            t.update(booking_stats)
            t["total_booking_count"] = booking_stats["internal_booking_count"] + booking_stats["external_booking_count"]
            t["total_pax_count"] = booking_stats["internal_pax"] + booking_stats["external_pax"]

            tour_profit = profit_by_tour.get(
                tid,
                {"organizer_profit": Decimal("0.00"), "admin_commission": Decimal("0.00")},
            )
            t["organizer_profit"] = tour_profit["organizer_profit"]
            t["admin_commission"] = tour_profit["admin_commission"]
            total_profit += tour_profit["organizer_profit"]
            total_admin_commission += tour_profit["admin_commission"]
            tour_booking_summaries.append(
                {
                    "tour_id": tid,
                    "title": t.get("title"),
                    "tour_status": t.get("tour_status"),
                    "internal_booking_count": booking_stats["internal_booking_count"],
                    "internal_pax": booking_stats["internal_pax"],
                    "paid_booking_count": booking_stats["paid_booking_count"],
                    "paid_pax": booking_stats["paid_pax"],
                    "external_booking_count": booking_stats["external_booking_count"],
                    "external_pax": booking_stats["external_pax"],
                    "total_booking_count": t["total_booking_count"],
                    "total_pax_count": t["total_pax_count"],
                    "max_group_size": to_int(t.get("max_group_size"), 0),
                }
            )

        charts, chart_error = _build_organizer_charts(tours, bookings)
        analytics = {
            "total_tours": len(tours),
            "total_bookings": len(bookings) + len(external_bookings),
            "paid_bookings": sum(1 for b in bookings if (b.get("status") or "").lower() == "paid"),
            "full_tours": sum(
                1
                for t in tours
                if (t.get("tour_status") or "").lower() == "full"
                or (
                    to_int(t.get("max_group_size"), 0)
                    and to_int(t.get("booked_pax"), 0) >= to_int(t.get("max_group_size"), 0)
                )
            ),
            "total_spots": len(spots),
            "partner_hotels": len(hotel_options),
            "partner_transport": sum(
                1
                for t in tours
                if to_int(t.get("linked_transport_count"), 0) > 0 or (t.get("transport_details") or "").strip()
            ),
            "external_bookings": len(external_bookings),
            "total_profit": f"{total_profit:.2f}",
            "total_admin_commission": f"{total_admin_commission:.2f}",
            "charts": charts,
            "chart_error": chart_error,
        }

        return render_template(
            "admin.html",
            tours=tours,
            bookings=bookings,
            states=states,
            cities=cities,
            spots=spots,
            spot_requests=spot_requests,
            hotel_options=hotel_options,
            guide_options=guide_options,
            transport_options=transport_options,
            external_bookings=external_bookings,
            tour_booking_summaries=tour_booking_summaries,
            analytics=analytics,
            panel_title="Organizer Panel",
        )

    @app.route("/organizer/api/resources")
    @login_required
    @role_required("organizer")
    def organizer_resources_api():
        city_id = to_int(request.args.get("city_id"), 0)
        tour_id = to_int(request.args.get("tour_id"), 0)

        if tour_id:
            owned_tour = query_db(
                "SELECT id FROM tours WHERE id=%s AND organizer_id=%s",
                (tour_id, session["user_id"]),
                one=True,
            )
            if not owned_tour:
                return jsonify({"error": "Tour not found for this organizer."}), 403

        clause = ""
        params = []
        if city_id:
            clause = " AND c.id = %s "
            params.append(city_id)

        spots = query_db(
            f"""
            SELECT ms.id, ms.spot_name, ms.image_url, ms.photo_source, ms.latitude, ms.longitude, c.city_name
            FROM master_spots ms
            JOIN cities c ON c.id=ms.city_id
            WHERE 1=1 {clause}
            ORDER BY ms.spot_name ASC
            """,
            tuple(params),
        )
        hotels = query_db(
            f"""
            SELECT s.id, hp.hotel_name, hp.star_rating, c.city_name
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            JOIN cities c ON c.id=s.city_id
            WHERE s.service_type='Hotel'
              AND COALESCE(hp.listing_status, 'active')='active'
              {clause}
            ORDER BY hp.hotel_name ASC
            """,
            tuple(params),
        )
        transports = []
        return jsonify({"spots": spots, "hotels": hotels, "transports": transports})
