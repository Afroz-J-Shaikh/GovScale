#!/usr/bin/env python3
"""Copy an existing GovScale SQLite database into the database configured by
GOVSCALE_DATABASE_URI (PostgreSQL). The SQLite file is only read.

    GOVSCALE_DATABASE_URI=postgresql+psycopg2://... \
        python scripts/migrate_sqlite_to_postgres.py instance/govscale.db

The target must be empty (a freshly created schema). Use --wipe-target to
delete every row in the target first. Everything runs in ONE transaction:
on any error nothing is written. Password hashes are copied unchanged, so
existing logins keep working.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import IS_POSTGRES, app, db  # noqa: E402
from dbtools import reset_postgres_sequences  # noqa: E402

BATCH_SIZE = 500


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", nargs="?", default=str(ROOT / "instance" / "govscale.db"))
    parser.add_argument("--wipe-target", action="store_true",
                        help="DELETE all rows in the target database first")
    parser.add_argument("--allow-non-postgres", action="store_true",
                        help="allow a non-PostgreSQL target (testing only)")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_file():
        fail(f"SQLite file not found: {source}")
    if not IS_POSTGRES and not args.allow_non_postgres:
        fail("GOVSCALE_DATABASE_URI must point to PostgreSQL for this script.")

    source_engine = create_engine("sqlite:///" + source.as_posix())

    with app.app_context():
        metadata = db.metadata
        source_inspector = inspect(source_engine)
        source_tables = set(source_inspector.get_table_names())
        tables = [t for t in metadata.sorted_tables if t.name in source_tables]
        ignored = sorted(source_tables - set(metadata.tables))

        with source_engine.connect() as source_conn, db.engine.begin() as target:
            if args.wipe_target:
                print("Wiping all rows in the target database...")
                for table in reversed(metadata.sorted_tables):
                    target.execute(table.delete())
            else:
                non_empty = [
                    t.name for t in metadata.sorted_tables
                    if target.execute(select(func.count()).select_from(t)).scalar()
                ]
                if non_empty:
                    fail("Target tables are not empty: " + ", ".join(non_empty)
                         + ". Use a fresh database or pass --wipe-target.")

            copied = {}
            for table in tables:
                source_columns = {c["name"] for c in source_inspector.get_columns(table.name)}
                columns = [c for c in table.columns if c.name in source_columns]
                rows = [dict(r._mapping) for r in source_conn.execute(select(*columns))]
                for start in range(0, len(rows), BATCH_SIZE):
                    target.execute(table.insert(), rows[start:start + BATCH_SIZE])
                copied[table.name] = len(rows)

            reset_postgres_sequences(target, tables)

            for table in tables:
                actual = target.execute(select(func.count()).select_from(table)).scalar()
                if actual != copied[table.name]:
                    fail(f"Row count mismatch in {table.name}: "
                         f"copied {copied[table.name]}, found {actual}")

    print("Migration succeeded.")
    for name, count in copied.items():
        print(f"  {name}: {count}")
    if ignored:
        print("Ignored source tables not in the application schema: " + ", ".join(ignored))


if __name__ == "__main__":
    main()
