"""Shared helpers for GovScale database scripts (SQLite and PostgreSQL)."""

from sqlalchemy import Integer, func, select, text


def reset_postgres_sequences(connection, tables):
    """After inserting rows with explicit ids, move each serial sequence
    past MAX(id) so later inserts do not collide. No-op on other databases."""
    if connection.dialect.name != "postgresql":
        return
    preparer = connection.dialect.identifier_preparer
    for table in tables:
        primary_key = list(table.primary_key.columns)
        if len(primary_key) != 1 or not isinstance(primary_key[0].type, Integer):
            continue
        column = primary_key[0]
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": preparer.quote(table.name), "column_name": column.name},
        ).scalar()
        if not sequence:
            continue
        max_id = connection.execute(select(func.max(column))).scalar()
        connection.execute(
            text("SELECT setval(CAST(:sequence AS regclass), :value, :is_called)"),
            {
                "sequence": sequence,
                "value": max_id or 1,
                "is_called": max_id is not None,
            },
        )
