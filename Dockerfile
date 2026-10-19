# ---- Stage 1: install dependencies into a plain folder ----
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# ---- Stage 2: runtime image (non-root, no pip cache, no build leftovers) ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 1001 govscale \
    && useradd --system --uid 1001 --gid govscale --home-dir /app --no-create-home govscale

COPY --from=builder /install /usr/local
COPY --chown=govscale:govscale . .

RUN mkdir -p /app/instance && chown govscale:govscale /app/instance

USER govscale

EXPOSE 5000

# Optional idempotent init (GOVSCALE_RUN_INIT=1), then the command below.
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]

# Workers/threads/port are configurable: WEB_CONCURRENCY (use 1 with SQLite),
# GUNICORN_THREADS and PORT (default 5000).
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-3} --threads ${GUNICORN_THREADS:-4} --timeout 60 --graceful-timeout 30 --worker-tmp-dir /dev/shm --access-logfile - --error-logfile - app:app"]
