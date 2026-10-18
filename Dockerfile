# ---- Stage 1: install dependencies into a plain folder ----
FROM python:3.12-slim AS builder

# pip: skip the "new pip available" check and don't keep a download cache
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Copy requirements first so this slow layer is cached until they change
COPY requirements.txt .
# --prefix puts packages in /install so stage 2 can copy them (like node_modules)
RUN pip install --prefix=/install -r requirements.txt


# ---- Stage 2: runtime image (non-root, no pip cache, no build leftovers) ----
FROM python:3.12-slim AS runtime

# Python: no .pyc files, and logs go straight to `docker logs`
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Unprivileged user; fixed IDs keep file ownership predictable
RUN groupadd --system --gid 1001 govscale \
    && useradd --system --uid 1001 --gid govscale --home-dir /app --no-create-home govscale

# Installed packages (and the gunicorn command) from stage 1
COPY --from=builder /install /usr/local
# App code; .dockerignore keeps secrets, .git and local DBs out
COPY --chown=govscale:govscale . .

# The SQLite database lives here; mount a volume on this path.
RUN mkdir -p /app/instance && chown govscale:govscale /app/instance

# Everything from here on, including the running app, is not root
USER govscale

# Documentation only; publishing the port is done in compose.yaml
EXPOSE 5000

# One worker + threads: the app writes to SQLite on every request.
# Binds 0.0.0.0 so the port is reachable from outside the container.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
