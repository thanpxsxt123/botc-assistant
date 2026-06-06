from sqlalchemy import text
from app.db.database import engine

def run_migrations():
    """
    ตรวจสอบและเพิ่ม Column ที่ขาดหายไปใน SQLite
    (วิธีแก้ขัดสำหรับงาน Dev โดยไม่ต้องใช้ Alembic)
    """
    with engine.connect() as conn:
        # 1. ตรวจสอบ Column ใน game_sessions
        result = conn.execute(text("PRAGMA table_info(game_sessions)"))
        columns = [row[1] for row in result]
        
        if "timer_expires_at" not in columns:
            print("🔧 Adding column timer_expires_at to game_sessions")
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN timer_expires_at DATETIME"))
            conn.commit()

        if "is_automated" not in columns:
            print("🔧 Adding column is_automated to game_sessions")
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN is_automated BOOLEAN DEFAULT 0"))
            conn.commit()
            
    print("✅ Database migration check complete.")
