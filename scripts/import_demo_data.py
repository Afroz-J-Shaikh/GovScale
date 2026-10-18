#!/usr/bin/env python3
"""Optionally load the sanitized demo dataset into a freshly initialized database.

Run after the default initialization (institutions + admin). The default
institutions and administrator are replaced by the seed's rows. The existing
administrator's email and password are carried over to the seed's system admin,
so you can still sign in. Demo students get GOVSCALE_DEMO_PASSWORD (random if unset).
"""

import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed_data" / "govscale_demo.json"
DATABASE = (ROOT / "instance" / "govscale.db").resolve()
SYSTEM_EMAIL = "govscale-demo-system@example.invalid"


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def main():
    if len(sys.argv) != 1:
        fail("Run without arguments: python scripts/import_demo_data.py")

    try:
        payload = json.loads(SEED.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read seed: {exc}")

    if payload.get("format_version") != 1:
        fail("Unsupported seed format.")

    tables = payload.get("tables")
    counts = payload.get("row_counts")
    identity = payload.get("system_identity")
    if not isinstance(tables, dict) or not isinstance(counts, dict):
        fail("Seed tables or row counts are missing.")
    if not isinstance(identity, dict):
        fail("Seed system identity is missing.")

    system_id = identity.get("user_id")
    users = tables.get("user")
    if not isinstance(users, list):
        fail("Seed user table is missing.")
    if any("password_hash" in row for row in users):
        fail("Seed unexpectedly contains password hashes.")

    system_rows = [
        row for row in users
        if row.get("id") == system_id
        and row.get("email") == SYSTEM_EMAIL
        and row.get("is_admin") == 1
    ]
    if len(system_rows) != 1:
        fail("Expected exactly one synthetic system identity.")

    for table, rows in tables.items():
        if not isinstance(table, str) or not isinstance(rows, list):
            fail(f"Invalid table data: {table!r}")
        if any(not isinstance(row, dict) or not row for row in rows):
            fail(f"Invalid row in table: {table}")
        if counts.get(table) != len(rows):
            fail(f"Seed row count mismatch: {table}")

    # Importing the app creates the schema if it does not exist yet.
    sys.path.insert(0, str(ROOT))
    import app as govscale_app

    if govscale_app.app.config["SQLALCHEMY_DATABASE_URI"] != "sqlite:///" + str(DATABASE):
        fail("Application is not configured for the standard database.")
    if not DATABASE.is_file():
        fail("The application did not create the expected database.")

    demo_password = os.environ.get("GOVSCALE_DEMO_PASSWORD", "").strip()
    random_password = not demo_password
    if random_password:
        demo_password = secrets.token_urlsafe(24)
    student_hash = generate_password_hash(demo_password)

    connection = sqlite3.connect(DATABASE)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")

        available = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = set(tables) - available
        if missing:
            fail("Schema missing tables: " + ", ".join(sorted(missing)))

        # The database must be in its default state: one admin, no students,
        # only the seeded institutions, and nothing else.
        admins = connection.execute(
            'SELECT id, email, password_hash FROM "user" WHERE is_admin = 1'
        ).fetchall()
        student_count = connection.execute(
            'SELECT COUNT(*) FROM "user" WHERE is_admin = 0'
        ).fetchone()[0]
        if len(admins) != 1 or student_count:
            fail(
                "Demo data can only be loaded into a freshly initialized "
                "database (one admin, no students)."
            )

        for table in sorted(available - {"user", "institution"}):
            if connection.execute(f"SELECT COUNT(*) FROM {qi(table)}").fetchone()[0]:
                fail(
                    f"Table {table} already contains data. Demo data can only "
                    "be loaded into a freshly initialized database."
                )

        custom_institutions = connection.execute(
            "SELECT COUNT(*) FROM institution "
            "WHERE created_by_user_id IS NOT NULL OR is_verified = 0"
        ).fetchone()[0]
        if custom_institutions:
            fail("The database contains user-created institutions; refusing to replace them.")

        _admin_id, admin_email, admin_hash = admins[0]

        connection.execute("BEGIN")
        connection.execute("DELETE FROM institution")
        connection.execute('DELETE FROM "user"')

        for table, rows in tables.items():
            quoted_table = qi(table)
            schema_columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({quoted_table})")
            }

            for original in rows:
                row = dict(original)
                unknown = set(row) - schema_columns
                if unknown:
                    fail(f"Unknown columns in {table}: " + ", ".join(sorted(unknown)))

                if table == "user":
                    if row.get("id") == system_id:
                        # Keep the real administrator's login.
                        row["email"] = admin_email
                        row["password_hash"] = admin_hash
                    else:
                        row["password_hash"] = student_hash
                        # email-validator rejects the reserved ".invalid" domain,
                        # which would block login through the web form.
                        row["email"] = row["email"].replace("@example.invalid", "@example.com")

                columns = list(row)
                connection.execute(
                    f"INSERT INTO {quoted_table} "
                    f"({', '.join(qi(c) for c in columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    [row[c] for c in columns],
                )

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            fail(f"Foreign-key check failed: {violations[:10]}")

        for table, rows in tables.items():
            actual = connection.execute(f"SELECT COUNT(*) FROM {qi(table)}").fetchone()[0]
            if actual != len(rows):
                fail(f"Imported row count mismatch: {table}")

        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    print("Demo seed import succeeded.")
    print(f"Tables: {len(tables)}  Rows: {sum(len(r) for r in tables.values())}")
    print("Foreign-key check: PASS")
    print(f"Admin login unchanged: {admin_email}")
    if random_password:
        print("Demo students have a random password (set GOVSCALE_DEMO_PASSWORD to choose one).")
    else:
        print("Demo students (student-N@example.com) use GOVSCALE_DEMO_PASSWORD.")


if __name__ == "__main__":
    main()
