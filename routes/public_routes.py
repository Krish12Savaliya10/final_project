from datetime import datetime
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.auth import login_required
from core.bootstrap import ensure_hotel_tables, ensure_support_tables, ensure_tour_tables, ensure_transport_tables
from core.db import execute_db, get_db, query_db
from core.helpers import normalize_role, save_upload, to_int


def register_routes(app):
    @app.route("/")
    def home():
        ensure_tour_tables()
        ensure_transport_tables()
        tours = query_db(
            """
            SELECT
                t.*,
                (
                    SELECT COUNT(*)
                    FROM tour_hotel_links thl
                    WHERE thl.tour_id=t.id
                ) AS linked_hotels_count,
                (
                    SELECT COUNT(*)
                    FROM tour_transport_links ttl
                    WHERE ttl.tour_id=t.id
                ) AS linked_transport_count,
                (
                    SELECT COUNT(*)
                    FROM tour_guide_links tgl
                    WHERE tgl.tour_id=t.id
                ) AS linked_guides_count
            FROM tours t
            ORDER BY t.id DESC
            LIMIT 3
            """
        )
        return render_template("home.html", tours=tours)

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/tour")
    def tour():
        ensure_tour_tables()
        ensure_transport_tables()
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
                    FROM tour_hotel_links thl
                    WHERE thl.tour_id=t.id
                ) AS linked_hotels_count,
                (
                    SELECT COUNT(*)
                    FROM tour_transport_links ttl
                    WHERE ttl.tour_id=t.id
                ) AS linked_transport_count,
                (
                    SELECT COUNT(*)
                    FROM tour_guide_links tgl
                    WHERE tgl.tour_id=t.id
                ) AS linked_guides_count
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
    @login_required
    def hotels():
        ensure_hotel_tables()
        search = request.args.get("search", "").strip()
        params = []
        where = ""
        if search:
            where = """
            WHERE hp.hotel_name LIKE %s
               OR hp.locality LIKE %s
               OR c.city_name LIKE %s
               OR s.state_name LIKE %s
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

    @app.route("/hotels/<int:service_id>", methods=["GET", "POST"])
    @login_required
    def hotel_detail(service_id):
        ensure_hotel_tables()
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
        inventory_updates = query_db(
            """
            SELECT
                l.created_at, l.old_available, l.new_available,
                rt.room_type_name, u.full_name AS changed_by_name
            FROM hotel_room_inventory_logs l
            JOIN hotel_room_types rt ON rt.id=l.room_type_id
            JOIN users u ON u.id=l.changed_by
            WHERE rt.service_id=%s
            ORDER BY l.id DESC
            LIMIT 20
            """,
            (service_id,),
        )

        if request.method == "POST":
            room_type_id = to_int(request.form.get("room_type_id"), 0)
            rooms_booked = max(1, to_int(request.form.get("rooms_booked"), 1))
            guests_count = max(1, to_int(request.form.get("guests_count"), 1))
            check_in_date = request.form.get("check_in_date", "").strip()
            check_out_date = request.form.get("check_out_date", "").strip()

            if not room_type_id or not check_in_date or not check_out_date:
                flash("Please fill booking details correctly.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            try:
                check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
                check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
            except ValueError:
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

            if int(room_row["available_rooms"] or 0) < rooms_booked:
                flash("Requested rooms are not available.")
                return redirect(url_for("hotel_detail", service_id=service_id))

            total_amount = Decimal(str(room_row["base_price"])) * Decimal(rooms_booked) * Decimal(nights)

            db = get_db()
            cur = db.cursor()
            cur.execute(
                "UPDATE hotel_room_types SET available_rooms = available_rooms - %s WHERE id=%s",
                (rooms_booked, room_type_id),
            )
            cur.execute(
                """
                INSERT INTO hotel_bookings(
                    user_id, service_id, room_type_id, check_in_date, check_out_date,
                    rooms_booked, guests_count, nights, total_amount, status
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed')
                """,
                (
                    session["user_id"],
                    service_id,
                    room_type_id,
                    check_in_date,
                    check_out_date,
                    rooms_booked,
                    guests_count,
                    nights,
                    total_amount,
                ),
            )
            cur.execute(
                """
                INSERT INTO hotel_room_inventory_logs(room_type_id, changed_by, old_available, new_available, note)
                VALUES(%s,%s,%s,%s,%s)
                """,
                (
                    room_type_id,
                    session["user_id"],
                    int(room_row["available_rooms"] or 0),
                    int(room_row["available_rooms"] or 0) - rooms_booked,
                    "Booked from hotel detail page",
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
            inventory_updates=inventory_updates,
        )

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        ensure_support_tables()
        errors = {}

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            selected_role = request.form.get("role", "traveler")
            role = normalize_role(selected_role)

            provider_category = request.form.get("provider_category", "").strip()
            business_name = request.form.get("business_name", "").strip()
            document = request.files.get("document")

            if not full_name:
                errors["full_name"] = "Full name is required."
            if not email or "@" not in email:
                errors["email"] = "Enter a valid email address."
            if not phone.isdigit() or len(phone) < 10:
                errors["phone"] = "Enter a valid mobile number."
            if len(password) < 6:
                errors["password"] = "Password must be at least 6 characters."
            if password != confirm:
                errors["confirm"] = "Passwords do not match."

            if role in {"organizer", "provider", "admin"} and not document:
                errors["document"] = "Document is required for this role."

            if role == "provider" and not provider_category:
                errors["provider_category"] = "Please select service category."

            existing_user = query_db(
                "SELECT id FROM users WHERE email=%s OR phone=%s",
                (email, phone),
                one=True,
            )
            if existing_user:
                errors["email"] = "Email or phone is already registered."

            if errors:
                return render_template("signup.html", errors=errors)

            status = "approved" if role == "customer" else "pending"
            hashed = generate_password_hash(password)
            document_name = save_upload(document, app.config["DOC_UPLOAD_FOLDER"])

            user_id = execute_db(
                """
                INSERT INTO users(full_name,email,phone,password,role,status,document_path)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                """,
                (full_name, email, phone, hashed, role, status, document_name),
            )

            execute_db(
                """
                INSERT INTO user_profiles(user_id, requested_role, business_name, provider_category)
                VALUES(%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    requested_role=VALUES(requested_role),
                    business_name=VALUES(business_name),
                    provider_category=VALUES(provider_category)
                """,
                (user_id, selected_role, business_name or None, provider_category or None),
            )

            if status == "pending":
                flash("Signup submitted. Admin approval is required before login.")
            else:
                flash("Account created successfully. You can login now.")
            return redirect(url_for("login"))

        return render_template("signup.html", errors={})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            login_input = request.form.get("login", "").strip()
            password = request.form.get("password", "")

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

            if user["status"] != "approved":
                flash("Your account is pending admin approval.")
                return redirect(url_for("login"))

            session["user_id"] = user["id"]
            session["username"] = user["full_name"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin"))
            if user["role"] == "organizer":
                return redirect(url_for("organizer_dashboard"))
            if user["role"] == "provider":
                return redirect(url_for("provider_dashboard"))
            return redirect(url_for("home"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"))
