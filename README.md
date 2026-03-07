### นายฉัตรชนก นิโครธานนท์ 6810110557

# Personal Finance Tracker

เว็บแอปสำหรับบันทึกรายรับ-รายจ่าย จัดหมวดหมู่ วางงบประมาณ ตั้งเป้าการออม และดูกราฟสรุปข้อมูลการเงินรายเดือน

## Tech Stack

- Backend: Flask
- Database: SQLite + Flask-SQLAlchemy
- Frontend: Jinja2 + Tailwind CSS
- Authentication: Flask-Login
- Forms & Validation: Flask-WTF
- Migration: Flask-Migrate

## Features

- สมัครสมาชิก / เข้าสู่ระบบ / ออกจากระบบ
- แก้ไขข้อมูลผู้ใช้และเปลี่ยนรหัสผ่าน
- จัดการธุรกรรมรายรับ-รายจ่าย (เพิ่ม/แก้ไข/ลบ/กู้คืนที่ลบล่าสุด)
- จัดการหมวดหมู่รายรับ-รายจ่าย
- จัดการแท็ก (Tag) ให้ธุรกรรม
- วางงบประมาณรายเดือนตามหมวดหมู่
- ตั้งเป้าการออมและบันทึกการเติมเงิน
- ตั้งรายการธุรกรรมแบบประจำ (Recurring)
- แสดงกราฟสรุปข้อมูล 3 แบบ (รายจ่ายตามหมวดหมู่, รายรับ-รายจ่ายตามช่วงเวลา, Top 5 หมวดหมู่รายจ่าย)
- นำเข้าข้อมูลจาก CSV และส่งออก CSV (ในส่วนนี้ผมคิดว่ามันไม่ค่อยเสถียรเท่าไหร่ครับต้องมีความสอดคล้องกับตัวเว็บด้วย)

## Code Explanation

โปรเจกต์แยกโครงสร้างตามฟีเจอร์ด้วย Flask Blueprint เพื่อให้อ่านและดูแลง่าย

- `app/auth/`: ระบบผู้ใช้ (register, login, profile, change password)
- `app/main/transactions/`: ธุรกรรมและสรุปผลการเงิน
- `app/main/categories/`: หมวดหมู่รายรับ-รายจ่าย
- `app/main/budgets/`: งบประมาณรายเดือน
- `app/main/savings/`: เป้าหมายการออม
- `app/main/recurring/`: ธุรกรรมที่เกิดซ้ำ
- `app/main/data/`: นำเข้า/ส่งออกข้อมูล
- `app/models.py`: โครงสร้างฐานข้อมูลและความสัมพันธ์ระหว่างตาราง
- `app/templates/`: หน้าเว็บทั้งหมด (Jinja2)

ฐานข้อมูลจัดการด้วย SQLAlchemy model เช่น `User`, `Transaction`, `Category`, `Budget`, `RecurringTransaction`, `SavingsGoal`, `Tag`

## Project Structure

```text
Finance-Tracker/
├── app/
│   ├── auth/
│   ├── main/
│   │   ├── transactions/
│   │   ├── categories/
│   │   ├── budgets/
│   │   ├── savings/
│   │   ├── recurring/
│   │   └── data/
│   ├── templates/
│   ├── static/
│   ├── models.py
│   └── __init__.py
├── tests/
├── requirements.txt
└── run.py
```

## Installation & Run

```bash
git clone git@github.com:Pu2f/Finance-Tracker.git
cd Finance-Tracker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

เปิดใช้งานที่ `http://127.0.0.1:5000`

## Tailwind CSS (Optional)

หากต้องการ build ไฟล์ CSS ใหม่:

```bash
cd app/static
npm install
npm run tw:build
```

## Environment

- `APP_ENV=development` (default): ใช้ `DevelopmentConfig`
- `APP_ENV=production`: ใช้ `ProductionConfig`

### Required in production

- `SECRET_KEY`
- `DATABASE_URL`

หาก `APP_ENV=production` แต่ไม่ได้ตั้งค่าตัวแปรที่จำเป็น แอปจะหยุดทำงานทันที (fail-fast)

## Tests

รันเทสทั้งหมดด้วย:

```bash
./venv/bin/python -m unittest discover -s tests -v
```

## Git Repository

- URL: `git@github.com:Pu2f/Finance-Tracker.git`
- มีการพัฒนาแบบ Commit Early และ Commit Often

## จำนวนหน้าเว็บ (ไม่นับ base.html) มีทั้งหมด 17 หน้า

หน้าหลัก:

- home.html
- ระบบสมาชิก (Auth):
- login.html
- register.html
- profile.html
- change_password.html
  รายการ (Transactions):
- index.html (หน้ารายการ)
- form.html (หน้าฟอร์มเพิ่ม/แก้ไข)
  หมวดหมู่ (Categories):
- index.html
- form.html
  งบประมาณ (Budgets):
- index.html
- form.html
  รายการประจำ (Recurring):
- index.html
- form.html
  เป้าหมายการออม (Savings):
  -index.html
- form.html
- contribute.html (หน้าฟอร์มเพิ่มเงินออม)
  ข้อมูล (Data): (ส่วนนี้คือฟังก์ชัน data tools สำหรับ import และ export ไฟล์ csv)
- index.html
