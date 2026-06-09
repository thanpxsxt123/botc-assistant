import sys
import os
from sqlalchemy.orm import Session

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal, engine, Base
from app.db.models import GameSession, Player, Character, GamePhase, CharacterType, Alignment, Nomination
from app.core.fsm import GameEngine

def run_test_suite():
    print("🚀 Starting Edge Case Test Suite...")
    db = SessionLocal()
    engine_logic = GameEngine(db)
    
    # 1. Setup a Test Session
    session = engine_logic.create_room("TEST1")
    
    # Add 5 players
    p1 = engine_logic.add_player(session.id, "Alice", 1) # Slayer
    p2 = engine_logic.add_player(session.id, "Bob", 2)   # Virgin
    p3 = engine_logic.add_player(session.id, "Charlie", 3) # Townsfolk (Nominator)
    p4 = engine_logic.add_player(session.id, "Dave", 4)  # Minion
    p5 = engine_logic.add_player(session.id, "Eve", 5)   # Demon (Imp)

    # Manually assign roles for testing
    chars = {c.name: c.id for c in db.query(Character).all()}
    p1.character_id = chars["Slayer"]
    p2.character_id = chars["Virgin"]
    p3.character_id = chars["Investigator"] # Any townsfolk
    p4.character_id = chars["Poisoner"]
    p5.character_id = chars["Imp"]
    db.commit()

    print("✅ Session setup complete.")

    # 2. Test Virgin Trigger
    print("\n--- Testing Virgin Trigger ---")
    session.current_phase = GamePhase.DAY_NOMINATION
    db.commit()
    
    # Charlie nominates Virgin (Bob)
    print("Action: Charlie (Townsfolk) nominates Bob (Virgin)")
    engine_logic.create_nomination(session.id, p3.id, p2.id)
    
    db.refresh(p3)
    db.refresh(session)
    if not p3.is_alive and session.current_phase == GamePhase.NIGHT:
        print("✅ SUCCESS: Nominator executed and Day ended immediately.")
    else:
        print(f"❌ FAILED: Status - P3 Alive: {p3.is_alive}, Phase: {session.current_phase}")

    # 3. Test Dead Vote Logic
    print("\n--- Testing Dead Vote Logic ---")
    # Charlie is dead. Let's try to make him vote.
    nom = engine_logic.create_nomination(session.id, p1.id, p4.id) # Slayer nominates Poisoner
    
    print("Action: Dead Charlie votes for the first time")
    res1 = engine_logic.handle_dead_vote(p3.id)
    print(f"Result 1: {res1} (Expected: True)")
    
    print("Action: Dead Charlie votes for the second time")
    res2 = engine_logic.handle_dead_vote(p3.id)
    print(f"Result 2: {res2} (Expected: False)")
    
    if res1 == True and res2 == False:
        print("✅ SUCCESS: Dead vote limited to 1.")
    else:
        print("❌ FAILED: Dead vote logic incorrect.")

    # 4. Test Slayer Shot (Win Condition)
    print("\n--- Testing Slayer Shot ---")
    session.current_phase = GamePhase.DAY_CHITCHAT
    db.commit()
    
    print("Action: Slayer (Alice) shoots the Imp (Eve)")
    hit = engine_logic.slayer_shot(session.id, p1.id, p5.id)
    
    db.refresh(session)
    if hit and session.current_phase == GamePhase.GAME_OVER:
        print("✅ SUCCESS: Demon killed, Game Over.")
    else:
        print(f"❌ FAILED: Hit: {hit}, Phase: {session.current_phase}")

    # Cleanup
    db.delete(session)
    db.commit()
    db.close()
    print("\n🏁 Test Suite Finished.")

if __name__ == "__main__":
    run_test_suite()
