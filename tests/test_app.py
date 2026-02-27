import io
import os
import tempfile
import unittest
from datetime import date

from app import create_app
from app.extensions import db
from app.models import Budget, Category, RecurringTransaction, SavingsGoal, Transaction, User


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

        resp = self.client.get("/dashboard/", follow_redirects=True)
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("แดชบอร์ดภาพรวม", text)
        self.assertIn("Income", text)
        self.assertIn("Expense", text)

    def test_transaction_can_use_typed_category_name(self):
        user = self._create_user("catname@example.com", "password123", "CatName")
        self._login("catname@example.com", "password123")

        create_resp = self.client.post(
            "/transactions/new",
            data={
                "type": "expense",
                "amount": "250.00",
                "tx_date": "2026-02-25",
                "category_id": "-1",
                "category_name": "Food",
                "note": "Lunch",
            },
            follow_redirects=True,
        )
        self.assertEqual(create_resp.status_code, 200)

        with self.app.app_context():
            category = Category.query.filter_by(user_id=user.id, type="expense", name="Food").first()
            self.assertIsNotNone(category)
            tx = Transaction.query.filter_by(user_id=user.id, note="Lunch").first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.category_id, category.id)

        create_again_resp = self.client.post(
            "/transactions/new",
            data={
                "type": "expense",
                "amount": "100.00",
                "tx_date": "2026-02-25",
                "category_id": "-1",
                "category_name": "Food",
                "note": "Dinner",
            },
            follow_redirects=True,
        )
        self.assertEqual(create_again_resp.status_code, 200)

        with self.app.app_context():
            self.assertEqual(
                Category.query.filter_by(user_id=user.id, type="expense", name="Food").count(),
                1,
            )

    def test_typed_category_requires_other_selection(self):
        self._create_user("typedrule@example.com", "password123", "TypedRule")
        self._login("typedrule@example.com", "password123")

        resp = self.client.post(
            "/transactions/new",
            data={
                "type": "expense",
                "amount": "50.00",
                "tx_date": "2026-02-25",
                "category_id": "-2",
                "category_name": "Transport",
                "note": "Bus",
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("ให้เลือก &#39;อื่นๆ&#39; ก่อน", resp.get_data(as_text=True))

    def test_other_selection_requires_typed_category_name(self):
        self._create_user("otherrule@example.com", "password123", "OtherRule")
        self._login("otherrule@example.com", "password123")

        resp = self.client.post(
            "/transactions/new",
            data={
                "type": "expense",
                "amount": "75.00",
                "tx_date": "2026-02-25",
                "category_id": "-1",
                "category_name": "",
                "note": "Taxi",
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("โปรดกรอกชื่อหมวดหมู่เมื่อเลือก &#39;อื่นๆ&#39;", resp.get_data(as_text=True))

    def test_income_requires_typed_category_name(self):
        self._create_user("income-required@example.com", "password123", "IncomeReq")
        self._login("income-required@example.com", "password123")

        resp = self.client.post(
            "/transactions/new",
            data={
                "type": "income",
                "amount": "1200.00",
                "tx_date": "2026-02-25",
                "category_id": "-2",
                "category_name": "",
                "note": "Salary",
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("โปรดระบุหมวดหมู่รายรับ", resp.get_data(as_text=True))

    def test_income_uses_typed_category_name(self):
        user = self._create_user("income-typed@example.com", "password123", "IncomeTyped")
        self._login("income-typed@example.com", "password123")

        resp = self.client.post(
            "/transactions/new",
            data={
                "type": "income",
                "amount": "5000.00",
                "tx_date": "2026-02-25",
                "category_id": "-2",
                "category_name": "โบนัส",
                "note": "Bonus",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            category = Category.query.filter_by(user_id=user.id, type="income", name="โบนัส").first()
            self.assertIsNotNone(category)
            tx = Transaction.query.filter_by(user_id=user.id, type="income", note="Bonus").first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.category_id, category.id)

    def test_budget_create_and_prevent_duplicate_in_same_month(self):
        user = self._create_user("budget@example.com", "password123", "BudgetUser")
        self._login("budget@example.com", "password123")

        with self.app.app_context():
            category = Category(user_id=user.id, name="Food", type="expense", is_active=True)
            db.session.add(category)
            db.session.commit()
            db.session.refresh(category)
            category_id = category.id

        create_resp = self.client.post(
            "/budgets/new",
            data={"category_id": str(category_id), "month": "2026-02", "amount": "4000.00"},
            follow_redirects=True,
        )
        self.assertEqual(create_resp.status_code, 200)
        self.assertIn("เพิ่มงบประมาณแล้ว", create_resp.get_data(as_text=True))

        dup_resp = self.client.post(
            "/budgets/new",
            data={"category_id": str(category_id), "month": "2026-02", "amount": "4500.00"},
            follow_redirects=False,
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertIn("อาจมีงบหมวดนี้ในเดือนนี้แล้ว", dup_resp.get_data(as_text=True))

        with self.app.app_context():
            self.assertEqual(
                Budget.query.filter_by(user_id=user.id, category_id=category_id).count(), 1
            )

    def test_dashboard_shows_budget_progress(self):
        user = self._create_user("budgetdash@example.com", "password123", "BudgetDash")
        self._login("budgetdash@example.com", "password123")

        with self.app.app_context():
            category = Category(user_id=user.id, name="Travel", type="expense", is_active=True)
            db.session.add(category)
            db.session.commit()
            db.session.refresh(category)

            budget = Budget(
                user_id=user.id,
                category_id=category.id,
                month_start=date(2026, 2, 1),
                amount=1000.00,
            )
            db.session.add(budget)

            tx = Transaction(
                user_id=user.id,
                category_id=category.id,
                type="expense",
                amount=250.00,
                tx_date=date(2026, 2, 10),
                note="Train",
            )
            db.session.add(tx)
            db.session.commit()

        resp = self.client.get("/transactions/")
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Budget เดือนนี้", text)
        self.assertIn("Travel", text)

    def test_transactions_show_deep_dashboard_insights(self):
        user = self._create_user("insight@example.com", "password123", "InsightUser")
        self._login("insight@example.com", "password123")

        today = date.today()
        current_month_start = today.replace(day=1)
        if current_month_start.month == 1:
            previous_month_date = date(current_month_start.year - 1, 12, 15)
        else:
            previous_month_date = date(
                current_month_start.year, current_month_start.month - 1, 15
            )

        with self.app.app_context():
            food = Category(user_id=user.id, name="Food", type="expense", is_active=True)
            rent = Category(user_id=user.id, name="Rent", type="expense", is_active=True)
            db.session.add_all([food, rent])
            db.session.commit()
            db.session.refresh(food)
            db.session.refresh(rent)

            db.session.add_all(
                [
                    Transaction(
                        user_id=user.id,
                        category_id=food.id,
                        type="expense",
                        amount=300.00,
                        tx_date=today,
                        note="Food current",
                    ),
                    Transaction(
                        user_id=user.id,
                        category_id=rent.id,
                        type="expense",
                        amount=1200.00,
                        tx_date=today,
                        note="Rent current",
                    ),
                    Transaction(
                        user_id=user.id,
                        category_id=food.id,
                        type="expense",
                        amount=500.00,
                        tx_date=previous_month_date,
                        note="Food previous",
                    ),
                    Transaction(
                        user_id=user.id,
                        category_id=None,
                        type="income",
                        amount=2500.00,
                        tx_date=today,
                        note="Income current",
                    ),
                ]
            )
            db.session.commit()

        resp = self.client.get("/transactions/")
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("เดือนนี้ vs เดือนก่อน", text)
        self.assertIn("หมวดใช้จ่ายสูงสุด (เดือนนี้)", text)
        self.assertIn("ค่าเฉลี่ยรายวัน (รายจ่าย)", text)
        self.assertIn("Rent", text)

    def test_recurring_generates_transaction_and_does_not_duplicate_same_day(self):
        user = self._create_user("recur@example.com", "password123", "RecurUser")
        self._login("recur@example.com", "password123")

        with self.app.app_context():
            category = Category(user_id=user.id, name="Rent", type="expense", is_active=True)
            db.session.add(category)
            db.session.commit()
            db.session.refresh(category)

            recurring = RecurringTransaction(
                user_id=user.id,
                category_id=category.id,
                type="expense",
                amount=500.00,
                note="Monthly rent",
                frequency="monthly",
                interval_count=1,
                start_date=date.today(),
                next_run_date=date.today(),
                is_active=True,
            )
            db.session.add(recurring)
            db.session.commit()

        first_resp = self.client.get("/transactions/", follow_redirects=True)
        self.assertEqual(first_resp.status_code, 200)
        self.assertIn("สร้างรายการอัตโนมัติ", first_resp.get_data(as_text=True))

        with self.app.app_context():
            self.assertEqual(
                Transaction.query.filter_by(user_id=user.id, note="Monthly rent").count(),
                1,
            )

        second_resp = self.client.get("/transactions/", follow_redirects=True)
        self.assertEqual(second_resp.status_code, 200)

        with self.app.app_context():
            self.assertEqual(
                Transaction.query.filter_by(user_id=user.id, note="Monthly rent").count(),
                1,
            )

    def test_recurring_permission_blocks_other_users_edit(self):
        user_a = self._create_user("ra@example.com", "password123", "RecurA")
        user_b = self._create_user("rb@example.com", "password123", "RecurB")

        with self.app.app_context():
            recurring_b = RecurringTransaction(
                user_id=user_b.id,
                category_id=None,
                type="income",
                amount=1000.00,
                note="Salary",
                frequency="monthly",
                interval_count=1,
                start_date=date.today(),
                next_run_date=date.today(),
                is_active=True,
            )
            db.session.add(recurring_b)
            db.session.commit()
            recurring_id = recurring_b.id

        self._login("ra@example.com", "password123")
        edit_resp = self.client.get(f"/recurring/{recurring_id}/edit")
        self.assertEqual(edit_resp.status_code, 404)

        delete_resp = self.client.post(f"/recurring/{recurring_id}/delete")
        self.assertEqual(delete_resp.status_code, 404)

    def test_transactions_export_csv_returns_user_data(self):
        user = self._create_user("csv-export@example.com", "password123", "CsvExport")
        self._login("csv-export@example.com", "password123")

        with self.app.app_context():
            category = Category(user_id=user.id, name="Food", type="expense", is_active=True)
            db.session.add(category)
            db.session.commit()
            db.session.refresh(category)

            tx = Transaction(
                user_id=user.id,
                category_id=category.id,
                type="expense",
                amount=120.50,
                tx_date=date(2026, 2, 26),
                note="Lunch",
            )
            db.session.add(tx)
            db.session.commit()

        resp = self.client.get("/transactions/export.csv")
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.content_type)
        self.assertIn("tx_date,type,amount,category,note", text)
        self.assertIn("2026-02-26,expense,120.50,Food,Lunch", text)

    def test_transactions_import_csv_creates_rows_and_skips_invalid(self):
        user = self._create_user("csv-import@example.com", "password123", "CsvImport")
        self._login("csv-import@example.com", "password123")

        csv_content = (
            "tx_date,type,amount,category,note\n"
            "2026-02-20,expense,95.00,Transport,Taxi\n"
            "bad-date,expense,30.00,Food,Invalid Date\n"
            "2026-02-21,income,5000.00,Salary,Payday\n"
        )
        data = {
            "csv_file": (io.BytesIO(csv_content.encode("utf-8")), "transactions.csv"),
        }
        resp = self.client.post(
            "/transactions/import.csv",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("นำเข้า CSV สำเร็จ 2 รายการ, ข้าม 1 รายการ", text)

        with self.app.app_context():
            self.assertEqual(Transaction.query.filter_by(user_id=user.id).count(), 2)
            self.assertIsNotNone(
                Category.query.filter_by(user_id=user.id, type="expense", name="Transport").first()
            )
            self.assertIsNotNone(
                Category.query.filter_by(user_id=user.id, type="income", name="Salary").first()
            )

    def test_data_tools_page_render_for_authenticated_user(self):
        self._create_user("data-tools@example.com", "password123", "DataTools")
        self._login("data-tools@example.com", "password123")

        resp = self.client.get("/data/")
        text = resp.get_data(as_text=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Data Tools", text)
        self.assertIn("Export CSV", text)
        self.assertIn("Import CSV", text)

    def test_savings_goal_create_and_contribute(self):
        user = self._create_user("goal@example.com", "password123", "GoalUser")
        self._login("goal@example.com", "password123")

        create_resp = self.client.post(
            "/savings/new",
            data={
                "name": "Emergency Fund",
                "target_amount": "10000.00",
                "current_amount": "2000.00",
                "monthly_plan_amount": "1000.00",
                "start_date": "2026-02-01",
                "target_date": "2026-12-31",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        self.assertEqual(create_resp.status_code, 200)
        self.assertIn("เพิ่มเป้าหมายการออมแล้ว", create_resp.get_data(as_text=True))

        with self.app.app_context():
            goal = SavingsGoal.query.filter_by(user_id=user.id, name="Emergency Fund").first()
            self.assertIsNotNone(goal)
            goal_id = goal.id

        contribute_resp = self.client.post(
            f"/savings/{goal_id}/contribute",
            data={"amount": "500.00"},
            follow_redirects=True,
        )
        self.assertEqual(contribute_resp.status_code, 200)
        self.assertIn("บันทึกเงินออมเข้าเป้าหมายแล้ว", contribute_resp.get_data(as_text=True))

        with self.app.app_context():
            goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user.id).first()
            self.assertEqual(float(goal.current_amount), 2500.00)

    def test_savings_goal_permission_blocks_other_users_edit(self):
        user_a = self._create_user("goala@example.com", "password123", "GoalA")
        user_b = self._create_user("goalb@example.com", "password123", "GoalB")

        with self.app.app_context():
            goal_b = SavingsGoal(
                user_id=user_b.id,
                name="Trip",
                target_amount=5000.00,
                current_amount=1000.00,
                monthly_plan_amount=500.00,
                start_date=date(2026, 2, 1),
                target_date=None,
                is_active=True,
            )
            db.session.add(goal_b)
            db.session.commit()
            goal_id = goal_b.id

        self._login("goala@example.com", "password123")
        edit_resp = self.client.get(f"/savings/{goal_id}/edit")
        self.assertEqual(edit_resp.status_code, 404)

        delete_resp = self.client.post(f"/savings/{goal_id}/delete")
        self.assertEqual(delete_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
