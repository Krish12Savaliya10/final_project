import base64
from collections import Counter
from datetime import datetime
from io import BytesIO

from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.bootstrap import ensure_hotel_tables, ensure_tour_tables, ensure_transport_tables
from core.db import execute_db, get_db, query_db
from core.helpers import save_upload


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


def _fig_to_base64(fig):
    buff = BytesIO()
    fig.tight_layout()
    fig.savefig(buff, format="png", dpi=120, bbox_inches="tight")
    buff.seek(0)
    encoded = base64.b64encode(buff.read()).decode("utf-8")
    buff.close()
    return encoded


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
        ensure_hotel_tables()
        ensure_transport_tables()
        ensure_tour_tables()

        if request.method == "POST":
            action = request.form.get("action", "").strip()

            if action == "add_state":
                state_name = request.form.get("state_name", "").strip()
                if state_name:
                    execute_db("INSERT INTO states(state_name) VALUES(%s)", (state_name,))
                    flash("State added.")

            elif action == "add_city":
                state_id = request.form.get("state_id")
                city_name = request.form.get("city_name", "").strip()
                if state_id and city_name:
                    execute_db(
                        "INSERT INTO cities(state_id, city_name) VALUES(%s,%s)",
                        (state_id, city_name),
                    )
                    flash("City added.")

            elif action == "add_spot":
                city_id = request.form.get("city_id")
                spot_name = request.form.get("spot_name", "").strip()
                image_file = request.files.get("spot_image")
                image_name = save_upload(image_file, app.config["UPLOAD_FOLDER"])
                if city_id and spot_name:
                    execute_db(
                        "INSERT INTO master_spots(spot_name,image_url,city_id) VALUES(%s,%s,%s)",
                        (spot_name, image_name or "demo.jpg", city_id),
                    )
                    flash("Spot added.")

            elif action == "add_tour":
                title = request.form.get("title", "").strip()
                description = request.form.get("description", "").strip()
                price = request.form.get("price", "0")
                start_point = request.form.get("start_point", "").strip()
                end_point = request.form.get("end_point", "").strip()
                start_date = request.form.get("start_date")
                end_date = request.form.get("end_date")
                travel_mode = request.form.get("travel_mode", "").strip()
                food_plan = request.form.get("food_plan", "").strip()
                transport_details = request.form.get("transport_details", "").strip()
                hotel_notes = request.form.get("hotel_notes", "").strip()
                inclusions = request.form.get("inclusions", "").strip()
                exclusions = request.form.get("exclusions", "").strip()
                pickup_state_id = request.form.get("pickup_state_id") or None
                pickup_city_id = request.form.get("pickup_city_id") or None
                drop_state_id = request.form.get("drop_state_id") or None
                drop_city_id = request.form.get("drop_city_id") or None
                max_group_size = request.form.get("max_group_size") or None
                difficulty_level = request.form.get("difficulty_level", "").strip()
                linked_hotels = request.form.getlist("linked_hotels[]")
                linked_transport = request.form.getlist("linked_transport[]")
                linked_guides = request.form.getlist("linked_guides[]")
                image_name = save_upload(request.files.get("tour_image"), app.config["UPLOAD_FOLDER"]) or "demo.jpg"
                day_numbers = request.form.getlist("day_numbers[]")
                spots = request.form.getlist("spots[]")

                if title and start_point and end_point and start_date and end_date:
                    db = get_db()
                    cur = db.cursor()
                    cur.execute(
                        """
                        INSERT INTO tours(
                            title,description,price,start_date,end_date,start_point,end_point,image_path,
                            travel_mode,food_plan,transport_details,hotel_notes,inclusions,exclusions,
                            pickup_state_id,pickup_city_id,drop_state_id,drop_city_id,max_group_size,difficulty_level
                        )
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
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
                            difficulty_level or None,
                        ),
                    )
                    tour_id = cur.lastrowid
                    for idx, spot_id in enumerate(spots):
                        if not spot_id:
                            continue
                        day_num = 1
                        if idx < len(day_numbers):
                            try:
                                day_num = int(day_numbers[idx])
                            except ValueError:
                                day_num = 1
                        cur.execute(
                            """
                            INSERT INTO tour_itinerary(tour_id, spot_id, order_sequence, day_number)
                            VALUES(%s,%s,%s,%s)
                            """,
                            (tour_id, int(spot_id), idx + 1, day_num),
                        )

                    for service_id in linked_hotels:
                        try:
                            sid = int(service_id)
                        except (TypeError, ValueError):
                            continue
                        cur.execute(
                            """
                            INSERT IGNORE INTO tour_hotel_links(tour_id, service_id)
                            SELECT %s, id
                            FROM services
                            WHERE id=%s AND service_type='Hotel'
                            """,
                            (tour_id, sid),
                        )
                    for service_id in linked_transport:
                        try:
                            sid = int(service_id)
                        except (TypeError, ValueError):
                            continue
                        cur.execute(
                            """
                            INSERT IGNORE INTO tour_transport_links(tour_id, service_id)
                            SELECT %s, id
                            FROM services
                            WHERE id=%s AND service_type='Transport'
                            """,
                            (tour_id, sid),
                        )
                    for service_id in linked_guides:
                        try:
                            sid = int(service_id)
                        except (TypeError, ValueError):
                            continue
                        cur.execute(
                            """
                            INSERT IGNORE INTO tour_guide_links(tour_id, service_id)
                            SELECT %s, id
                            FROM services
                            WHERE id=%s AND service_type='Guides'
                            """,
                            (tour_id, sid),
                        )
                    db.commit()
                    cur.close()
                    db.close()
                    flash("Tour published.")

            return redirect(url_for("organizer_dashboard"))

        tours = query_db("SELECT * FROM tours ORDER BY id DESC")
        bookings = query_db(
            """
            SELECT b.*, u.full_name, t.title
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            JOIN tours t ON t.id=b.tour_id
            ORDER BY b.id DESC
            """
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
            ORDER BY s.state_name, c.city_name, hp.hotel_name
            """
        )
        transport_options = query_db(
            """
            SELECT
                svc.id AS service_id,
                svc.service_name,
                tp.transport_type,
                tp.vehicle_model,
                tp.seating_capacity,
                tp.driver_available,
                tp.price_per_day,
                c.id AS city_id,
                c.city_name,
                s.id AS state_id,
                s.state_name
            FROM services svc
            JOIN transport_profiles tp ON tp.service_id=svc.id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            WHERE svc.service_type='Transport'
            ORDER BY s.state_name, c.city_name, svc.service_name
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
        charts, chart_error = _build_organizer_charts(tours, bookings)
        analytics = {
            "total_tours": len(tours),
            "total_bookings": len(bookings),
            "paid_bookings": sum(1 for b in bookings if (b.get("status") or "").lower() == "paid"),
            "total_spots": len(spots),
            "partner_hotels": len(hotel_options),
            "partner_transport": len(transport_options),
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
            hotel_options=hotel_options,
            transport_options=transport_options,
            guide_options=guide_options,
            analytics=analytics,
            panel_title="Organizer Panel",
        )
