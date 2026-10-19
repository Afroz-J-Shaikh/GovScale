import sys
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
