from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.db import execute_db, get_db, query_db
from core.helpers import (
    is_allowed_document_filename,
    is_allowed_image_filename,
    is_non_negative_amount,
    is_within_india_bounds,
    is_valid_email,
    is_valid_latitude,
    is_valid_longitude,
    is_valid_phone,
    is_valid_pincode,
    save_upload,
    to_int,
    update_room_inventory_for_provider,
)


def register_routes(app):
    def _load_hotel_form_options():
        amenities = query_db("SELECT * FROM amenity_master ORDER BY amenity_name ASC")
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
        return amenities, states, cities

    def _create_hotel_listing(redirect_endpoint):
        hotel_name = request.form.get("hotel_name", "").strip()
        brand_name = request.form.get("brand_name", "").strip()
        star_rating = to_int(request.form.get("star_rating"), 0)
        city_id = to_int(request.form.get("city_id"), 0)
        address_line1 = request.form.get("address_line1", "").strip()
        address_line2 = request.form.get("address_line2", "").strip()
        locality = request.form.get("locality", "").strip()
        landmark = request.form.get("landmark", "").strip()
        pincode = request.form.get("pincode", "").strip()
        latitude = (request.form.get("latitude") or "").strip() or None
        longitude = (request.form.get("longitude") or "").strip() or None
        check_in_time = request.form.get("check_in_time") or None
        check_out_time = request.form.get("check_out_time") or None
        hotel_description = request.form.get("hotel_description", "").strip()
        house_rules = request.form.get("house_rules", "").strip()
        terms_conditions = request.form.get("terms_conditions", "").strip()
        listing_status = (request.form.get("listing_status") or "active").strip().lower()
        owner_name = request.form.get("owner_name", "").strip()
        hotel_contact_phone = request.form.get("hotel_contact_phone", "").strip()
        hotel_contact_email = request.form.get("hotel_contact_email", "").strip().lower()
        gst_number = request.form.get("gst_number", "").strip().upper()
        trade_license_number = request.form.get("trade_license_number", "").strip()
        registration_doc = request.files.get("registration_doc")
        couple_friendly = 1 if request.form.get("couple_friendly") else 0
        pets_allowed = 1 if request.form.get("pets_allowed") else 0
        parking_available = 1 if request.form.get("parking_available") else 0
        breakfast_available = 1 if request.form.get("breakfast_available") else 0
        amenity_ids = request.form.getlist("amenity_ids")
        base_price = request.form.get("base_price", "0").strip() or "0"

        if not (hotel_name and city_id and address_line1):
            flash("Hotel name, city and address are required.")
            return redirect(url_for(redirect_endpoint))
        if len(hotel_name) > 120:
            flash("Hotel name is too long.")
            return redirect(url_for(redirect_endpoint))
        if len(brand_name) > 120:
            flash("Brand name is too long.")
            return redirect(url_for(redirect_endpoint))
        if len(address_line1) > 255 or len(address_line2) > 255:
            flash("Address lines are too long.")
            return redirect(url_for(redirect_endpoint))
        if len(locality) > 120 or len(landmark) > 120:
            flash("Locality or landmark is too long.")
            return redirect(url_for(redirect_endpoint))
        if not owner_name or len(owner_name) > 120:
            flash("Owner name is required (max 120 chars).")
            return redirect(url_for(redirect_endpoint))
        if not hotel_contact_phone or not is_valid_phone(hotel_contact_phone):
            flash("Valid hotel contact phone is required (10 digits).")
            return redirect(url_for(redirect_endpoint))
        if hotel_contact_email and (len(hotel_contact_email) > 120 or not is_valid_email(hotel_contact_email)):
            flash("Hotel contact email is invalid.")
            return redirect(url_for(redirect_endpoint))
        if len(gst_number) > 30:
            flash("GST number is too long.")
            return redirect(url_for(redirect_endpoint))
        if len(trade_license_number) > 60:
            flash("Trade license number is too long.")
            return redirect(url_for(redirect_endpoint))
        if len(hotel_description) > 5000 or len(house_rules) > 4000 or len(terms_conditions) > 4000:
            flash("Description, rules, or terms are too long.")
            return redirect(url_for(redirect_endpoint))
        if listing_status not in {"active", "inactive", "maintenance"}:
            flash("Invalid hotel status selected.")
            return redirect(url_for(redirect_endpoint))
        if not query_db("SELECT id FROM cities WHERE id=%s", (city_id,), one=True):
            flash("Invalid city selected.")
            return redirect(url_for(redirect_endpoint))
        if star_rating and (star_rating < 1 or star_rating > 5):
            flash("Star rating must be between 1 and 5.")
            return redirect(url_for(redirect_endpoint))
        if pincode and not is_valid_pincode(pincode):
            flash("Pincode must be 6 digits.")
            return redirect(url_for(redirect_endpoint))
        has_lat = bool(latitude)
        has_lng = bool(longitude)
        if has_lat != has_lng:
            flash("Enter both latitude and longitude together, or leave both blank.")
            return redirect(url_for(redirect_endpoint))
        if latitude and not is_valid_latitude(latitude):
            flash("Latitude must be between -90 and 90.")
            return redirect(url_for(redirect_endpoint))
        if longitude and not is_valid_longitude(longitude):
            flash("Longitude must be between -180 and 180.")
            return redirect(url_for(redirect_endpoint))
        if has_lat and has_lng and not is_within_india_bounds(latitude, longitude):
            flash("Hotel coordinates must be inside India.")
            return redirect(url_for(redirect_endpoint))
        if not is_non_negative_amount(base_price):
            flash("Base price must be a non-negative number.")
            return redirect(url_for(redirect_endpoint))

        registration_doc_path = None
        if registration_doc and registration_doc.filename:
            if not is_allowed_document_filename(registration_doc.filename):
                flash("Registration document must be PDF, PNG, JPG, JPEG, or WEBP.")
                return redirect(url_for(redirect_endpoint))
            registration_doc_path = save_upload(registration_doc, app.config["DOC_UPLOAD_FOLDER"])
            if not registration_doc_path:
                flash("Unable to upload registration document.")
                return redirect(url_for(redirect_endpoint))

        parsed_amenity_ids = []
        for value in amenity_ids:
            amenity_id = to_int(value, 0)
            if amenity_id > 0:
                parsed_amenity_ids.append(amenity_id)
        parsed_amenity_ids = sorted(set(parsed_amenity_ids))
        valid_amenity_ids = []
        if parsed_amenity_ids:
            placeholders = ", ".join(["%s"] * len(parsed_amenity_ids))
            rows = query_db(
                f"SELECT id FROM amenity_master WHERE id IN ({placeholders})",
                tuple(parsed_amenity_ids),
            )
            valid_amenity_ids = [to_int(row.get("id"), 0) for row in rows if to_int(row.get("id"), 0) > 0]

        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO services(provider_id, service_type, service_name, price, description, city_id)
            VALUES(%s,'Hotel',%s,%s,%s,%s)
            """,
            (session["user_id"], hotel_name, base_price, hotel_description, city_id),
        )
        service_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO hotel_profiles(
                service_id, hotel_name, brand_name, star_rating, address_line1, address_line2,
                locality, landmark, pincode, latitude, longitude, check_in_time, check_out_time,
                hotel_description, house_rules, couple_friendly, pets_allowed, parking_available,
                breakfast_available, listing_status, terms_conditions, owner_name, hotel_contact_phone,
                hotel_contact_email, gst_number, trade_license_number, registration_doc_path
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                service_id,
                hotel_name,
                brand_name or None,
                star_rating,
                address_line1,
                address_line2 or None,
                locality or None,
                landmark or None,
                pincode or None,
                latitude,
                longitude,
                check_in_time,
                check_out_time,
                hotel_description or None,
                house_rules or None,
                couple_friendly,
                pets_allowed,
                parking_available,
                breakfast_available,
                listing_status,
                terms_conditions or None,
                owner_name,
                hotel_contact_phone,
                hotel_contact_email or None,
                gst_number or None,
                trade_license_number or None,
                registration_doc_path,
            ),
        )

        for amenity_id in valid_amenity_ids:
            cur.execute(
                "INSERT IGNORE INTO hotel_amenities(service_id, amenity_id) VALUES(%s,%s)",
                (service_id, amenity_id),
            )

        db.commit()
        cur.close()
        db.close()
        flash("Hotel listing created successfully.")
        return redirect(url_for("provider_hotels_management"))

    @app.route("/provider", methods=["GET", "POST"])
    @login_required
    @role_required("hotel_provider")
    def provider_dashboard():
        if request.method == "POST":
            action = request.form.get("action", "").strip()

            if action == "add_service":
                if session.get("role") != "hotel_provider":
                    flash("Use your hotel & services dashboard role for this action.")
                    return redirect(url_for("provider_dashboard"))
                service_type = request.form.get("service_type", "").strip()
                service_name = request.form.get("service_name", "").strip()
                description = request.form.get("description", "").strip()
                city_id = to_int(request.form.get("city_id"), 0)
                price = request.form.get("price", "").strip()

                if service_type not in {"Guides", "Food"}:
                    flash("Invalid service type.")
                elif not service_name or len(service_name) > 100:
                    flash("Valid service name is required.")
                elif len(description) > 2000:
                    flash("Service description must be 2000 characters or less.")
                elif not city_id or not query_db("SELECT id FROM cities WHERE id=%s", (city_id,), one=True):
                    flash("Invalid city selected.")
                elif not is_non_negative_amount(price):
                    flash("Price must be a non-negative number.")
                else:
                    execute_db(
                        """
                        INSERT INTO services(provider_id, service_type, service_name, price, description, city_id)
                        VALUES(%s,%s,%s,%s,%s,%s)
                        """,
                        (session["user_id"], service_type, service_name, price, description, city_id),
                    )
                    flash("Service published successfully.")

            elif action == "add_hotel":
                return _create_hotel_listing("provider_dashboard")

            elif action == "add_room_type":
                service_id = to_int(request.form.get("service_id"), 0)
                room_type_name = request.form.get("room_type_name", "").strip()
                bed_type = request.form.get("bed_type", "").strip()
                room_size_sqft = request.form.get("room_size_sqft") or None
                max_guests = to_int(request.form.get("max_guests"), 2)
                total_rooms = to_int(request.form.get("total_rooms"), 0)
                available_rooms = to_int(request.form.get("available_rooms"), 0)
                if total_rooms < 0:
                    total_rooms = 0
                available_rooms = max(0, min(available_rooms, total_rooms))
                base_price = request.form.get("room_base_price", "0").strip() or "0"
                strike_price = request.form.get("strike_price") or None
                tax_percent = request.form.get("tax_percent", "0").strip() or "0"
                breakfast_included = 1 if request.form.get("breakfast_included") else 0
                ac_available = 1 if request.form.get("ac_available") else 0
                wifi_available = 1 if request.form.get("wifi_available") else 0
                refundable = 1 if request.form.get("refundable") else 0
                cancellation_policy = request.form.get("cancellation_policy", "").strip()
                room_description = request.form.get("room_description", "").strip()

                owner = query_db(
                    "SELECT id FROM services WHERE id=%s AND provider_id=%s AND service_type='Hotel'",
                    (service_id, session["user_id"]),
                    one=True,
                )
                if not owner:
                    flash("Invalid hotel selected.")
                    return redirect(url_for("provider_dashboard"))
                if not room_type_name or len(room_type_name) > 120:
                    flash("Valid room type name is required.")
                    return redirect(url_for("provider_dashboard"))
                if max_guests < 1:
                    flash("Max guests must be at least 1.")
                    return redirect(url_for("provider_dashboard"))
                if room_size_sqft is not None and to_int(room_size_sqft, -1) < 0:
                    flash("Room size cannot be negative.")
                    return redirect(url_for("provider_dashboard"))
                if not is_non_negative_amount(base_price):
                    flash("Room base price must be a non-negative number.")
                    return redirect(url_for("provider_dashboard"))
                if strike_price and not is_non_negative_amount(strike_price):
                    flash("Strike price must be a non-negative number.")
                    return redirect(url_for("provider_dashboard"))
                if not is_non_negative_amount(tax_percent):
                    flash("Tax percent must be a non-negative number.")
                    return redirect(url_for("provider_dashboard"))

                execute_db(
                    """
                    INSERT INTO hotel_room_types(
                        service_id, room_type_name, bed_type, room_size_sqft, max_guests,
                        total_rooms, available_rooms, base_price, strike_price, tax_percent,
                        breakfast_included, ac_available, wifi_available, refundable,
                        cancellation_policy, room_description
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        service_id, room_type_name, bed_type or None, room_size_sqft, max_guests,
                        total_rooms, available_rooms, base_price, strike_price, tax_percent,
                        breakfast_included, ac_available, wifi_available, refundable,
                        cancellation_policy or None, room_description or None,
                    ),
                )
                flash("Room type added.")

            elif action == "add_transport":
                flash("Transport listing is disabled in this app version.")
                return redirect(url_for("provider_dashboard"))

            elif action == "update_inventory":
                room_type_id = to_int(request.form.get("room_type_id"), 0)
                new_available = to_int(request.form.get("new_available"), 0)
                note = request.form.get("note", "").strip()
                if room_type_id <= 0 or new_available < 0:
                    flash("Invalid room inventory values.")
                    return redirect(url_for("provider_dashboard"))
                ok, msg = update_room_inventory_for_provider(
                    room_type_id=room_type_id,
                    new_available=new_available,
                    provider_user_id=session["user_id"],
                    note=note,
                )
                flash(msg)

            elif action == "update_transport_inventory":
                flash("Transport inventory is disabled in this app version.")
                return redirect(url_for("provider_dashboard"))

            elif action == "update_hotel_booking_status":
                booking_id = to_int(request.form.get("booking_id"), 0)
                next_status = (request.form.get("next_status") or "").strip().lower()
                allowed_statuses = {"confirmed", "checked_in", "completed", "cancelled"}
                if booking_id <= 0 or next_status not in allowed_statuses:
                    flash("Invalid hotel booking status update.")
                    return redirect(url_for("provider_dashboard"))
                booking_row = query_db(
                    """
                    SELECT hb.id
                    FROM hotel_bookings hb
                    JOIN services s ON s.id=hb.service_id
                    WHERE hb.id=%s AND s.provider_id=%s AND s.service_type='Hotel'
                    """,
                    (booking_id, session["user_id"]),
                    one=True,
                )
                if not booking_row:
                    flash("Hotel booking not found.")
                    return redirect(url_for("provider_dashboard"))
                execute_db(
                    "UPDATE hotel_bookings SET status=%s WHERE id=%s",
                    (next_status, booking_id),
                )
                flash(f"Hotel booking #{booking_id} status updated to {next_status}.")

            return redirect(url_for("provider_dashboard"))

        services = query_db(
            """
            SELECT s.*, c.city_name
            FROM services s
            LEFT JOIN cities c ON c.id=s.city_id
            WHERE s.provider_id=%s
            ORDER BY s.id DESC
            """,
            (session["user_id"],),
        )
        hotel_services = query_db(
            """
            SELECT
                s.id, hp.hotel_name, hp.star_rating, c.city_name,
                COALESCE(SUM(rt.available_rooms), 0) AS total_available,
                COALESCE(MIN(rt.base_price), s.price) AS min_price
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN hotel_room_types rt ON rt.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            GROUP BY s.id, hp.hotel_name, hp.star_rating, c.city_name, s.price
            ORDER BY s.id DESC
            """,
            (session["user_id"],),
        )
        room_types = query_db(
            """
            SELECT rt.*, hp.hotel_name
            FROM hotel_room_types rt
            JOIN hotel_profiles hp ON hp.service_id=rt.service_id
            JOIN services s ON s.id=rt.service_id
            WHERE s.provider_id=%s
            ORDER BY rt.id DESC
            """,
            (session["user_id"],),
        )
        transport_services = []
        transport_logs = []
        hotel_bookings = query_db(
            """
            SELECT
                hb.id,
                hb.check_in_date,
                hb.check_out_date,
                hb.rooms_booked,
                hb.guests_count,
                hb.total_amount,
                hb.status,
                hb.created_at,
                hp.hotel_name,
                rt.room_type_name,
                u.full_name AS traveler_name,
                u.phone AS traveler_phone
            FROM hotel_bookings hb
            JOIN services s ON s.id=hb.service_id
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN hotel_room_types rt ON rt.id=hb.room_type_id
            JOIN users u ON u.id=hb.user_id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            ORDER BY hb.id DESC
            LIMIT 200
            """,
            (session["user_id"],),
        )
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
        profile = query_db(
            "SELECT * FROM user_profiles WHERE user_id=%s",
            (session["user_id"],),
            one=True,
        )

        return render_template(
            "provider_dashboard.html",
            services=services,
            hotel_services=hotel_services,
            room_types=room_types,
            transport_services=transport_services,
            states=states,
            cities=cities,
            profile=profile,
            transport_logs=transport_logs,
            hotel_bookings=hotel_bookings,
        )

    @app.route("/provider/hotels/add", methods=["GET", "POST"])
    @login_required
    @role_required("hotel_provider")
    def provider_add_hotel():
        if request.method == "POST":
            return _create_hotel_listing("provider_add_hotel")

        amenities, states, cities = _load_hotel_form_options()
        profile = query_db(
            "SELECT * FROM user_profiles WHERE user_id=%s",
            (session["user_id"],),
            one=True,
        )
        return render_template(
            "provider_add_hotel.html",
            amenities=amenities,
            states=states,
            cities=cities,
            profile=profile,
        )

    @app.route("/provider/hotels-management", methods=["GET", "POST"])
    @login_required
    @role_required("hotel_provider")
    def provider_hotels_management():
        if request.method == "POST":
            room_type_id = to_int(request.form.get("room_type_id"), 0)
            new_available = to_int(request.form.get("new_available"), 0)
            note = request.form.get("note", "").strip()
            if room_type_id <= 0 or new_available < 0:
                flash("Invalid inventory values.")
                return redirect(url_for("provider_hotels_management"))
            ok, msg = update_room_inventory_for_provider(
                room_type_id=room_type_id,
                new_available=new_available,
                provider_user_id=session["user_id"],
                note=note,
            )
            flash(msg)
            return redirect(url_for("provider_hotels_management"))

        hotel_stats = query_db(
            """
            SELECT
                COUNT(DISTINCT s.id) AS total_hotels,
                COALESCE(SUM(rt.total_rooms), 0) AS total_rooms,
                COALESCE(SUM(rt.available_rooms), 0) AS available_rooms
            FROM services s
            LEFT JOIN hotel_room_types rt ON rt.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            """,
            (session["user_id"],),
            one=True,
        )
        hotels = query_db(
            """
            SELECT
                s.id AS service_id, hp.hotel_name, hp.star_rating,
                c.city_name, hp.locality, hp.address_line1,
                hp.listing_status, hp.owner_name, hp.hotel_contact_phone,
                hp.gst_number, hp.trade_license_number,
                COALESCE(MIN(rt.base_price), s.price, 0) AS min_price,
                COALESCE(SUM(rt.total_rooms), 0) AS total_rooms,
                COALESCE(SUM(rt.available_rooms), 0) AS available_rooms
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN hotel_room_types rt ON rt.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            GROUP BY s.id, hp.hotel_name, hp.star_rating, c.city_name, hp.locality, hp.address_line1, hp.listing_status, hp.owner_name, hp.hotel_contact_phone, hp.gst_number, hp.trade_license_number, s.price
            ORDER BY s.id DESC
            """,
            (session["user_id"],),
        )
        room_types = query_db(
            """
            SELECT rt.*, hp.hotel_name, s.id AS service_id
            FROM hotel_room_types rt
            JOIN services s ON s.id=rt.service_id
            JOIN hotel_profiles hp ON hp.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            ORDER BY s.id DESC, rt.base_price ASC
            """,
            (session["user_id"],),
        )
        logs = query_db(
            """
            SELECT
                l.created_at, l.old_available, l.new_available, l.note,
                rt.room_type_name, hp.hotel_name
            FROM hotel_room_inventory_logs l
            JOIN hotel_room_types rt ON rt.id=l.room_type_id
            JOIN hotel_profiles hp ON hp.service_id=rt.service_id
            JOIN services s ON s.id=rt.service_id
            WHERE s.provider_id=%s
            ORDER BY l.id DESC
            LIMIT 50
            """,
            (session["user_id"],),
        )

        return render_template(
            "provider_hotels_management.html",
            hotel_stats=hotel_stats,
            hotels=hotels,
            room_types=room_types,
            logs=logs,
        )

    @app.route("/provider/hotels-management/<int:service_id>", methods=["GET", "POST"])
    @login_required
    @role_required("hotel_provider")
    def provider_hotel_manage_detail(service_id):
        hotel = query_db(
            """
            SELECT
                s.id AS service_id,
                s.provider_id,
                s.city_id,
                s.price,
                s.service_name,
                hp.*,
                c.state_id AS city_state_id
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            WHERE s.id=%s AND s.provider_id=%s AND s.service_type='Hotel'
            """,
            (service_id, session["user_id"]),
            one=True,
        )
        if not hotel:
            flash("Hotel not found.")
            return redirect(url_for("provider_hotels_management"))

        if request.method == "POST":
            action = (request.form.get("action") or "update_hotel").strip()

            if action in {"add_images", "replace_image", "set_cover_image"}:
                flash("Hotel image update options are removed.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            hotel_name = request.form.get("hotel_name", "").strip()
            brand_name = request.form.get("brand_name", "").strip()
            star_rating = to_int(request.form.get("star_rating"), 0)
            city_id = to_int(request.form.get("city_id"), 0)
            address_line1 = request.form.get("address_line1", "").strip()
            address_line2 = request.form.get("address_line2", "").strip()
            locality = request.form.get("locality", "").strip()
            landmark = request.form.get("landmark", "").strip()
            pincode = request.form.get("pincode", "").strip()
            latitude = (request.form.get("latitude") or "").strip() or None
            longitude = (request.form.get("longitude") or "").strip() or None
            check_in_time = request.form.get("check_in_time") or None
            check_out_time = request.form.get("check_out_time") or None
            base_price = request.form.get("base_price", "0").strip() or "0"
            hotel_description = request.form.get("hotel_description", "").strip()
            house_rules = request.form.get("house_rules", "").strip()
            terms_conditions = request.form.get("terms_conditions", "").strip()
            listing_status = (request.form.get("listing_status") or "active").strip().lower()
            owner_name = request.form.get("owner_name", "").strip()
            hotel_contact_phone = request.form.get("hotel_contact_phone", "").strip()
            hotel_contact_email = request.form.get("hotel_contact_email", "").strip().lower()
            gst_number = request.form.get("gst_number", "").strip().upper()
            trade_license_number = request.form.get("trade_license_number", "").strip()
            registration_doc = request.files.get("registration_doc")
            couple_friendly = 1 if request.form.get("couple_friendly") else 0
            pets_allowed = 1 if request.form.get("pets_allowed") else 0
            parking_available = 1 if request.form.get("parking_available") else 0
            breakfast_available = 1 if request.form.get("breakfast_available") else 0
            amenity_ids = request.form.getlist("amenity_ids")

            if not (hotel_name and city_id and address_line1):
                flash("Hotel name, city and address are required.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(hotel_name) > 120:
                flash("Hotel name is too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(brand_name) > 120:
                flash("Brand name is too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(address_line1) > 255 or len(address_line2) > 255:
                flash("Address lines are too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(locality) > 120 or len(landmark) > 120:
                flash("Locality or landmark is too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if not owner_name or len(owner_name) > 120:
                flash("Owner name is required (max 120 chars).")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if not hotel_contact_phone or not is_valid_phone(hotel_contact_phone):
                flash("Valid hotel contact phone is required (10 digits).")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if hotel_contact_email and (len(hotel_contact_email) > 120 or not is_valid_email(hotel_contact_email)):
                flash("Hotel contact email is invalid.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(gst_number) > 30:
                flash("GST number is too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(trade_license_number) > 60:
                flash("Trade license number is too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if len(hotel_description) > 5000 or len(house_rules) > 4000 or len(terms_conditions) > 4000:
                flash("Description, rules, or terms are too long.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if listing_status not in {"active", "inactive", "maintenance"}:
                flash("Invalid hotel status selected.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if not query_db("SELECT id FROM cities WHERE id=%s", (city_id,), one=True):
                flash("Invalid city selected.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if star_rating and (star_rating < 1 or star_rating > 5):
                flash("Star rating must be between 1 and 5.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if pincode and not is_valid_pincode(pincode):
                flash("Pincode must be 6 digits.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            has_lat = bool(latitude)
            has_lng = bool(longitude)
            if has_lat != has_lng:
                flash("Enter both latitude and longitude together, or leave both blank.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if latitude and not is_valid_latitude(latitude):
                flash("Latitude must be between -90 and 90.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if longitude and not is_valid_longitude(longitude):
                flash("Longitude must be between -180 and 180.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if has_lat and has_lng and not is_within_india_bounds(latitude, longitude):
                flash("Hotel coordinates must be inside India.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
            if not is_non_negative_amount(base_price):
                flash("Base price must be a non-negative number.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            registration_doc_path = (hotel.get("registration_doc_path") or "").strip() or None
            if registration_doc and registration_doc.filename:
                if not is_allowed_document_filename(registration_doc.filename):
                    flash("Registration document must be PDF, PNG, JPG, JPEG, or WEBP.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
                registration_doc_path = save_upload(registration_doc, app.config["DOC_UPLOAD_FOLDER"])
                if not registration_doc_path:
                    flash("Unable to upload registration document.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            parsed_amenity_ids = []
            for value in amenity_ids:
                amenity_id = to_int(value, 0)
                if amenity_id > 0:
                    parsed_amenity_ids.append(amenity_id)
            parsed_amenity_ids = sorted(set(parsed_amenity_ids))
            valid_amenity_ids = []
            if parsed_amenity_ids:
                placeholders = ", ".join(["%s"] * len(parsed_amenity_ids))
                rows = query_db(
                    f"SELECT id FROM amenity_master WHERE id IN ({placeholders})",
                    tuple(parsed_amenity_ids),
                )
                valid_amenity_ids = [to_int(row.get("id"), 0) for row in rows if to_int(row.get("id"), 0) > 0]

            db = get_db()
            cur = db.cursor(dictionary=True)
            cur.execute(
                """
                UPDATE services
                SET service_name=%s, city_id=%s, price=%s, description=%s
                WHERE id=%s AND provider_id=%s AND service_type='Hotel'
                """,
                (
                    hotel_name,
                    city_id,
                    base_price,
                    hotel_description or None,
                    service_id,
                    session["user_id"],
                ),
            )
            cur.execute(
                """
                UPDATE hotel_profiles
                SET
                    hotel_name=%s,
                    brand_name=%s,
                    star_rating=%s,
                    address_line1=%s,
                    address_line2=%s,
                    locality=%s,
                    landmark=%s,
                    pincode=%s,
                    latitude=%s,
                    longitude=%s,
                    check_in_time=%s,
                    check_out_time=%s,
                    hotel_description=%s,
                    house_rules=%s,
                    couple_friendly=%s,
                    pets_allowed=%s,
                    parking_available=%s,
                    breakfast_available=%s,
                    listing_status=%s,
                    terms_conditions=%s,
                    owner_name=%s,
                    hotel_contact_phone=%s,
                    hotel_contact_email=%s,
                    gst_number=%s,
                    trade_license_number=%s,
                    registration_doc_path=%s
                WHERE service_id=%s
                """,
                (
                    hotel_name,
                    brand_name or None,
                    star_rating,
                    address_line1,
                    address_line2 or None,
                    locality or None,
                    landmark or None,
                    pincode or None,
                    latitude,
                    longitude,
                    check_in_time,
                    check_out_time,
                    hotel_description or None,
                    house_rules or None,
                    couple_friendly,
                    pets_allowed,
                    parking_available,
                    breakfast_available,
                    listing_status,
                    terms_conditions or None,
                    owner_name,
                    hotel_contact_phone,
                    hotel_contact_email or None,
                    gst_number or None,
                    trade_license_number or None,
                    registration_doc_path,
                    service_id,
                ),
            )
            cur.execute("DELETE FROM hotel_amenities WHERE service_id=%s", (service_id,))
            for amenity_id in valid_amenity_ids:
                cur.execute(
                    "INSERT INTO hotel_amenities(service_id, amenity_id) VALUES(%s,%s)",
                    (service_id, amenity_id),
                )

            db.commit()
            cur.close()
            db.close()
            flash("Hotel details updated successfully.")
            return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

        amenities, states, cities = _load_hotel_form_options()
        selected_amenity_rows = query_db(
            "SELECT amenity_id FROM hotel_amenities WHERE service_id=%s",
            (service_id,),
        )
        selected_amenity_ids = {to_int(row.get("amenity_id"), 0) for row in selected_amenity_rows}
        room_types = query_db(
            """
            SELECT id, room_type_name, base_price, total_rooms, available_rooms
            FROM hotel_room_types
            WHERE service_id=%s
            ORDER BY base_price ASC, id DESC
            """,
            (service_id,),
        )

        return render_template(
            "provider_hotel_manage_detail.html",
            hotel=hotel,
            amenities=amenities,
            selected_amenity_ids=selected_amenity_ids,
            states=states,
            cities=cities,
            room_types=room_types,
        )
