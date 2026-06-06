# BOTC Assistant v2.0 - Server-as-Storyteller

โปรเจกต์ช่วยรันเกม Blood on the Clocktower (Trouble Brewing) แบบอัตโนมัติ

## 🛠️ การติดตั้ง (Installation)

1. **ติดตั้ง Library ที่จำเป็น:**
   ```powershell
   pip install -r requirements.txt
   ```

2. **เตรียมฐานข้อมูล (Seed Data):**
   ```powershell
   python scripts/seed_db.py
   ```

## 🚀 การใช้งาน (Getting Started)

1. **รันเซิร์ฟเวอร์:**
   ```powershell
   python -m app.main
   ```

2. **เข้าใช้งาน:**
   - **สำหรับผู้เล่น:** `http://localhost:8000/?room=ROOM_CODE&session=1`
   - **สำหรับ Storyteller:** `http://localhost:8000/storyteller?room=ROOM_CODE&session=1`

## ✨ ฟีเจอร์หลัก
- **Grimoire View:** Storyteller เห็นบทบาทและความลับทั้งหมด
- **Real-time Sync:** อัปเดตสถานะเกมผ่าน WebSocket
- **Thai Narration:** เสียงบรรยายภาษาไทยอัตโนมัติ
- **Rule Engine:** ตรวจสอบกฎการโหวต, ความสามารถตัวละคร (Virgin, Slayer, etc.) อัตโนมัติ

## 🧪 การทดสอบ
รันสคริปต์ทดสอบกฎพิเศษ:
```powershell
python test_edge_cases.py
```
