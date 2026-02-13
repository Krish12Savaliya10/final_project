from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.bootstrap import ensure_support_tables
from core.db import execute_db, query_db


def register_routes(app):
    @app.route("/admin", methods=["GET", "POST"])
    @login_required
    @role_required("admin")
    def admin():
        ensure_support_tables()

        if request.method == "POST":
            user_id = request.form.get("user_id")
            action = request.form.get("action")
            note = request.form.get("note", "").strip()

            if user_id and action in {"approve", "reject", "set_pending"}:
                new_status_map = {
                    "approve": "approved",
                    "reject": "rejected",
                    "set_pending": "pending",
                }
                new_status = new_status_map[action]
                execute_db("UPDATE users SET status=%s WHERE id=%s", (new_status, int(user_id)))
                execute_db(
                    """
                    INSERT INTO user_approval_logs(user_id, admin_id, action_taken, note)
                    VALUES(%s,%s,%s,%s)
                    """,
                    (int(user_id), int(session["user_id"]), action, note or None),
                )
                flash(f"User status updated to {new_status}.")
            return redirect(url_for("admin"))

        pending_users = query_db(
            """
            SELECT
                u.id, u.full_name, u.email, u.phone, u.role, u.status, u.document_path,
                up.requested_role, up.business_name, up.provider_category
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id = u.id
            WHERE u.status='pending'
            ORDER BY u.id DESC
            """
        )
        approval_logs = query_db(
            """
            SELECT
                l.created_at, l.action_taken, l.note,
                u.full_name AS target_user_name,
                a.full_name AS admin_name
            FROM user_approval_logs l
            JOIN users u ON u.id=l.user_id
            JOIN users a ON a.id=l.admin_id
            ORDER BY l.id DESC
            LIMIT 30
            """
        )

        stats_row = query_db(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN role='customer' THEN 1 ELSE 0 END) AS total_travelers,
                SUM(CASE WHEN role='organizer' THEN 1 ELSE 0 END) AS total_organizers,
                SUM(CASE WHEN role='provider' THEN 1 ELSE 0 END) AS total_providers,
                SUM(CASE WHEN role='admin' THEN 1 ELSE 0 END) AS total_admins,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_approvals
            FROM users
            """,
            one=True,
        )
        tour_stats = query_db(
            """
            SELECT
                COUNT(*) AS total_tours,
                COALESCE(MIN(start_date), NULL) AS nearest_tour_date
            FROM tours
            """,
            one=True,
        )
        booking_stats = query_db(
            """
            SELECT
                COUNT(*) AS total_bookings,
                SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid_bookings,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_bookings
            FROM bookings
            """,
            one=True,
        )
        service_stats = query_db(
            """
            SELECT COUNT(*) AS total_services
            FROM services
            """,
            one=True,
        )
        payment_stats = query_db(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total_revenue,
                COUNT(*) AS total_payments
            FROM payments
            WHERE paid=1
            """,
            one=True,
        )

        all_users = query_db(
            """
            SELECT
                u.id, u.full_name, u.email, u.phone, u.role, u.status,
                up.provider_category, up.business_name
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id=u.id
            ORDER BY u.id DESC
            """
        )
        all_tours = query_db(
            """
            SELECT id, title, start_point, end_point, start_date, end_date, price
            FROM tours
            ORDER BY id DESC
            """
        )
        all_services = query_db(
            """
            SELECT
                s.id, s.service_name, s.service_type, s.price,
                u.full_name AS provider_name, c.city_name
            FROM services s
            LEFT JOIN users u ON u.id=s.provider_id
            LEFT JOIN cities c ON c.id=s.city_id
            ORDER BY s.id DESC
            """
        )
        recent_bookings = query_db(
            """
            SELECT
                b.id, b.date, b.status, u.full_name, t.title
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            JOIN tours t ON t.id=b.tour_id
            ORDER BY b.id DESC
            LIMIT 20
            """
        )

        return render_template(
            "admin_approvals.html",
            pending_users=pending_users,
            stats=stats_row,
            tour_stats=tour_stats,
            booking_stats=booking_stats,
            service_stats=service_stats,
            payment_stats=payment_stats,
            all_users=all_users,
            all_tours=all_tours,
            all_services=all_services,
            recent_bookings=recent_bookings,
            approval_logs=approval_logs,
        )

    @app.route("/approve/<int:user_id>")
    @login_required
    @role_required("admin")
    def approve(user_id):
        execute_db("UPDATE users SET status='approved' WHERE id=%s", (user_id,))
        execute_db(
            """
            INSERT INTO user_approval_logs(user_id, admin_id, action_taken, note)
            VALUES(%s,%s,'approve','Legacy approve route used')
            """,
            (user_id, int(session["user_id"])),
        )
        flash("User approved.")
        return redirect(url_for("admin"))

    @app.route("/approval")
    @login_required
    @role_required("admin")
    def approval_alias():
        return redirect(url_for("admin"))
