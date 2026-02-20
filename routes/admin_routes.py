from flask import flash, redirect, render_template, request, session, url_for

from core.auth import login_required, role_required
from core.db import execute_db, get_db, query_db
from core.helpers import get_onboarding_document_requirements, to_int


def _resolve_requested_photo(image_url, photo_source):
    final_image = (image_url or "").strip() or "demo.jpg"
    source = (photo_source or "").strip() or "local_file"
    if final_image.lower().startswith(("http://", "https://")):
        source = "external_url"
    elif final_image == "demo.jpg":
        source = "local_file"
    return final_image, source


def _approve_spot_request(spot_request_id, admin_id, note):
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM spot_change_requests WHERE id=%s FOR UPDATE", (spot_request_id,))
        request_row = cur.fetchone()
        if not request_row:
            db.rollback()
            return False, "Spot request not found."
        if (request_row.get("status") or "").strip().lower() != "pending":
            db.rollback()
            return False, f"Spot request #{spot_request_id} is already {request_row.get('status') or 'processed'}."

        request_type = (request_row.get("request_type") or "").strip()
        requested_image, requested_photo_source = _resolve_requested_photo(
            request_row.get("image_url"),
            request_row.get("photo_source"),
        )

        applied_spot_id = None
        if request_type == "add_spot":
            city_id = to_int(request_row.get("city_id"), 0)
            spot_name = (request_row.get("spot_name") or "").strip()
            if city_id <= 0 or not spot_name:
                db.rollback()
                return False, "Invalid add-spot request: city and spot name are required."

            cur.execute("SELECT id FROM cities WHERE id=%s", (city_id,))
            if not cur.fetchone():
                db.rollback()
                return False, "City from spot request no longer exists."

            cur.execute(
                """
                INSERT INTO master_spots(spot_name,image_url,photo_source,city_id,latitude,longitude,spot_details)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    spot_name,
                    requested_image,
                    requested_photo_source,
                    city_id,
                    request_row.get("latitude"),
                    request_row.get("longitude"),
                    request_row.get("spot_details") or None,
                ),
            )
            applied_spot_id = int(cur.lastrowid)
        elif request_type == "update_spot_image":
            spot_id = to_int(request_row.get("spot_id"), 0)
            if spot_id <= 0:
                db.rollback()
                return False, "Invalid image-change request: target spot is missing."

            cur.execute("SELECT id FROM master_spots WHERE id=%s", (spot_id,))
            if not cur.fetchone():
                db.rollback()
                return False, "Target spot no longer exists."

            cur.execute(
                "UPDATE master_spots SET image_url=%s, photo_source=%s WHERE id=%s",
                (requested_image, requested_photo_source, spot_id),
            )
            applied_spot_id = spot_id
        else:
            db.rollback()
            return False, "Unknown spot request type."

        cur.execute(
            """
            UPDATE spot_change_requests
            SET status='approved', admin_note=%s, reviewed_by=%s, reviewed_at=NOW(),
                applied_spot_id=%s, updated_at=NOW()
            WHERE id=%s
            """,
            (note or None, admin_id, applied_spot_id, spot_request_id),
        )
        db.commit()
        return True, f"Spot request #{spot_request_id} approved."
    except Exception as exc:
        db.rollback()
        return False, f"Failed to approve spot request #{spot_request_id}: {exc}"
    finally:
        cur.close()
        db.close()


def register_routes(app):
    @app.route("/admin", methods=["GET", "POST"])
    @login_required
    @role_required("admin")
    def admin():
        if request.method == "POST":
            user_id = to_int(request.form.get("user_id"), 0)
            issue_id = to_int(request.form.get("issue_id"), 0)
            spot_request_id = to_int(request.form.get("spot_request_id"), 0)
            action = (request.form.get("action") or "").strip()
            note = request.form.get("note", "").strip()
            if len(note) > 255:
                flash("Admin note must be 255 characters or less.")
                return redirect(url_for("admin"))

            if issue_id and action in {"set_issue_open", "set_issue_in_progress", "set_issue_resolved"}:
                issue_status_map = {
                    "set_issue_open": "open",
                    "set_issue_in_progress": "in_progress",
                    "set_issue_resolved": "resolved",
                }
                next_status = issue_status_map[action]
                execute_db(
                    """
                    UPDATE support_issues
                    SET status=%s, admin_note=%s, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (next_status, note or None, issue_id),
                )
                flash(f"Issue #{issue_id} marked as {next_status}.")
                return redirect(url_for("admin"))

            if spot_request_id and action in {"approve_spot_request", "reject_spot_request", "set_spot_request_pending"}:
                request_row = query_db(
                    "SELECT id, status FROM spot_change_requests WHERE id=%s",
                    (spot_request_id,),
                    one=True,
                )
                if not request_row:
                    flash("Spot request not found.")
                    return redirect(url_for("admin"))

                if action == "approve_spot_request":
                    ok, message = _approve_spot_request(spot_request_id, int(session["user_id"]), note)
                    flash(message)
                    return redirect(url_for("admin"))

                if action == "reject_spot_request":
                    execute_db(
                        """
                        UPDATE spot_change_requests
                        SET status='rejected', admin_note=%s, reviewed_by=%s, reviewed_at=NOW(), updated_at=NOW()
                        WHERE id=%s
                        """,
                        (note or None, int(session["user_id"]), spot_request_id),
                    )
                    flash(f"Spot request #{spot_request_id} rejected.")
                    return redirect(url_for("admin"))

                execute_db(
                    """
                    UPDATE spot_change_requests
                    SET status='pending', admin_note=%s, reviewed_by=NULL, reviewed_at=NULL, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (note or None, spot_request_id),
                )
                flash(f"Spot request #{spot_request_id} set back to pending.")
                return redirect(url_for("admin"))

            if user_id and action in {"approve", "reject", "set_pending"} and user_id != int(session["user_id"]):
                new_status_map = {
                    "approve": "approved",
                    "reject": "rejected",
                    "set_pending": "pending",
                }
                new_status = new_status_map[action]
                execute_db("UPDATE users SET status=%s WHERE id=%s", (new_status, user_id))
                if action == "approve":
                    execute_db(
                        """
                        UPDATE user_profiles
                        SET verification_badge=1, kyc_stage='verified', admin_note=%s, reviewed_at=NOW()
                        WHERE user_id=%s
                        """,
                        (note or None, user_id),
                    )
                elif action == "reject":
                    execute_db(
                        """
                        UPDATE user_profiles
                        SET verification_badge=0, kyc_stage='rejected', admin_note=%s, reviewed_at=NOW()
                        WHERE user_id=%s
                        """,
                        (note or None, user_id),
                    )
                else:
                    execute_db(
                        """
                        UPDATE user_profiles
                        SET verification_badge=0, kyc_stage='submitted_for_admin_approval', admin_note=%s
                        WHERE user_id=%s
                        """,
                        (note or None, user_id),
                    )
                execute_db(
                    """
                    INSERT INTO user_approval_logs(user_id, admin_id, action_taken, note)
                    VALUES(%s,%s,%s,%s)
                    """,
                    (user_id, int(session["user_id"]), action, note or None),
                )
                flash(f"User status updated to {new_status}.")
                return redirect(url_for("admin"))

            flash("Invalid admin action.")
            return redirect(url_for("admin"))

        pending_users = query_db(
            """
            SELECT
                u.id, u.full_name, u.email, u.phone, u.role, u.status, u.document_path,
                up.requested_role, up.business_name, up.provider_category,
                up.kyc_completed, up.kyc_stage, up.verification_badge, up.admin_note,
                up.identity_proof_path, up.business_proof_path, up.property_proof_path,
                up.vehicle_proof_path, up.driver_verification_path, up.bank_proof_path,
                up.address_proof_path, up.operational_photo_path
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id = u.id
            WHERE u.status='pending'
            ORDER BY u.id DESC
            """
        )
        for u in pending_users:
            required_docs = get_onboarding_document_requirements(u.get("role"), u.get("provider_category"))
            uploaded_count = 0
            docs = []
            for doc in required_docs:
                path = u.get(doc["field"])
                is_uploaded = bool(path)
                if is_uploaded:
                    uploaded_count += 1
                docs.append(
                    {
                        "field": doc["field"],
                        "label": doc["label"],
                        "path": path,
                        "is_uploaded": is_uploaded,
                    }
                )
            u["required_documents"] = docs
            u["required_doc_total"] = len(docs)
            u["required_doc_uploaded"] = uploaded_count
            u["required_docs_complete"] = uploaded_count == len(docs)

        pending_spot_requests = query_db(
            """
            SELECT
                r.id,
                r.organizer_id,
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
                u.full_name AS organizer_name,
                u.email AS organizer_email,
                c.city_name,
                s.state_name,
                ms.spot_name AS current_spot_name,
                ms.image_url AS current_image_url,
                ms.photo_source AS current_photo_source
            FROM spot_change_requests r
            JOIN users u ON u.id=r.organizer_id
            LEFT JOIN cities c ON c.id=r.city_id
            LEFT JOIN states s ON s.id=c.state_id
            LEFT JOIN master_spots ms ON ms.id=r.spot_id
            WHERE r.status='pending'
            ORDER BY r.id DESC
            LIMIT 200
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
                SUM(CASE WHEN role='hotel_provider' THEN 1 ELSE 0 END) AS total_providers,
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
                SUM(CASE WHEN start_date > CURDATE() THEN 1 ELSE 0 END) AS upcoming_tours,
                SUM(CASE WHEN start_date <= CURDATE() AND end_date >= CURDATE() THEN 1 ELSE 0 END) AS current_tours,
                SUM(CASE WHEN end_date < CURDATE() THEN 1 ELSE 0 END) AS completed_tours,
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
                COALESCE(SUM(admin_commission), 0) AS total_admin_commission,
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
                up.provider_category, up.business_name, up.kyc_stage, up.verification_badge
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id=u.id
            ORDER BY u.id DESC
            """
        )
        all_tours = query_db(
            """
            SELECT
                id, title, start_point, end_point, start_date, end_date, price,
                CASE
                    WHEN start_date > CURDATE() THEN 'upcoming'
                    WHEN start_date <= CURDATE() AND end_date >= CURDATE() THEN 'current'
                    WHEN end_date < CURDATE() THEN 'completed'
                    ELSE 'unknown'
                END AS lifecycle_status
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
        all_reviews = query_db(
            """
            SELECT
                r.id,
                r.target_type,
                r.target_id,
                r.rating,
                r.review_text,
                r.created_at,
                u.full_name AS user_name,
                u.role AS user_role
            FROM platform_reviews r
            JOIN users u ON u.id=r.user_id
            ORDER BY r.id DESC
            LIMIT 100
            """
        )
        all_issues = query_db(
            """
            SELECT
                s.id,
                s.user_id,
                s.user_role,
                s.subject,
                s.issue_text,
                s.status,
                s.admin_note,
                s.created_at,
                s.updated_at,
                u.full_name AS user_name
            FROM support_issues s
            JOIN users u ON u.id=s.user_id
            ORDER BY s.id DESC
            LIMIT 100
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
            pending_spot_requests=pending_spot_requests,
            all_reviews=all_reviews,
            all_issues=all_issues,
        )
