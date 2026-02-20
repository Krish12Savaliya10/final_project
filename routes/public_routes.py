import json
import urllib.parse
import urllib.request
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.auth import login_required
from core.config import (
    GOOGLE_MAPS_API_KEY,
)
from core.db import execute_db, get_db, query_db
from core.helpers import (
    get_onboarding_document_requirements,
    is_allowed_document_filename,
    is_within_india_bounds,
    is_valid_email,
    is_valid_pincode,
    is_valid_phone,
    normalize_phone,
    normalize_provider_category,
    normalize_role,
    parse_date,
    save_upload,
    to_int,
)


SIGNUP_DOCUMENT_INPUTS = {
    "identity_proof_path": "identity_proof",
    "business_proof_path": "business_proof",
    "property_proof_path": "property_proof",
    "vehicle_proof_path": "vehicle_proof",
    "driver_verification_path": "driver_verification",
    "bank_proof_path": "bank_proof",
    "address_proof_path": "address_proof",
    "operational_photo_path": "operational_photo",
}
BOOKING_ID_PROOF_TYPES = [
    "Aadhaar Card",
    "Passport",
    "Driving License",
    "Voter ID",
    "PAN Card",
    "Government ID",
]


def _google_maps_geocoding_enabled():
    key = (GOOGLE_MAPS_API_KEY or "").strip()
    return bool(key and key != "YOUR_GOOGLE_MAPS_API_KEY")


def _extract_location_from_geocode(result):
    components = (result or {}).get("address_components") or []
    city = ""
    district = ""
    state = ""

    for comp in components:
        long_name = (comp.get("long_name") or "").strip()
        comp_types = set(comp.get("types") or [])
        if not long_name:
            continue
        if not city and (
            "locality" in comp_types
            or "postal_town" in comp_types
            or "administrative_area_level_3" in comp_types
            or "sublocality_level_1" in comp_types
            or "administrative_area_level_2" in comp_types
        ):
            city = long_name
        if not district and ("administrative_area_level_2" in comp_types or "administrative_area_level_3" in comp_types):
            district = long_name
        if not state and "administrative_area_level_1" in comp_types:
            state = long_name

    if not city:
        city = district
    if not district:
        district = city
    return {
        "city": (city or "").strip(),
        "district": (district or "").strip(),
        "state": (state or "").strip(),
    }


def _resolve_location_from_pincode(pincode):
    if not is_valid_pincode(pincode):
        return None, "Pincode must be a valid 6-digit number."
    if not _google_maps_geocoding_enabled():
        return None, "Google Maps API key is not configured for pincode lookup."

    params = urllib.parse.urlencode(
        {
            "address": pincode,
            "components": f"country:IN|postal_code:{pincode}",
            "region": "in",
            "language": "en",
            "key": GOOGLE_MAPS_API_KEY,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None, "Unable to fetch city details from Google Maps right now."

    status = (payload or {}).get("status")
    if status != "OK":
        api_message = (payload or {}).get("error_message")
        if api_message:
            return None, f"Google Maps error: {api_message}"
        return None, f"Could not resolve this pincode (status: {status or 'UNKNOWN'})."

    results = (payload or {}).get("results") or []
    if not results:
        return None, "No location result found for this pincode."

    location = _extract_location_from_geocode(results[0])
    if not location.get("city"):
        return None, "Google Maps did not return a valid city for this pincode."
    return location, ""


def _get_or_create_state_id(state_name):
    # apply normalization to correct common typos before touching the database
    from core.helpers import normalize_state_name

    name = normalize_state_name(state_name)
    if not name:
        return None

    row = query_db(
        "SELECT id FROM states WHERE LOWER(state_name)=LOWER(%s) LIMIT 1",
        (name,),
        one=True,
    )
    if row:
        return row["id"]

    try:
        return execute_db("INSERT INTO states(state_name) VALUES(%s)", (name,))
    except Exception:
        row = query_db(
            "SELECT id FROM states WHERE LOWER(state_name)=LOWER(%s) LIMIT 1",
            (name,),
            one=True,
        )
        return row["id"] if row else None


def _get_or_create_city_id(city_name, state_id):
    name = (city_name or "").strip()
    if not (name and state_id):
        return None

    row = query_db(
        """
        SELECT id
        FROM cities
        WHERE state_id=%s AND LOWER(city_name)=LOWER(%s)
        ORDER BY id ASC
        LIMIT 1
        """,
        (state_id, name),
        one=True,
    )
    if row:
        return row["id"]
    return execute_db(
        "INSERT INTO cities(state_id, city_name) VALUES(%s, %s)",
        (state_id, name),
    )


def _sync_user_location_from_pincode(user_id, pincode):
    location, error = _resolve_location_from_pincode(pincode)
    if error:
        return None, error

    city_name = (location.get("city") or "").strip()
    district_name = (location.get("district") or city_name).strip()
    state_name = (location.get("state") or "").strip()

    state_id = _get_or_create_state_id(state_name)
    city_id = _get_or_create_city_id(city_name, state_id) if state_id else None

    execute_db(
        """
        INSERT INTO user_profiles(user_id, city_id, city, district, pincode)
        VALUES(%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            city_id=VALUES(city_id),
            city=VALUES(city),
            district=VALUES(district),
            pincode=VALUES(pincode)
        """,
        (user_id, city_id, city_name or None, district_name or None, pincode),
    )
    return {
        "city_id": city_id,
        "city": city_name,
        "district": district_name,
        "state": state_name,
        "pincode": pincode,
    }, ""


def _login_session_and_redirect(user_row):
    session["user_id"] = user_row["id"]
    session["username"] = user_row["full_name"]
    session["role"] = user_row["role"]
    if user_row["role"] == "admin":
        return redirect(url_for("admin"))
    if user_row["role"] == "organizer":
        return redirect(url_for("organizer_dashboard"))
    if user_row["role"] == "hotel_provider":
        return redirect(url_for("provider_dashboard"))
    return redirect(url_for("home"))


def _spot_logo_meta(spot_name, spot_details=""):
    text = f"{spot_name} {spot_details}".lower()
    rules = [
        (
            (
                "temple",
                "mandir",
                "dargah",
                "mosque",
                "masjid",
                "church",
                "cathedral",
                "gurudwara",
                "monastery",
                "ashram",
                "jyotirlinga",
            ),
            "bi-bank2",
            "Spiritual Site",
        ),
        (("fort", "palace", "qila", "haveli", "mahal", "stambh", "tomb"), "bi-building", "Heritage Site"),
        (
            (
                "beach",
                "lake",
                "ghat",
                "river",
                "waterfall",
                "falls",
                "dam",
                "island",
                "backwater",
                "sangam",
                "cruise",
            ),
            "bi-water",
            "Waterfront",
        ),
        (("park", "garden", "sanctuary", "zoo", "safari", "wildlife", "forest"), "bi-tree", "Nature Spot"),
        (("museum", "science", "planetarium", "memorial", "observatory"), "bi-camera", "Culture Spot"),
        (("market", "mall", "street", "bazaar"), "bi-shop", "Market Area"),
        (("hill", "peak", "valley", "pass", "cave", "ropeway", "trek", "dunes", "mount"), "bi-compass", "Adventure"),
    ]
    for keywords, icon_class, label in rules:
        if any(keyword in text for keyword in keywords):
            return {"logo_icon_class": icon_class, "logo_label": label}
    return {"logo_icon_class": "bi-geo-alt-fill", "logo_label": "Tourist Spot"}


def register_routes(app):
    @app.route("/")
    def home():
        tours = query_db(
            """
            SELECT
                t.*,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Hotel'
                ) AS linked_hotels_count,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Transport'
                ) AS linked_transport_count,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Guides'
                ) AS linked_guides_count,
                NULL AS transport_vehicle_image
            FROM tours t
            ORDER BY t.id DESC
            LIMIT 3
            """
        )
        return render_template("home.html", tours=tours)

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/spots")
    def spots():
        search = request.args.get("search", "").strip()
        state_id = to_int(request.args.get("state_id"), 0)
        city_id = to_int(request.args.get("city_id"), 0)

        where = []
        params = []
        if search:
            like = f"%{search}%"
            where.append("(ms.spot_name LIKE %s OR c.city_name LIKE %s OR s.state_name LIKE %s)")
            params.extend([like, like, like])
        if state_id:
            where.append("s.id=%s")
            params.append(state_id)
        if city_id:
            where.append("c.id=%s")
            params.append(city_id)

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        spots_rows = query_db(
            f"""
            SELECT
                ms.id AS spot_id,
                ms.spot_name,
                ms.image_url,
                ms.photo_source,
                ms.spot_details,
                ms.latitude,
                ms.longitude,
                c.id AS city_id,
                c.city_name,
                s.id AS state_id,
                s.state_name
            FROM master_spots ms
            JOIN cities c ON c.id=ms.city_id
            JOIN states s ON s.id=c.state_id
            {where_clause}
            ORDER BY s.state_name, c.city_name, ms.spot_name
            LIMIT 1000
            """,
            tuple(params),
        )
        for row in spots_rows:
            row.update(_spot_logo_meta(row.get("spot_name", ""), row.get("spot_details", "")))

        map_spots = []
        for s in spots_rows:
            try:
                lat = float(s.get("latitude"))
                lng = float(s.get("longitude"))
            except (TypeError, ValueError):
                continue
            if is_within_india_bounds(lat, lng):
                map_spots.append(s)
        states = query_db("SELECT id, state_name FROM states ORDER BY state_name")
        cities = query_db(
            """
            SELECT c.id, c.city_name, c.state_id, s.state_name
            FROM cities c
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name
            """
        )
        return render_template(
            "spots.html",
            spots=spots_rows,
            map_spots=map_spots,
            states=states,
            cities=cities,
            search=search,
            state_id=state_id,
            city_id=city_id,
        )

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/india-map")
    def india_map():
        return render_template("india_map.html")

    @app.route("/tour")
    def tour():
        search = request.args.get("search", "").strip()
        state_id = to_int(request.args.get("state_id"), 0)
        city_id = to_int(request.args.get("city_id"), 0)
        where = []
        params = []

        if search:
            where.append(
                "(t.title LIKE %s OR t.start_point LIKE %s OR t.end_point LIKE %s OR t.description LIKE %s)"
            )
            like_term = f"%{search}%"
            params.extend([like_term, like_term, like_term, like_term])
        if state_id:
            where.append("(t.pickup_state_id=%s OR t.drop_state_id=%s)")
            params.extend([state_id, state_id])
        if city_id:
            where.append("(t.pickup_city_id=%s OR t.drop_city_id=%s)")
            params.extend([city_id, city_id])

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        tours = query_db(
            f"""
            SELECT
                t.*,
                ps.state_name AS pickup_state_name,
                pc.city_name AS pickup_city_name,
                ds.state_name AS drop_state_name,
                dc.city_name AS drop_city_name,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Hotel'
                ) AS linked_hotels_count,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Transport'
                ) AS linked_transport_count,
                (
                    SELECT COUNT(*)
                    FROM tour_service_links tsl
                    WHERE tsl.tour_id=t.id
                      AND tsl.service_kind='Guides'
                ) AS linked_guides_count,
                NULL AS transport_vehicle_image
            FROM tours t
            LEFT JOIN states ps ON ps.id=t.pickup_state_id
            LEFT JOIN cities pc ON pc.id=t.pickup_city_id
            LEFT JOIN states ds ON ds.id=t.drop_state_id
            LEFT JOIN cities dc ON dc.id=t.drop_city_id
            {where_clause}
            ORDER BY t.id DESC
            """,
            tuple(params),
        )

        states = query_db("SELECT id, state_name FROM states ORDER BY state_name")
        cities = query_db(
            """
            SELECT c.id, c.city_name, c.state_id, s.state_name
            FROM cities c
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name
            """
        )
        return render_template(
            "tour.html",
            tours=tours,
            search=search,
            states=states,
            cities=cities,
            state_id=state_id,
            city_id=city_id,
        )

    @app.route("/hotels")
    def hotels():
        search = request.args.get("search", "").strip()
        params = []
        where = "WHERE COALESCE(hp.listing_status, 'active')='active'"
        if search:
            where += """
              AND (
                   hp.hotel_name LIKE %s
                OR hp.locality LIKE %s
                OR c.city_name LIKE %s
                OR s.state_name LIKE %s
              )
            """
            term = f"%{search}%"
            params = [term, term, term, term]

        hotel_rows = query_db(
            f"""
            SELECT
                svc.id AS service_id,
                hp.hotel_name,
                hp.star_rating,
                hp.locality,
                hp.address_line1,
                c.city_name,
                s.state_name,
                COALESCE(hi.image_url, 'demo.jpg') AS cover_image,
                COALESCE(MIN(rt.base_price), svc.price, 0) AS starting_price,
                COALESCE(SUM(rt.available_rooms), 0) AS total_available_rooms
            FROM services svc
            JOIN hotel_profiles hp ON hp.service_id=svc.id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            LEFT JOIN hotel_images hi ON hi.service_id=svc.id AND hi.is_cover=1
            LEFT JOIN hotel_room_types rt ON rt.service_id=svc.id
            {where}
            GROUP BY
                svc.id, hp.hotel_name, hp.star_rating, hp.locality, hp.address_line1,
                c.city_name, s.state_name, hi.image_url, svc.price
            ORDER BY hp.star_rating DESC, svc.id DESC
            """,
            tuple(params),
        )
        return render_template("hotels.html", hotels=hotel_rows, search=search)

    @app.route("/transports")
    def transports():
        search = request.args.get("search", "").strip()
        return render_template("transports.html", transports=[], search=search)

    @app.route("/transports/<int:service_id>")
    def transport_detail(service_id):
        abort(404)

    @app.route("/hotels/<int:service_id>", methods=["GET", "POST"])
    def hotel_detail(service_id):
        hotel = query_db(
            """
            SELECT
                svc.id AS service_id,
                svc.provider_id,
                svc.service_name,
                svc.city_id,
                hp.*, c.city_name, s.state_name
            FROM services svc
            JOIN hotel_profiles hp ON hp.service_id=svc.id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE svc.id=%s
            """,
            (service_id,),
            one=True,
        )
        if not hotel:
            abort(404)

        images = query_db(
            """
            SELECT image_url, image_title, is_cover
            FROM hotel_images
            WHERE service_id=%s
            ORDER BY is_cover DESC, sort_order ASC, id ASC
            """,
            (service_id,),
        )
        room_types = query_db(
            """
            SELECT *
            FROM hotel_room_types
            WHERE service_id=%s
            ORDER BY base_price ASC, id DESC
            """,
            (service_id,),
        )
        amenities = query_db(
            """
            SELECT am.amenity_name, am.amenity_icon
            FROM hotel_amenities ha
            JOIN amenity_master am ON am.id=ha.amenity_id
            WHERE ha.service_id=%s
            ORDER BY am.amenity_name ASC
            """,
            (service_id,),
        )

        if request.method == "POST":
            if not session.get("user_id"):
                flash("Please login to book this hotel.")
                return redirect(url_for("login"))

            room_type_id = to_int(request.form.get("room_type_id"), 0)
            rooms_booked = max(1, to_int(request.form.get("rooms_booked"), 1))
            guests_count = max(1, to_int(request.form.get("guests_count"), 1))
            check_in_date = request.form.get("check_in_date", "").strip()
            check_out_date = request.form.get("check_out_date", "").strip()
            id_proof_type = (request.form.get("id_proof_type") or "").strip()
            id_proof_number = (request.form.get("id_proof_number") or "").strip()

            if not room_type_id or not check_in_date or not check_out_date:
                flash("Please fill booking details correctly.")
                return redirect(url_for("hotel_detail", service_id=service_id))
            if not id_proof_type or id_proof_type not in BOOKING_ID_PROOF_TYPES:
                flash("Select a valid ID proof type for hotel booking.")
                return redirect(url_for("hotel_detail", service_id=service_id))
            if not id_proof_number or len(id_proof_number) > 120:
                flash("Valid ID proof number is required for hotel booking.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            check_in = parse_date(check_in_date)
            check_out = parse_date(check_out_date)
            if not check_in or not check_out:
                flash("Invalid check-in/check-out date.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            nights = (check_out - check_in).days
            if nights <= 0:
                flash("Check-out date must be after check-in date.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            room_row = query_db(
                """
                SELECT id, room_type_name, available_rooms, base_price
                FROM hotel_room_types
                WHERE id=%s AND service_id=%s
                """,
                (room_type_id, service_id),
                one=True,
            )
            if not room_row:
                flash("Selected room type is invalid.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            total_amount = Decimal(str(room_row["base_price"])) * Decimal(rooms_booked) * Decimal(nights)

            db = get_db()
            cur = db.cursor(dictionary=True)
            cur.execute(
                """
                SELECT available_rooms
                FROM hotel_room_types
                WHERE id=%s AND service_id=%s
                FOR UPDATE
                """,
                (room_type_id, service_id),
            )
            locked_room = cur.fetchone()
            if not locked_room:
                db.rollback()
                cur.close()
                db.close()
                flash("Selected room type is invalid.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            base_available_rooms = max(0, to_int(locked_room.get("available_rooms"), 0))
            cur.execute(
                """
                SELECT COALESCE(SUM(rooms_booked), 0) AS overlapping_rooms
                FROM hotel_bookings
                WHERE room_type_id=%s
                  AND status='confirmed'
                  AND check_in_date < %s
                  AND check_out_date > %s
                """,
                (room_type_id, check_out, check_in),
            )
            overlap_row = cur.fetchone() or {}
            overlapping_rooms = max(0, to_int(overlap_row.get("overlapping_rooms"), 0))
            currently_available = base_available_rooms - overlapping_rooms
            if currently_available < rooms_booked:
                db.rollback()
                cur.close()
                db.close()
                flash("Requested rooms are not available for selected dates.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            cur.execute(
                """
                INSERT INTO hotel_bookings(
                    user_id, service_id, room_type_id, id_proof_type, id_proof_number,
                    check_in_date, check_out_date, rooms_booked, guests_count, nights, total_amount, status
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed')
                """,
                (
                    session["user_id"],
                    service_id,
                    room_type_id,
                    id_proof_type,
                    id_proof_number,
                    check_in_date,
                    check_out_date,
                    rooms_booked,
                    guests_count,
                    nights,
                    total_amount,
                ),
            )
            db.commit()
            cur.close()
            db.close()

            flash(f"Hotel booked successfully for {nights} night(s). Total: Rs {total_amount}")
            return redirect(url_for("hotel_detail", service_id=service_id))

        return render_template(
            "hotel_detail.html",
            hotel=hotel,
            images=images,
            room_types=room_types,
            amenities=amenities,
            id_proof_types=BOOKING_ID_PROOF_TYPES,
        )

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        errors = {}
        form_values = {
            "full_name": request.form.get("full_name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "phone": normalize_phone(request.form.get("phone", "").strip()),
            "role": request.form.get("role", "traveler"),
            "provider_category": normalize_provider_category(request.form.get("provider_category", "")),
            "business_name": request.form.get("business_name", "").strip(),
        }

        if request.method == "POST":
            full_name = form_values["full_name"]
            email = form_values["email"]
            phone = form_values["phone"]
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            selected_role = form_values["role"]
            role = normalize_role(selected_role)
            if role == "admin":
                errors["role"] = "Admin account creation is disabled."
                role = "customer"
                selected_role = "traveler"
                form_values["role"] = "traveler"
            if role == "hotel_provider":
                selected_role = "hotel_provider"
            provider_category = form_values["provider_category"]
            if role == "hotel_provider":
                provider_category = "Hotel"

            form_values["provider_category"] = provider_category
            business_name = form_values["business_name"]
            document_files = {
                db_field: request.files.get(input_field)
                for db_field, input_field in SIGNUP_DOCUMENT_INPUTS.items()
            }
            required_docs = get_onboarding_document_requirements(role, provider_category)
            required_doc_fields = {item["field"] for item in required_docs}

            if not full_name:
                errors["full_name"] = "Full name is required."
            if len(full_name) > 100:
                errors["full_name"] = "Full name is too long."
            if not is_valid_email(email):
                errors["email"] = "Enter a valid email address."
            if not is_valid_phone(phone):
                errors["phone"] = "Enter a valid mobile number."
            if len(password) < 6:
                errors["password"] = "Password must be at least 6 characters."
            if password != confirm:
                errors["confirm"] = "Passwords do not match."

            if role in {"organizer", "hotel_provider"} and not business_name:
                errors["business_name"] = "Business name is required for this role."
            if business_name and len(business_name) > 120:
                errors["business_name"] = "Business name is too long."

            for doc in required_docs:
                field = doc["field"]
                file_input = SIGNUP_DOCUMENT_INPUTS[field]
                file_obj = document_files.get(field)
                if not file_obj or not file_obj.filename:
                    errors[file_input] = f"{doc['label']} is required for selected role."
                    continue
                if not is_allowed_document_filename(file_obj.filename):
                    errors[file_input] = "Allowed file types: pdf, png, jpg, jpeg, webp."

            for field, file_obj in document_files.items():
                if field in required_doc_fields:
                    continue
                if file_obj and file_obj.filename and not is_allowed_document_filename(file_obj.filename):
                    file_input = SIGNUP_DOCUMENT_INPUTS[field]
                    errors[file_input] = "Allowed file types: pdf, png, jpg, jpeg, webp."

            existing_user = query_db(
                "SELECT id FROM users WHERE email=%s OR phone=%s",
                (email, phone),
                one=True,
            )
            if existing_user:
                errors["email"] = "Email or phone is already registered."

            if errors:
                return render_template(
                    "signup.html",
                    errors=errors,
                    form_values=form_values,
                )

            uploaded_doc_names = {}
            for db_field, file_input in SIGNUP_DOCUMENT_INPUTS.items():
                file_obj = document_files.get(db_field)
                if file_obj and file_obj.filename:
                    uploaded_doc_names[db_field] = save_upload(file_obj, app.config["DOC_UPLOAD_FOLDER"])
                else:
                    uploaded_doc_names[db_field] = None

            role_is_customer = role == "customer"
            status = "approved" if role_is_customer else "pending"
            verified_badge = 1 if role_is_customer else 0
            kyc_completed = 1 if role_is_customer else int(
                all(uploaded_doc_names.get(field) for field in required_doc_fields)
            )
            kyc_stage = "verified" if role_is_customer else "submitted_for_admin_approval"
            hashed = generate_password_hash(password)
            identity_doc_path = uploaded_doc_names.get("identity_proof_path")

            user_id = execute_db(
                """
                INSERT INTO users(full_name,email,phone,password,role,status,document_path)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                """,
                (full_name, email, phone, hashed, role, status, identity_doc_path),
            )

            execute_db(
                """
                INSERT INTO user_profiles(
                    user_id, requested_role, business_name, provider_category,
                    kyc_completed, kyc_stage, verification_badge,
                    identity_proof_path, business_proof_path, property_proof_path,
                    vehicle_proof_path, driver_verification_path, bank_proof_path,
                    address_proof_path, operational_photo_path
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    requested_role=VALUES(requested_role),
                    business_name=VALUES(business_name),
                    provider_category=VALUES(provider_category),
                    kyc_completed=VALUES(kyc_completed),
                    kyc_stage=VALUES(kyc_stage),
                    verification_badge=VALUES(verification_badge),
                    identity_proof_path=VALUES(identity_proof_path),
                    business_proof_path=VALUES(business_proof_path),
                    property_proof_path=VALUES(property_proof_path),
                    vehicle_proof_path=VALUES(vehicle_proof_path),
                    driver_verification_path=VALUES(driver_verification_path),
                    bank_proof_path=VALUES(bank_proof_path),
                    address_proof_path=VALUES(address_proof_path),
                    operational_photo_path=VALUES(operational_photo_path)
                """,
                (
                    user_id,
                    selected_role,
                    business_name or None,
                    provider_category or None,
                    kyc_completed,
                    kyc_stage,
                    verified_badge,
                    uploaded_doc_names.get("identity_proof_path"),
                    uploaded_doc_names.get("business_proof_path"),
                    uploaded_doc_names.get("property_proof_path"),
                    uploaded_doc_names.get("vehicle_proof_path"),
                    uploaded_doc_names.get("driver_verification_path"),
                    uploaded_doc_names.get("bank_proof_path"),
                    uploaded_doc_names.get("address_proof_path"),
                    uploaded_doc_names.get("operational_photo_path"),
                ),
            )

            if status == "pending":
                flash("Signup submitted with KYC documents. Admin approval is required before login.")
            else:
                flash("Account created successfully. You can login now.")
            return redirect(url_for("login"))

        return render_template(
            "signup.html",
            errors={},
            form_values=form_values,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            login_input = request.form.get("login", "").strip()
            password = request.form.get("password", "")
            if not login_input or not password:
                flash("Login and password are required.")
                return redirect(url_for("login"))

            user = query_db(
                "SELECT * FROM users WHERE email=%s OR phone=%s",
                (login_input, login_input),
                one=True,
            )

            if not user:
                flash("User not found")
                return redirect(url_for("login"))

            if not check_password_hash(user["password"], password):
                flash("Wrong password")
                return redirect(url_for("login"))

            profile_row = query_db(
                """
                SELECT kyc_stage, kyc_completed, admin_note
                FROM user_profiles
                WHERE user_id=%s
                """,
                (user["id"],),
                one=True,
            ) or {}

            if user["status"] != "approved":
                stage = profile_row.get("kyc_stage") or "pending"
                admin_note = profile_row.get("admin_note")
                if stage == "rejected":
                    message = "Your verification request was rejected."
                    if admin_note:
                        message += f" Note: {admin_note}"
                    flash(message)
                elif not to_int(profile_row.get("kyc_completed"), 0):
                    flash("KYC documents are incomplete. Please resubmit your signup form.")
                else:
                    flash("Your account is pending admin approval.")
                return redirect(url_for("login"))

            return _login_session_and_redirect(user)

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user = query_db(
            """
            SELECT id, full_name, email, phone, role
            FROM users
            WHERE id=%s
            """,
            (session["user_id"],),
            one=True,
        )
        if not user:
            abort(404)

        profile_row = query_db(
            """
            SELECT
                user_id,
                requested_role,
                business_name,
                provider_category,
                kyc_completed,
                kyc_stage,
                verification_badge,
                admin_note,
                identity_proof_path,
                business_proof_path,
                property_proof_path,
                vehicle_proof_path,
                driver_verification_path,
                bank_proof_path,
                address_proof_path,
                operational_photo_path,
                bio,
                gender,
                date_of_birth,
                emergency_contact,
                address_line,
                city_id,
                city,
                district,
                pincode
            FROM user_profiles
            WHERE user_id=%s
            """,
            (session["user_id"],),
            one=True,
        ) or {}

        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            phone = normalize_phone(request.form.get("phone", "").strip())
            requested_role = normalize_role(request.form.get("requested_role") or user.get("role") or "customer")
            if (user.get("role") or "").strip().lower() == "admin":
                # Keep existing admin accounts stable from profile edits.
                requested_role = "admin"
            elif requested_role == "admin":
                flash("Admin role request is disabled.")
                return redirect(url_for("profile"))
            business_name = (request.form.get("business_name") or "").strip()
            provider_category = normalize_provider_category(request.form.get("provider_category", ""))
            if requested_role == "hotel_provider":
                provider_category = "Hotel"
            bio = (request.form.get("bio") or "").strip()
            gender = (request.form.get("gender") or "").strip()
            date_of_birth = (request.form.get("date_of_birth") or "").strip()
            emergency_contact = normalize_phone(request.form.get("emergency_contact", "").strip())
            address_line = (request.form.get("address_line") or "").strip()
            city_id = to_int(request.form.get("city_id"), 0) or None
            city = (request.form.get("city") or "").strip()
            district = (request.form.get("district") or "").strip()
            pincode = (request.form.get("pincode") or "").strip()

            if not full_name or len(full_name) > 100:
                flash("Valid full name is required (max 100 characters).")
                return redirect(url_for("profile"))
            if not is_valid_phone(phone):
                flash("Phone must be a valid 10-digit mobile number.")
                return redirect(url_for("profile"))
            if business_name and len(business_name) > 120:
                flash("Business name is too long.")
                return redirect(url_for("profile"))
            if provider_category and len(provider_category) > 60:
                flash("Provider category is too long.")
                return redirect(url_for("profile"))
            if bio and len(bio) > 255:
                flash("Bio should be 255 characters or less.")
                return redirect(url_for("profile"))
            if gender and gender not in {"Male", "Female", "Other", "Prefer not to say"}:
                flash("Invalid gender selected.")
                return redirect(url_for("profile"))
            dob_value = None
            if date_of_birth:
                dob_value = parse_date(date_of_birth)
                if not dob_value:
                    flash("Invalid date of birth.")
                    return redirect(url_for("profile"))
            if emergency_contact and not is_valid_phone(emergency_contact):
                flash("Emergency contact must be a valid 10-digit mobile number.")
                return redirect(url_for("profile"))
            if pincode and not is_valid_pincode(pincode):
                flash("Pincode must be a valid 6-digit number.")
                return redirect(url_for("profile"))

            if pincode:
                location_data, location_error = _sync_user_location_from_pincode(session["user_id"], pincode)
                if location_error:
                    flash(location_error)
                    return redirect(url_for("profile"))
                city = location_data.get("city") or city
                district = location_data.get("district") or district
                city_id = location_data.get("city_id") or city_id

            if city and len(city) > 120:
                flash("City name is too long.")
                return redirect(url_for("profile"))
            if district and len(district) > 120:
                flash("District name is too long.")
                return redirect(url_for("profile"))
            if city_id and not query_db("SELECT id FROM cities WHERE id=%s", (city_id,), one=True):
                flash("Invalid city selected.")
                return redirect(url_for("profile"))

            if city_id and not city:
                city_row = query_db("SELECT city_name FROM cities WHERE id=%s", (city_id,), one=True)
                if city_row:
                    city = city_row["city_name"]
            if city and not district:
                district = city

            execute_db(
                """
                UPDATE users
                SET full_name=%s, phone=%s
                WHERE id=%s
                """,
                (full_name, phone, session["user_id"]),
            )
            execute_db(
                """
                INSERT INTO user_profiles(
                    user_id, requested_role, business_name, provider_category,
                    bio, gender, date_of_birth, emergency_contact, address_line, city_id,
                    city, district, pincode
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    requested_role=VALUES(requested_role),
                    business_name=VALUES(business_name),
                    provider_category=VALUES(provider_category),
                    bio=VALUES(bio),
                    gender=VALUES(gender),
                    date_of_birth=VALUES(date_of_birth),
                    emergency_contact=VALUES(emergency_contact),
                    address_line=VALUES(address_line),
                    city_id=VALUES(city_id),
                    city=VALUES(city),
                    district=VALUES(district),
                    pincode=VALUES(pincode)
                """,
                (
                    session["user_id"],
                    requested_role,
                    business_name or None,
                    provider_category or None,
                    bio or None,
                    gender or None,
                    dob_value,
                    emergency_contact or None,
                    address_line or None,
                    city_id,
                    city or None,
                    district or None,
                    pincode or None,
                ),
            )
            session["username"] = full_name
            flash("Profile updated successfully.")
            return redirect(url_for("profile"))

        states = query_db(
            """
            SELECT id, state_name
            FROM states
            ORDER BY state_name
            """
        )
        cities = query_db(
            """
            SELECT c.id, c.city_name, c.state_id, s.state_name
            FROM cities c
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name
            """
        )

        return render_template(
            "profile.html",
            user=user,
            profile=profile_row,
            states=states,
            cities=cities,
            doc_labels={
                "identity_proof_path": "Identity KYC",
                "business_proof_path": "Business Proof",
                "property_proof_path": "Property Proof",
                "vehicle_proof_path": "Vehicle Proof",
                "driver_verification_path": "Driver Verification",
                "bank_proof_path": "Bank Proof",
                "address_proof_path": "Address Proof",
                "operational_photo_path": "Operational Photos",
            },
        )

    @app.route("/feedback", methods=["GET", "POST"])
    @login_required
    def feedback():
        if request.method == "POST":
            action = (request.form.get("action") or "").strip().lower()
            if action == "submit_review":
                target_type = (request.form.get("target_type") or "platform").strip().lower()
                if target_type not in {"platform", "tour", "hotel"}:
                    flash("Invalid review target.")
                    return redirect(url_for("feedback"))

                target_id = to_int(request.form.get("target_id"), 0) or None
                rating = to_int(request.form.get("rating"), 0)
                review_text = (request.form.get("review_text") or "").strip()

                if rating < 1 or rating > 5:
                    flash("Rating must be between 1 and 5.")
                    return redirect(url_for("feedback"))
                if len(review_text) < 5 or len(review_text) > 500:
                    flash("Review must be between 5 and 500 characters.")
                    return redirect(url_for("feedback"))
                if target_type != "platform" and not target_id:
                    flash("Please select a valid target.")
                    return redirect(url_for("feedback"))
                if target_type == "tour":
                    target_ok = query_db(
                        """
                        SELECT 1
                        FROM bookings
                        WHERE user_id=%s AND tour_id=%s
                        LIMIT 1
                        """,
                        (session["user_id"], target_id),
                        one=True,
                    )
                    if not target_ok:
                        flash("You can review only your booked tours.")
                        return redirect(url_for("feedback"))
                elif target_type == "hotel":
                    target_ok = query_db(
                        """
                        SELECT 1
                        FROM hotel_bookings
                        WHERE user_id=%s AND service_id=%s
                        LIMIT 1
                        """,
                        (session["user_id"], target_id),
                        one=True,
                    )
                    if not target_ok:
                        flash("You can review only your booked hotels.")
                        return redirect(url_for("feedback"))

                execute_db(
                    """
                    INSERT INTO platform_reviews(
                        user_id, user_role, target_type, target_id, rating, review_text
                    )
                    VALUES(%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        session["user_id"],
                        session.get("role"),
                        target_type,
                        target_id,
                        rating,
                        review_text,
                    ),
                )
                flash("Thank you. Your review was submitted.")
                return redirect(url_for("feedback"))

            if action == "submit_issue":
                subject = (request.form.get("subject") or "").strip()
                issue_text = (request.form.get("issue_text") or "").strip()
                if len(subject) < 3 or len(subject) > 160:
                    flash("Issue subject must be between 3 and 160 characters.")
                    return redirect(url_for("feedback"))
                if len(issue_text) < 10:
                    flash("Issue description is too short.")
                    return redirect(url_for("feedback"))

                execute_db(
                    """
                    INSERT INTO support_issues(user_id, user_role, subject, issue_text, status)
                    VALUES(%s,%s,%s,%s,'open')
                    """,
                    (
                        session["user_id"],
                        session.get("role"),
                        subject,
                        issue_text,
                    ),
                )
                flash("Issue submitted successfully. Admin will review it.")
                return redirect(url_for("feedback"))

            flash("Invalid feedback action.")
            return redirect(url_for("feedback"))

        tour_targets = query_db(
            """
            SELECT DISTINCT t.id, t.title
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            WHERE b.user_id=%s
            ORDER BY t.title
            """,
            (session["user_id"],),
        )
        hotel_targets = query_db(
            """
            SELECT DISTINCT s.id, hp.hotel_name AS title
            FROM hotel_bookings hb
            JOIN services s ON s.id=hb.service_id
            JOIN hotel_profiles hp ON hp.service_id=s.id
            WHERE hb.user_id=%s
            ORDER BY hp.hotel_name
            """,
            (session["user_id"],),
        )
        my_reviews = query_db(
            """
            SELECT id, target_type, rating, review_text, created_at
            FROM platform_reviews
            WHERE user_id=%s
            ORDER BY id DESC
            LIMIT 20
            """,
            (session["user_id"],),
        )
        my_issues = query_db(
            """
            SELECT id, subject, issue_text, status, admin_note, created_at
            FROM support_issues
            WHERE user_id=%s
            ORDER BY id DESC
            LIMIT 20
            """,
            (session["user_id"],),
        )

        return render_template(
            "feedback.html",
            tour_targets=tour_targets,
            hotel_targets=hotel_targets,
            my_reviews=my_reviews,
            my_issues=my_issues,
        )
