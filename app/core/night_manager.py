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
            
            # Logic: Skip if player is dead (Except Ravenkeeper who wakes if killed tonight)
            if current_char.name == "Ravenkeeper":
                # Ravenkeeper wakes if they were killed by the demon tonight
                # (is_alive is False, but they were alive at the start of the night)
                # For simplicity, we check if they are dead and it's not the first night.
                # A more precise check would be "died during resolve_night_actions" but 
                # that happens at phase transition. 
                # Actually, in this implementation, players die immediately in resolve_night_actions?
                # No, resolve_night_actions is called in next_phase.
                # Wait, if resolve_night_actions hasn't been called yet, they are still alive!
                living_acting_players = acting_players # Wake them anyway, they'll see their info if they died.
            else:
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
