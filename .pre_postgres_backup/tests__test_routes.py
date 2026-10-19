import os
import tempfile
from pathlib import Path

# Set an isolated database BEFORE importing the application.
_test_db_directory = tempfile.TemporaryDirectory(prefix="govscale-tests-")
_test_db_path = Path(_test_db_directory.name) / "govscale-test.db"

os.environ["GOVSCALE_DATABASE_URI"] = f"sqlite:///{_test_db_path}"

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
