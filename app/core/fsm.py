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
        
        # 1. Select Minions first to check for Baron
        minions_pool = self.db.query(Character).filter(Character.char_type == CharacterType.MINION).all()
        selected_minions = random.sample(minions_pool, m_count)
        
        has_baron = any(m.name == "Baron" for m in selected_minions)
        if has_baron:
            t_count = max(0, t_count - 2)
            o_count += 2

        # 2. Select others
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
            # Reset player flags
            player.is_alive = True
            player.is_drunk = False
            player.is_poisoned = False
            player.is_red_herring = False
            player.secret_info = None
            player.has_used_ability = False
            player.has_used_dead_vote = False
            player.has_voted_this_day = False
            
            if char.name == "Drunk":
                # The Drunk thinks they are a Townsfolk
                not_in_play_tf = [tf for tf in townsfolk_pool if tf not in selected_townsfolk]
                fake_char = random.choice(not_in_play_tf)
                player.character_id = fake_char.id
                player.is_drunk = True
                # Store the real character name in secret_info (for internal use/ST)
                player.secret_info = f"[INTERNAL] บทบาทจริงคือ Drunk (เมา)"
            else:
                player.character_id = char.id
        
        # 🚀 3. Random Red Herring for Fortune Teller
        # A Red Herring is a living Townsfolk or Outsider (NOT the Demon)
        potential_rh = [p for p in players if p.character and p.character.char_type in [CharacterType.TOWNSFOLK, CharacterType.OUTSIDER]]
        if potential_rh:
            red_herring = random.choice(potential_rh)
            red_herring.is_red_herring = True

        self.db.commit()
        return True

    def start_game(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session or (session.current_phase != GamePhase.SETUP and session.current_phase != GamePhase.GAME_OVER):
            return False

        # 🔄 หากเป็นการเริ่มเกมใหม่จากสถานะจบเกม ให้ Reset ค่าต่างๆ ก่อน
        if session.current_phase == GamePhase.GAME_OVER:
            from app.db.models import GameLog, Nomination, NightAction
            self.db.query(GameLog).filter(GameLog.session_id == session_id).delete()
            self.db.query(Nomination).filter(Nomination.session_id == session_id).delete()
            self.db.query(NightAction).filter(NightAction.session_id == session_id).delete()
            self.db.commit()

        if not self.assign_characters(session_id):
            return False
            
        session.current_phase = GamePhase.FIRST_NIGHT
        session.day_number = 1
        session.night_action_step = 0
        if session.is_automated:
            session.timer_expires_at = datetime.utcnow() + timedelta(minutes=2)
            
        self.narrator.announce_night_start(1)
        self.log_action(session_id, GamePhase.SETUP, 1, "เกมเริ่มต้นขึ้นแล้ว บทบาทถูกแจกจ่าย และเข้าสู่คืนแรก")
        self.db.commit()
        return True

    def check_win_conditions(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        living_players = self.db.query(Player).filter(Player.session_id == session_id, Player.is_alive == True).all()
        
        # 1. Demon Death Check
        living_demon = next((p for p in living_players if p.character.char_type == CharacterType.DEMON), None)
        
        if not living_demon:
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.GAME_OVER, session.day_number, "🏆 บทสรุปเกม: ฝั่งดีชนะ! เนื่องจากปีศาจเสียชีวิต")
            return "GOOD_WINS"
        
        # 2. Evil Win Condition: Only 2 players left
        if len(living_players) <= 2:
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.GAME_OVER, session.day_number, "🏆 บทสรุปเกม: ฝั่งร้ายชนะ! เนื่องจากเหลือผู้เล่นเพียง 2 คน")
            return "EVIL_WINS"
            
        # 3. Mayor Win Condition (End of day, 3 alive, no execution)
        if len(living_players) == 3:
            mayor = next((p for p in living_players if p.character.name == "Mayor" and not p.is_drunk and not p.is_poisoned), None)
            if mayor:
                 executed_today = self.db.query(Nomination).filter(
                     Nomination.session_id == session_id,
                     Nomination.day_number == session.day_number,
                     Nomination.is_executed == True
                 ).first()
                 # Trigger if we are at the end of a nomination phase and no execution happened
                 if not executed_today:
                     session.current_phase = GamePhase.GAME_OVER
                     self.log_action(session_id, GamePhase.GAME_OVER, session.day_number, "🏆 บทสรุปเกม: ฝั่งดีชนะ! เนื่องจากพลังของ Mayor (เหลือ 3 คนและไม่มีการประหาร)")
                     return "GOOD_WINS (Mayor)"
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

        # 🚫 BOTC Rules:
        # 1. Nominator must be ALIVE
        if not nominator.is_alive:
            return "ALREADY_DEAD" # Only living players can nominate
            
        # 2. Each player can NOMINATE only once per day
        existing_by_nominator = self.db.query(Nomination).filter(
            Nomination.session_id == session_id,
            Nomination.day_number == session.day_number,
            Nomination.nominator_id == nominator_id
        ).first()
        if existing_by_nominator:
            return "ALREADY_NOMINATED"

        # 3. Each player can be NOMINATED only once per day
        existing_for_nominee = self.db.query(Nomination).filter(
            Nomination.session_id == session_id,
            Nomination.day_number == session.day_number,
            Nomination.nominee_id == nominee_id
        ).first()
        if existing_for_nominee:
            return "NOMINEE_ALREADY_TARGETED"

        # 🔔 Virgin Trigger Logic (Official BOTC)
        if nominee.character.name == "Virgin" and not nominee.is_poisoned and not nominee.is_drunk and not nominee.has_used_ability:
            if nominator.character.char_type == CharacterType.TOWNSFOLK:
                nominator.is_alive = False
                nominee.has_used_ability = True # Virgin ability used
                
                # Mark as execution for the Undertaker
                nomination = Nomination(
                    session_id=session_id,
                    nominator_id=nominator_id,
                    nominee_id=nominator_id, # Self-execution practically
                    day_number=session.day_number,
                    votes_received=0,
                    is_executed=True,
                    is_closed=True
                )
                self.db.add(nomination)
                
                session.current_phase = GamePhase.NIGHT
                self.log_action(session_id, GamePhase.DAY_NOMINATION, session.day_number,
                                f"🔔 Virgin Triggered! {nominator.name} ถูกประหารทันทีและช่วงกลางวันสิ้นสุดลง")
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

        if slayer.character.name != "Slayer" or slayer.has_used_ability:
            return False
            
        slayer.has_used_ability = True
        
        if slayer.is_poisoned or slayer.is_drunk:
            self.log_action(session_id, session.current_phase, session.day_number, f"🏹 Slayer shot {target.name} but they are drunk/poisoned. No effect.")
            self.db.commit()
            return False

        if target.character.char_type == CharacterType.DEMON:
            target.is_alive = False
            session.current_phase = GamePhase.GAME_OVER
            self.log_action(session_id, GamePhase.DAY_CHITCHAT, session.day_number,
                            f"🏹 Slayer shot the {target.character.name} ({target.name})! ฝั่งดีชนะ!")
            self.db.commit()
            self.check_win_conditions(session_id)
            return True
        else:
            self.log_action(session_id, session.current_phase, session.day_number, f"🏹 Slayer shot {target.name} but they are not the Demon.")
            self.db.commit()
            return False

    def finalize_nomination(self, nomination_id: int):
        """Official BOTC: Close a single nomination and check if it sets a new 'about to be executed' record."""
        nomination = self.db.query(Nomination).filter(Nomination.id == nomination_id).first()
        if not nomination: return None
        
        nomination.is_closed = True
        self.db.commit()
        return nomination

    def finalize_day_execution(self, session_id: int):
        """Official BOTC: At the end of nominations, find the one with strictly highest votes (min 50%)."""
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        living_count = self.db.query(Player).filter(Player.session_id == session_id, Player.is_alive == True).count()
        threshold = living_count / 2

        # Find all closed nominations of today
        nominations = self.db.query(Nomination).filter(
            Nomination.session_id == session_id,
            Nomination.day_number == session.day_number,
            Nomination.is_closed == True
        ).order_by(Nomination.votes_received.desc()).all()

        executed_player = None
        if nominations:
            highest = nominations[0]
            if highest.votes_received >= threshold:
                # Must be strictly higher than others to be executed
                ties = [n for n in nominations if n.votes_received == highest.votes_received]
                if len(ties) == 1:
                    highest.is_executed = True
                    executed_player = highest.nominee
                    executed_player.is_alive = False
                    self.db.commit()
                    self.log_action(session_id, session.current_phase, session.day_number, 
                                    f"⚖️ บทสรุปการประหาร: {executed_player.name} ถูกประหารด้วยคะแนน {highest.votes_received} เสียง")
                else:
                    self.log_action(session_id, session.current_phase, session.day_number, "⚖️ ไม่มีใครถูกประหารเนื่องจากคะแนนโหวตสูงสุดเท่ากัน")
            else:
                self.log_action(session_id, session.current_phase, session.day_number, f"⚖️ ไม่มีใครถูกประหารเนื่องจากคะแนนไม่ถึงเกณฑ์ ({highest.votes_received}/{threshold})")
        
        self.check_win_conditions(session_id)
        return executed_player

    def next_phase(self, session_id: int):
        session = self.db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session: return {"success": False}

        current = session.current_phase
        next_p = current
        announcement = None
        session.timer_expires_at = None

        if current == GamePhase.FIRST_NIGHT:
            self.resolve_night_actions(session_id)
            next_p = GamePhase.DAY_CHITCHAT
            announcement = "เช้าวันแรก เริ่มต้นการพูดคุยหาตัวคนร้ายได้เลย"
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=5)
        elif current == GamePhase.DAY_CHITCHAT:
            next_p = GamePhase.DAY_NOMINATION
            if session.is_automated: session.timer_expires_at = datetime.utcnow() + timedelta(minutes=5)
        elif current == GamePhase.DAY_NOMINATION:
            # 🚀 Before moving to Night, finalize today's execution
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
            
            if dead_names: announcement = f"เช้าวันนี้เราพบร่างของ {' และ '.join(dead_names)} เสียชีวิตลง"
            else: announcement = "เมื่อคืนนี้ไม่มีใครตาย ทุกคนยังอยู่ครบ"

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
                        # 🏰 Mayor Bounce Logic
                        if target.character.name == "Mayor" and not target.is_poisoned and not target.is_drunk:
                            if random.random() < 0.5: # 50% chance to bounce
                                other_targets = [p for p in players if p.is_alive and p.id != imp.id and p.id != target.id]
                                if other_targets:
                                    target = random.choice(other_targets)
                                    self.log_action(session_id, session.current_phase, day, f"🔮 Mayor bounced the kill to {target.name}!")
                        
                        target.is_alive = False
                        dead_tonight.append(target.name)
                        self.log_action(session_id, session.current_phase, day, f"🔮 Imp killed {target.name}.")
                        
        # --- Phase D: Scarlet Woman Inheritance ---
        living_demon = self.db.query(Player).join(Character).filter(
            Player.session_id == session_id,
            Player.is_alive == True,
            Character.char_type == CharacterType.DEMON
        ).first()
        
        if not living_demon:
            living_players_count = self.db.query(Player).filter(Player.session_id == session_id, Player.is_alive == True).count()
            if living_players_count >= 5:
                sw = self.db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Player.is_alive == True,
                    Character.name == "Scarlet Woman",
                    Player.is_drunk == False,
                    Player.is_poisoned == False
                ).first()
                if sw:
                    imp_char = self.db.query(Character).filter(Character.name == "Imp").first()
                    sw.character_id = imp_char.id
                    self.log_action(session_id, session.current_phase, day, f"🔮 Scarlet Woman ({sw.name}) becomes the new Imp.")

        self.db.commit()
        return dead_tonight

    def log_action(self, session_id: int, phase: GamePhase, day: int, detail: str):
        log = GameLog(session_id=session_id, phase=phase, day_number=day, action_detail=detail)
        self.db.add(log)
