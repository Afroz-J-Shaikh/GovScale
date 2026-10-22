#!/usr/bin/env python3
"""Add profile-completion guidance for grade-based scholarships."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
TEMPLATE = ROOT / "templates" / "scholarship_category.html"


def replace_once(text, old, new, label):
    if new in text:
        print(f"SKIP: {label} already applied")
        return text

    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"ERROR: expected exactly one match for {label}, found {count}."
        )

    print(f"PATCH: {label}")
    return text.replace(old, new, 1)


def main():
    app = APP.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    # 1. Add a one-time login notification helper.
    helper = '''

def notify_missing_student_profile(user):
    """Notify a student once if their education profile has not been created."""
    if user.is_admin:
        return

    profile = StudentProfile.query.filter_by(user_id=user.id).first()

    if profile is not None:
        return

    dispatch_notification(
        user.id,
        f"missing_student_profile:{user.id}",
        "Complete your student profile",
        "Add your education details to discover grade-based scholarships "
        "matched to your current class or year.",
        url_for("profile"),
    )
'''

    anchor = '''def dispatch_notification(user_id, event_key, title, message, link=None):'''
    if "def notify_missing_student_profile(user):" not in app:
        if anchor not in app:
            raise SystemExit("ERROR: could not find dispatch_notification().")
        app = app.replace(anchor, helper.strip() + "\n\n\n" + anchor, 1)
        print("PATCH: added notify_missing_student_profile()")
    else:
        print("SKIP: notify_missing_student_profile() already exists")

    # 2. Call it after successful student login.
    login_old = '''        if user and user.check_password(form.password.data):
            login_user(user)
'''
    login_new = '''        if user and user.check_password(form.password.data):
            login_user(user)

            if not user.is_admin:
                notify_missing_student_profile(user)
'''
    app = replace_once(app, login_old, login_new, "login profile notification")

    # 3. Track why grade-based scholarships are empty.
    category_old = '''        if profile is None:
            scholarships = []
'''
    category_new = '''        profile_missing = profile is None

        if profile_missing:
            scholarships = []
'''
    app = replace_once(
        app,
        category_old,
        category_new,
        "grade category profile_missing flag",
    )

    # 4. Pass the flag to the category template.
    render_anchor = '''    return render_template(
        "scholarship_category.html",'''
    render_new = '''    return render_template(
        "scholarship_category.html",
        profile_missing=profile_missing,'''

    if 'profile_missing=profile_missing,' in app:
        print("SKIP: scholarship_category template context already updated")
    elif render_anchor not in app:
        raise SystemExit("ERROR: could not find scholarship_category render call.")
    else:
        app = app.replace(render_anchor, render_new, 1)
        print("PATCH: passed profile_missing to scholarship_category.html")

    # 5. Replace the generic empty state with an actionable profile prompt.
    template_old = '''        {% else %}
        <article class="dashboard-card">
            <h2>No scholarships available yet</h2>
            <p>
                There are currently no active scholarships in this category
                matching your profile.
            </p>
        </article>
        {% endfor %}'''
    template_new = '''        {% else %}
        <article class="dashboard-card">
            {% if category == "grade" and profile_missing %}
                <h2>Complete your profile to see grade-based scholarships</h2>
                <p>
                    You have not created your student profile yet. Add your
                    education details so GovScale can match you with
                    grade-based scholarships.
                </p>
                <a href="{{ url_for('profile') }}" class="button button-primary">
                    Create or update profile
                </a>
            {% else %}
                <h2>No scholarships available yet</h2>
                <p>
                    There are currently no active scholarships in this category
                    matching your profile.
                </p>
            {% endif %}
        </article>
        {% endfor %}'''

    template = replace_once(
        template,
        template_old,
        template_new,
        "scholarship category empty state",
    )

    APP.write_text(app, encoding="utf-8")
    TEMPLATE.write_text(template, encoding="utf-8")
    print("\nDone. Review the diff, then run your app/tests.")


if __name__ == "__main__":
    main()