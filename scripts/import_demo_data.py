#!/usr/bin/env python3
"""Optionally load the sanitized demo dataset into a freshly initialized database.

Works on SQLite and PostgreSQL (whatever GOVSCALE_DATABASE_URI selects). Run
after the default initialization (institutions + admin). The default
institutions and administrator are replaced by the seed's rows. The existing
administrator's email and password are carried over to the seed's system admin,
so you can still sign in. Demo students get GOVSCALE_DEMO_PASSWORD (random if unset).
Everything runs in one transaction.
"""

import json
import os
import secrets
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, func, or_, select
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed_data" / "govscale_demo.json"
SYSTEM_EMAIL = "govscale-demo-system@example.invalid"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import app, db  # noqa: E402
from dbtools import reset_postgres_sequences  # noqa: E402


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def coerce(table, row):
    """Convert JSON values to the Python types the column expects."""
    converted = {}
    for name, value in row.items():
        column_type = table.c[name].type
        if value is None:
            converted[name] = None
        elif isinstance(column_type, Boolean):
            converted[name] = bool(value)
        elif isinstance(column_type, DateTime) and isinstance(value, str):
            converted[name] = datetime.fromisoformat(value)
        elif isinstance(column_type, Date) and isinstance(value, str):
            converted[name] = date.fromisoformat(value)
        else:
            converted[name] = value
    return converted


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

    for table_name, rows in tables.items():
        if not isinstance(table_name, str) or not isinstance(rows, list):
            fail(f"Invalid table data: {table_name!r}")
        if any(not isinstance(row, dict) or not row for row in rows):
            fail(f"Invalid row in table: {table_name}")
        if counts.get(table_name) != len(rows):
            fail(f"Seed row count mismatch: {table_name}")

    demo_password = os.environ.get("GOVSCALE_DEMO_PASSWORD", "").strip()
    random_password = not demo_password
    if random_password:
        demo_password = secrets.token_urlsafe(24)
    student_hash = generate_password_hash(demo_password)

    with app.app_context():
        metadata = db.metadata
        missing = set(tables) - set(metadata.tables)
        if missing:
            fail("Schema missing tables: " + ", ".join(sorted(missing)))

        user_table = metadata.tables["user"]
        institution_table = metadata.tables["institution"]

        with db.engine.begin() as connection:
            admins = connection.execute(
                select(user_table.c.id, user_table.c.email, user_table.c.password_hash)
                .where(user_table.c.is_admin.is_(True))
            ).all()
            student_count = connection.execute(
                select(func.count()).select_from(user_table)
                .where(user_table.c.is_admin.is_(False))
            ).scalar()
            if len(admins) != 1 or student_count:
                fail(
                    "Demo data can only be loaded into a freshly initialized "
                    "database (one admin, no students)."
                )

            for table in metadata.sorted_tables:
                if table.name in ("user", "institution"):
                    continue
                if connection.execute(select(func.count()).select_from(table)).scalar():
                    fail(
                        f"Table {table.name} already contains data. Demo data can "
                        "only be loaded into a freshly initialized database."
                    )

            custom_institutions = connection.execute(
                select(func.count()).select_from(institution_table).where(or_(
                    institution_table.c.created_by_user_id.is_not(None),
                    institution_table.c.is_verified.is_(False),
                ))
            ).scalar()
            if custom_institutions:
                fail("The database contains user-created institutions; refusing to replace them.")

            _admin_id, admin_email, admin_hash = admins[0]

            connection.execute(institution_table.delete())
            connection.execute(user_table.delete())

            for table in metadata.sorted_tables:
                rows = tables.get(table.name)
                if not rows:
                    continue
                prepared = []
                for original in rows:
                    row = dict(original)
                    unknown = set(row) - set(table.c.keys())
                    if unknown:
                        fail(f"Unknown columns in {table.name}: " + ", ".join(sorted(unknown)))

                    if table.name == "user":
                        if row.get("id") == system_id:
                            # Keep the real administrator's login.
                            row["email"] = admin_email
                            row["password_hash"] = admin_hash
                        else:
                            row["password_hash"] = student_hash
                            # email-validator rejects the reserved ".invalid" domain.
                            row["email"] = row["email"].replace("@example.invalid", "@example.com")

                    prepared.append(coerce(table, row))
                connection.execute(table.insert(), prepared)

            if connection.dialect.name == "sqlite":
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    fail(f"Foreign-key check failed: {violations[:10]}")

            reset_postgres_sequences(connection, [metadata.tables[n] for n in tables])

            for table_name, rows in tables.items():
                actual = connection.execute(
                    select(func.count()).select_from(metadata.tables[table_name])
                ).scalar()
                if actual != len(rows):
                    fail(f"Imported row count mismatch: {table_name}")

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
