#!/usr/bin/env python3
"""Send scheduled GovScale notifications. Run periodically (e.g. every 5 min)."""

from datetime import datetime, timedelta
import argparse
from zoneinfo import ZoneInfo

from app import (
    app,
    db,
    User,
    Scholarship,
    DemoExam,
    ExamRegistration,
    dispatch_notification,
    process_lifecycle_transitions,
)

IST = ZoneInfo("Asia/Kolkata")
REMINDER_WINDOW = timedelta(minutes=10)


def event_recipients(exam):
    """Admins and currently registered students for this exam."""
    recipients = {
        user.id for user in User.query.filter_by(is_admin=True).all()
    }
    recipients.update(
        row[0]
        for row in db.session.query(ExamRegistration.user_id)
        .filter_by(exam_id=exam.id, status="registered")
        .distinct()
        .all()
    )
    return recipients


def run(now=None, dry_run=False):
    now = now or datetime.now(IST)
    if now.tzinfo is not None:
        now = now.astimezone(IST).replace(tzinfo=None)

    sent = 0

    if dry_run:
        print("DRY RUN: no database writes will be made.")
        print("Lifecycle transitions: skipped in dry-run mode.")
    else:
        # Catch lifecycle transitions even if no one has visited the site.
        before = db.session.query(db.func.count()).select_from(
            __import__("app").NotificationDispatch
        ).scalar()
        process_lifecycle_transitions(now)
        after = db.session.query(db.func.count()).select_from(
            __import__("app").NotificationDispatch
        ).scalar()
        sent += max(0, after - before)

    # Grade deadline is the end of the stored deadline date (11:59:59 PM IST).
    # The reminder is sent only within a short window around the six-hour mark.
    for scholarship in Scholarship.query.filter_by(category="grade").all():
        if not scholarship.is_active or not scholarship.deadline:
            continue
        deadline_at = datetime.combine(
            scholarship.deadline,
            datetime.max.time().replace(microsecond=0),
        )
        reminder_at = deadline_at - timedelta(hours=6)
        if reminder_at <= now < reminder_at + REMINDER_WINDOW:
            admins = User.query.filter_by(is_admin=True).all()
            for admin in admins:
                if dry_run:
                    print(
                        f"WOULD NOTIFY admin user_id={admin.id}: "
                        f'Scholarship "{scholarship.title}" deadline in 6 hours.'
                    )
                elif dispatch_notification(
                    admin.id,
                    f"grade-deadline-6h:{scholarship.id}:user:{admin.id}",
                    "Scholarship deadline in 6 hours",
                    f'"{scholarship.title}" closes at '
                    f'{deadline_at.strftime("%d %b %Y, %I:%M %p")} IST.',
                ):
                    sent += 1

    for exam in DemoExam.query.filter_by(is_active=True).all():
        start_at = exam.start_at
        if start_at is None:
            continue

        # Reminder: only within 10 minutes of the six-hours-before mark.
        reminder_at = start_at - timedelta(hours=6)
        if reminder_at <= now < reminder_at + REMINDER_WINDOW:
            for user_id in event_recipients(exam):
                if dry_run:
                    print(
                        f"WOULD NOTIFY user_id={user_id}: "
                        f'Exam "{exam.title}" starts in 6 hours.'
                    )
                elif dispatch_notification(
                    user_id,
                    f"exam-start-6h:{exam.id}:user:{user_id}",
                    "Exam starts in 6 hours",
                    f'"{exam.title}" starts at '
                    f'{start_at.strftime("%d %b %Y, %I:%M %p")} IST.',
                ):
                    sent += 1

        # Start alerts are sent within 15 minutes of the start time, avoiding
        # misleading alerts for old exams if the scheduler was offline.
        if start_at <= now < start_at + timedelta(minutes=15):
            for user_id in event_recipients(exam):
                if dry_run:
                    print(
                        f"WOULD NOTIFY user_id={user_id}: "
                        f'Exam "{exam.title}" has started.'
                    )
                elif dispatch_notification(
                    user_id,
                    f"exam-started:{exam.id}:user:{user_id}",
                    "Exam has started",
                    f'"{exam.title}" started at '
                    f'{start_at.strftime("%d %b %Y, %I:%M %p")} IST.',
                ):
                    sent += 1

    if not dry_run:
        db.session.commit()
    return sent


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report reminders due now without writing to the database.",
    )
    args = parser.parse_args()

    with app.app_context():
        count = run(dry_run=args.dry_run)
        if not args.dry_run:
            print(f"Notification processor complete. New notifications: {count}")
