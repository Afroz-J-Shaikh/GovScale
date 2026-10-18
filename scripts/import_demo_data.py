#!/usr/bin/env python3
"""Import the sanitized seed into a new, standard GovScale SQLite database."""

import json
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

    if DATABASE.exists():
        fail(
            f"Database already exists: {DATABASE}\n"
            "Refusing to overwrite or seed an existing database."
        )

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
        and row.get("full_name") == "GovScale Demo System"
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

    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    # App startup creates the schema, so import it only after verifying that
    # the normal database file does not exist.
    sys.path.insert(0, str(ROOT))
    connection = None
    created_by_this_run = False

    try:
        import app as govscale_app

        configured_uri = govscale_app.app.config["SQLALCHEMY_DATABASE_URI"]
        expected_uri = "sqlite:///" + str(DATABASE)
        if configured_uri != expected_uri:
            fail("Application is not configured for the standard database.")

        if not DATABASE.is_file():
            fail("App did not create the expected database.")
        created_by_this_run = True

        connection = sqlite3.connect(DATABASE)
        connection.execute("PRAGMA foreign_keys = OFF")

        available = {
            row[0]
            for row in connection.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
        }
        missing = set(tables) - available
        if missing:
            fail("Schema missing tables: " + ", ".join(sorted(missing)))

        for table in available:
            count = connection.execute(
                f"SELECT COUNT(*) FROM {qi(table)}"
            ).fetchone()[0]
            if count:
                fail(f"Fresh database unexpectedly contains rows: {table}")

        connection.execute("BEGIN")

        for table, rows in tables.items():
            quoted_table = qi(table)
            schema_columns = {
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info({quoted_table})"
                )
            }

            for original in rows:
                row = dict(original)
                unknown = set(row) - schema_columns
                if unknown:
                    fail(
                        f"Unknown columns in {table}: "
                        + ", ".join(sorted(unknown))
                    )

                if table == "user" and row.get("id") == system_id:
                    row["password_hash"] = generate_password_hash(
                        secrets.token_urlsafe(48)
                    )

                if table == "user" and not row.get("password_hash"):
                    fail(f"Missing password hash for user ID {row.get('id')}")

                columns = list(row)
                statement = (
                    f"INSERT INTO {quoted_table} "
                    f"({', '.join(qi(c) for c in columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})"
                )
                connection.execute(statement, [row[c] for c in columns])

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            fail(f"Foreign-key check failed: {violations[:10]}")

        for table, rows in tables.items():
            actual = connection.execute(
                f"SELECT COUNT(*) FROM {qi(table)}"
            ).fetchone()[0]
            if actual != len(rows):
                fail(f"Imported row count mismatch: {table}")

        connection.commit()
        print("Demo seed import succeeded.")
        print(f"Database: {DATABASE}")
        print(f"Tables: {len(tables)}")
        print(f"Rows: {sum(len(rows) for rows in tables.values())}")
        print("Foreign-key check: PASS")

    except BaseException:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        if created_by_this_run:
            if connection is not None:
                connection.close()
                connection = None
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    Path(str(DATABASE) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass
        raise
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
