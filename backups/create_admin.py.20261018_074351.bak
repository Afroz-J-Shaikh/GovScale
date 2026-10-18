import getpass
import re
import sys
from pathlib import Path

# Add the project root so this script can import app.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, db, User


def main():
    print("\nGovScale — Create Administrator")
    print("--------------------------------")
    print("This creates an admin account, not a student profile.\n")

    full_name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()

    if not full_name or len(full_name) > 100:
        print("Error: Name must contain 1–100 characters.")
        return 1

    if len(email) > 254 or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        print("Error: Enter a valid email address.")
        return 1

    password = getpass.getpass("Password (8–128 characters): ")
    confirm_password = getpass.getpass("Confirm password: ")

    if not 8 <= len(password) <= 128:
        print("Error: Password must be 8–128 characters.")
        return 1

    if password != confirm_password:
        print("Error: Passwords do not match.")
        return 1

    with app.app_context():
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            print(
                "\nError: An account with this email already exists."
            )
            print(
                "No changes were made. Use a different email address."
            )
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
