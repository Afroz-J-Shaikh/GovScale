#!/usr/bin/env python3
"""Export a sanitized GovScale demo dataset without modifying the source DB."""

import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "instance" / "govscale.db"
OUTPUT = ROOT / "seed_data" / "govscale_demo.json"
SYSTEM_EMAIL = "govscale-demo-system@example.invalid"


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def main():
    if not SOURCE.is_file():
        fail(f"Database not found: {SOURCE}")

    if OUTPUT.exists():
        fail(
            f"{OUTPUT.relative_to(ROOT)} already exists. "
            "Move it aside or remove it deliberately before re-exporting."
        )

    con = sqlite3.connect(
        f"file:{SOURCE.resolve()}?mode=ro",
        uri=True,
    )
    con.row_factory = sqlite3.Row

    try:
        tables = [
            row["name"]
            for row in con.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
        ]

        if "user" not in tables:
            fail("The user table is missing.")

        users = [
            dict(row)
            for row in con.execute(
                'SELECT * FROM "user" ORDER BY id'
            )
        ]
        admins = [row for row in users if row.get("is_admin")]

        if len(admins) != 1:
            fail(
                "Expected exactly one administrator in the source DB; "
                f"found {len(admins)}. No export was written."
            )

        admin_id = admins[0]["id"]
        exported = {}

        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            rows = [
                dict(row)
                for row in con.execute(
                    f"SELECT * FROM {quoted} ORDER BY rowid"  # nosec B608 - identifier quoted, from sqlite schema
                )
            ]

            # Exclude authentication credentials from every exported user.
            if table == "user":
                for row in rows:
                    row.pop("password_hash", None)

                    if row["id"] == admin_id:
                        # Keep this ID only as a synthetic historical identity.
                        row.update({
                            "full_name": "GovScale Demo System",
                            "email": SYSTEM_EMAIL,
                            "education_level": "admin",
                            "indian_citizen_declared": 0,
                            "is_admin": 1,
                        })
                    else:
                        row["full_name"] = f"Demo Student {row['id']}"
                        row["email"] = (
                            f"student-{row['id']}@example.invalid"
                        )

            elif table == "student_payment_details":
                for row in rows:
                    uid = row.get("user_id")
                    row["recipient_name"] = f"Demo Recipient {uid}"
                    row["recipient_reference"] = f"DEMO-REDACTED-{uid}"

            elif table == "scholarship_payout_attempt":
                for row in rows:
                    uid = row.get("reward_id")
                    row["recipient_name_snapshot"] = (
                        f"Demo Recipient reward {uid}"
                    )
                    row["recipient_reference_snapshot"] = (
                        f"DEMO-PAYOUT-{uid}-{row.get('attempt_number', 1)}"
                    )

            exported[table] = rows

        # Defensive check: no exported user has a password hash.
        if any(
            "password_hash" in row
            for row in exported.get("user", [])
        ):
            fail("Password hash found in export data.")

        payload = {
            "format_version": 1,
            "source": "sanitized GovScale demo dataset",
            "system_identity": {
                "user_id": admin_id,
                "full_name": "GovScale Demo System",
                "email": SYSTEM_EMAIL,
            },
            "tables": exported,
            "row_counts": {
                table: len(rows) for table, rows in exported.items()
            },
        }

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("x", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
                default=json_default,
            )
            handle.write("\n")

        print(f"Export written: {OUTPUT.relative_to(ROOT)}")
        print(f"Tables exported: {len(exported)}")
        print("Row counts:")
        for table, count in payload["row_counts"].items():
            print(f"  {table}: {count}")
        print("Password hashes exported: 0")
        print("Source database modified: no")
        print(
            "\nNOTE: The administrator row has been replaced with a "
            "synthetic identity for historical references. This export "
            "is not yet the finished importer or Docker setup."
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
