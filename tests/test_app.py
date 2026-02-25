import os
import tempfile
import unittest

from app import create_app
from app.extensions import db
from app.models import Category, Transaction, User


class AppTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret-key"
            WTF_CSRF_ENABLED = False
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.db_path}"
            SQLALCHEMY_TRACK_MODIFICATIONS = False

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self, email: str, password: str, display_name: str = "User") -> User:
        with self.app.app_context():
            user = User(email=email, display_name=display_name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
            return user

    def _login(self, email: str, password: str, follow_redirects: bool = True):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=follow_redirects,
        )

    def _logout(self, follow_redirects: bool = True):
        return self.client.post("/auth/logout", follow_redirects=follow_redirects)

    def test_auth_login_flow(self):
        register_resp = self.client.post(
            "/auth/register",
            data={
                "email": "alice@example.com",
                "display_name": "Alice",
                "password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=True,
        )
        self.assertEqual(register_resp.status_code, 200)
        self.assertIn("สมัครสมาชิกสำเร็จ", register_resp.get_data(as_text=True))

        logout_resp = self._logout()
        self.assertEqual(logout_resp.status_code, 200)
        self.assertIn("ออกจากระบบแล้ว", logout_resp.get_data(as_text=True))

        login_resp = self._login("alice@example.com", "password123")
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("ล็อกอินสำเร็จ", login_resp.get_data(as_text=True))

        self._logout()
        bad_login_resp = self._login("alice@example.com", "wrong-password", follow_redirects=False)
        self.assertEqual(bad_login_resp.status_code, 401)

    def test_transaction_permission_blocks_other_users_data(self):
        user_a = self._create_user("usera@example.com", "password123", "UserA")
        user_b = self._create_user("userb@example.com", "password123", "UserB")

        with self.app.app_context():
            category_b = Category(user_id=user_b.id, name="Rent", type="expense", is_active=True)
            db.session.add(category_b)
            db.session.commit()
            db.session.refresh(category_b)

            tx_b = Transaction(
                user_id=user_b.id,
                category_id=category_b.id,
                type="expense",
                amount=1000.00,
                note="B-only transaction",
            )
            db.session.add(tx_b)
            db.session.commit()
            tx_id = tx_b.id

        self._login("usera@example.com", "password123")

        edit_resp = self.client.get(f"/transactions/{tx_id}/edit")
        self.assertEqual(edit_resp.status_code, 404)

        delete_resp = self.client.post(f"/transactions/{tx_id}/delete")
        self.assertEqual(delete_resp.status_code, 404)

        self._logout()
        self._login("userb@example.com", "password123")
        own_tx_resp = self.client.get(f"/transactions/{tx_id}/edit")
        self.assertEqual(own_tx_resp.status_code, 200)

        with self.app.app_context():
            self.assertTrue(
                Transaction.query.filter_by(user_id=user_a.id).count() == 0,
                "user A must not have access to user B transactions",
            )

    def test_transaction_date_filter_invalid_input_does_not_crash(self):
        self._create_user("date@example.com", "password123", "DateUser")
        self._login("date@example.com", "password123")

        resp = self.client.get("/transactions/?start=bad-date&end=2026-99-99", follow_redirects=True)
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("รูปแบบวันที่เริ่มต้นไม่ถูกต้อง", text)
        self.assertIn("รูปแบบวันที่สิ้นสุดไม่ถูกต้อง", text)

    def test_dashboard_render_for_authenticated_user(self):
        self._create_user("dash@example.com", "password123", "DashUser")
        self._login("dash@example.com", "password123")

        resp = self.client.get("/dashboard/")
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Dashboard", text)
        self.assertIn("Income", text)
        self.assertIn("Expense", text)


if __name__ == "__main__":
    unittest.main()
