
import os
import re
from functools import wraps
from sqlalchemy import text, or_
from pathlib import Path
from urllib.parse import urlsplit
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    url_for,
    request,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
)


app = Flask(__name__, instance_relative_config=True)

# Set GOVSCALE_SECRET_KEY in your environment before production deployment.
app.config["SECRET_KEY"] = os.environ.get(
    "GOVSCALE_SECRET_KEY",
    "local-development-key-change-before-deployment",
)

Path(app.instance_path).mkdir(parents=True, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + str(Path(app.instance_path) / "govscale.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Enable CSRF protection for POST forms
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access your student dashboard."
login_manager.init_app(app)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    education_level = db.Column(db.String(30), nullable=False)
    indian_citizen_declared = db.Column(
        db.Boolean, nullable=False, default=False
    )
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)



class Scholarship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(20), nullable=False, index=True)
    education_category = db.Column(db.String(30),nullable=True,index=True,)
    description = db.Column(db.Text, nullable=False)
    award_amount = db.Column(db.Integer, nullable=False)
    eligibility_description = db.Column(db.Text, nullable=False)
    eligible_education_levels = db.Column(db.String(100), nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class StudentProfile(db.Model):
    __tablename__ = "student_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"),
        unique=True, nullable=False
    )
    education_category = db.Column(db.String(30), nullable=False)
    study_level = db.Column(db.String(30), nullable=False)
    institution_name = db.Column(db.String(200), nullable=False)
    institution_not_listed = db.Column(
        db.Boolean, nullable=False, default=False
    )
    grading_system = db.Column(db.String(20), nullable=True)
    academic_score = db.Column(db.Float, nullable=True)
    annual_family_income = db.Column(db.Integer, nullable=True)

    user = db.relationship("User", backref=db.backref(
        "student_profile", uselist=False
    ))


class ScholarshipCriteria(db.Model):
    __tablename__ = "scholarship_criteria"

    id = db.Column(db.Integer, primary_key=True)
    scholarship_id = db.Column(
        db.Integer, db.ForeignKey("scholarship.id"),
        unique=True, nullable=False
    )
    eligible_study_levels = db.Column(db.String(200), nullable=False)
    minimum_percentage = db.Column(db.Float, nullable=True)
    minimum_cgpa = db.Column(db.Float, nullable=True)
    annual_income_limit = db.Column(db.Integer, nullable=True)
    requires_academic_proof = db.Column(
        db.Boolean, nullable=False, default=False
    )
    requires_income_proof = db.Column(
        db.Boolean, nullable=False, default=False
    )

    scholarship = db.relationship("Scholarship", backref=db.backref(
        "criteria", uselist=False
    ))

class ScholarshipApplication(db.Model):
    __tablename__ = "scholarship_application"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    scholarship_id = db.Column(
        db.Integer,
        db.ForeignKey("scholarship.id"),
        nullable=False,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="submitted",
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "scholarship_id",
            name="uq_student_scholarship_application",
        ),
    )

    user = db.relationship(
        "User",
        backref=db.backref("scholarship_applications", lazy=True),
    )

    scholarship = db.relationship(
        "Scholarship",
        backref=db.backref("applications", lazy=True),
    )


class DemoExam(db.Model):
    __tablename__ = "demo_exam"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    registration_opens_at = db.Column(db.DateTime, nullable=True)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    scholarship_id = db.Column(
        db.Integer,
        db.ForeignKey("scholarship.id"),
        nullable=True,
        index=True,
    )
    scholarship = db.relationship(
        "Scholarship",
        backref=db.backref("demo_exams", lazy=True),
    )

class ExamRegistration(db.Model):
    __tablename__ = "exam_registration"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    exam_id = db.Column(
        db.Integer,
        db.ForeignKey("demo_exam.id"),
        nullable=False,
    )

    registered_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="registered",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "exam_id",
            name="uq_student_exam_registration",
        ),
    )

    user = db.relationship(
        "User",
        backref=db.backref("exam_registrations", lazy=True),
    )

    exam = db.relationship(
        "DemoExam",
        backref=db.backref("registrations", lazy=True),
    )

class Institution(db.Model):
    __tablename__ = "institution"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    normalized_name = db.Column(
        db.String(200), unique=True, nullable=False, index=True
    )
    institution_type = db.Column(db.String(30), nullable=False)
    education_categories = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=db.func.current_timestamp()
    )


def normalize_institution_name(name):
    return re.sub(r"\s+", " ", name.strip()).casefold()

INSTITUTION_ALIASES = {
    "pune university": "Savitribai Phule Pune University",
    "university of pune": "Savitribai Phule Pune University",
    "mumbai university": "University of Mumbai",
    "bombay university": "University of Mumbai",
    "delhi university": "University of Delhi",
    "du": "University of Delhi",
    "iit bombay": "Indian Institute of Technology Bombay",
    "iit delhi": "Indian Institute of Technology Delhi",
    "iit madras": "Indian Institute of Technology Madras",
    "pune uni": "Savitribai Phule Pune University",
}


def canonical_institution_name(name):
    normalized = normalize_institution_name(name)
    return INSTITUTION_ALIASES.get(normalized, name.strip())

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view

def student_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))

        return view(*args, **kwargs)

    return wrapped_view

class SignUpForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=254)],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, max=128, message="Use 8–128 characters."),
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    indian_citizen = BooleanField(
        "I confirm that I am an Indian citizen.",
        validators=[DataRequired()],
    )
    submit = SubmitField("Create my account")

    def validate_full_name(self, field):
        if not field.data or not field.data.strip():
            raise ValidationError("Please enter your full name.")

    def validate_email(self, field):
        field.data = field.data.strip().lower()


class LoginForm(FlaskForm):
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=254)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")

    def validate_email(self, field):
        field.data = field.data.strip().lower()


class StudentProfileForm(FlaskForm):
    education_category = SelectField(
        "Education category",
        choices=[
            ("school_8_10", "Classes 8–10"),
            ("school_11_12", "Classes 11–12"),
            ("undergraduate_1_4", "Undergraduate — Years 1–4"),
        ],
        validators=[DataRequired()],
    )

    study_level = SelectField(
        "Current class or year",
        choices=[
            ("class_8", "Class 8"),
            ("class_9", "Class 9"),
            ("class_10", "Class 10"),
            ("class_11", "Class 11"),
            ("class_12", "Class 12"),
            ("ug_year_1", "Undergraduate Year 1"),
            ("ug_year_2", "Undergraduate Year 2"),
            ("ug_year_3", "Undergraduate Year 3"),
            ("ug_year_4", "Undergraduate Year 4"),
        ],
        validators=[DataRequired()],
    )

    institution_name = StringField(
        "School or institution name",
        validators=[DataRequired(), Length(min=2, max=200)],
    )

    institution_not_listed = BooleanField(
        "My institution is not listed"
    )

    grading_system = SelectField(
        "Academic grading format",
        choices=[
            ("", "Not provided"),
            ("percentage", "Percentage"),
            ("cgpa", "CGPA"),
        ],
        validators=[DataRequired()],
    )

    academic_score = StringField(
        "Academic score",
        validators=[Length(max=20)],
    )

    annual_family_income = StringField(
        "Annual family income in ₹ (optional)",
        validators=[Length(max=20)],
    )

    submit = SubmitField("Save profile")

def check_scholarship_eligibility(user, scholarship):
    """Return (eligible, reasons) using GovScale's existing rules."""
    reasons = []

    if not user.indian_citizen_declared:
        reasons.append(
            "This scholarship is available to registered students "
            "who declare Indian citizenship."
        )
        return False, reasons

    if scholarship.category == "exam":
        return True, []

    if scholarship.category == "grade":
        profile = StudentProfile.query.filter_by(
            user_id=user.id
        ).first()

        if profile is None:
            reasons.append(
                "Please complete your student profile first."
            )
            return False, reasons

        if profile.education_category != scholarship.education_category:
            reasons.append(
                "Your education category does not match this "
                "scholarship's requirements."
            )

        if profile.annual_family_income is None:
            reasons.append(
                "Please add your annual family income to your profile "
                "to check eligibility."
            )
        elif profile.annual_family_income > 400000:
            reasons.append(
                "Your annual family income exceeds the maximum "
                "eligible limit of ₹4,00,000."
            )

        return not reasons, reasons

    return False, ["This scholarship category is not supported."]

@app.route("/")
def home():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    upcoming_exam = DemoExam.query.join(
        Scholarship,
        DemoExam.scholarship_id == Scholarship.id,
    ).filter(
        DemoExam.is_active.is_(True),
        DemoExam.end_at > now_ist,
        Scholarship.is_active.is_(True),
        Scholarship.category == "exam",
    ).order_by(
        DemoExam.start_at.asc()
    ).first()

    upcoming_exam_start_iso = (
        upcoming_exam.start_at.replace(
            tzinfo=india_tz
        ).isoformat()
        if upcoming_exam else None
    )

    query = Scholarship.query.filter_by(is_active=True)

    if current_user.is_authenticated:
        profile = StudentProfile.query.filter_by(
            user_id=current_user.id
        ).first()

        if profile:
            query = query.filter(
                db.or_(
                    Scholarship.category == "exam",
                    db.and_(
                        Scholarship.category == "grade",
                        Scholarship.education_category
                        == profile.education_category,
                    ),
                )
            )
        else:
            # Until a student saves their education category,
            # show only exam-based scholarships.
            query = query.filter(Scholarship.category == "exam")

    
    scholarships = query.order_by(
        Scholarship.deadline.asc(),
        Scholarship.id.asc(),
    ).all()

    visible_exam_scholarship_ids = {
        row[0]
        for row in db.session.query(DemoExam.scholarship_id)
        .join(Scholarship, DemoExam.scholarship_id == Scholarship.id)
        .filter(
            DemoExam.is_active.is_(True),
            DemoExam.end_at > now_ist,
            Scholarship.is_active.is_(True),
            Scholarship.category == "exam",
        )
        .all()
    }

    scholarships = [
        scholarship for scholarship in scholarships
        if scholarship.category != "exam"
        or scholarship.id in visible_exam_scholarship_ids
    ]

    # Homepage impact metrics use global database totals,
    # not the personalized scholarship list shown to a logged-in student.
    impact_active_count = Scholarship.query.filter_by(
        is_active=True
    ).count()

    impact_applications_count = ScholarshipApplication.query.filter_by(
        status="submitted"
    ).count()

    impact_students_count = User.query.count()

    impact_grade_count = Scholarship.query.filter_by(
        is_active=True,
        category="grade",
    ).count()

    impact_exam_count = Scholarship.query.filter_by(
        is_active=True,
        category="exam",
    ).count()

    impact_scholarships_awarded = ScholarshipApplication.query.filter_by(
        status="approved"
    ).count()

    # TODO: Replace with a real count when exam registration is implemented.
    impact_exam_participants = 0

    return render_template(
        "index.html",
        scholarships=scholarships,
        impact_active_count=impact_active_count,
        impact_applications_count=impact_applications_count,
        impact_students_count=impact_students_count,
        impact_grade_count=impact_grade_count,
        impact_exam_count=impact_exam_count,
        impact_scholarships_awarded=impact_scholarships_awarded,
        impact_exam_participants=impact_exam_participants,
        upcoming_exam=upcoming_exam,
        upcoming_exam_start_iso=upcoming_exam_start_iso,
    )



@app.route("/scholarships/<int:scholarship_id>")
def scholarship_detail(scholarship_id):
    scholarship = db.session.get(Scholarship, scholarship_id)
    if scholarship is None or not scholarship.is_active:
        abort(404)

    linked_exam = None
    if scholarship.category == "exam":
        linked_exam = (
            DemoExam.query
            .filter_by(
                scholarship_id=scholarship.id,
                is_active=True,
            )
            .order_by(DemoExam.start_at.asc())
            .first()
        )
   
    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    if scholarship.category == "exam":
        if linked_exam is None or linked_exam.end_at <= now_ist:
            abort(404)

    exam_registration = None
    registration_status = None
    registration_closes_at = None

    if linked_exam:
        registration_closes_at = datetime.combine(
            linked_exam.start_at.date(), time.min
        )

        if linked_exam.end_at <= now_ist:
            registration_status = "finished"
        elif linked_exam.registration_opens_at is None:
            registration_status = "unconfigured"
        elif linked_exam.registration_opens_at > (
            linked_exam.start_at - timedelta(days=1)
        ):
            registration_status = "invalid"
        elif now_ist < linked_exam.registration_opens_at:
            registration_status = "upcoming"
        elif now_ist >= registration_closes_at:
            registration_status = "closed"
        else:
            registration_status = "open"

        if current_user.is_authenticated:
            exam_registration = ExamRegistration.query.filter_by(
                user_id=current_user.id,
                exam_id=linked_exam.id,
            ).first()

    eligible = None
    ineligible_reasons = []

    if current_user.is_authenticated:
        eligible, ineligible_reasons = (
            check_scholarship_eligibility(
                current_user, scholarship
            )
        )

    existing_application = None

    if current_user.is_authenticated:
        existing_application = ScholarshipApplication.query.filter_by(
            user_id=current_user.id,
            scholarship_id=scholarship.id,
        ).first()

    return render_template(
        "scholarship_detail.html",
        scholarship=scholarship,
        eligible=eligible,
        ineligible_reasons=ineligible_reasons,
        existing_application=existing_application,
        linked_exam=linked_exam,
        exam_registration=exam_registration,
        registration_status=registration_status,
        registration_closes_at=registration_closes_at,
        now_ist=now_ist,
    )

@app.route("/exams/<int:exam_id>/register", methods=["POST"])
@student_required
def register_for_exam(exam_id):
    exam = db.session.get(DemoExam, exam_id)

    if exam is None or not exam.is_active:
        abort(404)

    scholarship = db.session.get(Scholarship, exam.scholarship_id)

    if (
        scholarship is None
        or not scholarship.is_active
        or scholarship.category != "exam"
    ):
        abort(404)

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    # Registration closes at midnight at the beginning of exam day.
    registration_closes_at = datetime.combine(
        exam.start_at.date(), time.min
    )

    if exam.registration_opens_at is None:
        flash("Registration is not open yet.", "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    if now_ist < exam.registration_opens_at:
        flash("Registration has not opened yet.", "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    if now_ist >= exam.end_at:
        flash("This exam has already finished.", "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    if now_ist >= registration_closes_at:
        flash("Registration for this exam has closed.", "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    # Require at least 24 hours between opening and exam start.
    if exam.registration_opens_at > (
        exam.start_at - timedelta(days=1)
    ):
        flash(
            "This exam's registration schedule is invalid. "
            "Please contact the portal administrator.",
            "error",
        )
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    eligible, reasons = check_scholarship_eligibility(
        current_user, scholarship
    )

    if not eligible:
        for reason in reasons:
            flash(reason, "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    existing_registration = ExamRegistration.query.filter_by(
        user_id=current_user.id,
        exam_id=exam.id,
    ).first()

    if existing_registration:
        if existing_registration.status == "cancelled":
            flash(
                "You previously cancelled this registration. "
                "You cannot register for this exam again.",
                "error",
            )
        else:
            flash("You are already registered for this exam.", "info")

        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    registration = ExamRegistration(
        user_id=current_user.id,
        exam_id=exam.id,
        status="registered",
    )

    db.session.add(registration)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("You are already registered for this exam.", "info")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    flash("You are successfully registered for the exam.", "success")
    return redirect(
        url_for(
            "scholarship_detail",
            scholarship_id=scholarship.id,
        )
    )

@app.route(
    "/scholarships/<int:scholarship_id>/apply",
    methods=["POST"],
)
@student_required
def apply_for_scholarship(scholarship_id):
    scholarship = db.session.get(Scholarship, scholarship_id)

    if scholarship is None or not scholarship.is_active:
        abort(404)

    eligible, reasons = check_scholarship_eligibility(
        current_user, scholarship
    )

    if not eligible:
        for reason in reasons:
            flash(reason, "error")
        return redirect(
            url_for(
                "scholarship_detail",
                scholarship_id=scholarship.id,
            )
        )

    existing = ScholarshipApplication.query.filter_by(
        user_id=current_user.id,
        scholarship_id=scholarship.id,
    ).first()

    if existing:
        if existing.status == "withdrawn":
            flash(
                "You previously withdrew this application. "
                "You cannot apply for this scholarship again.",
                "error",
            )
        else:
            flash(
                "You already have an application record for this scholarship.",
                "info",
            )

        return redirect(url_for("my_applications"))

    application = ScholarshipApplication(
        user_id=current_user.id,
        scholarship_id=scholarship.id,
        status="submitted",
    )

    db.session.add(application)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "You have already applied for this scholarship.",
            "error",
        )
        return redirect(url_for("my_applications"))

    flash("Your scholarship application has been submitted.", "success")
    return redirect(url_for("my_applications"))


@app.route(
    "/applications/<int:application_id>/withdraw",
    methods=["POST"],
)
@student_required
def withdraw_scholarship_application(application_id):
    application = db.session.get(
        ScholarshipApplication, application_id
    )

    if application is None or application.user_id != current_user.id:
        abort(404)

    if application.scholarship.category != "grade":
        flash(
            "Only grade-based scholarship applications can be withdrawn.",
            "error",
        )
        return redirect(url_for("my_applications"))

    if application.status not in ("submitted", "pending"):
        flash(
            "This application cannot be withdrawn in its current status.",
            "error",
        )
        return redirect(url_for("my_applications"))

    application.status = "withdrawn"
    db.session.commit()

    flash(
        "Your application has been withdrawn. "
        "You cannot apply for this scholarship again.",
        "success",
    )
    return redirect(url_for("my_applications"))


@app.route(
    "/exam-registrations/<int:registration_id>/cancel",
    methods=["POST"],
)
@student_required
def cancel_exam_registration(registration_id):
    registration = db.session.get(
        ExamRegistration, registration_id
    )

    if registration is None or registration.user_id != current_user.id:
        abort(404)

    if registration.status != "registered":
        flash(
            "This exam registration cannot be cancelled again.",
            "error",
        )
        return redirect(url_for("my_applications"))

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    # Registration closes at midnight at the beginning of exam day.
    registration_closes_at = datetime.combine(
        registration.exam.start_at.date(), time.min
    )

    if now_ist >= registration_closes_at:
        flash(
            "The registration cancellation deadline has passed.",
            "error",
        )
        return redirect(url_for("my_applications"))

    registration.status = "cancelled"
    db.session.commit()

    flash(
        "Your exam registration has been cancelled. "
        "You cannot register for this exam again.",
        "success",
    )
    return redirect(url_for("my_applications"))

@app.route("/my-applications")
@student_required
def my_applications():
    applications = (
        ScholarshipApplication.query
        .filter_by(user_id=current_user.id)
        .order_by(ScholarshipApplication.submitted_at.desc())
        .all()
    )

    exam_registrations = (
        ExamRegistration.query
        .filter_by(user_id=current_user.id)
        .order_by(ExamRegistration.registered_at.desc())
        .all()
    )

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    return render_template(
        "my_applications.html",
        applications=applications,
        exam_registrations=exam_registrations,
        now_ist=now_ist,
    )


@app.route("/scholarships/category/<category>")
@student_required
def scholarship_category(category):
    if category not in ("grade", "exam"):
        abort(404)

    query = Scholarship.query.filter_by(
        is_active=True,
        category=category,
    )

    if category == "grade":
        profile = StudentProfile.query.filter_by(
            user_id=current_user.id
        ).first()

        if profile is None:
            scholarships = []
        else:
            scholarships = query.filter_by(
                education_category=profile.education_category
            ).order_by(
                Scholarship.deadline.asc(),
                Scholarship.id.asc(),
            ).all()
    else:
        scholarships = query.order_by(
            Scholarship.deadline.asc(),
            Scholarship.id.asc(),
        ).all()

        india_tz = ZoneInfo("Asia/Kolkata")
        now_ist = datetime.now(india_tz).replace(tzinfo=None)

        visible_exam_scholarship_ids = {
            row[0]
            for row in db.session.query(DemoExam.scholarship_id)
            .join(Scholarship, DemoExam.scholarship_id == Scholarship.id)
            .filter(
                DemoExam.is_active.is_(True),
                DemoExam.end_at > now_ist,
                Scholarship.is_active.is_(True),
                Scholarship.category == "exam",
            )
            .all()
        }

        scholarships = [
            scholarship for scholarship in scholarships
            if scholarship.id in visible_exam_scholarship_ids
        ]

    category_title = (
        "Grade-based Scholarships"
        if category == "grade"
        else "Exam-based Scholarships"
    )

    return render_template(
        "scholarship_category.html",
        scholarships=scholarships,
        category=category,
        category_title=category_title,
    )

def _safe_next_url(next_url):
    """Reject external redirects and admin destinations for students."""
    if not next_url or "\\" in next_url:
        return None

    parsed = urlsplit(next_url)

    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None

    if parsed.path.startswith("//"):
        return None

    if parsed.path == "/admin" or parsed.path.startswith("/admin/"):
        return None

    return next_url


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))

    form = SignUpForm()

    if form.validate_on_submit():
        email = form.email.data

        if db.session.query(User.id).filter_by(email=email).first():
            form.email.errors.append(
                "An account with this email already exists. Please log in."
            )
            return render_template("signup.html", form=form)

        user = User(
            full_name=form.full_name.data.strip(),
            email=email,
            education_level="not_specified",
            indian_citizen_declared=form.indian_citizen.data,
        )
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.email.errors.append(
                "This email is already registered. Please log in."
            )
            return render_template("signup.html", form=form)

        login_user(user)
        flash("Your account has been created. Welcome to GovScale!", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next", "")

    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))

        safe_next_url = _safe_next_url(next_url)
        if safe_next_url:
            return redirect(safe_next_url)

        return redirect(url_for("dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        user = db.session.query(User).filter_by(
            email=form.email.data.strip().lower()
        ).first()

        if user and user.check_password(form.password.data):
            login_user(user)
            flash("You are now logged in.", "success")

            # Admins must always enter the admin panel.
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))

            safe_next_url = _safe_next_url(next_url)
            if safe_next_url:
                return redirect(safe_next_url)

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/exams/<int:exam_id>/start")
@student_required
def exam_entry(exam_id):
    exam = db.session.get(DemoExam, exam_id)

    if exam is None:
        abort(404)

    registration = ExamRegistration.query.filter_by(
        user_id=current_user.id,
        exam_id=exam.id,
        status="registered",
    ).first()

    if registration is None:
        flash("You must have an active registration to access this exam.", "error")
        return redirect(url_for("dashboard"))

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    scholarship = db.session.get(Scholarship, exam.scholarship_id)

    if (
        not exam.is_active
        or scholarship is None
        or not scholarship.is_active
    ):
        flash("This exam is currently unavailable.", "error")
        return redirect(url_for("dashboard"))

    if now_ist < exam.start_at:
        return redirect(url_for("exam_lobby", exam_id=exam.id))

    if now_ist >= exam.end_at:
        flash("This exam has concluded.", "error")
        return redirect(url_for("exam_lobby", exam_id=exam.id))

    return redirect(url_for("exam_page", exam_id=exam.id))

@app.route("/exams/<int:exam_id>")
@student_required
def exam_lobby(exam_id):
    exam = db.session.get(DemoExam, exam_id)

    if exam is None:
        abort(404)

    registration = ExamRegistration.query.filter_by(
        user_id=current_user.id,
        exam_id=exam.id,
        status="registered",
    ).first()

    if registration is None:
        flash("You must have an active registration to access this exam.", "error")
        return redirect(url_for("dashboard"))

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    exam_start_iso = exam.start_at.replace(
        tzinfo=india_tz
    ).isoformat()

    exam_end_iso = exam.end_at.replace(
        tzinfo=india_tz
    ).isoformat()

    if now_ist >= exam.end_at:
        exam_state = "ended"
    elif now_ist >= exam.start_at:
        exam_state = "started"
    else:
        exam_state = "upcoming"

    return render_template(
        "exam_lobby.html",
        exam=exam,
        exam_start_iso=exam_start_iso,
        exam_end_iso=exam_end_iso,
        exam_state=exam_state,
    )

@app.route("/exams/<int:exam_id>/take")
@student_required
def exam_page(exam_id):
    exam = db.session.get(DemoExam, exam_id)

    if exam is None:
        abort(404)

    registration = ExamRegistration.query.filter_by(
        user_id=current_user.id,
        exam_id=exam.id,
        status="registered",
    ).first()

    if registration is None:
        flash("You must have an active registration to access this exam.", "error")
        return redirect(url_for("dashboard"))

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    scholarship = db.session.get(Scholarship, exam.scholarship_id)

    if (
        not exam.is_active
        or scholarship is None
        or not scholarship.is_active
        or now_ist < exam.start_at
        or now_ist >= exam.end_at
    ):
        return redirect(url_for("exam_entry", exam_id=exam.id))

    return render_template("exam_page.html", exam=exam)

@app.route("/dashboard")
@student_required
def dashboard():
    profile = StudentProfile.query.filter_by(
        user_id=current_user.id
    ).first()

    query = Scholarship.query.filter_by(is_active=True)

    if profile:
        query = query.filter(
            db.or_(
                Scholarship.category == "exam",
                db.and_(
                    Scholarship.category == "grade",
                    Scholarship.education_category
                    == profile.education_category,
                ),
            )
        )
    else:
        query = query.filter(Scholarship.category == "exam")

    scholarships = query.all()

    india_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(india_tz).replace(tzinfo=None)

    visible_exam_scholarship_ids = {
        row[0]
        for row in db.session.query(DemoExam.scholarship_id)
        .join(Scholarship, DemoExam.scholarship_id == Scholarship.id)
        .filter(
            DemoExam.is_active.is_(True),
            DemoExam.end_at > now_ist,
            Scholarship.is_active.is_(True),
            Scholarship.category == "exam",
        )
        .all()
    }

    scholarships = [
        scholarship for scholarship in scholarships
        if scholarship.category != "exam"
        or scholarship.id in visible_exam_scholarship_ids
    ]

    registered_exam = (
        DemoExam.query
        .join(
            ExamRegistration,
            ExamRegistration.exam_id == DemoExam.id,
        )
        .join(
            Scholarship,
            DemoExam.scholarship_id == Scholarship.id,
        )
        .filter(
            ExamRegistration.user_id == current_user.id,
            ExamRegistration.status == "registered",
            Scholarship.is_active.is_(True),
            DemoExam.is_active.is_(True),
            DemoExam.end_at > now_ist,
        )
        .order_by(DemoExam.start_at.asc())
        .first()
    )

    registered_exam_start_iso = (
        registered_exam.start_at.replace(
            tzinfo=india_tz
        ).isoformat()
        if registered_exam else None
    )

    registered_exam_end_iso = (
        registered_exam.end_at.replace(tzinfo=india_tz).isoformat()
        if registered_exam else None
    )

    grade_count = sum(
        1 for scholarship in scholarships
        if scholarship.category == "grade"
    )
    exam_count = sum(
        1 for scholarship in scholarships
        if scholarship.category == "exam"
    )

    return render_template(
        "dashboard.html",
        scholarships=scholarships,
        grade_count=grade_count,
        exam_count=exam_count,
        registered_exam=registered_exam,
        registered_exam_start_iso=registered_exam_start_iso,
        registered_exam_end_iso=registered_exam_end_iso,
    )

@app.route("/profile", methods=["GET", "POST"])
@student_required
def student_profile():
    profile = StudentProfile.query.filter_by(
        user_id=current_user.id
    ).first()

    form = StudentProfileForm()
    institution_data = [
    {
        "name": institution.name,
        "categories": institution.education_categories.split(",")
    }
    for institution in Institution.query.order_by(Institution.name.asc()).all()
    ]

    if request.method == "GET" and profile:
        form.education_category.data = profile.education_category
        form.study_level.data = profile.study_level
        form.institution_name.data = profile.institution_name
        form.institution_not_listed.data = profile.institution_not_listed
        form.grading_system.data = profile.grading_system or ""
        form.academic_score.data = (
            str(profile.academic_score)
            if profile.academic_score is not None else ""
        )
        form.annual_family_income.data = (
            str(profile.annual_family_income)
            if profile.annual_family_income is not None else ""
        )

    if form.validate_on_submit():
        category_for_level = {
            "class_8": "school_8_10",
            "class_9": "school_8_10",
            "class_10": "school_8_10",
            "class_11": "school_11_12",
            "class_12": "school_11_12",
            "ug_year_1": "undergraduate_1_4",
            "ug_year_2": "undergraduate_1_4",
            "ug_year_3": "undergraduate_1_4",
            "ug_year_4": "undergraduate_1_4",
        }

        if category_for_level.get(form.study_level.data) != form.education_category.data:
            flash(
                "Please select a class or year that matches your education category.",
                "error",
            )
            return render_template(
                "profile.html", form=form, profile=profile,
                institutions=institution_data,
            )

        score = None
        income = None

        try:
            if form.academic_score.data.strip():
                score = float(form.academic_score.data.strip())
            if form.annual_family_income.data.strip():
                income = int(form.annual_family_income.data.strip())
        except ValueError:
            flash("Enter a valid academic score and family income.", "error")
            return render_template(
                                "profile.html", form=form, profile=profile,
                                institutions=institution_data,
                            )

        if score is not None:
            maximum = 100 if form.grading_system.data == "percentage" else 10
            if score < 0 or score > maximum:
                flash(
                    f"Your score must be between 0 and {maximum}.",
                    "error",
                )
                return render_template(
                    "profile.html", form=form, profile=profile,
                    institutions=institution_data,
                )

        if income is not None and income < 0:
            flash("Family income cannot be negative.", "error")
            return render_template(
                                "profile.html", form=form, profile=profile,
                                institutions=institution_data,
                            )

        if profile is None:
            profile = StudentProfile(user_id=current_user.id)

        profile.education_category = form.education_category.data
        profile.study_level = form.study_level.data
        profile.institution_not_listed = bool(form.institution_not_listed.data)
        profile.grading_system = form.grading_system.data or None
        profile.academic_score = score
        profile.annual_family_income = income

        # Resolve recognized institution aliases to their canonical name.
        entered_name = form.institution_name.data.strip()
        canonical_name = canonical_institution_name(entered_name)
        normalized = normalize_institution_name(canonical_name)

        institution = Institution.query.filter_by(
            normalized_name=normalized
        ).first()

        if institution is None:
            is_school = form.education_category.data.startswith("school_")

            institution = Institution(
                name=canonical_name,
                normalized_name=normalized,
                institution_type="school" if is_school else "college",
                education_categories=form.education_category.data,
                is_verified=False,
                created_by_user_id=current_user.id,
            )
            db.session.add(institution)
        else:
            # Include this education category if it is not already supported.
            categories = institution.education_categories.split(",")
            selected_category = form.education_category.data

            if selected_category not in categories:
                categories.append(selected_category)
                institution.education_categories = ",".join(categories)

        # Store the canonical name in the student's profile.
        profile.institution_name = institution.name


        db.session.add(profile)
        db.session.commit()

        flash("Your student profile has been saved.", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "profile.html", form=form, profile=profile,
        institutions=institution_data,
    )

@app.route("/admin/applications")
@admin_required
def admin_applications():
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    allowed_statuses = {
        "submitted", "pending", "approved", "rejected", "withdrawn"
    }

    applications_query = (
        ScholarshipApplication.query
        .join(User, ScholarshipApplication.user_id == User.id)
        .join(Scholarship, ScholarshipApplication.scholarship_id == Scholarship.id)
    )

    if search:
        term = f"%{search}%"
        applications_query = applications_query.filter(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                Scholarship.title.ilike(term),
            )
        )

    if status_filter in allowed_statuses:
        applications_query = applications_query.filter(
            ScholarshipApplication.status == status_filter
        )
    else:
        status_filter = ""

    applications = applications_query.order_by(
        ScholarshipApplication.submitted_at.desc()
    ).all()

    return render_template(
        "admin/applications.html",
        applications=applications,
        search=search,
        status_filter=status_filter,
    )


@app.route("/admin/applications/<int:application_id>/review", methods=["POST"])
@admin_required
def admin_review_application(application_id):
    application = db.session.get(ScholarshipApplication, application_id)

    if application is None:
        abort(404)

    requested_status = request.form.get("status", "").strip().lower()

    if requested_status not in ("approved", "rejected"):
        flash("Invalid application review action.", "error")
        return redirect(url_for("admin_applications"))

    if application.status not in ("submitted", "pending"):
        flash(
            "Only submitted applications can be approved or rejected.",
            "error",
        )
        return redirect(url_for("admin_applications"))

    application.status = requested_status
    db.session.commit()

    flash(
        f"Application #{application.id} has been {requested_status}.",
        "success",
    )
    return redirect(url_for("admin_applications"))



@app.route("/admin/scholarships")
@admin_required
def admin_scholarships():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    query = Scholarship.query.filter_by(category="grade")

    if search:
        query = query.filter(Scholarship.title.ilike(f"%{search}%"))

    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)
    else:
        status = ""

    scholarships = query.order_by(Scholarship.id.desc()).all()

    return render_template(
        "admin/scholarships.html",
        scholarships=scholarships,
        search=search,
        status_filter=status,
    )


@app.route("/admin/scholarships/new", methods=["GET", "POST"])
@app.route("/admin/scholarships/<int:scholarship_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_scholarship_form(scholarship_id=None):
    scholarship = (
        db.session.get(Scholarship, scholarship_id)
        if scholarship_id is not None else None
    )

    if scholarship_id is not None and scholarship is None:
        abort(404)

    if scholarship is not None and scholarship.category != "grade":
        flash("Exam-based scholarships must be managed under Exam Management.", "error")
        return redirect(url_for("admin_scholarships"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = "grade"
        education_category = request.form.get("education_category", "").strip()
        description = request.form.get("description", "").strip()
        eligibility = request.form.get("eligibility_description", "").strip()

        education_levels = education_category
        amount_text = request.form.get("award_amount", "").strip()
        deadline_text = request.form.get("deadline", "").strip()

        errors = []

        if not title or len(title) > 160:
            errors.append("Enter a title between 1 and 160 characters.")

        if not description:
            errors.append("Enter a scholarship description.")

        if not eligibility:
            errors.append("Enter the eligibility requirements.")

        allowed_education_categories = {
            "school_8_10",
            "school_11_12",
            "undergraduate_1_4",
        }
        if category == "grade" and education_category not in allowed_education_categories:
            errors.append("Choose one valid education category.")

        try:
            amount = int(amount_text)
            if amount < 2000:
                raise ValueError
        except (ValueError, TypeError):
            amount = None
            errors.append("Reward amount must be a whole number of at least ₹2,000.")

        deadline = None
        if not deadline_text:
            errors.append("Enter an application deadline.")
        else:
            try:
                deadline = date.fromisoformat(deadline_text)
                today_ist = datetime.now(
                    ZoneInfo("Asia/Kolkata")
                ).date()
                if deadline <= today_ist:
                    errors.append(
                        "Application deadline must be later than today's date."
                    )
            except ValueError:
                errors.append("Enter a valid deadline.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            if scholarship is None:
                scholarship = Scholarship()
                db.session.add(scholarship)

            scholarship.title = title
            scholarship.category = category
            scholarship.education_category = education_category or None
            scholarship.description = description
            scholarship.award_amount = amount
            scholarship.eligibility_description = eligibility
            scholarship.eligible_education_levels = education_levels
            scholarship.deadline = deadline

            try:
                db.session.commit()
                flash(
                    "Scholarship created successfully."
                    if scholarship_id is None
                    else "Scholarship updated successfully.",
                    "success",
                )
                return redirect(url_for("admin_scholarships"))
            except Exception:
                db.session.rollback()
                app.logger.exception("Could not save scholarship")
                flash("The scholarship could not be saved. Please try again.", "error")

    return render_template(
        "admin/scholarship_form.html",
        scholarship=scholarship,
        is_edit=scholarship is not None,
    )


@app.route("/admin/scholarships/<int:scholarship_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_scholarship(scholarship_id):
    scholarship = db.session.get(Scholarship, scholarship_id)

    if scholarship is None:
        abort(404)

    scholarship.is_active = not scholarship.is_active
    db.session.commit()

    state = "activated" if scholarship.is_active else "deactivated"
    flash(f"'{scholarship.title}' has been {state}. Existing application history was retained.", "success")
    return redirect(url_for("admin_scholarships"))




@app.route("/admin/exams")
@admin_required
def admin_exams():
    exam_rows = []

    exam_scholarships = Scholarship.query.filter_by(
        category="exam"
    ).order_by(Scholarship.id.desc()).all()

    for scholarship in exam_scholarships:
        linked_exams = DemoExam.query.filter_by(
            scholarship_id=scholarship.id
        ).order_by(DemoExam.start_at.asc()).all()

        if linked_exams:
            for exam in linked_exams:
                exam_rows.append((scholarship, exam))
        else:
            # Keep existing exam scholarships visible so an admin can
            # complete their schedule without recreating the scholarship.
            exam_rows.append((scholarship, None))

    return render_template(
        "admin/exams.html",
        exam_rows=exam_rows,
    )


@app.route("/admin/exams/new", methods=["GET", "POST"])
@app.route("/admin/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@app.route(
    "/admin/exams/scholarship/<int:scholarship_id>/schedule",
    methods=["GET", "POST"],
)
@admin_required
def admin_exam_form(exam_id=None, scholarship_id=None):
    exam = None
    scholarship = None

    if exam_id is not None:
        exam = db.session.get(DemoExam, exam_id)
        if exam is None or exam.scholarship_id is None:
            abort(404)

        scholarship = db.session.get(Scholarship, exam.scholarship_id)
        if scholarship is None or scholarship.category != "exam":
            abort(404)

    elif scholarship_id is not None:
        scholarship = db.session.get(Scholarship, scholarship_id)
        if scholarship is None or scholarship.category != "exam":
            abort(404)

        exam = DemoExam.query.filter_by(
            scholarship_id=scholarship.id
        ).order_by(DemoExam.start_at.asc()).first()

        if exam is not None:
            return redirect(
                url_for("admin_exam_form", exam_id=exam.id)
            )

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        eligibility = request.form.get("eligibility_description", "").strip()
        amount_text = request.form.get("award_amount", "").strip()
        registration_text = request.form.get("registration_opens_at", "").strip()
        start_text = request.form.get("start_at", "").strip()
        duration_text = request.form.get("duration_minutes", "").strip()
        is_active = request.form.get("is_active") == "on"

        errors = []

        if not title or len(title) > 160:
            errors.append("Enter a title between 1 and 160 characters.")
        if not description:
            errors.append("Enter a scholarship description.")
        if not eligibility:
            errors.append("Enter the eligibility requirements.")

        try:
            amount = int(amount_text)
            if amount < 2000:
                raise ValueError
        except (ValueError, TypeError):
            amount = None
            errors.append("Reward amount must be a whole number of at least ₹2,000.")

        registration_opens_at = None
        start_at = None
        end_at = None
        duration_minutes = None

        for value, field_name in (
            (registration_text, "registration opening time"),
            (start_text, "exam start time"),
        ):
            if not value:
                errors.append(f"Enter the {field_name}.")
                continue
            try:
                parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
                if field_name == "registration opening time":
                    registration_opens_at = parsed
                else:
                    start_at = parsed
            except ValueError:
                errors.append(f"Enter a valid {field_name}.")

        try:
            duration_minutes = int(duration_text)
            if duration_minutes <= 15 or duration_minutes > 1440:
                raise ValueError
        except (ValueError, TypeError):
            duration_minutes = None
            errors.append(
                "Exam duration must be a whole number from 16 to 1440 minutes."
            )

        if start_at and duration_minutes:
            end_at = start_at + timedelta(minutes=duration_minutes)

        india_tz = ZoneInfo("Asia/Kolkata")
        now_ist = datetime.now(india_tz).replace(tzinfo=None)

        if registration_opens_at and registration_opens_at < now_ist:
            errors.append(
                "Registration opening must be the current date/time or a future time."
            )

        if registration_opens_at and start_at:
            if registration_opens_at > start_at - timedelta(days=1):
                errors.append(
                    "Registration must open at least 24 hours before the exam starts."
                )

        if registration_opens_at:
            latest_other_end = (
                db.session.query(db.func.max(DemoExam.end_at))
                .filter(
                    DemoExam.start_at.isnot(None),
                    DemoExam.end_at.isnot(None),
                    *(
                        [DemoExam.id != exam.id]
                        if exam is not None else []
                    ),
                )
                .scalar()
            )

            if (
                latest_other_end is not None
                and registration_opens_at <= latest_other_end
            ):
                errors.append(
                    "Registration must open after the end of every other "
                    "scheduled exam. The latest existing exam ends at "
                    f"{latest_other_end.strftime('%d %b %Y, %I:%M %p')} IST."
                )

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                if scholarship is None:
                    scholarship = Scholarship()
                    db.session.add(scholarship)

                scholarship.title = title
                scholarship.category = "exam"
                scholarship.education_category = None
                scholarship.description = description
                scholarship.award_amount = amount
                scholarship.eligibility_description = eligibility
                scholarship.eligible_education_levels = (
                    "school_8_10,school_11_12,undergraduate_1_4"
                )
                scholarship.is_active = is_active

                if exam is None:
                    exam = DemoExam()
                    db.session.add(exam)

                exam.title = title
                exam.description = description
                exam.registration_opens_at = registration_opens_at
                exam.start_at = start_at
                exam.end_at = end_at
                exam.is_active = is_active
                exam.scholarship = scholarship

                # One transaction: the scholarship and its exam schedule
                # are committed together or rolled back together.
                db.session.commit()

                flash(
                    "Exam-based scholarship and schedule saved successfully.",
                    "success",
                )
                return redirect(url_for("admin_exams"))

            except Exception:
                db.session.rollback()
                app.logger.exception(
                    "Could not save exam-based scholarship and schedule"
                )
                flash(
                    "Could not save the exam opportunity. Please try again.",
                    "error",
                )

    return render_template(
        "admin/exam_form.html",
        scholarship=scholarship,
        exam=exam,
        is_edit=scholarship is not None,
    )


@app.route("/admin")
@admin_required
def admin_dashboard():
    from datetime import datetime

    now = datetime.now()

    search = request.args.get("q", "").strip()
    category_filter = request.args.get("category", "").strip()
    status_filter = request.args.get("status", "").strip()

    # Every statistic is calculated from existing database records.
    stats = {
        "students": User.query.filter_by(is_admin=False).count(),
        "applications": ScholarshipApplication.query.count(),
        "pending_applications": ScholarshipApplication.query.filter_by(
            status="submitted"
        ).count(),
        "active_scholarships": Scholarship.query.filter_by(
            is_active=True
        ).count(),
        "upcoming_exams": DemoExam.query.filter(
            DemoExam.is_active.is_(True),
            DemoExam.end_at >= now,
        ).count(),
    }

    scholarship_query = Scholarship.query

    if search:
        scholarship_query = scholarship_query.filter(
            Scholarship.title.ilike(f"%{search}%")
        )

    if category_filter in ("grade", "exam"):
        scholarship_query = scholarship_query.filter_by(
            category=category_filter
        )

    if status_filter == "active":
        scholarship_query = scholarship_query.filter_by(is_active=True)
    elif status_filter == "inactive":
        scholarship_query = scholarship_query.filter_by(is_active=False)

    total_scholarships = scholarship_query.count()
    scholarships = scholarship_query.order_by(
        Scholarship.id.desc()
    ).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        scholarships=scholarships,
        total_scholarships=total_scholarships,
        search=search,
        category_filter=category_filter,
        status_filter=status_filter,
    )

@app.route("/health")
def health():
    return {"status": "healthy"}, 200


with app.app_context():
    db.create_all()

    # Safely add admin authorization to existing SQLite databases.
    user_columns = {
        row[1]
        for row in db.session.execute(
            text("PRAGMA table_info(user)")
        ).fetchall()
    }

    if "is_admin" not in user_columns:
        db.session.execute(
            text(
                "ALTER TABLE user "
                "ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
            )
        )
        db.session.commit()

    # Safely add registration opening time to existing SQLite databases.
    exam_columns = {
        row[1]
        for row in db.session.execute(
            text("PRAGMA table_info(demo_exam)")
        ).fetchall()
    }

    if "registration_opens_at" not in exam_columns:
        db.session.execute(
            text(
                "ALTER TABLE demo_exam "
                "ADD COLUMN registration_opens_at DATETIME"
            )
        )
        db.session.commit()

    # Existing demo exams default to opening registration 15 days early.
    db.session.execute(
        text("""
            UPDATE demo_exam
            SET registration_opens_at = datetime(start_at, '-15 days')
            WHERE registration_opens_at IS NULL
        """)
    )
    db.session.commit()

    # Seed fictional demonstration opportunities only when the catalogue
    # is empty. Existing users and scholarship records are preserved.
    if db.session.query(Scholarship.id).first() is None:
        demo_scholarships = [
            Scholarship(
                title="National Merit Challenge",
                category="exam",
                description=(
                    "A fictional scholarship opportunity based on performance "
                    "in a timed demonstration assessment."
                ),
                award_amount=25000,
                eligibility_description=(
                    "For declared Indian-citizen students who participate in "
                    "the demo exam and meet its illustrative score requirement."
                ),
                eligible_education_levels="school,college,university",
                deadline=date(2026, 11, 15),
            ),
            Scholarship(
                title="Future Learners Grant",
                category="merit",
                description=(
                    "A fictional education grant recognising academic "
                    "performance and consistent grades."
                ),
                award_amount=10000,
                eligibility_description=(
                    "For declared Indian-citizen students with an illustrative "
                    "minimum academic score of 75%. Actual marks are not "
                    "collected or verified by this demo."
                ),
                eligible_education_levels="school,college,university",
                deadline=date(2026, 12, 15),
            ),
            Scholarship(
                title="Digital Skills Award",
                category="merit",
                description=(
                    "A fictional award recognising academic achievement "
                    "and interest in digital skills."
                ),
                award_amount=15000,
                eligibility_description=(
                    "For declared Indian-citizen college and university "
                    "students meeting the illustrative academic requirements."
                ),
                eligible_education_levels="college,university",
                deadline=date(2026, 11, 30),
            ),
        ]

        starter_institutions = [
            # Schools — suggestions for Classes 8–10 and 11–12
            ("Delhi Public School, R.K. Puram", "school", "school_8_10,school_11_12", "Delhi"),
            ("The Doon School", "school", "school_8_10,school_11_12", "Uttarakhand"),
            ("Modern School, Barakhamba Road", "school", "school_8_10,school_11_12", "Delhi"),
            ("The Cathedral and John Connon School", "school", "school_8_10,school_11_12", "Maharashtra"),
            ("Bombay Scottish School, Mahim", "school", "school_8_10,school_11_12", "Maharashtra"),
            ("St. Xavier's Collegiate School", "school", "school_8_10,school_11_12", "West Bengal"),
            ("Loyola High School, Pune", "school", "school_8_10,school_11_12", "Maharashtra"),
            ("Kendriya Vidyalaya, IIT Bombay", "school", "school_8_10,school_11_12", "Maharashtra"),

            # Higher education — suggestions for undergraduate students
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

        for name, institution_type, categories, state in starter_institutions:
            normalized = normalize_institution_name(name)

            existing = Institution.query.filter_by(
                normalized_name=normalized
            ).first()

            if existing is None:
                db.session.add(
                    Institution(
                        name=name,
                        normalized_name=normalized,
                        institution_type=institution_type,
                        education_categories=categories,
                        state=state,
                        is_verified=True,
                    )
                )

        db.session.add_all(demo_scholarships)
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)
