from sqlalchemy.orm import Session
from app.db.models import Player, Character, GameSession, Alignment, CharacterType
from typing import List, Optional

class RuleEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_neighbors(self, player_id: int, session_id: int) -> List[Player]:
        """Get the two closest living neighbors of a player."""
        all_players = self.db.query(Player).filter(
            Player.session_id == session_id
        ).order_by(Player.seat_number).all()
        
        if not all_players:
            return []

        # Find the index of the current player
        idx = -1
        for i, p in enumerate(all_players):
            if p.id == player_id:
                idx = i
                break
        
        if idx == -1:
            return []

        num_players = len(all_players)
        neighbors = []
        
        # Look for the first living neighbor clockwise
        for i in range(1, num_players):
            p = all_players[(idx + i) % num_players]
            if p.is_alive:
                neighbors.append(p)
                break
        
        # Look for the first living neighbor counter-clockwise
        for i in range(1, num_players):
            p = all_players[(idx - i) % num_players]
            if p.is_alive:
                neighbors.append(p)
                break
        
        return neighbors

    def process_chef_info(self, session_id: int) -> int:
        """Calculate how many pairs of evil players are sitting next to each other."""
        players = self.db.query(Player).join(Character).filter(
            Player.session_id == session_id
        ).order_by(Player.seat_number).all()
        
        if not players:
            return 0

        evil_indices = [i for i, p in enumerate(players) if p.character.alignment == Alignment.EVIL]
        if not evil_indices:
            return 0

        pairs = 0
        num_players = len(players)
        for i in range(len(evil_indices)):
            current_idx = evil_indices[i]
            next_idx = (current_idx + 1) % num_players
            if players[next_idx].character.alignment == Alignment.EVIL:
                pairs += 1
        
        return pairs

    def apply_poison(self, target_player_id: int):
        """Set a player as poisoned."""
        player = self.db.query(Player).filter(Player.id == target_player_id).first()
        if player:
            player.is_poisoned = True
            self.db.commit()

    def clear_all_status_effects(self, session_id: int):
        """Clear poison and drunk status at the end of the night/day."""
        players = self.db.query(Player).filter(Player.session_id == session_id).all()
        for p in players:
            p.is_poisoned = False
            p.is_drunk = False
        self.db.commit()

    def process_investigator_info(self, session_id: int):
        """Investigator sees two players, one of which is a Minion."""
        players = self.db.query(Player).join(Character).filter(Player.session_id == session_id).all()
        minions = [p for p in players if p.character.char_type == CharacterType.MINION]
        if not minions:
            return None
        
        minion = random.choice(minions)
        other_player = random.choice([p for p in players if p.id != minion.id])
        
        # Randomize order
        result = [minion, other_player]
        random.shuffle(result)
        return {"players": result, "minion_type": minion.character.name}

    def process_fortune_teller_info(self, target1_id: int, target2_id: int):
        """Fortune Teller checks if either target is a Demon (or the Red Herring)."""
        targets = self.db.query(Player).join(Character).filter(Player.id.in_([target1_id, target2_id])).all()
        
        is_demon = any(p.character.char_type == CharacterType.DEMON for p in targets)
        # In a real game, we'd need to track who the 'Red Herring' is. 
        # For now, let's assume a static or random check for demonstration.
        return is_demon
