import unittest

from app import DemoExam, ExamQuestion, Scholarship, app


class GovScaleSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_health_reports_database_reachability(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "healthy")
        self.assertEqual(response.get_json()["database"], "reachable")

    def test_homepage_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_unknown_route_returns_not_found(self):
        response = self.client.get("/this-route-does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_demo_exam_and_questions_are_seeded(self):
        with app.app_context():
            exam = DemoExam.query.filter_by(
                title="National Merit Challenge — Practice Exam"
            ).first()
            self.assertIsNotNone(exam)
            self.assertGreater(ExamQuestion.query.filter_by(exam_id=exam.id).count(), 0)

    def test_seeded_scholarships_use_supported_categories(self):
        with app.app_context():
            unsupported = Scholarship.query.filter(
                Scholarship.category.notin_(["grade", "exam"])
            ).all()
            self.assertEqual(unsupported, [])


if __name__ == "__main__":
    unittest.main()
