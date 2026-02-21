#!/usr/bin/env python3
"""Project database cleanup utility.

Default behavior is dry-run to show what will be changed.
Use --apply to execute.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import mysql.connector

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import MYSQL_CONFIG


LEGACY_TABLES = [
    "booking_guide_requests",
    "booking_room_requests",
    "transport_bookings",
    "transport_inventory_logs",
    "transport_profiles",
    "self_trip_plan_items",
    "self_trip_plans",
]

LEGACY_COLUMNS = [
    ("user_profiles", "otp_verified"),
    ("self_trip_plans", "transport_service_id"),
    ("booking_travelers", "created_at"),
    ("hotel_images", "created_at"),
    ("self_trip_plan_items", "created_at"),
    ("tour_city_schedules", "created_at"),
    ("tour_hotel_stays", "created_at"),
    ("tour_service_links", "created_at"),
]

TRANSACTION_TABLES = [
    "user_approval_logs",
    "platform_reviews",
    "support_issues",
    "spot_change_requests",
    "organizer_external_bookings",
    "hotel_room_inventory_logs",
    "hotel_bookings",
    "payments",
    "booking_travelers",
    "bookings",
    "tour_city_schedules",
    "tour_hotel_stays",
    "tour_service_links",
    "tour_itinerary",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup legacy TourGen DB tables/columns.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute changes. Without this flag, dry-run mode is used.",
    )
    parser.add_argument(
        "--skip-legacy",
        action="store_true",
        help="Skip dropping legacy tables/columns.",
    )
    parser.add_argument(
        "--truncate-app-data",
        action="store_true",
        help="Truncate transactional app tables (bookings/payments/logs).",
    )
    return parser.parse_args()


def table_exists(cur, table_name: str) -> bool:
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


def column_exists(cur, table_name: str, column_name: str) -> bool:
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


def log_step(prefix: str, sql: str) -> None:
    print(f"{prefix} {sql}")


def maybe_drop_legacy(cur, apply: bool) -> int:
    changed = 0

    for table_name, column_name in LEGACY_COLUMNS:
        if not table_exists(cur, table_name):
            continue
        if not column_exists(cur, table_name, column_name):
            continue
        sql = f"ALTER TABLE `{table_name}` DROP COLUMN `{column_name}`"
        log_step("EXECUTE:" if apply else "DRY-RUN:", sql)
        if apply:
            cur.execute(sql)
            changed += 1

    for table_name in LEGACY_TABLES:
        if not table_exists(cur, table_name):
            continue
        sql = f"DROP TABLE `{table_name}`"
        log_step("EXECUTE:" if apply else "DRY-RUN:", sql)
        if apply:
            cur.execute(sql)
            changed += 1

    return changed


def _existing_tables(cur, table_names: Iterable[str]) -> list[str]:
    return [table_name for table_name in table_names if table_exists(cur, table_name)]


def maybe_truncate_app_data(cur, apply: bool) -> int:
    changed = 0
    existing = _existing_tables(cur, TRANSACTION_TABLES)
    if not existing:
        return changed

    if apply:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for table_name in existing:
        sql = f"TRUNCATE TABLE `{table_name}`"
        log_step("EXECUTE:" if apply else "DRY-RUN:", sql)
        if apply:
            cur.execute(sql)
            changed += 1
    if apply:
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
    return changed


def main() -> None:
    args = parse_args()
    apply = bool(args.apply)
    cleanup_legacy = not args.skip_legacy

    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cur = conn.cursor()
    try:
        total_changes = 0
        if cleanup_legacy:
            total_changes += maybe_drop_legacy(cur, apply=apply)
        if args.truncate_app_data:
            total_changes += maybe_truncate_app_data(cur, apply=apply)

        if apply:
            conn.commit()
            print(f"Completed. Total operations executed: {total_changes}")
        else:
            conn.rollback()
            print("Dry-run complete. No changes were committed.")
            print("Re-run with --apply to execute.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
