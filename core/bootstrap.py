"""Schema bootstrap helpers."""

from core.db import get_db


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


def _add_column_if_missing(cur, table_name, column_name, definition_sql):
    if _column_exists(cur, table_name, column_name):
        return
    cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition_sql}")


def ensure_tour_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tour_hotel_links (
            id INT NOT NULL AUTO_INCREMENT,
            tour_id INT NOT NULL,
            service_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_tour_hotel (tour_id, service_id),
            KEY idx_tour_hotel_tour (tour_id),
            KEY idx_tour_hotel_service (service_id),
            CONSTRAINT fk_tour_hotel_tour
                FOREIGN KEY (tour_id) REFERENCES tours(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_tour_hotel_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tour_transport_links (
            id INT NOT NULL AUTO_INCREMENT,
            tour_id INT NOT NULL,
            service_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_tour_transport (tour_id, service_id),
            KEY idx_tour_transport_tour (tour_id),
            KEY idx_tour_transport_service (service_id),
            CONSTRAINT fk_tour_transport_tour
                FOREIGN KEY (tour_id) REFERENCES tours(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_tour_transport_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tour_guide_links (
            id INT NOT NULL AUTO_INCREMENT,
            tour_id INT NOT NULL,
            service_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_tour_guide (tour_id, service_id),
            KEY idx_tour_guide_tour (tour_id),
            KEY idx_tour_guide_service (service_id),
            CONSTRAINT fk_tour_guide_tour
                FOREIGN KEY (tour_id) REFERENCES tours(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_tour_guide_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_guide_requests (
            id INT NOT NULL AUTO_INCREMENT,
            booking_id INT NOT NULL,
            service_id INT DEFAULT NULL,
            individual_requested BOOLEAN DEFAULT FALSE,
            note VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_booking_guide_booking (booking_id),
            KEY idx_booking_guide_service (service_id),
            CONSTRAINT fk_booking_guide_booking
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_booking_guide_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE SET NULL
        )
        """
    )
    _add_column_if_missing(cur, "tours", "travel_mode", "VARCHAR(40) DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "food_plan", "VARCHAR(60) DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "transport_details", "VARCHAR(255) DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "hotel_notes", "TEXT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "inclusions", "TEXT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "exclusions", "TEXT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "pickup_state_id", "INT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "pickup_city_id", "INT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "drop_state_id", "INT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "drop_city_id", "INT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "max_group_size", "INT DEFAULT NULL")
    _add_column_if_missing(cur, "tours", "difficulty_level", "VARCHAR(30) DEFAULT NULL")
    db.commit()
    cur.close()
    db.close()


def ensure_transport_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transport_profiles (
            id INT NOT NULL AUTO_INCREMENT,
            service_id INT NOT NULL,
            transport_type VARCHAR(60) NOT NULL,
            vehicle_model VARCHAR(120) DEFAULT NULL,
            registration_number VARCHAR(50) DEFAULT NULL,
            seating_capacity INT DEFAULT NULL,
            luggage_capacity VARCHAR(80) DEFAULT NULL,
            ac_available BOOLEAN DEFAULT TRUE,
            driver_available BOOLEAN DEFAULT TRUE,
            driver_name VARCHAR(120) DEFAULT NULL,
            driver_phone VARCHAR(30) DEFAULT NULL,
            price_per_day DECIMAL(10,2) DEFAULT NULL,
            price_per_km DECIMAL(10,2) DEFAULT NULL,
            permit_doc_path VARCHAR(255) DEFAULT NULL,
            insurance_doc_path VARCHAR(255) DEFAULT NULL,
            license_doc_path VARCHAR(255) DEFAULT NULL,
            rc_doc_path VARCHAR(255) DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_transport_service (service_id),
            CONSTRAINT fk_transport_profiles_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


def ensure_support_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INT PRIMARY KEY,
            requested_role VARCHAR(30) DEFAULT NULL,
            business_name VARCHAR(120) DEFAULT NULL,
            provider_category VARCHAR(60) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_user_profiles_user
                FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_approval_logs (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            admin_id INT NOT NULL,
            action_taken VARCHAR(20) NOT NULL,
            note TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_user_approval_user (user_id),
            KEY idx_user_approval_admin (admin_id),
            CONSTRAINT fk_user_approval_user
                FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_user_approval_admin
                FOREIGN KEY (admin_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


def ensure_hotel_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_profiles (
            id INT NOT NULL AUTO_INCREMENT,
            service_id INT NOT NULL,
            hotel_name VARCHAR(150) NOT NULL,
            brand_name VARCHAR(120) DEFAULT NULL,
            star_rating TINYINT DEFAULT 0,
            address_line1 VARCHAR(255) NOT NULL,
            address_line2 VARCHAR(255) DEFAULT NULL,
            locality VARCHAR(120) DEFAULT NULL,
            landmark VARCHAR(150) DEFAULT NULL,
            pincode VARCHAR(15) DEFAULT NULL,
            latitude DECIMAL(10,7) DEFAULT NULL,
            longitude DECIMAL(10,7) DEFAULT NULL,
            check_in_time TIME DEFAULT NULL,
            check_out_time TIME DEFAULT NULL,
            hotel_description TEXT,
            house_rules TEXT,
            couple_friendly BOOLEAN DEFAULT FALSE,
            pets_allowed BOOLEAN DEFAULT FALSE,
            parking_available BOOLEAN DEFAULT FALSE,
            breakfast_available BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_hotel_service (service_id),
            CONSTRAINT fk_hotel_profiles_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_images (
            id INT NOT NULL AUTO_INCREMENT,
            service_id INT NOT NULL,
            image_url VARCHAR(255) NOT NULL,
            image_title VARCHAR(120) DEFAULT NULL,
            is_cover BOOLEAN DEFAULT FALSE,
            sort_order INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_hotel_images_service (service_id),
            CONSTRAINT fk_hotel_images_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_room_types (
            id INT NOT NULL AUTO_INCREMENT,
            service_id INT NOT NULL,
            room_type_name VARCHAR(120) NOT NULL,
            bed_type VARCHAR(80) DEFAULT NULL,
            room_size_sqft INT DEFAULT NULL,
            max_guests INT DEFAULT 2,
            total_rooms INT DEFAULT 0,
            available_rooms INT DEFAULT 0,
            base_price DECIMAL(10,2) NOT NULL,
            strike_price DECIMAL(10,2) DEFAULT NULL,
            tax_percent DECIMAL(5,2) DEFAULT 0.00,
            breakfast_included BOOLEAN DEFAULT FALSE,
            ac_available BOOLEAN DEFAULT TRUE,
            wifi_available BOOLEAN DEFAULT TRUE,
            refundable BOOLEAN DEFAULT FALSE,
            cancellation_policy VARCHAR(255) DEFAULT NULL,
            room_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_room_service (service_id),
            CONSTRAINT fk_room_types_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS amenity_master (
            id INT NOT NULL AUTO_INCREMENT,
            amenity_name VARCHAR(100) NOT NULL,
            amenity_icon VARCHAR(100) DEFAULT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_amenity_name (amenity_name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_amenities (
            id INT NOT NULL AUTO_INCREMENT,
            service_id INT NOT NULL,
            amenity_id INT NOT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_hotel_amenity (service_id, amenity_id),
            KEY idx_hotel_amenity_service (service_id),
            KEY idx_hotel_amenity_amenity (amenity_id),
            CONSTRAINT fk_hotel_amenities_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_hotel_amenities_master
                FOREIGN KEY (amenity_id) REFERENCES amenity_master(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_room_inventory_logs (
            id INT NOT NULL AUTO_INCREMENT,
            room_type_id INT NOT NULL,
            changed_by INT NOT NULL,
            old_available INT NOT NULL,
            new_available INT NOT NULL,
            note VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_inventory_room (room_type_id),
            KEY idx_inventory_changed_by (changed_by),
            CONSTRAINT fk_inventory_room_type
                FOREIGN KEY (room_type_id) REFERENCES hotel_room_types(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_inventory_changed_by
                FOREIGN KEY (changed_by) REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_bookings (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            service_id INT NOT NULL,
            room_type_id INT NOT NULL,
            check_in_date DATE NOT NULL,
            check_out_date DATE NOT NULL,
            rooms_booked INT NOT NULL,
            guests_count INT NOT NULL,
            nights INT NOT NULL,
            total_amount DECIMAL(10,2) NOT NULL,
            status VARCHAR(30) DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_hotel_bookings_user (user_id),
            KEY idx_hotel_bookings_service (service_id),
            KEY idx_hotel_bookings_room_type (room_type_id),
            CONSTRAINT fk_hotel_bookings_user
                FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_hotel_bookings_service
                FOREIGN KEY (service_id) REFERENCES services(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_hotel_bookings_room_type
                FOREIGN KEY (room_type_id) REFERENCES hotel_room_types(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        INSERT IGNORE INTO amenity_master (amenity_name, amenity_icon) VALUES
            ('Free WiFi','bi-wifi'),
            ('AC','bi-snow'),
            ('Parking','bi-p-square'),
            ('Breakfast','bi-cup-hot'),
            ('Lift','bi-arrow-up-square'),
            ('Power Backup','bi-battery-charging'),
            ('TV','bi-tv'),
            ('24x7 Check-in','bi-clock')
        """
    )
    db.commit()
    cur.close()
    db.close()
