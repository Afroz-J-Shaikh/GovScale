#!/usr/bin/env python3
"""Apply the GovScale SQLite -> PostgreSQL patch. Run from the repo root:
    python apply_postgres_patch.py
All edits are verified in memory first; nothing is written unless every one matches."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "GOVSCALE_POSTGRES_PATCH_APPLIED"
errors = []
originals = {}   # rel path -> original text (for backups)
outputs = {}     # rel path -> new text


def read(rel, required=True):
    path = ROOT / rel
    if not path.is_file():
        if required:
            errors.append(f"missing file: {rel}")
        return None
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    originals[rel] = text
    return text


def sub(text, old, new, label, count=1):
    if text is None:
        return None
    found = text.count(old)
    if found != count:
        errors.append(f"[{label}] expected {count} match(es), found {found}")
        return text
    return text.replace(old, new)


def between(text, start, end, new, label):
    if text is None:
        return None
    if text.count(start) != 1:
        errors.append(f"[{label}] start marker found {text.count(start)} times")
        return text
    s = text.find(start)
    e = text.find(end, s)
    if e == -1:
        errors.append(f"[{label}] end marker not found")
        return text
    return text[:s] + new + text[e:]


# =====================================================================
# app.py
# =====================================================================
app = read("app.py")
if app is not None and MARKER in app:
    print("app.py is already patched; nothing to do.")
    sys.exit(0)

app = sub(app, "from sqlalchemy import text, or_\n",
          "from sqlalchemy import inspect as sa_inspect, text, or_\n", "import inspect")
app = sub(app, "from sqlalchemy.exc import IntegrityError\n",
          "from sqlalchemy.exc import IntegrityError, OperationalError\n", "import OperationalError")

app = sub(app, r'''app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "GOVSCALE_DATABASE_URI",
    "sqlite:///" + str(Path(app.instance_path) / "govscale.db"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
''', r'''# GOVSCALE_POSTGRES_PATCH_APPLIED
def _normalize_database_uri(uri):
    """Accept postgres:// and postgresql:// URLs and force the psycopg2 driver."""
    uri = (uri or "").strip()
    for prefix in ("postgres://", "postgresql://"):
        if uri.startswith(prefix):
            return "postgresql+psycopg2://" + uri[len(prefix):]
    return uri


app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_uri(
    os.environ.get("GOVSCALE_DATABASE_URI")
) or ("sqlite:///" + str(Path(app.instance_path) / "govscale.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

IS_POSTGRES = app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")
# PostgreSQL INTEGER limit. SQLite does not enforce it, PostgreSQL does.
MAX_DB_INTEGER = 2_147_483_647

_engine_options = {"pool_pre_ping": True}
if IS_POSTGRES:
    if app.config["SECRET_KEY"] == "local-development-key-change-before-deployment":
        raise RuntimeError(
            "Set GOVSCALE_SECRET_KEY (identical on every instance) "
            "when running against PostgreSQL."
        )
    _engine_options.update(
        pool_size=int(os.environ.get("GOVSCALE_DB_POOL_SIZE", "3")),
        max_overflow=int(os.environ.get("GOVSCALE_DB_MAX_OVERFLOW", "2")),
        pool_recycle=1800,
        # Store and read naive timestamps as UTC, like SQLite's CURRENT_TIMESTAMP.
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 10},
    )
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _engine_options
''', "db config")

app = sub(app, "def normalize_institution_name(name):\n", r'''class QuestionImportPreview(db.Model):
    """Pending question-import preview, stored in the DB so that any app
    instance behind the load balancer can confirm it."""
    __tablename__ = "question_import_preview"

    token = db.Column(db.String(64), primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exam_id = db.Column(
        db.Integer, db.ForeignKey("demo_exam.id"), nullable=False, index=True
    )
    created_at = db.Column(db.Float, nullable=False)  # epoch seconds
    payload = db.Column(db.Text, nullable=False)


def normalize_institution_name(name):
''', "preview model")

app = sub(app, "Scholarship.deadline.asc(),", "Scholarship.deadline.asc().nulls_first(),",
          "deadline ordering", count=3)
app = sub(app, "ScholarshipApplication.approved_at.desc(),",
          "ScholarshipApplication.approved_at.desc().nulls_last(),", "approved ordering")

app = sub(app, "    expired_exams = DemoExam.query.filter(DemoExam.end_at <= now_ist).all()",
          "    expired_exams = (\n        DemoExam.query.filter(DemoExam.end_at <= now_ist)\n"
          "        .order_by(DemoExam.id)\n        .all()\n    )", "expired exams order")
app = sub(app, "    for scholarship in Scholarship.query.all():\n",
          "    for scholarship in Scholarship.query.order_by(Scholarship.id).all():\n",
          "lifecycle order")

app = sub(app, "        db.session.add(profile)\n        db.session.commit()\n", r'''        db.session.add(profile)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Your profile could not be saved because of a simultaneous "
                "update. Please try again.",
                "error",
            )
            return render_template(
                "profile.html", form=form, profile=None,
                institutions=institution_data,
            )
''', "profile commit")
app = sub(app, "            if score < 0 or score > maximum:",
          "            if not (0 <= score <= maximum):", "score range")
app = sub(app, '''        if income is not None and income < 0:
            flash("Family income cannot be negative.", "error")''',
          '''        if income is not None and (income < 0 or income > MAX_DB_INTEGER):
            flash("Enter a valid family income (a non-negative whole number).", "error")''',
          "income range")
app = sub(app, '''        details.recipient_reference = recipient_reference
        db.session.commit()
        flash("Your simulated payment details have been saved.", "success")''',
          '''        details.recipient_reference = recipient_reference
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Your payment details were changed by another request. "
                "Please review and save again.",
                "error",
            )
            return redirect(url_for("payment_details"))
        flash("Your simulated payment details have been saved.", "success")''',
          "payment commit")
app = sub(app, "            if amount < 2000:\n                raise ValueError",
          "            if amount < 2000 or amount > MAX_DB_INTEGER:\n                raise ValueError",
          "amount range", count=2)
app = sub(app, '    now = datetime.now()\n\n    search = request.args.get("q", "").strip()',
          '    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)\n\n'
          '    search = request.args.get("q", "").strip()', "admin dashboard now")

NEW_IMPORT_VIEW = r'''@app.route("/admin/exams/<int:exam_id>/questions/import", methods=["GET", "POST"])
@admin_required
def admin_exam_question_import(exam_id):
    import json

    exam = db.session.get(DemoExam, exam_id)
    if exam is None or exam.scholarship_id is None:
        abort(404)

    scholarship = db.session.get(Scholarship, exam.scholarship_id)
    if scholarship is None or scholarship.category != "exam":
        abort(404)

    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    if now >= exam.start_at:
        flash("This exam has started. Its question paper is locked.", "error")
        return redirect(url_for("admin_exam_questions", exam_id=exam.id))

    errors = []
    preview = []
    preview_token = ""
    filename = ""
    invalid_preview_message = (
        "This preview is already being processed, expired, or invalid. "
        "Upload the file again if needed."
    )

    if request.method == "POST" and request.form.get("mode") == "confirm":
        try:
            token = request.form.get("preview_token", "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
                raise ValueError("Invalid import preview. Upload the file again.")

            stored_row = QuestionImportPreview.query.filter_by(
                token=token, admin_id=current_user.id, exam_id=exam.id,
            ).first()
            if stored_row is None:
                raise ValueError(invalid_preview_message)
            payload_text = stored_row.payload
            created_at = stored_row.created_at

            # Claim the token inside this transaction. A concurrent request
            # blocks here, then deletes zero rows and is rejected.
            claimed = QuestionImportPreview.query.filter_by(
                token=token
            ).delete(synchronize_session=False)
            if claimed != 1:
                raise ValueError(invalid_preview_message)

            age = time_module.time() - created_at
            try:
                stored = json.loads(payload_text)
            except ValueError:
                stored = None
            if not isinstance(stored, dict) or age > 900 or age < 0:
                db.session.commit()  # consume the invalid or expired preview
                raise ValueError(
                    "This preview has expired or is invalid. Upload the file again."
                )

            data = stored.get("questions")
            filename = stored.get("filename", "")
            if not isinstance(data, list) or not data or len(data) > 200:
                db.session.commit()
                raise ValueError("Invalid import preview. Upload the file again.")

            validated = _validate_import_questions(data)
            problems = [
                f"Row {r['source_row']}: " + "; ".join(r["errors"])
                for r in validated if r["errors"]
            ]
            if problems:
                raise ValueError("Validation failed: " + " ".join(problems))

            paper = ExamQuestionPaper.query.filter_by(exam_id=exam.id).first()
            if paper is None:
                paper = ExamQuestionPaper(exam_id=exam.id)
                db.session.add(paper)
                db.session.flush()

            # Prevent duplicate questions within this upload and against
            # questions already saved to this exam's paper.
            def _question_fingerprint(value):
                return re.sub(r"\s+", " ", str(value or "")).strip().casefold()

            existing_texts = {
                _question_fingerprint(question_text)
                for (question_text,) in db.session.query(ExamQuestion.question_text)
                .filter_by(paper_id=paper.id).all()
            }

            incoming_texts = set()
            duplicate_rows = []
            for row in validated:
                fingerprint = _question_fingerprint(row["question_text"])
                if fingerprint in existing_texts or fingerprint in incoming_texts:
                    duplicate_rows.append(row["source_row"])
                incoming_texts.add(fingerprint)

            if duplicate_rows:
                shown = ", ".join(str(number) for number in duplicate_rows[:20])
                suffix = "…" if len(duplicate_rows) > 20 else ""
                raise ValueError(f"Duplicate questions found (rows {shown}{suffix}).")

            for row in validated:
                db.session.add(ExamQuestion(
                    paper_id=paper.id,
                    question_text=row["question_text"],
                    option_a=row["option_a"],
                    option_b=row["option_b"],
                    option_c=row["option_c"],
                    option_d=row["option_d"],
                    correct_option=row["correct_option"],
                    marks=row["marks"],
                ))

            # Enforce the exam lock again immediately before committing.
            now_before_commit = datetime.now(
                ZoneInfo("Asia/Kolkata")
            ).replace(tzinfo=None)
            if now_before_commit >= exam.start_at:
                raise ValueError(
                    "The exam has started, so its question paper is locked. "
                    "Nothing was imported."
                )

            db.session.commit()
            flash(
                f"Imported {len(validated)} questions. Existing questions were preserved.",
                "success",
            )
            return redirect(url_for("admin_exam_questions", exam_id=exam.id))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            db.session.rollback()
            reason = str(exc).strip()
            if reason.lower().startswith("import rejected:"):
                reason = reason.split(":", 1)[1].strip()
            elif reason.startswith("Validation failed:"):
                reason = reason.split(":", 1)[1].strip()
            flash(f"Import rejected: {reason}", "error")
            return redirect(url_for("admin_exam_question_import", exam_id=exam.id))
        except Exception:
            db.session.rollback()
            app.logger.exception("Question import failed for exam %s", exam.id)
            errors.append(
                "Import failed. Please upload the file again if no questions were saved."
            )

    elif request.method == "POST":
        upload = request.files.get("question_file")
        if upload is None or not upload.filename:
            errors.append("Choose a CSV or Word document.")
        else:
            filename = Path(upload.filename).name
            content = upload.read(5 * 1024 * 1024 + 1)
            if len(content) > 5 * 1024 * 1024:
                errors.append("Maximum file size is 5 MB.")
            elif Path(filename).suffix.lower() not in (".csv", ".docx"):
                errors.append("Only .csv and .docx files are supported.")
            else:
                try:
                    parsed = _parse_question_csv_or_docx(filename, content)
                    # PostgreSQL cannot store NUL characters in text columns.
                    parsed = [
                        {
                            key: (value.replace("\x00", "") if isinstance(value, str) else value)
                            for key, value in record.items()
                        }
                        for record in parsed
                    ]
                    preview = _validate_import_questions(parsed)
                    if any(r["errors"] for r in preview):
                        errors.append(
                            "Fix the invalid rows in your file and upload it again. "
                            "Nothing has been imported."
                        )
                    else:
                        # Remove abandoned previews older than 24 hours.
                        QuestionImportPreview.query.filter(
                            QuestionImportPreview.created_at < time_module.time() - 86400
                        ).delete(synchronize_session=False)

                        preview_token = secrets.token_urlsafe(32)
                        db.session.add(QuestionImportPreview(
                            token=preview_token,
                            admin_id=current_user.id,
                            exam_id=exam.id,
                            created_at=time_module.time(),
                            payload=json.dumps({
                                "filename": filename,
                                "questions": [
                                    {k: r[k] for k in (
                                        "source_row", "question_text", "option_a",
                                        "option_b", "option_c", "option_d",
                                        "correct_option", "marks",
                                    )}
                                    for r in preview
                                ],
                            }, ensure_ascii=False),
                        ))
                        db.session.commit()
                except ValueError as exc:
                    db.session.rollback()
                    errors.append(str(exc))
                except Exception:
                    db.session.rollback()
                    preview = []
                    preview_token = ""
                    app.logger.exception("Question import preview failed for exam %s", exam.id)
                    errors.append("The file could not be processed. Please try again.")

    return render_template(
        "admin/exam_question_import.html",
        exam=exam,
        scholarship=scholarship,
        errors=errors,
        preview=preview,
        preview_token=preview_token,
        filename=filename,
    )


'''
app = between(
    app,
    '@app.route("/admin/exams/<int:exam_id>/questions/import", methods=["GET", "POST"])',
    '@app.route(\n    "/admin/exams/<int:exam_id>/questions/<int:question_id>/delete",',
    NEW_IMPORT_VIEW, "import view")

app = sub(app, r'''@app.before_request
def update_opportunity_lifecycles():
    """Persist lifecycle transitions and queue their notifications."""
    process_lifecycle_transitions()''', r'''_LIFECYCLE_INTERVAL_SECONDS = float(
    os.environ.get("GOVSCALE_LIFECYCLE_INTERVAL", "15")
)
_last_lifecycle_run = float("-inf")


@app.before_request
def update_opportunity_lifecycles():
    """Persist lifecycle transitions and queue their notifications.

    Throttled per worker process so it does not scan the database on every
    request, and skipped for health checks and static files."""
    global _last_lifecycle_run

    if request.endpoint in ("static", "health"):
        return None

    # PostgreSQL rejects NUL characters in text values.
    if request.method == "POST" and any(
        "\x00" in value for value in request.form.values()
    ):
        abort(400)

    now = time_module.monotonic()
    if (
        _LIFECYCLE_INTERVAL_SECONDS > 0
        and now - _last_lifecycle_run < _LIFECYCLE_INTERVAL_SECONDS
    ):
        return None
    _last_lifecycle_run = now

    try:
        process_lifecycle_transitions()
    except Exception:
        db.session.rollback()
        app.logger.exception("Lifecycle refresh failed; continuing with the request.")
    return None''', "before_request")

NEW_INIT_BLOCK = r'''# ---------------------------------------------------------------------------
# Startup schema initialisation (SQLite and PostgreSQL).
#
# Every gunicorn worker on every instance imports this module, so the work
# below must be idempotent and safe to run concurrently. On PostgreSQL a
# session-level advisory lock serialises it; SQLite is a single local file.
# ---------------------------------------------------------------------------
_SCHEMA_LOCK_KEY = 7264110211


def _ddl(sqlite_sql, postgres_sql=None):
    """Return a constant DDL statement for the active dialect."""
    if postgres_sql is not None and db.engine.dialect.name == "postgresql":
        return text(postgres_sql)
    return text(sqlite_sql)


def _column_names(table_name):
    """Column names of a table, read through the session's own connection."""
    return {
        column["name"]
        for column in sa_inspect(db.session.connection()).get_columns(table_name)
    }


def _initialize_schema():
    db.create_all()

    # Migrate legacy scholarship categories to the supported grade category.
    db.session.execute(
        text("UPDATE scholarship SET category = 'grade' WHERE category = 'merit'")
    )
    db.session.commit()

    scholarship_columns = _column_names("scholarship")

    if "lifecycle_status" not in scholarship_columns:
        db.session.execute(_ddl(
            "ALTER TABLE scholarship ADD COLUMN lifecycle_status "
            "VARCHAR(20) NOT NULL DEFAULT 'active'"
        ))
        db.session.execute(text(
            "UPDATE scholarship SET lifecycle_status = "
            "CASE WHEN is_active THEN 'active' ELSE 'inactive' END"
        ))
        db.session.commit()

    if "passing_threshold" not in scholarship_columns:
        db.session.execute(_ddl(
            "ALTER TABLE scholarship ADD COLUMN passing_threshold "
            "FLOAT NOT NULL DEFAULT 80.0"
        ))
        db.session.commit()

    if "is_admin" not in _column_names("user"):
        db.session.execute(_ddl(
            'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0',
            'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE',
        ))
        db.session.commit()

    if "registration_opens_at" not in _column_names("demo_exam"):
        db.session.execute(_ddl(
            "ALTER TABLE demo_exam ADD COLUMN registration_opens_at DATETIME",
            "ALTER TABLE demo_exam ADD COLUMN registration_opens_at TIMESTAMP",
        ))
        db.session.commit()

    application_columns = _column_names("scholarship_application")
    if "approved_at" not in application_columns:
        db.session.execute(_ddl(
            "ALTER TABLE scholarship_application ADD COLUMN approved_at DATETIME",
            "ALTER TABLE scholarship_application ADD COLUMN approved_at TIMESTAMP",
        ))
    if "withdrawn_at" not in application_columns:
        db.session.execute(_ddl(
            "ALTER TABLE scholarship_application ADD COLUMN withdrawn_at DATETIME",
            "ALTER TABLE scholarship_application ADD COLUMN withdrawn_at TIMESTAMP",
        ))
    db.session.commit()

    # Existing demo exams default to opening registration 15 days early.
    for exam in DemoExam.query.filter(
        DemoExam.registration_opens_at.is_(None)
    ).all():
        exam.registration_opens_at = exam.start_at - timedelta(days=15)
    db.session.commit()

    # Backfill only missing decision timestamps (real datetime values).
    backfill_timestamp = datetime.now()
    for application in ScholarshipApplication.query.filter(
        ScholarshipApplication.status == "approved",
        ScholarshipApplication.approved_at.is_(None),
    ).all():
        application.approved_at = backfill_timestamp
    for application in ScholarshipApplication.query.filter(
        ScholarshipApplication.status == "withdrawn",
        ScholarshipApplication.withdrawn_at.is_(None),
    ).all():
        application.withdrawn_at = backfill_timestamp
    db.session.commit()


def initialize_database():
    """Create tables and apply column migrations; safe to run concurrently."""
    lock_connection = None
    try:
        if db.engine.dialect.name == "postgresql":
            lock_connection = db.engine.connect()
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:key)"), {"key": _SCHEMA_LOCK_KEY}
            )
        _initialize_schema()
    except Exception:
        db.session.rollback()
        raise
    finally:
        if lock_connection is not None:
            try:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _SCHEMA_LOCK_KEY},
                )
            finally:
                lock_connection.close()


def _initialize_database_with_retry():
    attempts = max(1, int(os.environ.get("GOVSCALE_DB_CONNECT_RETRIES", "10")))
    delay = float(os.environ.get("GOVSCALE_DB_CONNECT_DELAY", "3"))
    for attempt in range(1, attempts + 1):
        try:
            initialize_database()
            return
        except OperationalError:
            db.session.rollback()
            if attempt == attempts:
                raise
            app.logger.warning(
                "Database not ready (attempt %s/%s); retrying in %ss.",
                attempt, attempts, delay,
            )
            time_module.sleep(delay)


with app.app_context():
    _initialize_database_with_retry()


'''
app = between(app, "with app.app_context():\n    db.create_all()",
              'if __name__ == "__main__":', NEW_INIT_BLOCK, "init block")
outputs["app.py"] = app

# =====================================================================
# requirements.txt
# =====================================================================
req = read("requirements.txt")
if req is not None:
    req = req.rstrip("\n") + "\n"
    if not re.search(r"(?im)^psycopg2(-binary)?\b", req):
        req += "psycopg2-binary>=2.9.10,<3.0\n"
    if not re.search(r"(?im)^tzdata\b", req):
        req += "tzdata\n"
    if not re.search(r"(?im)^gunicorn\b", req):
        req += "gunicorn>=23.0,<24.0\n"
    outputs["requirements.txt"] = req

# =====================================================================
# tests/test_routes.py
# =====================================================================
tests = read("tests/test_routes.py")
tests = sub(tests, 'os.environ["GOVSCALE_DATABASE_URI"] = f"sqlite:///{_test_db_path}"',
            'os.environ["GOVSCALE_DATABASE_URI"] = (\n'
            '    os.environ.get("GOVSCALE_TEST_DATABASE_URI") or f"sqlite:///{_test_db_path}"\n)\n'
            'os.environ.setdefault("GOVSCALE_SECRET_KEY", "test-only-secret-key")',
            "tests uri")
if tests is not None:
    tests = tests.rstrip("\n") + r'''


def test_database_initialization_is_idempotent():
    from app import initialize_database

    with app.app_context():
        initialize_database()
        initialize_database()


def test_database_roundtrip_on_configured_backend():
    from app import Institution, db

    name = "pytest roundtrip institution"
    with app.app_context():
        Institution.query.filter_by(normalized_name=name).delete()
        db.session.commit()
        db.session.add(Institution(
            name=name, normalized_name=name, institution_type="school",
            education_categories="school_8_10", is_verified=True,
        ))
        db.session.commit()
        assert Institution.query.filter_by(normalized_name=name).count() == 1
        Institution.query.filter_by(normalized_name=name).delete()
        db.session.commit()
'''
    outputs["tests/test_routes.py"] = tests

# =====================================================================
# README.md
# =====================================================================
readme = read("README.md")
if readme is not None and "## PostgreSQL (production)" not in readme:
    outputs["README.md"] = readme.rstrip("\n") + r'''

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
'''

# =====================================================================
# Whole-file writes
# =====================================================================
outputs[".env.example"] = r'''GOVSCALE_SECRET_KEY=
GOVSCALE_ADMIN_EMAIL=admin@gmail.com
GOVSCALE_ADMIN_PASSWORD=
GOVSCALE_DEMO_PASSWORD=

# Leave empty to use SQLite (instance/govscale.db).
# PostgreSQL: postgresql+psycopg2://user:password@host:5432/dbname
GOVSCALE_DATABASE_URI=

# docker compose (local PostgreSQL). Use letters and digits only.
POSTGRES_PASSWORD=
GOVSCALE_HOST_PORT=5000
GOVSCALE_PG_HOST_PORT=5433

# Containers
WEB_CONCURRENCY=3
GUNICORN_THREADS=4
# GOVSCALE_RUN_INIT=1   # run institution + admin init at container start
'''

outputs["Dockerfile"] = r'''# ---- Stage 1: install dependencies into a plain folder ----
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
'''

outputs["docker-entrypoint.sh"] = r'''#!/bin/sh
set -eu

# Both scripts are idempotent and safe if several instances start together.
if [ "${GOVSCALE_RUN_INIT:-0}" = "1" ]; then
    : "${GOVSCALE_ADMIN_PASSWORD:?Set GOVSCALE_ADMIN_PASSWORD when GOVSCALE_RUN_INIT=1}"
    python scripts/seed_institutions.py
    python scripts/create_admin.py
fi

exec "$@"
'''

outputs["compose.yaml"] = r'''# Shared build settings, reused by all app services (same image)
x-build: &build
  context: .

# Shared environment. Values come from .env; `:?` stops with an error if missing.
x-env: &env
  GOVSCALE_SECRET_KEY: ${GOVSCALE_SECRET_KEY:?Set GOVSCALE_SECRET_KEY in .env}
  GOVSCALE_ADMIN_EMAIL: ${GOVSCALE_ADMIN_EMAIL:-admin@gmail.com}
  GOVSCALE_ADMIN_PASSWORD: ${GOVSCALE_ADMIN_PASSWORD:?Set GOVSCALE_ADMIN_PASSWORD in .env}
  GOVSCALE_DATABASE_URI: postgresql+psycopg2://govscale:${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}@db:5432/govscale

x-hardening: &hardening
  cap_drop: [ALL]
  security_opt:
    - no-new-privileges:true

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: govscale
      POSTGRES_DB: govscale
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      # Local only; used by scripts/test_postgres.sh and migration scripts
      - "127.0.0.1:${GOVSCALE_PG_HOST_PORT:-5433}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U govscale -d govscale"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  # Default initialization: institutions + admin. Idempotent and race-safe.
  init:
    <<: *hardening
    build: *build
    image: govscale:local
    command: ["sh", "-c", "python scripts/seed_institutions.py && python scripts/create_admin.py"]
    environment: *env
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

  app:
    <<: *hardening
    build: *build
    image: govscale:local
    depends_on:
      init:
        condition: service_completed_successfully
    ports:
      - "${GOVSCALE_HOST_PORT:-5000}:5000"
    environment:
      <<: *env
      WEB_CONCURRENCY: ${WEB_CONCURRENCY:-3}
      GUNICORN_THREADS: ${GUNICORN_THREADS:-4}
    cpus: 1.0
    mem_limit: 512m
    pids_limit: 256
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s

  # Optional demo data. Run with: docker compose run --rm demo-seed
  demo-seed:
    <<: *hardening
    build: *build
    image: govscale:local
    profiles: ["demo"]
    command: ["python", "scripts/import_demo_data.py"]
    environment:
      <<: *env
      GOVSCALE_DEMO_PASSWORD: ${GOVSCALE_DEMO_PASSWORD:-}
    depends_on:
      init:
        condition: service_completed_successfully
    restart: "no"

volumes:
  pgdata:
'''

outputs["scripts/test_postgres.sh"] = r'''#!/usr/bin/env sh
# Run the test-suite against a throwaway PostgreSQL database.
# Usage: export POSTGRES_PASSWORD=<letters-and-digits>; sh scripts/test_postgres.sh [pytest args]
set -eu
cd "$(dirname "$0")/.."

: "${POSTGRES_PASSWORD:?Export POSTGRES_PASSWORD first}"
export GOVSCALE_SECRET_KEY="${GOVSCALE_SECRET_KEY:-test-only-secret-key}"
export GOVSCALE_ADMIN_PASSWORD="${GOVSCALE_ADMIN_PASSWORD:-test-only-admin-pass}"
PORT_ON_HOST="${GOVSCALE_PG_HOST_PORT:-5433}"

docker compose up -d --wait db
docker compose exec -T db psql -U govscale -d postgres \
    -c "DROP DATABASE IF EXISTS govscale_test WITH (FORCE)" \
    -c "CREATE DATABASE govscale_test"

GOVSCALE_TEST_DATABASE_URI="postgresql+psycopg2://govscale:${POSTGRES_PASSWORD}@127.0.0.1:${PORT_ON_HOST}/govscale_test" \
    python -m pytest -q "$@"
'''

outputs["scripts/dbtools.py"] = r'''"""Shared helpers for GovScale database scripts (SQLite and PostgreSQL)."""

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
'''

outputs["scripts/migrate_sqlite_to_postgres.py"] = r'''#!/usr/bin/env python3
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
'''

outputs["scripts/import_demo_data.py"] = r'''#!/usr/bin/env python3
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
'''

outputs["scripts/seed_institutions.py"] = r'''import sys
from pathlib import Path

from sqlalchemy.exc import IntegrityError

# Allow this script to import the application from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, db, Institution, normalize_institution_name  # noqa: E402

institutions = [
    # Schools: Classes 8–10 and 11–12
    ("Delhi Public School, R.K. Puram", "school", "school_8_10,school_11_12", "Delhi"),
    ("The Doon School", "school", "school_8_10,school_11_12", "Uttarakhand"),
    ("Modern School, Barakhamba Road", "school", "school_8_10,school_11_12", "Delhi"),
    ("The Cathedral and John Connon School", "school", "school_8_10,school_11_12", "Maharashtra"),
    ("Bombay Scottish School, Mahim", "school", "school_8_10,school_11_12", "Maharashtra"),
    ("St. Xavier's Collegiate School", "school", "school_8_10,school_11_12", "West Bengal"),
    ("Loyola High School, Pune", "school", "school_8_10,school_11_12", "Maharashtra"),
    ("Kendriya Vidyalaya, IIT Bombay", "school", "school_8_10,school_11_12", "Maharashtra"),

    # Universities and higher-education institutions
    ("University of Delhi", "university", "undergraduate_1_4", "Delhi"),
    ("University of Mumbai", "university", "undergraduate_1_4", "Maharashtra"),
    ("Savitribai Phule Pune University", "university", "undergraduate_1_4", "Maharashtra"),
    ("Jawaharlal Nehru University", "university", "undergraduate_1_4", "Delhi"),
    ("University of Hyderabad", "university", "undergraduate_1_4", "Telangana"),
    ("Banaras Hindu University", "university", "undergraduate_1_4", "Uttar Pradesh"),
    ("Aligarh Muslim University", "university", "undergraduate_1_4", "Uttar Pradesh"),
    ("Jamia Millia Islamia", "university", "undergraduate_1_4", "Delhi"),
    ("University of Calcutta", "university", "undergraduate_1_4", "West Bengal"),
    ("Anna University", "university", "undergraduate_1_4", "Tamil Nadu"),
    ("Andhra University", "university", "undergraduate_1_4", "Andhra Pradesh"),
    ("University of Madras", "university", "undergraduate_1_4", "Tamil Nadu"),
    ("Bangalore University", "university", "undergraduate_1_4", "Karnataka"),
    ("University of Rajasthan", "university", "undergraduate_1_4", "Rajasthan"),
    ("Panjab University", "university", "undergraduate_1_4", "Chandigarh"),
    ("Gujarat University", "university", "undergraduate_1_4", "Gujarat"),
    ("Osmania University", "university", "undergraduate_1_4", "Telangana"),
    ("Indian Institute of Technology Bombay", "higher_institute", "undergraduate_1_4", "Maharashtra"),
    ("Indian Institute of Technology Delhi", "higher_institute", "undergraduate_1_4", "Delhi"),
    ("Indian Institute of Technology Madras", "higher_institute", "undergraduate_1_4", "Tamil Nadu"),
    ("Birla Institute of Technology and Science, Pilani", "higher_institute", "undergraduate_1_4", "Rajasthan"),
    ("Manipal Academy of Higher Education", "higher_institute", "undergraduate_1_4", "Karnataka"),
]

with app.app_context():
    db.create_all()
    added = 0

    for name, kind, categories, state in institutions:
        normalized = normalize_institution_name(name)

        if Institution.query.filter_by(normalized_name=normalized).first():
            continue

        try:
            # Savepoint: if another instance inserted the same institution
            # a moment ago, only this one insert is rolled back.
            with db.session.begin_nested():
                db.session.add(
                    Institution(
                        name=name,
                        normalized_name=normalized,
                        institution_type=kind,
                        education_categories=categories,
                        state=state,
                        is_verified=True,
                    )
                )
                db.session.flush()
        except IntegrityError:
            continue

        added += 1

    db.session.commit()

    print(f"Institutions added: {added}")
    print(f"Total institutions in database: {Institution.query.count()}")
'''

outputs["scripts/create_admin.py"] = r'''import os
import re
import sys
from pathlib import Path

from sqlalchemy.exc import IntegrityError

# Add the project root so this script can import app.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, db, User  # noqa: E402


def main():
    print("\nGovScale — Create Administrator")
    print("--------------------------------")
    print("This creates an admin account, not a student profile.\n")

    full_name = "GovScale Administrator"
    email = os.environ.get("GOVSCALE_ADMIN_EMAIL", "admin@gmail.com").strip().lower()

    if not full_name or len(full_name) > 100:
        print("Error: Name must contain 1–100 characters.")
        return 1

    if len(email) > 254 or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        print("Error: Enter a valid email address.")
        return 1

    password = os.environ.get("GOVSCALE_ADMIN_PASSWORD", "admin123")

    if not 8 <= len(password) <= 128:
        print("Error: Password must be 8–128 characters.")
        return 1

    with app.app_context():
        # Preserve the existing administrator even if their email has changed.
        existing_admin = User.query.filter_by(is_admin=True).first()
        if existing_admin:
            print(f"Administrator already exists: {existing_admin.email}")
            print("No changes made; existing account and credentials are preserved.")
            return 0

        # Do not promote or overwrite a non-admin account using the default email.
        existing_user = User.query.filter(
            db.func.lower(User.email) == email
        ).first()
        if existing_user:
            print(f"ERROR: {email} belongs to a non-admin account.")
            print("No changes made. Resolve this email conflict manually.")
            return 1

        admin = User(
            full_name=full_name,
            email=email,
            # Required by the existing database schema.
            # This account has no StudentProfile.
            education_level="admin",
            indian_citizen_declared=False,
            is_admin=True,
        )
        admin.set_password(password)

        try:
            db.session.add(admin)
            db.session.commit()
        except IntegrityError:
            # Another instance created the administrator at the same moment.
            db.session.rollback()
            if User.query.filter_by(is_admin=True).first():
                print("Administrator was created concurrently; no changes made.")
                return 0
            print(f"ERROR: {email} is already registered by a non-admin account.")
            return 1
        except Exception:
            db.session.rollback()
            print(
                "\nError: Administrator creation failed. "
                "Check the application logs."
            )
            return 1

        print("\nAdministrator created successfully.")
        print(f"Email: {admin.email}")
        print("Admin access: enabled")
        print("Student profile: not created")

    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

# =====================================================================
# Validate everything, then write
# =====================================================================
for rel, content in outputs.items():
    if rel.endswith(".py"):
        try:
            compile(content, rel, "exec")
        except SyntaxError as exc:
            errors.append(f"[{rel}] generated code has a syntax error: {exc}")

if errors:
    print("PATCH NOT APPLIED. Nothing was changed. Problems:\n")
    for message in errors:
        print("  -", message)
    print("\nPaste these messages (and the relevant part of app.py) back to me.")
    sys.exit(1)

backup_dir = ROOT / ".pre_postgres_backup"
backup_dir.mkdir(exist_ok=True)
for rel in outputs:
    original = originals.get(rel)
    if original is None:
        path = ROOT / rel
        if path.is_file():
            original = path.read_text(encoding="utf-8")
    if original is not None:
        (backup_dir / rel.replace("/", "__")).write_text(original, encoding="utf-8", newline="\n")

for rel, content in outputs.items():
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

print("Patch applied. Files written:")
for rel in sorted(outputs):
    print("  -", rel)
print(f"Originals saved in {backup_dir.name}/ (delete it when you are happy).")
print("Next: python -m pytest -q")