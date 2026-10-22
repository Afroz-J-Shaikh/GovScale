# GovScale Local Setup

This guide explains how to run GovScale locally using Docker Compose. This is the fastest way to start the application, create the PostgreSQL database, seed initial data, and create the first administrator account.

## Prerequisites

Install the following before starting:

- Git
- Docker Desktop or Docker Engine
- Docker Compose v2
- Python 3.12, only if you want to generate secrets locally

Verify the installation:

```bash
docker --version
docker compose version
git --version
```

## 1. Clone the repository

```bash
git clone <your-repository-url>
cd govscale
```

## 2. Create the environment file

```bash
cp .env.example .env
```

Open `.env` and set the following values:

```env
GOVSCALE_SECRET_KEY=<long-random-secret>
GOVSCALE_ADMIN_EMAIL=<your-admin-email>
GOVSCALE_ADMIN_PASSWORD=<strong-admin-password>
POSTGRES_PASSWORD=<strong-database-password>
GOVSCALE_HOST_PORT=5000
GOVSCALE_PG_HOST_PORT=5433
WEB_CONCURRENCY=3
GUNICORN_THREADS=4
```

Generate a secure Flask secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

You can generate a strong database or admin password in the same way.

Never commit the real `.env` file. It contains credentials and must remain local.

## Environment variables

| Variable | Purpose |
|---|---|
| `GOVSCALE_SECRET_KEY` | Flask session-signing key. Must be a long random value. |
| `GOVSCALE_ADMIN_EMAIL` | Email used to create the initial administrator. |
| `GOVSCALE_ADMIN_PASSWORD` | Password used to create the initial administrator. |
| `POSTGRES_PASSWORD` | Password for the local PostgreSQL container. |
| `GOVSCALE_DATABASE_URI` | PostgreSQL connection URI. Compose supplies this automatically for the local database. |
| `GOVSCALE_HOST_PORT` | Host port exposed for the web application. Default is `5000`. |
| `GOVSCALE_PG_HOST_PORT` | Host port exposed for PostgreSQL. Default is `5433`. |
| `WEB_CONCURRENCY` | Number of Gunicorn worker processes. |
| `GUNICORN_THREADS` | Number of Gunicorn threads per worker. |

## 3. Start GovScale

```bash
docker compose up --build
```

Docker Compose performs the following startup sequence:

1. Starts PostgreSQL.
2. Runs `db-ensure`, which creates the `govscale` database if it does not exist.
3. Runs `init`, which seeds institution data.
4. Runs `admin-init`, which creates the initial administrator.
5. Starts the GovScale Flask application through Gunicorn.

When startup completes, open:

```text
http://localhost:5000
```

## 4. Log in as administrator

Use the email and password you placed in `.env`:

- Email: value of `GOVSCALE_ADMIN_EMAIL`
- Password: value of `GOVSCALE_ADMIN_PASSWORD`

Do not use example credentials for any deployment that is publicly accessible.

## 5. Stop the application

Stop the containers but preserve database data:

```bash
docker compose down
```

Stop the containers and delete the local PostgreSQL volume:

```bash
docker compose down -v
```

Use `docker compose down -v` only when you want a completely fresh local database.

## 6. View logs

Follow all service logs:

```bash
docker compose logs -f
```

Follow only the application logs:

```bash
docker compose logs -f app
```

Check container status:

```bash
docker compose ps
```

## Application health check

The application exposes:

```text
GET /health
```

A successful response confirms that the Flask application is running. Docker Compose also uses this endpoint for container health checks.

## Common problems

### Port 5000 is already in use

Change the host port in `.env`:

```env
GOVSCALE_HOST_PORT=5001
```

Then restart:

```bash
docker compose up --build
```

Open `http://localhost:5001`.

### Port 5433 is already in use

Change:

```env
GOVSCALE_PG_HOST_PORT=5434
```

Then restart Compose.

### Database is not ready

The Compose startup order waits for database creation and initialization before launching the app. If you manually changed the Compose file, ensure `db-ensure`, `init`, and `admin-init` complete before `app` starts.

### Forgot the administrator password

For local development, reset the database:

```bash
docker compose down -v
docker compose up --build
```

This deletes local data and recreates the administrator using the current `.env` values.

### Changes to Python code are not visible

Rebuild the image:

```bash
docker compose up --build
```

## What runs locally

| Service | Purpose |
|---|---|
| `db` | PostgreSQL database |
| `db-ensure` | Creates the GovScale database if missing |
| `init` | Seeds institution data |
| `admin-init` | Creates the initial administrator |
| `app` | Flask application served by Gunicorn |

The local application container runs as a non-root user, has a read-only filesystem, drops Linux capabilities, and uses resource limits. These settings mirror the security posture used in the production container image. [file:9][file:10]
