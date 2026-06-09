from sqlalchemy.orm import Session
from app.db.models import GameSession, Player, Character, GamePhase, CharacterType

class NightManager:
    def __init__(self, db: Session):
        self.db = db

    def get_night_order(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        is_first_night = (session.day_number == 1 and session.current_phase == GamePhase.FIRST_NIGHT)
        
        # Get characters in play
        players = self.db.query(Player).filter(Player.session_id == session_id).all()
        in_play_char_ids = [p.character_id for p in players if p.character_id]
        
        # Query characters in play that have a night order
        if is_first_night:
            chars = self.db.query(Character).filter(
                Character.id.in_(in_play_char_ids),
                Character.first_night_order.isnot(None)
            ).order_by(Character.first_night_order).all()
        else:
            chars = self.db.query(Character).filter(
                Character.id.in_(in_play_char_ids),
                Character.other_night_order.isnot(None)
            ).order_by(Character.other_night_order).all()
            
        return chars

    def get_current_step_info(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        order = self.get_night_order(session_id)
        
        while session.night_action_step < len(order):
            current_char = order[session.night_action_step]
            # Find acting player(s)
            acting_players = self.db.query(Player).filter(
                Player.session_id == session_id,
                Player.character_id == current_char.id
            ).all()
            
            # Logic: Skip if player is dead (Except some roles, but for Trouble Brewing most skip)
            # Special case: Ravenkeeper only wakes if they died tonight.
            # For simplicity in v2.0, we only wake living players.
            living_acting_players = [p for p in acting_players if p.is_alive]
            
            if living_acting_players:
                return {
                    "status": "active",
                    "step": session.night_action_step + 1,
                    "total_steps": len(order),
                    "character": current_char.name,
                    "description": current_char.ability_description,
                    "players": [p.name for p in living_acting_players]
                }
            else:
                # No living player for this role, skip to next
                session.night_action_step += 1
                self.db.commit()
                
        return {"status": "finished"}

    def advance_step(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        order = self.get_night_order(session_id)
        
        session.night_action_step += 1
        self.db.commit()
        
        if session.night_action_step >= len(order):
            # No more steps, ST should manually call Next Phase or we can auto-trigger
            return {"status": "finished"}
            
        return self.get_current_step_info(session_id)

    def reset_steps(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        session.night_action_step = 0
        self.db.commit()
