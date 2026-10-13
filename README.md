# GovScale

GovScale is a student scholarship and examination portal built with Flask, Flask-Login, Flask-WTF, and SQLAlchemy. It includes student registration and profiles, scholarship discovery and applications, exam registration, and an administrator area for scholarship management and application review.

> **Demo data notice:** The bundled scholarship opportunities are fictional examples. This project is a demonstration, not an official government service or eligibility verification system.

## Requirements

- Python 3.12 (recommended)
- pip
- Docker (optional)

## Run locally

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Set a unique secret key before starting the app. Do not commit real secrets to Git.

```bash
# macOS/Linux
export GOVSCALE_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

The app starts at http://127.0.0.1:5000. The SQLite database is created under Flask's `instance/` directory. Initial demo scholarships and institutions are seeded when the relevant tables are empty.

To create an administrator, use the helper script and follow its prompts:

```bash
python scripts/create_admin.py
```

## Tests

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the same smoke-test suite on pushes to `main` and `codex/**` branches and on pull requests targeting `main`.

## Docker

Build and run the production container:

```bash
docker build -t govscale .
docker run --rm -p 8000:8000 \
  -e GOVSCALE_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  govscale
```

The container runs Gunicorn as a non-root user and exposes port 8000. Its health check calls `/health`. The SQLite database is stored inside the container unless you mount a persistent volume at `/app/instance`; for durable deployments, attach persistent storage or migrate to a managed database and adapt the current SQLite-specific startup migration code first.

## Health endpoint

`GET /health` returns HTTP 200 when the application can reach its database and HTTP 503 when the database check fails. It is intended for container/orchestrator health checks.

## Security and deployment notes

- Always set `GOVSCALE_SECRET_KEY` to a strong, unique secret in any shared or production environment.
- `GOVSCALE_DEBUG=true` enables Flask debug mode and should only be used for local development.
- The current schema initialization includes SQLite-specific migrations. A move to PostgreSQL or another database requires a migration strategy rather than simply changing a connection URL.
- Use HTTPS, backups, persistent database storage, and a managed secret store for real deployments.
- The included CI suite is a smoke test, not a substitute for comprehensive business-rule, authorization, concurrency, and end-to-end tests.

## Main areas

- `app.py`: Flask routes, SQLAlchemy models, validation, authentication, and startup initialization
- `templates/`: Jinja templates for public pages, student flows, exams, and admin pages
- `static/`: CSS, JavaScript, and image assets
- `scripts/create_admin.py`: interactive administrator creation helper
- `seed_institutions.py`: institution seeding utility
