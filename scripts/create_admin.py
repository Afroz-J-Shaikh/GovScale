import os
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
