#!/usr/bin/env python3
"""Seed travelers, tour enrollments, and hotel bookings for demo/testing."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from werkzeug.security import generate_password_hash

from core.db import get_db


SEED_EMAIL_PREFIX = "seed.traveler."
SEED_EMAIL_DOMAIN = "tourgen.local"
SEED_PASSWORD = "Krish@1101"
ID_PROOF_TYPE = "Aadhaar Card"
ID_PROOF_FILE = "seed_id_proof.pdf"


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pick_phone(used: set[str], idx: int) -> str:
    candidate = 7800000000 + idx
    while str(candidate) in used:
        candidate += 97
    phone = str(candidate)
    used.add(phone)
    return phone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed travelers + bookings data")
    parser.add_argument("--count", type=int, default=75, help="Traveler count (default: 75)")
    parser.add_argument(
        "--tour-enrollments",
        type=int,
        default=58,
        help="Number of seeded travelers to enroll in tours (default: 58)",
    )
    parser.add_argument(
        "--hotel-bookings",
        type=int,
        default=36,
        help="Number of seeded travelers to create hotel bookings for (default: 36)",
    )
    parser.add_argument("--seed", type=int, default=20260220, help="Random seed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    traveler_count = max(1, min(80, args.count))
    tour_enrollment_target = max(1, min(traveler_count, args.tour_enrollments))
    hotel_booking_target = max(1, min(traveler_count, args.hotel_bookings))

    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT c.id, c.city_name, c.state_id, s.state_name
            FROM cities c
            JOIN states s ON s.id=c.state_id
            ORDER BY s.state_name, c.city_name
            """
        )
        cities = cur.fetchall()
        if len(cities) < traveler_count:
            raise RuntimeError(
                f"Need at least {traveler_count} cities, found only {len(cities)}."
            )

        cur.execute("SELECT phone FROM users WHERE phone IS NOT NULL")
        used_phones = {str(row["phone"]).strip() for row in cur.fetchall() if row.get("phone")}

        cur.execute(
            """
            SELECT
                t.id,
                t.title,
                t.price,
                t.child_price_percent,
                t.max_group_size,
                (
                    SELECT COALESCE(SUM(b.pax_count), 0)
                    FROM bookings b
                    WHERE b.tour_id=t.id AND b.status IN ('pending', 'paid')
                ) + (
                    SELECT COALESCE(SUM(eb.pax_count), 0)
                    FROM organizer_external_bookings eb
                    WHERE eb.tour_id=t.id
                ) AS booked
            FROM tours t
            WHERE t.tour_status='open'
            ORDER BY t.id ASC
            """
        )
        tours = cur.fetchall()
        if not tours:
            raise RuntimeError("No open tours available to seed enrollments.")

        cur.execute(
            """
            SELECT
                rt.id AS room_type_id,
                rt.service_id,
                rt.available_rooms,
                rt.base_price,
                rt.max_guests
            FROM hotel_room_types rt
            JOIN services s ON s.id=rt.service_id
            WHERE s.service_type='Hotel'
            ORDER BY rt.available_rooms DESC, rt.id ASC
            """
        )
        room_types = cur.fetchall()
        if not room_types:
            raise RuntimeError("No hotel room types available for hotel booking seed.")

        cur.execute(
            f"""
            SELECT u.id, u.email
            FROM users u
            WHERE u.email LIKE %s
            """,
            (f"{SEED_EMAIL_PREFIX}%@{SEED_EMAIL_DOMAIN}",),
        )
        existing_seeded_users = {
            (row["email"] or "").strip().lower(): int(row["id"])
            for row in cur.fetchall()
            if row.get("email")
        }

        hashed_password = generate_password_hash(SEED_PASSWORD)
        seeded_users: List[Dict[str, object]] = []
        new_users = 0
        updated_users = 0

        for idx in range(1, traveler_count + 1):
            city = cities[idx - 1]
            city_name = (city.get("city_name") or "City").strip()
            state_name = (city.get("state_name") or "State").strip()
            city_id = int(city["id"])
            email = f"{SEED_EMAIL_PREFIX}{idx:03d}@{SEED_EMAIL_DOMAIN}"
            full_name = f"{city_name} Traveler {idx:02d}"
            phone = pick_phone(used_phones, idx)
            pincode = str(350000 + idx)

            user_id = existing_seeded_users.get(email.lower())
            if user_id:
                cur.execute(
                    """
                    UPDATE users
                    SET full_name=%s, phone=%s, password=%s, role='customer', status='approved'
                    WHERE id=%s
                    """,
                    (full_name, phone, hashed_password, user_id),
                )
                updated_users += 1
            else:
                cur.execute(
                    """
                    INSERT INTO users(full_name, email, phone, password, role, status, document_path)
                    VALUES(%s,%s,%s,%s,'customer','approved',NULL)
                    """,
                    (full_name, email, phone, hashed_password),
                )
                user_id = int(cur.lastrowid)
                new_users += 1

            cur.execute(
                """
                INSERT INTO user_profiles(
                    user_id, requested_role, city_id, city, district, pincode,
                    kyc_completed, kyc_stage, verification_badge
                )
                VALUES(%s,'traveler',%s,%s,%s,%s,1,'verified',1)
                ON DUPLICATE KEY UPDATE
                    requested_role=VALUES(requested_role),
                    city_id=VALUES(city_id),
                    city=VALUES(city),
                    district=VALUES(district),
                    pincode=VALUES(pincode),
                    kyc_completed=VALUES(kyc_completed),
                    kyc_stage=VALUES(kyc_stage),
                    verification_badge=VALUES(verification_badge)
                """,
                (user_id, city_id, city_name, state_name, pincode),
            )

            seeded_users.append(
                {
                    "user_id": user_id,
                    "full_name": full_name,
                    "phone": phone,
                    "city_id": city_id,
                    "city_name": city_name,
                }
            )

        # Create tour enrollments
        tour_remaining: Dict[int, int] = {}
        tours_by_id = {}
        for tour in tours:
            tour_id = int(tour["id"])
            max_group = int(tour["max_group_size"] or 0)
            booked = int(tour["booked"] or 0)
            remaining = max(0, max_group - booked) if max_group > 0 else 999999
            tour_remaining[tour_id] = remaining
            tours_by_id[tour_id] = tour

        tour_ids = [int(t["id"]) for t in tours]
        bookings_created = 0
        payments_created = 0
        travelers_rows_created = 0
        touched_tours: set[int] = set()

        booking_users = seeded_users[:tour_enrollment_target]
        for i, user in enumerate(booking_users):
            user_id = int(user["user_id"])
            cur.execute("SELECT id FROM bookings WHERE user_id=%s LIMIT 1", (user_id,))
            if cur.fetchone():
                continue

            eligible_tour_ids = [tid for tid in tour_ids if tour_remaining.get(tid, 0) > 0]
            if not eligible_tour_ids:
                break
            chosen_tour_id = eligible_tour_ids[i % len(eligible_tour_ids)]
            tour_row = tours_by_id[chosen_tour_id]

            max_pax = min(4, tour_remaining.get(chosen_tour_id, 4))
            pax_count = max(1, rng.randint(1, max_pax))
            booking_status = "paid" if (i % 3 == 0) else "pending"
            booking_date = (datetime.now() - timedelta(days=rng.randint(1, 45))).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            id_number = f"{rng.randint(100000000000, 999999999999)}"

            cur.execute(
                """
                INSERT INTO bookings(
                    user_id,tour_id,pax_count,date,status,id_proof_type,id_proof_number,id_proof_file_path,
                    guide_service_id,guide_individual_requested,guide_note,
                    room_hotel_service_id,room_type_id,room_rooms_requested,room_note
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NULL,0,NULL,NULL,NULL,1,NULL)
                """,
                (
                    user_id,
                    chosen_tour_id,
                    pax_count,
                    booking_date,
                    booking_status,
                    ID_PROOF_TYPE,
                    id_number,
                    ID_PROOF_FILE,
                ),
            )
            booking_id = int(cur.lastrowid)
            bookings_created += 1
            touched_tours.add(chosen_tour_id)
            tour_remaining[chosen_tour_id] = max(0, tour_remaining[chosen_tour_id] - pax_count)

            child_slot = rng.randint(0, pax_count - 1) if pax_count > 1 and (i % 4 == 0) else -1
            child_count = 0
            for traveler_idx in range(pax_count):
                is_child = 1 if traveler_idx == child_slot else 0
                age = rng.randint(6, 11) if is_child else rng.randint(19, 58)
                if is_child:
                    child_count += 1
                cur.execute(
                    """
                    INSERT INTO booking_travelers(
                        booking_id, full_name, age, id_proof_type, id_proof_number, contact_number, is_child
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        booking_id,
                        f"{user['full_name']} Member {traveler_idx + 1}",
                        age,
                        ID_PROOF_TYPE,
                        f"{rng.randint(100000000000, 999999999999)}",
                        user["phone"],
                        is_child,
                    ),
                )
                travelers_rows_created += 1

            if booking_status == "paid":
                adult_count = max(0, pax_count - child_count)
                unit_price = Decimal(str(tour_row.get("price") or 0))
                child_percent = Decimal(str(tour_row.get("child_price_percent") or 100))
                child_multiplier = child_percent / Decimal("100")
                amount = quantize_money(
                    unit_price * Decimal(adult_count) + (unit_price * child_multiplier * Decimal(child_count))
                )
                admin_commission = quantize_money(amount * Decimal("0.01"))
                organizer_earning = quantize_money(amount - admin_commission)
                cur.execute(
                    """
                    INSERT INTO payments(booking_id, amount, admin_commission, organizer_earning, payment_provider, paid)
                    VALUES(%s,%s,%s,%s,'seed',1)
                    """,
                    (booking_id, amount, admin_commission, organizer_earning),
                )
                payments_created += 1

        for tour_id in touched_tours:
            original_tour = tours_by_id[tour_id]
            max_group = int(original_tour.get("max_group_size") or 0)
            if max_group > 0:
                next_status = "full" if tour_remaining.get(tour_id, 0) <= 0 else "open"
                cur.execute("UPDATE tours SET tour_status=%s WHERE id=%s", (next_status, tour_id))

        # Create hotel bookings
        room_remaining = {int(r["room_type_id"]): int(r["available_rooms"] or 0) for r in room_types}
        room_info = {int(r["room_type_id"]): r for r in room_types}
        room_type_ids = [int(r["room_type_id"]) for r in room_types]
        hotel_bookings_created = 0
        updated_room_types: set[int] = set()

        hotel_users = seeded_users[-hotel_booking_target:]
        for i, user in enumerate(hotel_users):
            user_id = int(user["user_id"])
            cur.execute("SELECT id FROM hotel_bookings WHERE user_id=%s LIMIT 1", (user_id,))
            if cur.fetchone():
                continue

            available_rooms = [rid for rid in room_type_ids if room_remaining.get(rid, 0) > 0]
            if not available_rooms:
                break
            room_type_id = available_rooms[i % len(available_rooms)]
            room = room_info[room_type_id]
            service_id = int(room["service_id"])
            max_guests = max(1, int(room.get("max_guests") or 2))
            guests_count = rng.randint(1, min(4, max_guests))
            nights = rng.randint(1, 3)
            check_in = datetime.now().date() + timedelta(days=rng.randint(5, 65))
            check_out = check_in + timedelta(days=nights)
            base_price = Decimal(str(room.get("base_price") or 0))
            total_amount = quantize_money(base_price * Decimal(nights))
            status = ["confirmed", "checked_in", "completed"][i % 3]

            cur.execute(
                """
                INSERT INTO hotel_bookings(
                    user_id, service_id, room_type_id,
                    id_proof_type, id_proof_number, id_proof_file_path,
                    check_in_date, check_out_date, rooms_booked, guests_count, nights, total_amount, status
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    service_id,
                    room_type_id,
                    ID_PROOF_TYPE,
                    f"{rng.randint(100000000000, 999999999999)}",
                    ID_PROOF_FILE,
                    check_in,
                    check_out,
                    guests_count,
                    nights,
                    total_amount,
                    status,
                ),
            )
            hotel_bookings_created += 1
            room_remaining[room_type_id] = max(0, room_remaining[room_type_id] - 1)
            updated_room_types.add(room_type_id)

        for room_type_id in updated_room_types:
            cur.execute(
                "UPDATE hotel_room_types SET available_rooms=%s WHERE id=%s",
                (room_remaining[room_type_id], room_type_id),
            )

        db.commit()

        print("Seed completed.")
        print(f"Travelers targeted: {traveler_count}")
        print(f"Travelers created: {new_users}")
        print(f"Travelers updated: {updated_users}")
        print(f"Tour enrollments created: {bookings_created}")
        print(f"Booking traveler rows created: {travelers_rows_created}")
        print(f"Payments created: {payments_created}")
        print(f"Hotel bookings created: {hotel_bookings_created}")
        print(f"Shared traveler password: {SEED_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()
        db.close()


if __name__ == "__main__":
    main()
