from sqlalchemy.orm import Session
from app.db.models import GameSession, GamePhase, Player, Character, GameLog, CharacterType, Alignment, Nomination
from app.db.database import SessionLocal
from app.narration.engine import ThaiNarrator
import random
from datetime import datetime, timedelta

class GameEngine:
    def __init__(self, db: Session):
        self.db = db
        self.narrator = ThaiNarrator()

    def create_room(self, room_code: str, is_automated: bool = False):
        session = GameSession(
            room_code=room_code, 
            current_phase=GamePhase.SETUP,
            is_automated=is_automated
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def add_player(self, session_id: int, name: str, seat_number: int):
        player = Player(session_id=session_id, name=name, seat_number=seat_number)
        self.db.add(player)
        self.db.commit()
        return player

    def get_setup_count(self, num_players: int):
        setup_map = {
            5: [3, 0, 1, 1],
            6: [3, 1, 1, 1],
            7: [5, 0, 1, 1],
            8: [5, 1, 1, 1],
            9: [5, 2, 1, 1],
            10: [7, 0, 2, 1],
            11: [7, 1, 2, 1],
            12: [7, 2, 2, 1],
            13: [9, 0, 3, 1],
            14: [9, 1, 3, 1],
            15: [9, 2, 3, 1],
        }
        return setup_map.get(num_players, [3, 0, 1, 1] if num_players < 5 else [9, 2, 3, 1])

    def assign_characters(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        players = session.players
        num_players = len(players)
        
        counts = self.get_setup_count(num_players)
        t_count, o_count, m_count, d_count = counts
        
        minions_pool = self.db.query(Character).filter(Character.char_type == CharacterType.MINION).all()
        selected_minions = random.sample(minions_pool, m_count)
        
        has_baron = any(m.name == "Baron" for m in selected_minions)
        if has_baron:
            t_count -= 2
            o_count += 2

        townsfolk_pool = self.db.query(Character).filter(Character.char_type == CharacterType.TOWNSFOLK).all()
        outsiders_pool = self.db.query(Character).filter(Character.char_type == CharacterType.OUTSIDER).all()
        demons_pool = self.db.query(Character).filter(Character.char_type == CharacterType.DEMON).all()
        
        selected_townsfolk = random.sample(townsfolk_pool, t_count)
        selected_outsiders = random.sample(outsiders_pool, o_count)
        selected_demon = random.sample(demons_pool, d_count)
        
        final_pool = selected_townsfolk + selected_outsiders + selected_minions + selected_demon
        random.shuffle(final_pool)
        
        for i, player in enumerate(players):
            char = final_pool[i]
            if char.name == "Drunk":
                not_in_play_tf = [tf for tf in townsfolk_pool if tf not in selected_townsfolk]
                fake_char = random.choice(not_in_play_tf)
                player.character_id = fake_char.id
                player.is_drunk = True
            else:
                player.character_id = char.id
        
        self.db.commit()
        return True

    def start_game(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session or session.current_phase != GamePhase.SETUP:
            return False

        if not self.assign_characters(session_id):
            return False
            
        session.current_phase = GamePhase.FIRST_NIGHT
        session.day_number = 1
        session.night_action_step = 0
        if session.is_automated:
            session.timer_expires_at = datetime.utcnow() + timedelta(minutes=2) # คืนแรกให้เวลา 2 นาทีสำหรับเตรียมตัว
            
        self.narrator.announce_night_start(1)
        self.log_action(session_id, GamePhase.SETUP, 1, "Game started, characters assigned, transitioning to First Night")
        self.db.commit()
        return True

    def check_win_conditions(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        living_players = self.db.query(Player).filter(Player.session_id == session_id, Player.is_alive == True).all()
        demon = next((p for p in living_players if p.character.char_type == CharacterType.DEMON), None)
        
        if not demon:
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.GAME_OVER, session.day_number, "Good wins! Demon is dead.")
            return "GOOD_WINS"
        
        if len(living_players) <= 2:
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.GAME_OVER, session.day_number, "Evil wins! Only 2 players left.")
            return "EVIL_WINS"
        return None

    def handle_dead_vote(self, player_id: int):
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player.is_alive:
            if player.has_used_dead_vote:
                return False
            player.has_used_dead_vote = True
            self.db.commit()
        return True

    def create_nomination(self, session_id: int, nominator_id: int, nominee_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        nominator = self.db.query(Player).filter(Player.id == nominator_id).first()
        nominee = self.db.query(Player).filter(Player.id == nominee_id).first()

        if nominee.character.name == "Virgin" and not nominee.is_poisoned and not nominee.is_drunk:
            if nominator.character.char_type == CharacterType.TOWNSFOLK:
                nominator.is_alive = False
                session.current_phase = GamePhase.NIGHT
                self.log_action(session_id, GamePhase.DAY_NOMINATION, session.day_number, 
                                f"Virgin triggered! {nominator.name} executed immediately. Day ends.")
                self.db.commit()
                return None

        nomination = Nomination(
            session_id=session_id,
            nominator_id=nominator_id,
            nominee_id=nominee_id,
            day_number=session.day_number
        )
        self.db.add(nomination)
        self.db.commit()
        return nomination

    def slayer_shot(self, session_id: int, slayer_id: int, target_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        slayer = self.db.query(Player).filter(Player.id == slayer_id).first()
        target = self.db.query(Player).filter(Player.id == target_id).first()

        if slayer.character.name != "Slayer" or slayer.is_poisoned or slayer.is_drunk:
            return False

        if target.character.char_type == CharacterType.DEMON:
            target.is_alive = False
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.DAY_CHITCHAT, session.day_number, 
                            f"Slayer shot the {target.character.name}! Evil dies.")
            self.db.commit()
            self.check_win_conditions(session_id)
            return True
        
        self.log_action(session_id, GamePhase.DAY_CHITCHAT, session.day_number, 
                        f"Slayer shot {target.name}, but nothing happened.")
        return False

    def resolve_voting(self, nomination_id: int, votes: int):
        nomination = self.db.query(Nomination).filter(Nomination.id == nomination_id).first()
        nomination.votes_received = votes
        nomination.is_closed = True
        self.db.commit()
        return nomination

    def finalize_day_execution(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        living_count = self.db.query(Player).filter(Player.session_id == session_id, Player.is_alive == True).count()
        # Trouble Brewing: 50% or more (threshold = living / 2)
        threshold = living_count / 2

        # 🚀 ปิดทุก Nomination ของวันนี้ก่อนประมวลผล
        self.db.query(Nomination).filter(
            Nomination.session_id == session_id,
            Nomination.day_number == session.day_number
        ).update({"is_closed": True})
        self.db.commit()

        nominations = self.db.query(Nomination).filter(
            Nomination.session_id == session_id,
            Nomination.day_number == session.day_number
        ).order_by(Nomination.votes_received.desc()).all()

        executed_player = None
        if nominations:
            highest = nominations[0]
            if highest.votes_received >= threshold:
                # Check for tie
                ties = [n for n in nominations if n.votes_received == highest.votes_received]
                if len(ties) == 1:
                    # No tie, execute
                    highest.is_executed = True
                    executed_player = highest.nominee
                    executed_player.is_alive = False
                    self.db.commit()
                    self.log_action(session_id, session.current_phase, session.day_number, 
                                    f"Execution: {executed_player.name} died with {highest.votes_received} votes.")
                else:
                    self.log_action(session_id, session.current_phase, session.day_number, 
                                    "No execution: It's a tie between players.")
            else:
                self.log_action(session_id, session.current_phase, session.day_number, 
                                f"No execution: Highest votes ({highest.votes_received}) below threshold ({threshold}).")
                    
        self.narrator.announce_execution(executed_player.name if executed_player else None)
        self.check_win_conditions(session_id)
        return executed_player

    def next_phase(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session:
            return {"success": False}

        current = session.current_phase
        next_p = current
        announcement = None
        
        # Clear timer
        session.timer_expires_at = None

        if current == GamePhase.FIRST_NIGHT:
            self.resolve_night_actions(session_id)
            next_p = GamePhase.DAY_CHITCHAT
            announcement = "เช้าวันแรก เริ่มต้นการพูดคุยหาตัวคนร้ายได้เลย"
            self.log_action(session_id, GamePhase.FIRST_NIGHT, session.day_number, announcement)
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=5)
        elif current == GamePhase.DAY_CHITCHAT:
            next_p = GamePhase.DAY_NOMINATION
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=3)
        elif current == GamePhase.DAY_NOMINATION:
            next_p = GamePhase.DAY_VOTING
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=2)
        elif current == GamePhase.DAY_VOTING:
            self.finalize_day_execution(session_id)
            if session.current_phase != GamePhase.GAME_OVER:
                next_p = GamePhase.NIGHT
                session.night_action_step = 0
                self.narrator.announce_night_start(session.day_number + 1)
                if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=3)
            else:
                next_p = GamePhase.GAME_OVER
        elif current == GamePhase.NIGHT:
            dead_names = self.resolve_night_actions(session_id)
            session.day_number += 1
            next_p = GamePhase.DAY_CHITCHAT
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=5)
            
            if dead_names:
                announcement = f"เช้าวันนี้เราพบร่างของ {' และ '.join(dead_names)} เสียชีวิตลง"
            else:
                announcement = "เมื่อคืนนี้ไม่มีใครตาย ทุกคนยังอยู่ครบ"
            self.log_action(session_id, GamePhase.NIGHT, session.day_number, announcement)

        session.current_phase = next_p
        self.db.commit()
        return {"success": True, "announcement": announcement, "new_phase": next_p.value}

    def resolve_night_actions(self, session_id: int):
        from app.db.models import NightAction, Character
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        day = session.day_number
        
        # Get all players in this session
        players = self.db.query(Player).filter(Player.session_id == session_id).all()
        players_by_id = {p.id: p for p in players}
        
        # 1. Reset temporary statuses from the previous day/night
        for p in players:
            p.is_poisoned = False
        
        # Query all night actions submitted tonight
        actions = self.db.query(NightAction).filter(
            NightAction.session_id == session_id,
            NightAction.day_number == day
        ).all()
        
        # Group actions by player role
        actions_by_role = {}
        for act in actions:
            p = players_by_id.get(act.player_id)
            if p and p.character:
                actions_by_role[p.character.name] = act

        # --- Phase A: Apply Poisoner ---
        poisoner_act = actions_by_role.get("Poisoner")
        if poisoner_act:
            poisoner = players_by_id.get(poisoner_act.player_id)
            if poisoner and poisoner.is_alive and not poisoner.is_poisoned and not poisoner.is_drunk:
                target = players_by_id.get(poisoner_act.target_player_id)
                if target:
                    target.is_poisoned = True
                    self.log_action(session_id, session.current_phase, day, f"🔮 Poisoner poisoned {target.name}.")

        # --- Phase B: Apply Monk Protection ---
        monk_act = actions_by_role.get("Monk")
        protected_target_id = None
        if monk_act:
            monk = players_by_id.get(monk_act.player_id)
            if monk and monk.is_alive and not monk.is_poisoned and not monk.is_drunk:
                target = players_by_id.get(monk_act.target_player_id)
                if target and target.id != monk.id: # Monk cannot protect self
                    protected_target_id = target.id
                    self.log_action(session_id, session.current_phase, day, f"🔮 Monk protected {target.name}.")

        # --- Phase C: Apply Demon (Imp) Kill ---
        dead_tonight = []
        is_first_night = (session.current_phase == GamePhase.FIRST_NIGHT)
        imp_act = actions_by_role.get("Imp")
        if imp_act and not is_first_night:
            imp = players_by_id.get(imp_act.player_id)
            if imp and imp.is_alive and not imp.is_poisoned and not imp.is_drunk:
                target = players_by_id.get(imp_act.target_player_id)
                if target:
                    if target.id == protected_target_id:
                        self.log_action(session_id, session.current_phase, day, f"🔮 Imp tried to kill {target.name}, but they were protected by the Monk.")
                    elif target.character and target.character.name == "Soldier" and not target.is_poisoned and not target.is_drunk:
                        self.log_action(session_id, session.current_phase, day, f"🔮 Imp tried to kill Soldier ({target.name}), but their ability protected them.")
                    elif target.id == imp.id:
                        target.is_alive = False
                        dead_tonight.append(target.name)
                        self.log_action(session_id, session.current_phase, day, f"🔮 Imp ({imp.name}) chose to kill themselves (Starpass).")
                        
                        living_minions = [p for p in players if p.is_alive and p.character and p.character.char_type == CharacterType.MINION]
                        if living_minions:
                            new_imp = random.choice(living_minions)
                            imp_char = self.db.query(Character).filter(Character.name == "Imp").first()
                            if imp_char:
                                new_imp.character_id = imp_char.id
                                self.log_action(session_id, session.current_phase, day, f"🔮 Minion {new_imp.name} becomes the new Imp.")
                    else:
                        target.is_alive = False
                        dead_tonight.append(target.name)
                        self.log_action(session_id, session.current_phase, day, f"🔮 Imp killed {target.name}.")
                        
        self.db.commit()
        return dead_tonight

    def log_action(self, session_id: int, phase: GamePhase, day: int, detail: str):
        log = GameLog(session_id=session_id, phase=phase, day_number=day, action_detail=detail)
        self.db.add(log)
