"""Database helpers for MySQL."""

import os
import time

import mysql.connector

from core.config import MYSQL_CONFIG


DB_RETRY_ATTEMPTS = max(1, int(os.getenv("DB_RETRY_ATTEMPTS", "3")))
DB_RETRY_DELAY_SEC = max(0.0, float(os.getenv("DB_RETRY_DELAY_SEC", "0.4")))
TRANSIENT_DB_ERROR_CODES = {1205, 1213, 2002, 2003, 2006, 2013, 2055}


def _is_retryable_db_error(exc):
    errno = getattr(exc, "errno", None)
    if errno in TRANSIENT_DB_ERROR_CODES:
        return True
    return isinstance(exc, (mysql.connector.InterfaceError, mysql.connector.OperationalError))


def _run_with_retry(operation, runner, attempts=DB_RETRY_ATTEMPTS):
    last_exc = None
    safe_attempts = max(1, int(attempts))
    for attempt in range(1, safe_attempts + 1):
        try:
            return runner()
        except mysql.connector.Error as exc:
            last_exc = exc
            if attempt >= safe_attempts or not _is_retryable_db_error(exc):
                raise
            wait_s = DB_RETRY_DELAY_SEC * attempt
            print(f"[db-retry] {operation} failed (attempt {attempt}/{safe_attempts}): {exc}")
            if wait_s > 0:
                time.sleep(wait_s)
    raise last_exc


def get_db(retries=None):
    retry_attempts = DB_RETRY_ATTEMPTS if retries is None else max(1, int(retries))
    return _run_with_retry("connect", lambda: mysql.connector.connect(**MYSQL_CONFIG), attempts=retry_attempts)


def query_db(query, args=(), one=False):
    def _run_once():
        db = None
        cur = None
        try:
            db = get_db(retries=1)
            cur = db.cursor(dictionary=True)
            cur.execute(query, args)
            return cur.fetchone() if one else cur.fetchall()
        finally:
            if cur is not None:
                cur.close()
            if db is not None:
                db.close()

    return _run_with_retry("query", _run_once)


def execute_db(query, args=()):
    def _run_once():
        db = None
        cur = None
        try:
            db = get_db(retries=1)
            cur = db.cursor()
            cur.execute(query, args)
            db.commit()
            return cur.lastrowid
        finally:
            if cur is not None:
                cur.close()
            if db is not None:
                db.close()

    return _run_with_retry("execute", _run_once)


def _table_exists(cur, table_name):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cur.fetchone() is not None


def _column_exists(cur, table_name, column_name):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def _foreign_key_exists(cur, table_name, column_name, referenced_table):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
          AND REFERENCED_TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name, referenced_table),
    )
    return cur.fetchone() is not None


def _column_type(cur, table_name, column_name):
    cur.execute(
        """
        SELECT COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _add_column_if_missing(cur, table_name, column_name, column_definition):
    if not _table_exists(cur, table_name):
        return
    if _column_exists(cur, table_name, column_name):
        return
    cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {column_definition}")


def ensure_runtime_schema():
    """Create/patch runtime tables and columns required by latest features."""
    db = get_db()
    cur = db.cursor()
    try:
        has_tours = _table_exists(cur, "tours")
        has_services = _table_exists(cur, "services")
        has_bookings = _table_exists(cur, "bookings")
        has_hotel_room_types = _table_exists(cur, "hotel_room_types")
        has_users = _table_exists(cur, "users")
        has_cities = _table_exists(cur, "cities")
        has_master_spots = _table_exists(cur, "master_spots")

        if has_tours and has_services:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tour_service_links (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tour_id INT NOT NULL,
                    service_id INT NOT NULL,
                    service_kind VARCHAR(20) NOT NULL,
                    UNIQUE KEY uk_tour_service_link (tour_id, service_id, service_kind),
                    KEY idx_tour_service_link_tour (tour_id),
                    KEY idx_tour_service_link_service (service_id),
                    KEY idx_tour_service_link_kind (service_kind),
                    CONSTRAINT fk_tour_service_link_tour
                        FOREIGN KEY (tour_id) REFERENCES tours(id) ON DELETE CASCADE,
                    CONSTRAINT fk_tour_service_link_service
                        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tour_hotel_stays (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tour_id INT NOT NULL,
                    service_id INT NOT NULL,
                    check_in_date DATE NOT NULL,
                    check_out_date DATE NOT NULL,
                    nights INT NOT NULL DEFAULT 1,
                    stay_notes VARCHAR(255) DEFAULT NULL,
                    UNIQUE KEY uk_tour_hotel_stay (tour_id, service_id, check_in_date, check_out_date),
                    KEY idx_tour_hotel_stay_tour (tour_id),
                    KEY idx_tour_hotel_stay_service (service_id),
                    CONSTRAINT fk_tour_hotel_stay_tour
                        FOREIGN KEY (tour_id) REFERENCES tours(id) ON DELETE CASCADE,
                    CONSTRAINT fk_tour_hotel_stay_service
                        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
                )
                """
            )

        if has_tours and has_cities:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tour_city_schedules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tour_id INT NOT NULL,
                    city_id INT NOT NULL,
                    arrival_datetime DATETIME DEFAULT NULL,
                    departure_datetime DATETIME DEFAULT NULL,
                    sequence_no INT NOT NULL DEFAULT 1,
                    note VARCHAR(255) DEFAULT NULL,
                    KEY idx_tour_city_schedule_tour (tour_id),
                    KEY idx_tour_city_schedule_city (city_id),
                    CONSTRAINT fk_tour_city_schedule_tour
                        FOREIGN KEY (tour_id) REFERENCES tours(id) ON DELETE CASCADE,
                    CONSTRAINT fk_tour_city_schedule_city
                        FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
                )
                """
            )

        if has_users and has_services and has_hotel_room_types:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hotel_bookings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    service_id INT NOT NULL,
                    room_type_id INT NOT NULL,
                    id_proof_type VARCHAR(50) DEFAULT NULL,
                    id_proof_number VARCHAR(120) DEFAULT NULL,
                    id_proof_file_path VARCHAR(255) DEFAULT NULL,
                    check_in_date DATE NOT NULL,
                    check_out_date DATE NOT NULL,
                    rooms_booked INT NOT NULL DEFAULT 1,
                    guests_count INT NOT NULL DEFAULT 1,
                    nights INT NOT NULL DEFAULT 1,
                    total_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    status VARCHAR(30) DEFAULT 'confirmed',
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_hotel_booking_user (user_id),
                    KEY idx_hotel_booking_service (service_id),
                    KEY idx_hotel_booking_room_type (room_type_id),
                    CONSTRAINT fk_hotel_booking_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_hotel_booking_service
                        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
                    CONSTRAINT fk_hotel_booking_room_type
                        FOREIGN KEY (room_type_id) REFERENCES hotel_room_types(id) ON DELETE CASCADE
                )
                """
            )

        if has_bookings:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS booking_travelers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    booking_id INT NOT NULL,
                    full_name VARCHAR(120) NOT NULL,
                    age INT NOT NULL,
                    id_proof_type VARCHAR(50) DEFAULT NULL,
                    id_proof_number VARCHAR(120) DEFAULT NULL,
                    contact_number VARCHAR(20) DEFAULT NULL,
                    is_child TINYINT(1) NOT NULL DEFAULT 0,
                    KEY idx_booking_travelers_booking (booking_id),
                    CONSTRAINT fk_booking_travelers_booking
                        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
                )
                """
            )

        if has_tours:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS organizer_external_bookings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    organizer_id INT NOT NULL,
                    tour_id INT NOT NULL,
                    traveler_name VARCHAR(120) NOT NULL,
                    contact_number VARCHAR(20) DEFAULT NULL,
                    pax_count INT NOT NULL DEFAULT 1,
                    amount_received DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    admin_commission DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    organizer_earning DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    notes VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_external_booking_tour (tour_id),
                    KEY idx_external_booking_organizer (organizer_id),
                    CONSTRAINT fk_external_booking_tour
                        FOREIGN KEY (tour_id) REFERENCES tours(id) ON DELETE CASCADE
                )
                """
            )

        if has_users:
            role_col_type = (_column_type(cur, "users", "role") or "").lower()
            if role_col_type.startswith("enum("):
                # Older snapshots can have a restricted enum set.
                required_roles = {"admin", "organizer", "hotel_provider", "customer"}
                if not all(f"'{role}'" in role_col_type for role in required_roles):
                    try:
                        cur.execute("ALTER TABLE users MODIFY COLUMN role VARCHAR(50) NOT NULL DEFAULT 'customer'")
                    except mysql.connector.Error:
                        # Ignore in environments with restrictive DDL permissions.
                        pass

            # Legacy migration: provider becomes hotel_provider; transport role is removed.
            cur.execute("UPDATE users SET role='hotel_provider' WHERE role='provider'")
            cur.execute("UPDATE users SET role='organizer' WHERE role IN ('transport_provider', 'transport')")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS support_issues (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    user_role VARCHAR(50) DEFAULT NULL,
                    subject VARCHAR(160) NOT NULL,
                    issue_text TEXT NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'open',
                    admin_note VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    KEY idx_support_issue_user (user_id),
                    KEY idx_support_issue_status (status),
                    CONSTRAINT fk_support_issue_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_reviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    user_role VARCHAR(50) DEFAULT NULL,
                    target_type VARCHAR(30) NOT NULL DEFAULT 'platform',
                    target_id INT DEFAULT NULL,
                    rating TINYINT NOT NULL DEFAULT 5,
                    review_text VARCHAR(500) NOT NULL,
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_platform_review_user (user_id),
                    KEY idx_platform_review_target (target_type, target_id),
                    CONSTRAINT fk_platform_review_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

        if has_users and has_cities and has_master_spots:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS spot_change_requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    organizer_id INT NOT NULL,
                    request_type VARCHAR(30) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    spot_id INT DEFAULT NULL,
                    city_id INT DEFAULT NULL,
                    spot_name VARCHAR(150) NOT NULL,
                    image_url VARCHAR(255) DEFAULT NULL,
                    photo_source VARCHAR(20) DEFAULT 'local_file',
                    latitude DECIMAL(10,7) DEFAULT NULL,
                    longitude DECIMAL(10,7) DEFAULT NULL,
                    spot_details TEXT,
                    admin_note VARCHAR(255) DEFAULT NULL,
                    reviewed_by INT DEFAULT NULL,
                    applied_spot_id INT DEFAULT NULL,
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP NULL DEFAULT NULL,
                    KEY idx_spot_req_status (status),
                    KEY idx_spot_req_organizer (organizer_id),
                    KEY idx_spot_req_city (city_id),
                    KEY idx_spot_req_spot (spot_id),
                    KEY idx_spot_req_reviewed_by (reviewed_by),
                    KEY idx_spot_req_applied_spot (applied_spot_id),
                    CONSTRAINT fk_spot_req_organizer
                        FOREIGN KEY (organizer_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_spot_req_city
                        FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL,
                    CONSTRAINT fk_spot_req_spot
                        FOREIGN KEY (spot_id) REFERENCES master_spots(id) ON DELETE SET NULL,
                    CONSTRAINT fk_spot_req_reviewer
                        FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
                    CONSTRAINT fk_spot_req_applied_spot
                        FOREIGN KEY (applied_spot_id) REFERENCES master_spots(id) ON DELETE SET NULL
                )
                """
            )

        # Backward-compatible column guards for older database snapshots.
        column_patches = [
            ("bookings", "pax_count", "`pax_count` INT NOT NULL DEFAULT 1"),
            ("bookings", "id_proof_type", "`id_proof_type` VARCHAR(50) DEFAULT NULL"),
            ("bookings", "id_proof_number", "`id_proof_number` VARCHAR(120) DEFAULT NULL"),
            ("bookings", "id_proof_file_path", "`id_proof_file_path` VARCHAR(255) DEFAULT NULL"),
            ("bookings", "guide_service_id", "`guide_service_id` INT DEFAULT NULL"),
            (
                "bookings",
                "guide_individual_requested",
                "`guide_individual_requested` TINYINT(1) NOT NULL DEFAULT 0",
            ),
            ("bookings", "guide_note", "`guide_note` VARCHAR(255) DEFAULT NULL"),
            ("bookings", "room_hotel_service_id", "`room_hotel_service_id` INT DEFAULT NULL"),
            ("bookings", "room_type_id", "`room_type_id` INT DEFAULT NULL"),
            ("bookings", "room_rooms_requested", "`room_rooms_requested` INT NOT NULL DEFAULT 1"),
            ("bookings", "room_note", "`room_note` VARCHAR(255) DEFAULT NULL"),
            ("payments", "admin_commission", "`admin_commission` DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            ("payments", "organizer_earning", "`organizer_earning` DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            ("payments", "payment_provider", "`payment_provider` VARCHAR(30) DEFAULT NULL"),
            ("tours", "min_group_size", "`min_group_size` INT NOT NULL DEFAULT 1"),
            ("tours", "terms_conditions", "`terms_conditions` TEXT"),
            ("tours", "child_price_percent", "`child_price_percent` DECIMAL(5,2) NOT NULL DEFAULT 100.00"),
            ("tours", "departure_datetime", "`departure_datetime` DATETIME DEFAULT NULL"),
            ("tours", "return_datetime", "`return_datetime` DATETIME DEFAULT NULL"),
            ("master_spots", "image_url", "`image_url` VARCHAR(255) DEFAULT 'demo.jpg'"),
            ("master_spots", "photo_source", "`photo_source` VARCHAR(20) DEFAULT 'local_file'"),
            ("master_spots", "spot_details", "`spot_details` TEXT"),
            ("master_spots", "latitude", "`latitude` DECIMAL(10,7) DEFAULT NULL"),
            ("master_spots", "longitude", "`longitude` DECIMAL(10,7) DEFAULT NULL"),
            (
                "hotel_profiles",
                "listing_status",
                "`listing_status` VARCHAR(20) NOT NULL DEFAULT 'active'",
            ),
            ("hotel_profiles", "terms_conditions", "`terms_conditions` TEXT"),
            ("hotel_profiles", "owner_name", "`owner_name` VARCHAR(120) DEFAULT NULL"),
            ("hotel_profiles", "hotel_contact_phone", "`hotel_contact_phone` VARCHAR(20) DEFAULT NULL"),
            ("hotel_profiles", "hotel_contact_email", "`hotel_contact_email` VARCHAR(120) DEFAULT NULL"),
            ("hotel_profiles", "gst_number", "`gst_number` VARCHAR(30) DEFAULT NULL"),
            ("hotel_profiles", "trade_license_number", "`trade_license_number` VARCHAR(60) DEFAULT NULL"),
            ("hotel_profiles", "registration_doc_path", "`registration_doc_path` VARCHAR(255) DEFAULT NULL"),
            ("hotel_bookings", "id_proof_type", "`id_proof_type` VARCHAR(50) DEFAULT NULL"),
            ("hotel_bookings", "id_proof_number", "`id_proof_number` VARCHAR(120) DEFAULT NULL"),
            ("hotel_bookings", "id_proof_file_path", "`id_proof_file_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "requested_role", "`requested_role` VARCHAR(50) DEFAULT NULL"),
            ("user_profiles", "business_name", "`business_name` VARCHAR(120) DEFAULT NULL"),
            ("user_profiles", "provider_category", "`provider_category` VARCHAR(60) DEFAULT NULL"),
            ("user_profiles", "bio", "`bio` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "gender", "`gender` VARCHAR(20) DEFAULT NULL"),
            ("user_profiles", "date_of_birth", "`date_of_birth` DATE DEFAULT NULL"),
            ("user_profiles", "emergency_contact", "`emergency_contact` VARCHAR(20) DEFAULT NULL"),
            ("user_profiles", "address_line", "`address_line` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "city_id", "`city_id` INT DEFAULT NULL"),
            ("user_profiles", "city", "`city` VARCHAR(120) DEFAULT NULL"),
            ("user_profiles", "district", "`district` VARCHAR(120) DEFAULT NULL"),
            ("user_profiles", "pincode", "`pincode` VARCHAR(15) DEFAULT NULL"),
            ("user_profiles", "kyc_completed", "`kyc_completed` TINYINT(1) NOT NULL DEFAULT 0"),
            ("user_profiles", "kyc_stage", "`kyc_stage` VARCHAR(60) DEFAULT 'registered'"),
            ("user_profiles", "verification_badge", "`verification_badge` TINYINT(1) NOT NULL DEFAULT 0"),
            ("user_profiles", "identity_proof_path", "`identity_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "business_proof_path", "`business_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "property_proof_path", "`property_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "vehicle_proof_path", "`vehicle_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "driver_verification_path", "`driver_verification_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "bank_proof_path", "`bank_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "address_proof_path", "`address_proof_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "operational_photo_path", "`operational_photo_path` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "admin_note", "`admin_note` VARCHAR(255) DEFAULT NULL"),
            ("user_profiles", "reviewed_at", "`reviewed_at` TIMESTAMP NULL DEFAULT NULL"),
            (
                "user_profiles",
                "updated_at",
                "`updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
            ),
        ]
        for table_name, column_name, column_definition in column_patches:
            _add_column_if_missing(cur, table_name, column_name, column_definition)

        # Merge booking guide/room request detail tables into bookings.
        if has_bookings and _table_exists(cur, "booking_guide_requests"):
            cur.execute(
                """
                UPDATE bookings b
                JOIN booking_guide_requests g ON g.booking_id=b.id
                SET
                    b.guide_individual_requested = CASE
                        WHEN b.guide_service_id IS NULL AND g.service_id IS NOT NULL
                            THEN COALESCE(g.individual_requested, 0)
                        ELSE COALESCE(b.guide_individual_requested, 0)
                    END,
                    b.guide_service_id = COALESCE(b.guide_service_id, g.service_id),
                    b.guide_note = COALESCE(NULLIF(b.guide_note, ''), g.note)
                """
            )

        if has_bookings and _table_exists(cur, "booking_room_requests"):
            cur.execute(
                """
                UPDATE bookings b
                JOIN booking_room_requests r ON r.booking_id=b.id
                SET
                    b.room_rooms_requested = CASE
                        WHEN b.room_type_id IS NULL AND r.room_type_id IS NOT NULL
                            THEN COALESCE(r.rooms_requested, 1)
                        ELSE COALESCE(NULLIF(b.room_rooms_requested, 0), 1)
                    END,
                    b.room_hotel_service_id = COALESCE(b.room_hotel_service_id, r.hotel_service_id),
                    b.room_type_id = COALESCE(b.room_type_id, r.room_type_id),
                    b.room_note = COALESCE(NULLIF(b.room_note, ''), r.note)
                """
            )

        if has_bookings and has_services and _column_exists(cur, "bookings", "guide_service_id"):
            if not _foreign_key_exists(cur, "bookings", "guide_service_id", "services"):
                try:
                    cur.execute(
                        """
                        ALTER TABLE bookings
                        ADD CONSTRAINT fk_bookings_guide_service
                        FOREIGN KEY (guide_service_id) REFERENCES services(id) ON DELETE SET NULL
                        """
                    )
                except mysql.connector.Error:
                    pass

        if has_bookings and has_services and _column_exists(cur, "bookings", "room_hotel_service_id"):
            if not _foreign_key_exists(cur, "bookings", "room_hotel_service_id", "services"):
                try:
                    cur.execute(
                        """
                        ALTER TABLE bookings
                        ADD CONSTRAINT fk_bookings_room_service
                        FOREIGN KEY (room_hotel_service_id) REFERENCES services(id) ON DELETE SET NULL
                        """
                    )
                except mysql.connector.Error:
                    pass

        if has_bookings and has_hotel_room_types and _column_exists(cur, "bookings", "room_type_id"):
            if not _foreign_key_exists(cur, "bookings", "room_type_id", "hotel_room_types"):
                try:
                    cur.execute(
                        """
                        ALTER TABLE bookings
                        ADD CONSTRAINT fk_bookings_room_type
                        FOREIGN KEY (room_type_id) REFERENCES hotel_room_types(id) ON DELETE SET NULL
                        """
                    )
                except mysql.connector.Error:
                    pass

        # Backfill coordinates from legacy typo columns if they exist.
        if has_master_spots and _column_exists(cur, "master_spots", "latitude"):
            if _column_exists(cur, "master_spots", "letitude"):
                cur.execute(
                    """
                    UPDATE master_spots
                    SET latitude = COALESCE(latitude, letitude)
                    WHERE letitude IS NOT NULL
                    """
                )
            if _column_exists(cur, "master_spots", "longitude") and _column_exists(cur, "master_spots", "longtitude"):
                cur.execute(
                    """
                    UPDATE master_spots
                    SET longitude = COALESCE(longitude, longtitude)
                    WHERE longtitude IS NOT NULL
                    """
                )

        # Ensure each user has one profile row for consistent onboarding/location fields.
        has_user_profiles = _table_exists(cur, "user_profiles")
        if has_user_profiles and has_users:
            cur.execute(
                """
                UPDATE user_profiles
                SET
                    requested_role=CASE
                        WHEN requested_role IN ('transport_provider', 'transport') THEN 'organizer'
                        ELSE 'hotel_provider'
                    END,
                    provider_category=COALESCE(NULLIF(provider_category, ''), 'Hotel')
                WHERE requested_role IN ('provider', 'transport_provider', 'transport')
                """
            )
            cur.execute(
                """
                INSERT INTO user_profiles(
                    user_id, requested_role, kyc_completed, kyc_stage, verification_badge
                )
                SELECT
                    u.id,
                    CASE WHEN u.role='customer' THEN 'traveler' ELSE u.role END,
                    CASE WHEN u.status='approved' THEN 1 ELSE 0 END,
                    CASE WHEN u.status='approved' THEN 'verified' ELSE 'registered' END,
                    CASE WHEN u.status='approved' THEN 1 ELSE 0 END
                FROM users u
                LEFT JOIN user_profiles up ON up.user_id=u.id
                WHERE up.user_id IS NULL
                """
            )

        # Add foreign key for profile city only if it's not present already.
        has_city_column = _column_exists(cur, "user_profiles", "city_id")
        if has_user_profiles and has_cities and has_city_column:
            if _column_exists(cur, "user_profiles", "city"):
                cur.execute(
                    """
                    UPDATE user_profiles up
                    JOIN cities c ON c.id=up.city_id
                    SET up.city = COALESCE(NULLIF(up.city, ''), c.city_name)
                    WHERE up.city_id IS NOT NULL
                    """
                )
            if _column_exists(cur, "user_profiles", "district"):
                cur.execute(
                    """
                    UPDATE user_profiles up
                    JOIN cities c ON c.id=up.city_id
                    SET up.district = COALESCE(NULLIF(up.district, ''), c.city_name)
                    WHERE up.city_id IS NOT NULL
                    """
                )
            if not _foreign_key_exists(cur, "user_profiles", "city_id", "cities"):
                try:
                    cur.execute(
                        """
                        ALTER TABLE user_profiles
                        ADD CONSTRAINT fk_user_profiles_city
                        FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
                        """
                    )
                except mysql.connector.Error:
                    # Some environments may already have an equivalent FK with a different name.
                    pass

        # Remove deprecated OTP column from profile schema.
        if _column_exists(cur, "user_profiles", "otp_verified"):
            try:
                cur.execute("ALTER TABLE user_profiles DROP COLUMN otp_verified")
            except mysql.connector.Error:
                pass

        # Remove fields that are no longer used by current flows.
        obsolete_columns = [
            ("self_trip_plans", "transport_service_id"),
            ("booking_travelers", "created_at"),
            ("hotel_images", "created_at"),
            ("self_trip_plan_items", "created_at"),
            ("tour_city_schedules", "created_at"),
            ("tour_hotel_stays", "created_at"),
            ("tour_service_links", "created_at"),
        ]
        for table_name, column_name in obsolete_columns:
            if _column_exists(cur, table_name, column_name):
                try:
                    cur.execute(f"ALTER TABLE `{table_name}` DROP COLUMN `{column_name}`")
                except mysql.connector.Error:
                    pass

        # Remove transport service-table flow; tours keep text-based transport_details only.
        if has_tours and has_services and _table_exists(cur, "tour_service_links"):
            try:
                cur.execute(
                    """
                    UPDATE tours t
                    SET t.transport_details = COALESCE(
                        NULLIF(t.transport_details, ''),
                        (
                            SELECT GROUP_CONCAT(DISTINCT s.service_name ORDER BY s.service_name SEPARATOR ', ')
                            FROM tour_service_links tsl
                            JOIN services s ON s.id=tsl.service_id
                            WHERE tsl.tour_id=t.id
                              AND (tsl.service_kind='Transport' OR s.service_type='Transport')
                        )
                    )
                    WHERE t.transport_details IS NULL OR t.transport_details=''
                    """
                )
                cur.execute(
                    """
                    DELETE tsl
                    FROM tour_service_links tsl
                    JOIN services s ON s.id=tsl.service_id
                    WHERE tsl.service_kind='Transport' OR s.service_type='Transport'
                    """
                )
            except mysql.connector.Error:
                pass

        # Deprecated flow cleanup.
        for legacy_table in (
            "booking_guide_requests",
            "booking_room_requests",
            "transport_bookings",
            "transport_inventory_logs",
            "transport_profiles",
        ):
            if _table_exists(cur, legacy_table):
                try:
                    cur.execute(f"DROP TABLE {legacy_table}")
                except mysql.connector.Error:
                    # Ignore environments where the app user cannot drop tables.
                    pass

        if has_services:
            try:
                cur.execute("DELETE FROM services WHERE service_type='Transport'")
            except mysql.connector.Error:
                pass

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()
        db.close()
