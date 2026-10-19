# GovScale
GovScale is a scalable student scholarship and examination portal designed to demonstrate how DevOps practices and AWS cloud infrastructure can help public-service applications handle sudden traffic spikes.

## Setup and Initialization

After installing dependencies and configuring the application, run these
commands from the project root:

```bash
python scripts/seed_institutions.py
python scripts/create_admin.py
```

Use `.venv/bin/python` instead of `python` when using the project virtual
environment.

### Institutions

The institution seeder adds missing institutions by normalized name. It
does not overwrite existing institution records and can be rerun safely.

### Default administrator

The initializer creates this account if its email is not already registered:

- Email: `admin@gmail.com`
- Password: `admin123`

Rerunning it preserves an existing administrator and their password. If the
email belongs to a non-admin account, the script stops without changing it.
Change the default password before exposing the application publicly.

### Redeployment

Run initialization explicitly during setup, not on every application startup.
Keep the database and persistent storage when redeploying application code.
These commands do not import the optional demo JSON data.

## PostgreSQL (production)

SQLite stays the default for local development and tests. Set
`GOVSCALE_DATABASE_URI` to use PostgreSQL (for example Amazon RDS):

```
GOVSCALE_DATABASE_URI=postgresql+psycopg2://user:password@host:5432/govscale
```

Percent-encode special characters in the password, or use letters and digits.
`GOVSCALE_SECRET_KEY` is mandatory on PostgreSQL and must be identical on
every instance.

- Local stack with PostgreSQL: set `POSTGRES_PASSWORD`, `GOVSCALE_SECRET_KEY`
  and `GOVSCALE_ADMIN_PASSWORD` in `.env`, then `docker compose up --build`.
- Run the tests on PostgreSQL: `export POSTGRES_PASSWORD=...` then
  `sh scripts/test_postgres.sh`.
- Copy an existing SQLite database into PostgreSQL:
  `GOVSCALE_DATABASE_URI=... python scripts/migrate_sqlite_to_postgres.py instance/govscale.db`
- Containers: `WEB_CONCURRENCY` (gunicorn workers, default 3; use 1 with
  SQLite), `GUNICORN_THREADS` (default 4), `PORT` (default 5000). Set
  `GOVSCALE_RUN_INIT=1` to run the idempotent institution and admin
  initialisation at container start; it is safe with several instances.
- `scripts/export_demo_data.py` reads the local SQLite file only.
