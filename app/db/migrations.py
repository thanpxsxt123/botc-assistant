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
        cols_sessions = [row[1] for row in result]
        
        if "timer_expires_at" not in cols_sessions:
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN timer_expires_at DATETIME"))
        if "is_automated" not in cols_sessions:
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN is_automated BOOLEAN DEFAULT 0"))
        if "is_active" not in cols_sessions:
            conn.execute(text("ALTER TABLE game_sessions ADD COLUMN is_active BOOLEAN DEFAULT 1"))

        # 2. ตรวจสอบ Column ใน players
        result = conn.execute(text("PRAGMA table_info(players)"))
        cols_players = [row[1] for row in result]

        if "has_voted_this_day" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN has_voted_this_day BOOLEAN DEFAULT 0"))
        if "has_used_dead_vote" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN has_used_dead_vote BOOLEAN DEFAULT 0"))
        if "is_poisoned" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN is_poisoned BOOLEAN DEFAULT 0"))
        if "is_drunk" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN is_drunk BOOLEAN DEFAULT 0"))
        if "pos_x" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN pos_x INTEGER"))
        if "pos_y" not in cols_players:
            conn.execute(text("ALTER TABLE players ADD COLUMN pos_y INTEGER"))
            
        conn.commit()
    print("✅ Database migration check complete.")
