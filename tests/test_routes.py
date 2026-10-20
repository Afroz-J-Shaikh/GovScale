import os
import tempfile
from pathlib import Path

# Set an isolated database BEFORE importing the application.
_test_db_directory = tempfile.TemporaryDirectory(prefix="govscale-tests-")
_test_db_path = Path(_test_db_directory.name) / "govscale-test.db"

os.environ.setdefault("GOVSCALE_DATABASE_URI", (
    os.environ.get("GOVSCALE_TEST_DATABASE_URI") or f"postgresql://govscale_user:test_password@localhost:5432/govscale_test"
))
os.environ.setdefault("GOVSCALE_SECRET_KEY", "test-only-secret-key")

from app import app  # noqa: E402


app.config["TESTING"] = True


def test_health_endpoint_returns_healthy():
    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


def test_homepage_loads_successfully():
    response = app.test_client().get("/")

    assert response.status_code == 200


def test_student_dashboard_requires_authentication():
    response = app.test_client().get("/dashboard")

    assert response.status_code in (302, 401, 403)

    if response.status_code == 302:
        assert "/login" in response.headers["Location"]


def test_admin_dashboard_rejects_unauthenticated_access():
    response = app.test_client().get("/admin")

    assert response.status_code in (302, 401, 403)

    if response.status_code == 302:
        assert "/login" in response.headers["Location"]


def test_unknown_url_returns_404():
    response = app.test_client().get("/this-route-does-not-exist-for-tests")

    assert response.status_code == 404


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
