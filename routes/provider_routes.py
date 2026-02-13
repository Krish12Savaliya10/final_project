from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.bootstrap import ensure_hotel_tables, ensure_support_tables, ensure_transport_tables
from core.db import execute_db, get_db, query_db
from core.helpers import save_upload, to_int, update_room_inventory_for_provider


def register_routes(app):
    @app.route("/provider", methods=["GET", "POST"])
    @login_required
    @role_required("provider")
    def provider_dashboard():
        ensure_support_tables()
        ensure_hotel_tables()
        ensure_transport_tables()

        if request.method == "POST":
            action = request.form.get("action", "").strip()

            if action == "add_service":
                service_type = request.form.get("service_type", "").strip()
                service_name = request.form.get("service_name", "").strip()
                description = request.form.get("description", "").strip()
                city_id = request.form.get("city_id")
                price = request.form.get("price", "").strip()

                if service_type and service_name and city_id and price:
                    execute_db(
                        """
                        INSERT INTO services(provider_id, service_type, service_name, price, description, city_id)
                        VALUES(%s,%s,%s,%s,%s,%s)
                        """,
                        (session["user_id"], service_type, service_name, price, description, city_id),
                    )
                    flash("Service published successfully.")
                else:
                    flash("Please fill all required service fields.")

            elif action == "add_hotel":
                hotel_name = request.form.get("hotel_name", "").strip()
                brand_name = request.form.get("brand_name", "").strip()
                star_rating = to_int(request.form.get("star_rating"), 0)
                city_id = request.form.get("city_id")
                address_line1 = request.form.get("address_line1", "").strip()
                address_line2 = request.form.get("address_line2", "").strip()
                locality = request.form.get("locality", "").strip()
                landmark = request.form.get("landmark", "").strip()
                pincode = request.form.get("pincode", "").strip()
                latitude = request.form.get("latitude") or None
                longitude = request.form.get("longitude") or None
                check_in_time = request.form.get("check_in_time") or None
                check_out_time = request.form.get("check_out_time") or None
                hotel_description = request.form.get("hotel_description", "").strip()
                house_rules = request.form.get("house_rules", "").strip()
                couple_friendly = 1 if request.form.get("couple_friendly") else 0
                pets_allowed = 1 if request.form.get("pets_allowed") else 0
                parking_available = 1 if request.form.get("parking_available") else 0
                breakfast_available = 1 if request.form.get("breakfast_available") else 0
                amenity_ids = request.form.getlist("amenity_ids")
                base_price = request.form.get("base_price", "0").strip() or "0"
                hotel_images = request.files.getlist("hotel_images")

                if not (hotel_name and city_id and address_line1):
                    flash("Hotel name, city and address are required.")
                    return redirect(url_for("provider_dashboard"))

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
                        hotel_description, house_rules, couple_friendly, pets_allowed, parking_available, breakfast_available
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        service_id, hotel_name, brand_name or None, star_rating, address_line1, address_line2 or None,
                        locality or None, landmark or None, pincode or None, latitude, longitude, check_in_time, check_out_time,
                        hotel_description or None, house_rules or None, couple_friendly, pets_allowed, parking_available, breakfast_available,
                    ),
                )

                for amenity_id in amenity_ids:
                    try:
                        aid = int(amenity_id)
                    except ValueError:
                        continue
                    cur.execute(
                        "INSERT IGNORE INTO hotel_amenities(service_id, amenity_id) VALUES(%s,%s)",
                        (service_id, aid),
                    )

                sort_order = 1
                for img in hotel_images:
                    filename = save_upload(img, app.config["UPLOAD_FOLDER"])
                    if not filename:
                        continue
                    cur.execute(
                        """
                        INSERT INTO hotel_images(service_id, image_url, image_title, is_cover, sort_order)
                        VALUES(%s,%s,%s,%s,%s)
                        """,
                        (service_id, filename, hotel_name, 1 if sort_order == 1 else 0, sort_order),
                    )
                    sort_order += 1

                db.commit()
                cur.close()
                db.close()
                flash("Hotel listing created. Add room types below.")

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
                service_name = request.form.get("service_name", "").strip()
                city_id = request.form.get("city_id")
                transport_type = request.form.get("transport_type", "").strip()
                vehicle_model = request.form.get("vehicle_model", "").strip()
                registration_number = request.form.get("registration_number", "").strip()
                seating_capacity = to_int(request.form.get("seating_capacity"), 0) or None
                luggage_capacity = request.form.get("luggage_capacity", "").strip()
                ac_available = 1 if request.form.get("ac_available") else 0
                driver_available = 1 if request.form.get("driver_available") else 0
                driver_name = request.form.get("driver_name", "").strip()
                driver_phone = request.form.get("driver_phone", "").strip()
                price_per_day = request.form.get("price_per_day", "").strip() or "0"
                price_per_km = request.form.get("price_per_km", "").strip() or None
                description = request.form.get("description", "").strip()

                permit_doc = request.files.get("permit_doc")
                insurance_doc = request.files.get("insurance_doc")
                license_doc = request.files.get("license_doc")
                rc_doc = request.files.get("rc_doc")

                if not (
                    service_name
                    and city_id
                    and transport_type
                    and registration_number
                    and price_per_day
                    and permit_doc
                    and insurance_doc
                    and license_doc
                    and rc_doc
                ):
                    flash("Transport listing requires core fields and all transport documents.")
                    return redirect(url_for("provider_dashboard"))

                permit_doc_name = save_upload(permit_doc, app.config["DOC_UPLOAD_FOLDER"])
                insurance_doc_name = save_upload(insurance_doc, app.config["DOC_UPLOAD_FOLDER"])
                license_doc_name = save_upload(license_doc, app.config["DOC_UPLOAD_FOLDER"])
                rc_doc_name = save_upload(rc_doc, app.config["DOC_UPLOAD_FOLDER"])

                if not (permit_doc_name and insurance_doc_name and license_doc_name and rc_doc_name):
                    flash("Unable to upload transport documents. Please try again.")
                    return redirect(url_for("provider_dashboard"))

                db = get_db()
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO services(provider_id, service_type, service_name, price, description, city_id)
                    VALUES(%s,'Transport',%s,%s,%s,%s)
                    """,
                    (session["user_id"], service_name, price_per_day, description, city_id),
                )
                service_id = cur.lastrowid

                cur.execute(
                    """
                    INSERT INTO transport_profiles(
                        service_id, transport_type, vehicle_model, registration_number, seating_capacity,
                        luggage_capacity, ac_available, driver_available, driver_name, driver_phone,
                        price_per_day, price_per_km, permit_doc_path, insurance_doc_path,
                        license_doc_path, rc_doc_path, notes
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        service_id,
                        transport_type,
                        vehicle_model or None,
                        registration_number,
                        seating_capacity,
                        luggage_capacity or None,
                        ac_available,
                        driver_available,
                        driver_name or None,
                        driver_phone or None,
                        price_per_day,
                        price_per_km,
                        permit_doc_name,
                        insurance_doc_name,
                        license_doc_name,
                        rc_doc_name,
                        description or None,
                    ),
                )
                db.commit()
                cur.close()
                db.close()
                flash("Transport listing published with documents.")

            elif action == "update_inventory":
                room_type_id = to_int(request.form.get("room_type_id"), 0)
                new_available = to_int(request.form.get("new_available"), 0)
                note = request.form.get("note", "").strip()
                ok, msg = update_room_inventory_for_provider(
                    room_type_id=room_type_id,
                    new_available=new_available,
                    provider_user_id=session["user_id"],
                    note=note,
                )
                flash(msg)

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
        transport_services = query_db(
            """
            SELECT
                s.id AS service_id,
                s.service_name,
                tp.transport_type,
                tp.vehicle_model,
                tp.registration_number,
                tp.seating_capacity,
                tp.driver_available,
                tp.price_per_day,
                tp.price_per_km,
                c.city_name,
                st.state_name
            FROM services s
            JOIN transport_profiles tp ON tp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
            WHERE s.provider_id=%s AND s.service_type='Transport'
            ORDER BY s.id DESC
            """,
            (session["user_id"],),
        )
        amenities = query_db("SELECT * FROM amenity_master ORDER BY amenity_name ASC")
        cities = query_db(
            """
            SELECT c.id, c.city_name, s.state_name
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
            amenities=amenities,
            cities=cities,
            profile=profile,
        )

    @app.route("/provider/hotels-management", methods=["GET", "POST"])
    @login_required
    @role_required("provider")
    def provider_hotels_management():
        ensure_hotel_tables()

        if request.method == "POST":
            room_type_id = to_int(request.form.get("room_type_id"), 0)
            new_available = to_int(request.form.get("new_available"), 0)
            note = request.form.get("note", "").strip()
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
                COALESCE(MIN(rt.base_price), s.price, 0) AS min_price,
                COALESCE(SUM(rt.total_rooms), 0) AS total_rooms,
                COALESCE(SUM(rt.available_rooms), 0) AS available_rooms
            FROM services s
            JOIN hotel_profiles hp ON hp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN hotel_room_types rt ON rt.service_id=s.id
            WHERE s.provider_id=%s AND s.service_type='Hotel'
            GROUP BY s.id, hp.hotel_name, hp.star_rating, c.city_name, hp.locality, hp.address_line1, s.price
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
