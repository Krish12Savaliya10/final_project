from decimal import Decimal, InvalidOperation
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, session, url_for

from core.auth import login_required
from core.bootstrap import ensure_hotel_tables, ensure_tour_tables, ensure_transport_tables
from core.db import execute_db, query_db


def register_routes(app):
    @app.route("/booking/<int:tour_id>", methods=["GET", "POST"])
    @login_required
    def booking(tour_id):
        ensure_hotel_tables()
        ensure_transport_tables()
        ensure_tour_tables()
        tour = query_db(
            """
            SELECT
                t.*,
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
            SELECT ti.day_number, ms.spot_name, ms.image_url
            FROM tour_itinerary ti
            JOIN master_spots ms ON ms.id=ti.spot_id
            WHERE ti.tour_id=%s
            ORDER BY ti.day_number ASC, ti.order_sequence ASC, ti.id ASC
            """,
            (tour_id,),
        )
        existing = query_db(
            """
            SELECT * FROM bookings
            WHERE user_id=%s AND tour_id=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (session["user_id"], tour_id),
            one=True,
        )
        linked_hotels = query_db(
            """
            SELECT
                hp.hotel_name,
                hp.star_rating,
                c.city_name,
                s.state_name,
                COALESCE(MIN(rt.base_price), 0) AS from_price
            FROM tour_hotel_links thl
            JOIN hotel_profiles hp ON hp.service_id=thl.service_id
            JOIN services svc ON svc.id=thl.service_id
            LEFT JOIN cities c ON c.id=svc.city_id
            LEFT JOIN states s ON s.id=c.state_id
            LEFT JOIN hotel_room_types rt ON rt.service_id=svc.id
            WHERE thl.tour_id=%s
            GROUP BY hp.hotel_name, hp.star_rating, c.city_name, s.state_name
            ORDER BY hp.star_rating DESC, hp.hotel_name
            """,
            (tour_id,),
        )
        linked_transports = query_db(
            """
            SELECT
                s.service_name,
                tp.transport_type,
                tp.vehicle_model,
                tp.registration_number,
                tp.seating_capacity,
                tp.driver_available,
                tp.driver_name,
                tp.price_per_day,
                tp.price_per_km,
                c.city_name,
                st.state_name
            FROM tour_transport_links ttl
            JOIN services s ON s.id=ttl.service_id
            JOIN transport_profiles tp ON tp.service_id=s.id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
            WHERE ttl.tour_id=%s
            ORDER BY tp.transport_type, s.service_name
            """,
            (tour_id,),
        )
        linked_guides = query_db(
            """
            SELECT
                s.id AS service_id,
                s.service_name,
                s.description,
                s.price,
                c.city_name,
                st.state_name
            FROM tour_guide_links tgl
            JOIN services s ON s.id=tgl.service_id
            LEFT JOIN cities c ON c.id=s.city_id
            LEFT JOIN states st ON st.id=c.state_id
            WHERE tgl.tour_id=%s
            ORDER BY s.service_name
            """,
            (tour_id,),
        )

        if request.method == "POST":
            if existing and existing["status"] == "paid":
                flash("This tour is already booked and paid.")
                return redirect(url_for("booking", tour_id=tour_id))

            individual_guide = 1 if request.form.get("need_individual_guide") else 0
            selected_guide_id = request.form.get("guide_service_id")
            guide_note = request.form.get("guide_note", "").strip()

            booking_id = None
            if existing and existing["status"] == "pending":
                booking_id = existing["id"]
            else:
                booking_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                booking_id = execute_db(
                    """
                    INSERT INTO bookings(user_id,tour_id,date,status)
                    VALUES(%s,%s,%s,'pending')
                    """,
                    (session["user_id"], tour_id, booking_date),
                )

            guide_service_id = None
            try:
                if selected_guide_id:
                    candidate = int(selected_guide_id)
                    if any(int(g["service_id"]) == candidate for g in linked_guides):
                        guide_service_id = candidate
            except (TypeError, ValueError):
                guide_service_id = None

            execute_db(
                """
                INSERT INTO booking_guide_requests(booking_id, service_id, individual_requested, note)
                VALUES(%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    service_id=VALUES(service_id),
                    individual_requested=VALUES(individual_requested),
                    note=VALUES(note)
                """,
                (booking_id, guide_service_id, individual_guide, guide_note or None),
            )
            return redirect(url_for("payment", booking_id=booking_id))

        return render_template(
            "booking.html",
            tour=tour,
            itinerary=itinerary,
            linked_hotels=linked_hotels,
            linked_transports=linked_transports,
            linked_guides=linked_guides,
            readonly=bool(existing and existing["status"] == "paid"),
            booking_id=existing["id"] if existing and existing["status"] == "paid" else None,
        )

    @app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
    @login_required
    def payment(booking_id):
        booking = query_db(
            """
            SELECT b.*, t.title, t.price, t.start_date
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

        base_price = Decimal(str(booking["price"]))
        amount_to_pay = base_price

        if request.method == "POST":
            raw_amount = request.form.get("amount", str(base_price))
            try:
                amount_to_pay = Decimal(str(raw_amount))
            except InvalidOperation:
                amount_to_pay = base_price
            execute_db(
                "INSERT INTO payments(booking_id, amount, paid) VALUES(%s,%s,1)",
                (booking_id, amount_to_pay),
            )
            execute_db("UPDATE bookings SET status='paid' WHERE id=%s", (booking_id,))
            flash("Payment successful. Your booking is confirmed.")
            return redirect(url_for("invoice", booking_id=booking_id))

        extra_charges = max(amount_to_pay - base_price, Decimal("0.00"))
        return render_template(
            "payment.html",
            booking=booking,
            base_price=base_price,
            extra_charges=extra_charges,
            amount_to_pay=amount_to_pay,
        )

    @app.route("/invoice/<int:booking_id>")
    @login_required
    def invoice(booking_id):
        booking = query_db(
            """
            SELECT b.*, t.title, t.price, t.start_date
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
            SELECT b.*, t.title, t.price, t.start_date
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            WHERE b.user_id=%s
            ORDER BY b.id DESC
            """,
            (session["user_id"],),
        )
        return render_template("mybookings.html", bookings=bookings)
