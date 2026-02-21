from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.db import execute_db, get_db, query_db
from core.helpers import (
    is_allowed_document_filename,
    is_allowed_image_filename,
    is_non_negative_amount,
    is_valid_email,
    is_valid_phone,
    is_valid_pincode,
    save_upload,
    to_int,
    update_room_inventory_for_provider,
)


def register_routes(app):
    MAX_HOTEL_PHOTOS = 20
    MAX_HOTEL_ROOM_ROWS = 20

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

    def _save_hotel_photo_files(file_items, require_any=False):
        uploaded_photo_paths = []
        selected_count = 0
        for file_obj in file_items or []:
            if not file_obj or not (file_obj.filename or "").strip():
                continue
            selected_count += 1
            if selected_count > MAX_HOTEL_PHOTOS:
                return None, f"You can upload maximum {MAX_HOTEL_PHOTOS} hotel photos."
            if not is_allowed_image_filename(file_obj.filename):
                return None, "Hotel photos must be PNG, JPG, JPEG, or WEBP."
            saved_name = save_upload(file_obj, app.config["UPLOAD_FOLDER"])
            if not saved_name:
                return None, "Unable to upload hotel photo."
            uploaded_photo_paths.append(saved_name)
        if require_any and selected_count <= 0:
            return None, "Please upload at least one hotel photo."
        if require_any and not uploaded_photo_paths:
            return None, "Unable to upload hotel photo."
        return uploaded_photo_paths, None

    def _insert_hotel_images(cur, service_id, image_paths, image_title=None):
        if not image_paths:
            return 0

        cover_exists = False
        cur.execute(
            "SELECT id FROM hotel_images WHERE service_id=%s AND is_cover=1 LIMIT 1",
            (service_id,),
        )
        if cur.fetchone():
            cover_exists = True

        next_sort_order = 1
        try:
            cur.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS max_sort_order FROM hotel_images WHERE service_id=%s",
                (service_id,),
            )
            sort_row = cur.fetchone()
            if sort_row:
                next_sort_order = to_int(sort_row[0], 0) + 1
        except Exception:
            next_sort_order = 1

        uploaded_count = 0
        for idx, image_path in enumerate(image_paths):
            is_cover = 1 if (not cover_exists and uploaded_count == 0) else 0
            try:
                cur.execute(
                    """
                    INSERT INTO hotel_images(service_id, image_url, image_title, is_cover, sort_order)
                    VALUES(%s,%s,%s,%s,%s)
                    """,
                    (service_id, image_path, image_title, is_cover, next_sort_order + idx),
                )
            except Exception:
                cur.execute(
                    "INSERT INTO hotel_images(service_id, image_url, is_cover) VALUES(%s,%s,%s)",
                    (service_id, image_path, is_cover),
                )
            uploaded_count += 1

        return uploaded_count

    def _parse_hotel_room_rows(require_at_least_one=True):
        room_type_names = request.form.getlist("room_type_name[]")
        room_base_prices = request.form.getlist("room_base_price[]")
        room_total_rooms = request.form.getlist("room_total_rooms[]")
        room_available_rooms = request.form.getlist("room_available_rooms[]")
        room_max_guests = request.form.getlist("room_max_guests[]")
        room_bed_types = request.form.getlist("room_bed_type[]")
        room_descriptions = request.form.getlist("room_description[]")

        row_count = max(
            len(room_type_names),
            len(room_base_prices),
            len(room_total_rooms),
            len(room_available_rooms),
            len(room_max_guests),
            len(room_bed_types),
            len(room_descriptions),
        )
        if row_count > MAX_HOTEL_ROOM_ROWS:
            return None, f"You can add maximum {MAX_HOTEL_ROOM_ROWS} room types."
        room_rows = []
        seen_room_types = set()
        for idx in range(row_count):
            row_number = idx + 1
            room_type_name = (room_type_names[idx] if idx < len(room_type_names) else "").strip()
            room_base_price = (room_base_prices[idx] if idx < len(room_base_prices) else "").strip()
            total_rooms_raw = (room_total_rooms[idx] if idx < len(room_total_rooms) else "").strip()
            available_rooms_raw = (room_available_rooms[idx] if idx < len(room_available_rooms) else "").strip()
            max_guests_raw = (room_max_guests[idx] if idx < len(room_max_guests) else "").strip()
            room_bed_type = (room_bed_types[idx] if idx < len(room_bed_types) else "").strip()
            room_description = (room_descriptions[idx] if idx < len(room_descriptions) else "").strip()

            has_any_value = any(
                [
                    room_type_name,
                    room_base_price,
                    total_rooms_raw,
                    available_rooms_raw,
                    max_guests_raw,
                    room_bed_type,
                    room_description,
                ]
            )
            if not has_any_value:
                continue

            if not room_type_name:
                return None, f"Room type name is required in row {row_number}."
            if len(room_type_name) > 120:
                return None, f"Room type name is too long in row {row_number} (max 120 chars)."
            room_type_key = room_type_name.lower()
            if room_type_key in seen_room_types:
                return None, f"Duplicate room type name in row {row_number}."
            seen_room_types.add(room_type_key)
            if room_bed_type and len(room_bed_type) > 120:
                return None, f"Bed type is too long in row {row_number} (max 120 chars)."
            if room_description and len(room_description) > 1000:
                return None, f"Room description is too long in row {row_number} (max 1000 chars)."
            if not is_non_negative_amount(room_base_price):
                return None, f"Invalid base price in row {row_number}."

            total_rooms = to_int(total_rooms_raw, 0)
            if total_rooms < 1:
                return None, f"Total rooms must be at least 1 in row {row_number}."

            if available_rooms_raw == "":
                available_rooms = total_rooms
            else:
                available_rooms = to_int(available_rooms_raw, -1)
                if available_rooms < 0:
                    return None, f"Available rooms cannot be negative in row {row_number}."
            if available_rooms > total_rooms:
                return None, f"Available rooms cannot be more than total rooms in row {row_number}."

            if max_guests_raw == "":
                max_guests = 2
            else:
                max_guests = to_int(max_guests_raw, 0)
                if max_guests < 1 or max_guests > 20:
                    return None, f"Max guests must be between 1 and 20 in row {row_number}."

            room_rows.append(
                {
                    "room_type_name": room_type_name,
                    "bed_type": room_bed_type or None,
                    "base_price": room_base_price,
                    "total_rooms": total_rooms,
                    "available_rooms": available_rooms,
                    "max_guests": max_guests,
                    "room_description": room_description or None,
                }
            )

        if require_at_least_one and not room_rows:
            return None, "Please add at least one room type for this hotel."
        return room_rows, None

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
        photo_files = request.files.getlist("hotel_photos")

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
        if not is_non_negative_amount(base_price):
            flash("Base price must be a non-negative number.")
            return redirect(url_for(redirect_endpoint))

        room_rows, room_error = _parse_hotel_room_rows(require_at_least_one=True)
        if room_error:
            flash(room_error)
            return redirect(url_for(redirect_endpoint))

        uploaded_photo_paths, photo_error = _save_hotel_photo_files(photo_files, require_any=True)
        if photo_error:
            flash(photo_error)
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
        try:
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
                    locality, landmark, pincode, check_in_time, check_out_time,
                    hotel_description, house_rules, couple_friendly, pets_allowed, parking_available,
                    breakfast_available, listing_status, terms_conditions, owner_name, hotel_contact_phone,
                    hotel_contact_email, gst_number, trade_license_number, registration_doc_path
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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

            for room_row in room_rows:
                cur.execute(
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
                        service_id,
                        room_row["room_type_name"],
                        room_row["bed_type"],
                        None,
                        room_row["max_guests"],
                        room_row["total_rooms"],
                        room_row["available_rooms"],
                        room_row["base_price"],
                        None,
                        "0",
                        0,
                        1,
                        1,
                        0,
                        None,
                        room_row["room_description"],
                    ),
                )

            _insert_hotel_images(cur, service_id, uploaded_photo_paths, image_title=hotel_name or None)

            db.commit()
        except Exception:
            db.rollback()
            flash("Unable to create hotel right now. Please try again.")
            return redirect(url_for(redirect_endpoint))
        finally:
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
            states=states,
            cities=cities,
            profile=profile,
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

        hotels = query_db(
            """
            SELECT
                s.id AS service_id,
                hp.hotel_name,
                hp.star_rating,
                c.city_name,
                st.state_name,
                hp.locality,
                hp.address_line1,
                hp.listing_status,
                hp.owner_name,
                hp.hotel_contact_phone,
                hp.hotel_contact_email,
                COALESCE(MIN(rt.base_price), s.price, 0) AS min_price,
                COALESCE(SUM(rt.total_rooms), 0) AS total_rooms,
                COALESCE(SUM(rt.available_rooms), 0) AS available_rooms,
                (
                    SELECT COUNT(*)
                    FROM hotel_images hi_count
                    WHERE hi_count.service_id=s.id
                ) AS photo_count,
                (
                    SELECT hi.image_url
                    FROM hotel_images hi
                    WHERE hi.service_id=s.id
                    ORDER BY hi.is_cover DESC, hi.id ASC
                    LIMIT 1
                ) AS cover_image
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
            LEFT JOIN hotel_room_types rt ON rt.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            GROUP BY
                s.id,
                hp.hotel_name,
                hp.star_rating,
                c.city_name,
                st.state_name,
                hp.locality,
                hp.address_line1,
                hp.listing_status,
                hp.owner_name,
                hp.hotel_contact_phone,
                hp.hotel_contact_email,
                s.price
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

        return render_template(
            "provider_hotels_management.html",
            hotels=hotels,
            room_types=room_types,
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
                c.state_id AS city_state_id,
                c.city_name,
                st.state_name
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
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

            if action == "add_photos":
                photo_files = request.files.getlist("hotel_photos")
                uploaded_photo_paths, photo_error = _save_hotel_photo_files(photo_files, require_any=True)
                if photo_error:
                    flash(photo_error)
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

                db = get_db()
                cur = db.cursor()
                try:
                    uploaded_count = _insert_hotel_images(
                        cur,
                        service_id,
                        uploaded_photo_paths,
                        image_title=hotel.get("hotel_name") or None,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    flash("Unable to upload hotel photos.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
                finally:
                    cur.close()
                    db.close()

                flash(f"{uploaded_count} hotel photo(s) uploaded.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            if action == "set_cover_photo":
                image_id = to_int(request.form.get("image_id"), 0)
                if image_id <= 0:
                    flash("Invalid photo selected.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

                db = get_db()
                cur = db.cursor()
                try:
                    cur.execute(
                        "SELECT id FROM hotel_images WHERE id=%s AND service_id=%s LIMIT 1",
                        (image_id, service_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        flash("Photo not found.")
                        return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

                    cur.execute("UPDATE hotel_images SET is_cover=0 WHERE service_id=%s", (service_id,))
                    cur.execute("UPDATE hotel_images SET is_cover=1 WHERE id=%s", (image_id,))
                    db.commit()
                except Exception:
                    db.rollback()
                    flash("Unable to update cover photo.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
                finally:
                    cur.close()
                    db.close()

                flash("Cover photo updated.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            if action == "delete_photo":
                image_id = to_int(request.form.get("image_id"), 0)
                if image_id <= 0:
                    flash("Invalid photo selected.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

                db = get_db()
                cur = db.cursor()
                try:
                    cur.execute(
                        "SELECT id, is_cover FROM hotel_images WHERE id=%s AND service_id=%s LIMIT 1",
                        (image_id, service_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        flash("Photo not found.")
                        return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

                    was_cover = bool(to_int(row[1], 0))
                    cur.execute("DELETE FROM hotel_images WHERE id=%s AND service_id=%s", (image_id, service_id))

                    if was_cover:
                        cur.execute("SELECT id FROM hotel_images WHERE service_id=%s ORDER BY id ASC LIMIT 1", (service_id,))
                        next_row = cur.fetchone()
                        if next_row:
                            cur.execute("UPDATE hotel_images SET is_cover=0 WHERE service_id=%s", (service_id,))
                            cur.execute("UPDATE hotel_images SET is_cover=1 WHERE id=%s", (next_row[0],))

                    db.commit()
                except Exception:
                    db.rollback()
                    flash("Unable to delete photo.")
                    return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))
                finally:
                    cur.close()
                    db.close()

                flash("Photo deleted.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            if action != "update_hotel":
                flash("Invalid action.")
                return redirect(url_for("provider_hotel_manage_detail", service_id=service_id))

            hotel_name = request.form.get("hotel_name", "").strip()
            brand_name = request.form.get("brand_name", "").strip()
            star_rating = to_int(request.form.get("star_rating"), 0)
            city_id = to_int(request.form.get("city_id"), 0)
            address_line1 = request.form.get("address_line1", "").strip()
            address_line2 = request.form.get("address_line2", hotel.get("address_line2") or "").strip()
            locality = request.form.get("locality", "").strip()
            landmark = request.form.get("landmark", hotel.get("landmark") or "").strip()
            pincode = request.form.get("pincode", "").strip()
            check_in_time = request.form.get("check_in_time")
            if check_in_time is None:
                check_in_time = hotel.get("check_in_time")
            else:
                check_in_time = check_in_time or None
            check_out_time = request.form.get("check_out_time")
            if check_out_time is None:
                check_out_time = hotel.get("check_out_time")
            else:
                check_out_time = check_out_time or None
            base_price = request.form.get("base_price", "0").strip() or "0"
            hotel_description = request.form.get("hotel_description", "").strip()
            house_rules = request.form.get("house_rules", "").strip()
            terms_conditions = request.form.get("terms_conditions", "").strip()
            listing_status = (request.form.get("listing_status") or "active").strip().lower()
            owner_name = request.form.get("owner_name", "").strip()
            hotel_contact_phone = request.form.get("hotel_contact_phone", "").strip()
            hotel_contact_email = request.form.get("hotel_contact_email", "").strip().lower()
            gst_number = request.form.get("gst_number", hotel.get("gst_number") or "").strip().upper()
            trade_license_number = request.form.get("trade_license_number", hotel.get("trade_license_number") or "").strip()
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
        selected_amenity_name_rows = query_db(
            """
            SELECT am.amenity_name
            FROM hotel_amenities ha
            JOIN amenity_master am ON am.id=ha.amenity_id
            WHERE ha.service_id=%s
            ORDER BY am.amenity_name ASC
            """,
            (service_id,),
        )
        selected_amenity_names = [row.get("amenity_name") for row in selected_amenity_name_rows if row.get("amenity_name")]
        hotel_images = query_db(
            """
            SELECT id, image_url, image_title, is_cover
            FROM hotel_images
            WHERE service_id=%s
            ORDER BY is_cover DESC, id ASC
            """,
            (service_id,),
        )
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
            selected_amenity_names=selected_amenity_names,
            states=states,
            cities=cities,
            hotel_images=hotel_images,
            room_types=room_types,
        )
