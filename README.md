# Personal-Finance-Tracker
เว็บบันทึกรายรับรายจ่าย พร้อมกราฟสรุป

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
