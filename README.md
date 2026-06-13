# 🏰 BOTC Assistant v2.0
### *The Ultimate Server-as-Storyteller for Blood on the Clocktower*

[![Status: Live](https://img.shields.io/badge/Status-Live-success.svg?style=for-the-badge)](https://botc-assistant.onrender.com)
[![Engine: Trouble Brewing](https://img.shields.io/badge/Engine-Trouble_Brewing-red.svg?style=for-the-badge)](#)
[![Language: Thai](https://img.shields.io/badge/Language-Thai-blue.svg?style=for-the-badge)](#)

โปรเจกต์ช่วยรันเกม **Blood on the Clocktower** ภาค *Trouble Brewing* แบบอัตโนมัติ ที่ช่วยเปลี่ยนประสบการณ์การเล่นให้ไหลลื่นและน่าตื่นเต้นกว่าเดิม ไม่ว่าจะเป็นการเล่นแบบมี Storyteller คุม หรือรันเองด้วยระบบ AI อัตโนมัติ

---

## ✨ ฟีเจอร์เด่น (Key Features)

### 👑 Storyteller Grimoire (หน้าจอคนคุมเกม)
- **Real-time Sync:** รายชื่อผู้เล่นปรากฏขึ้นทันทีเมื่อมีคน Join ผ่านมือถือ ไม่ต้องพิมพ์ชื่อเอง!
- **Interactive Magic Circle:** ลากวางเหรียญโทเคนได้อิสระ จัดวงตามตำแหน่งที่นั่งจริง
- **Guided Night Order:** ระบบบอกลำดับการปลุกรายบุคคลทีละขั้น (First Night/Other Night) ป้องกันความผิดพลาด
- **Rule Engine:** ตรวจสอบกฎอัตโนมัติ (เช่น Virgin ประหารทันทีเมื่อถูกชาวเมืองเสนอชื่อ)

### 🔮 Player Identity (หน้าจอผู้เล่น)
- **Thai Localization:** คำอธิบายความสามารถภาษาไทย 100% อ่านง่าย เข้าใจชัดเจน
- **Secret Reveal:** ปีศาจและสมุนเห็นชื่อทีมเดียวกันทันทีเมื่อเริ่มเกมตามกฎจริง
- **Night Action Panel:** ปุ่มร่ายสกิลยามค่ำคืนที่ฉลาด (กรองเป้าหมายที่เลือกได้จริงมาให้)

### 🤖 Automated Mode (โหมดไร้คนคุม)
- **Phase Timer:** ระบบนับเวลาถอยหลังและเปลี่ยนเฟส (กลางคืน/กลางวัน) ให้อัตโนมัติ
- **Host Controls:** ผู้สร้างห้องสามารถกดเริ่มสุ่มบทบาทได้เองโดยไม่ต้องมี Storyteller

### 📢 Thai Voice Narration
- **AI Voice:** สั่งประกาศเนื้อเรื่องด้วยเสียงภาษาไทยอัตโนมัติ ส่งสัญญาณเสียงไปดังที่เครื่องผู้เล่นทุกคนพร้อมกัน

---

## 🚀 เริ่มต้นใช้งาน (Getting Started)

### การติดตั้ง (Installation)
1. **Clone Repository:**
   ```powershell
   git clone https://github.com/your-repo/BOTC_Assistant.git
   cd BOTC_Assistant
   ```

2. **Install Dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Initialize Database:**
   ```powershell
   python scripts/seed_db.py
   ```

4. **Run Application:**
   ```powershell
   uvicorn app.main:app --reload
   ```

---

## 🛠️ โครงสร้างโปรเจกต์ (Project Structure)

```text
BOTC_Assistant/
├── app/
│   ├── api/          # REST & WebSocket Endpoints
│   ├── core/         # Game Engine & Night Manager
│   ├── db/           # Models & Migrations
│   ├── narration/    # Thai TTS Engine
│   └── templates/    # UI Views (HTML/JS)
├── assets/           # Narration Audio Files
├── config/           # System Settings
├── scripts/          # Database Seeding
└── test_edge_cases.py # Validation Scripts
```

---

## 🧪 การทดสอบ
คุณสามารถทดสอบกฎพิเศษ (Edge Cases) ของตัวละครต่างๆ ได้ด้วยคำสั่ง:
```powershell
python test_edge_cases.py
```

---

## 📜 ลิขสิทธิ์
Blood on the Clocktower เป็นเครื่องหมายการค้าของ **The Pandemonium Institute** โปรเจกต์นี้สร้างขึ้นเพื่อช่วยอำนวยความสะดวกในการเล่นเท่านั้น

---
*พัฒนาด้วย ❤️ เพื่อคอมมูนิตี้ BOTC ไทย*
