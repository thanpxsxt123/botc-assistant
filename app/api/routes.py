from fastapi import APIRouter, Depends, HTTPException
import random
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import GameSession, Player, Character, CharacterType, Alignment, Nomination, NightAction
from app.core.fsm import GameEngine
from app.api.websocket import manager
from pydantic import BaseModel
from typing import Optional

from app.core.night_manager import NightManager

router = APIRouter()

# --- Configuration ---
BASE_URL = "https://botc-assistant.onrender.com"

# --- Models ---

class CreateRoom(BaseModel):
    room_code: str
    is_automated: bool = False

class JoinRoom(BaseModel):
    session_id: int
    name: str

class PhaseChange(BaseModel):
    session_id: int

class SetPhaseRequest(BaseModel):
    session_id: int
    phase: str

class PlayerAction(BaseModel):
    session_id: int
    player_id: int
    target_id: int
    target_id_2: Optional[int] = None
    action_type: str

class NominationCreate(BaseModel):
    session_id: int
    nominator_id: int
    nominee_id: int

class VoteSubmit(BaseModel):
    nomination_id: int
    player_id: int

class SlayerShot(BaseModel):
    session_id: int
    slayer_id: int
    target_id: int

class PlayerUpdate(BaseModel):
    player_id: int
    is_alive: Optional[bool] = None
    is_poisoned: Optional[bool] = None
    is_drunk: Optional[bool] = None
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None

# --- Helper ---

async def broadcast_game_state(room_code: str, session_id: int, db: Session):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    players = db.query(Player).filter(Player.session_id == session_id).all()
    
    player_list = []
    for p in players:
        player_list.append({
            "id": p.id,
            "name": p.name,
            "is_alive": p.is_alive,
            "is_poisoned": p.is_poisoned,
            "is_drunk": p.is_drunk,
            "has_used_dead_vote": p.has_used_dead_vote,
            "pos_x": p.pos_x,
            "pos_y": p.pos_y,
            "character_name": p.character.name if p.character else "Unknown",
            "alignment": p.character.alignment.value if p.character else "Unknown"
        })

    active_char = None
    if "NIGHT" in session.current_phase.value:
        from app.core.night_manager import NightManager
        nm = NightManager(db)
        step_info = nm.get_current_step_info(session_id)
        if step_info.get("status") == "active":
            active_char = step_info.get("character")

    await manager.broadcast(room_code, {
        "event": "state_update",
        "data": {
            "phase": session.current_phase.value,
            "round": session.day_number,
            "players": player_list,
            "timer_expires": session.timer_expires_at.isoformat() + "Z" if session.timer_expires_at else None,
            "active_character": active_char
        }
    })

# --- Endpoints ---

@router.get("/session/{room_code}")
async def get_session_by_code(room_code: str, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.room_code == room_code.upper()).first()
    if not session:
        engine = GameEngine(db)
        session = engine.create_room(room_code.upper())
    
    return {
        "session_id": session.id,
        "room_code": session.room_code,
        "current_phase": session.current_phase.value,
        "day_number": session.day_number,
        "is_automated": session.is_automated
    }

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.post("/create-room")
async def create_room(data: CreateRoom, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    session = engine.create_room(data.room_code, is_automated=data.is_automated)
    join_link = f"{BASE_URL}/join/{session.id}"
    return {
        "status": "success", 
        "session_id": session.id,
        "join_link": join_link,
        "is_automated": session.is_automated
    }

@router.post("/join")
async def join_room(data: JoinRoom, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # 🚫 ห้ามใช้ชื่อที่จองไว้สำหรับ Master
    if data.name.lower() in ["storyteller", "st", "master", "ผู้เล่าเรื่อง"]:
        raise HTTPException(status_code=400, detail="Name reserved for Master")

    existing_player = db.query(Player).filter(
        Player.session_id == data.session_id,
        Player.name == data.name
    ).first()

    if existing_player:
        player = existing_player
    else:
        current_players_count = db.query(Player).filter(Player.session_id == data.session_id).count()
        auto_assigned_seat = current_players_count + 1
        engine = GameEngine(db)
        player = engine.add_player(data.session_id, data.name, auto_assigned_seat)
    
    await broadcast_game_state(session.room_code, data.session_id, db)
    
    return {
        "status": "success", 
        "player_id": player.id,
        "assigned_seat": player.seat_number
    }

@router.post("/start")
async def start_game(data: PhaseChange, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    success = engine.start_game(data.session_id)
    if success:
        session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
        await broadcast_game_state(session.room_code, data.session_id, db)
        return {"status": "success"}
    return {"status": "failed"}

@router.get("/night-step")
async def get_night_step(session_id: int, db: Session = Depends(get_db)):
    manager_logic = NightManager(db)
    return manager_logic.get_current_step_info(session_id)

@router.post("/night-next")
async def next_night_step(data: PhaseChange, db: Session = Depends(get_db)):
    manager_logic = NightManager(db)
    result = manager_logic.advance_step(data.session_id)
    
    # Broadcast state update to ensure all STs are synced
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if session:
        await broadcast_game_state(session.room_code, data.session_id, db)
        
    return result

@router.get("/player-info")
async def get_player_info(session_id: int, name: str, db: Session = Depends(get_db)):
    player = db.query(Player).filter(
        Player.session_id == session_id,
        Player.name == name
    ).first()
    
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
        
    secret_info = ""
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if player.character and session:
        char_name = player.character.name

        # 🔥 Return stored secret info if exists (prevents random values changing on refresh)
        if player.secret_info:
            secret_info = player.secret_info
        else:
            # 1. Demon Info
            if player.character.char_type == CharacterType.DEMON:
                minions = db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Character.char_type == CharacterType.MINION
                ).all()
                if minions:
                    secret_info = f"😈 สมุนของคุณคือ: {', '.join([m.name for m in minions])}"

            # 2. Minion Info
            elif player.character.char_type == CharacterType.MINION:
                demon = db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Character.char_type == CharacterType.DEMON
                ).first()
                other_minions = db.query(Player).join(Character).filter(
                    Player.session_id == session_id, Character.char_type == CharacterType.MINION, Player.id != player.id
                ).all()
                info = []
                if demon: info.append(f"🔥 ปีศาจคือ: {demon.name}")
                if other_minions: info.append(f"👥 สมุนคนอื่น: {', '.join([m.name for m in other_minions])}")
                secret_info = " | ".join(info)

                # --- Spy Special Logic ---
                if char_name == "Spy":
                    all_players = db.query(Player).filter(Player.session_id == session_id).order_by(Player.seat_number).all()
                    grimoire_info = "\n".join([f"{p.name}: {p.character.name if p.character else 'Unknown'}" for p in all_players])
                    secret_info += f"\n\n📖 [Spy] ข้อมูลคัมภีร์:\n{grimoire_info}"

            # 3. Chef Info
            elif char_name == "Chef":
                from app.core.rules import RuleEngine
                re_engine = RuleEngine(db)
                evil_pairs = re_engine.process_chef_info(session_id)
                if player.is_poisoned or player.is_drunk:
                    evil_pairs = random.randint(0, 3) # ข้อมูลมั่ว
                secret_info = f"👨‍🍳 คู่ผู้เล่นฝั่งร้ายนั่งติดกันคือ: {evil_pairs} คู่"

            # 4. Empath Info
            elif char_name == "Empath":
                from app.core.rules import RuleEngine
                re_engine = RuleEngine(db)
                neighbors = re_engine.get_neighbors(player.id, session_id)
                evil_count = sum(1 for n in neighbors if n.character and n.character.alignment == Alignment.EVIL)
                if player.is_poisoned or player.is_drunk:
                    evil_count = random.randint(0, 2) # ข้อมูลมั่ว
                secret_info = f"🔮 คนร้ายข้างตัวคุณที่ยังมีชีวิตอยู่มีจำนวน: {evil_count} คน"

            # 4.1 Fortune Teller Info
            elif char_name == "Fortune Teller":
                last_act = db.query(NightAction).filter(
                    NightAction.session_id == session_id,
                    NightAction.player_id == player.id,
                    NightAction.day_number == session.day_number
                ).first()

                if last_act:
                    target1 = db.query(Player).filter(Player.id == last_act.target_player_id).first()
                    target2 = db.query(Player).filter(Player.id == last_act.target_player_id_2).first()

                    if target1 and target2:
                        is_demon = False
                        if (target1.character and target1.character.char_type == CharacterType.DEMON) or target1.is_red_herring:
                            is_demon = True
                        if (target2.character and target2.character.char_type == CharacterType.DEMON) or target2.is_red_herring:
                            is_demon = True

                        if player.is_poisoned or player.is_drunk:
                            is_demon = random.choice([True, False])

                        res_text = "ใช่ (YES)" if is_demon else "ไม่ใช่ (NO)"
                        secret_info = f"🔮 ผลการพยากรณ์คืนนี้ ({target1.name}, {target2.name}): {res_text}"
                else:
                    secret_info = "🔮 โปรดเลือกเป้าหมาย 2 คนเพื่อพยากรณ์"

            # 5. Washerwoman Info (First Night only)
            elif char_name == "Washerwoman" and session.day_number == 1:
                townsfolk_players = db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Player.id != player.id,
                    Character.char_type == CharacterType.TOWNSFOLK
                ).all()
                if townsfolk_players:
                    target_tf = random.choice(townsfolk_players)
                    other_players = db.query(Player).filter(
                        Player.session_id == session_id,
                        Player.id != player.id,
                        Player.id != target_tf.id
                    ).all()
                    if other_players:
                        other_p = random.choice(other_players)
                        pair = [target_tf.name, other_p.name]
                        random.shuffle(pair)
                        secret_info = f"🧺 1 ใน 2 คนนี้คือ {target_tf.character.name}: {pair[0]} หรือ {pair[1]}"

            # 6. Librarian Info (First Night only)
            elif char_name == "Librarian" and session.day_number == 1:
                outsiders = db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Player.id != player.id,
                    Character.char_type == CharacterType.OUTSIDER
                ).all()
                if outsiders:
                    target_os = random.choice(outsiders)
                    other_players = db.query(Player).filter(
                        Player.session_id == session_id,
                        Player.id != player.id,
                        Player.id != target_os.id
                    ).all()
                    if other_players:
                        other_p = random.choice(other_players)
                        pair = [target_os.name, other_p.name]
                        random.shuffle(pair)
                        secret_info = f"📖 1 ใน 2 คนนี้คือ {target_os.character.name}: {pair[0]} หรือ {pair[1]}"

            # 7. Investigator Info (First Night only)
            elif char_name == "Investigator" and session.day_number == 1:
                minions = db.query(Player).join(Character).filter(
                    Player.session_id == session_id,
                    Player.id != player.id,
                    Character.char_type == CharacterType.MINION
                ).all()
                if minions:
                    target_m = random.choice(minions)
                    other_players = db.query(Player).filter(
                        Player.session_id == session_id,
                        Player.id != player.id,
                        Player.id != target_m.id
                    ).all()
                    if other_players:
                        other_p = random.choice(other_players)
                        pair = [target_m.name, other_p.name]
                        random.shuffle(pair)
                        secret_info = f"🔍 1 ใน 2 คนนี้คือ {target_m.character.name}: {pair[0]} หรือ {pair[1]}"

            # 8. Undertaker Info
            elif char_name == "Undertaker" and session.day_number > 1:
                executed_nom = db.query(Nomination).filter(
                    Nomination.session_id == session_id,
                    Nomination.day_number == session.day_number - 1,
                    Nomination.is_executed == True
                ).first()
                if executed_nom and executed_nom.nominee and executed_nom.nominee.character:
                    secret_info = f"⚰️ ผู้เล่นที่ถูกประหารชีวิตเมื่อวานนี้คือ: {executed_nom.nominee.character.name}"
                else:
                    secret_info = "⚰️ ไม่มีใครถูกประหารชีวิตเมื่อวานนี้"

            # 9. Ravenkeeper Info
            elif char_name == "Ravenkeeper":
                # 🦉 Ravenkeeper Official: Wakes ONLY if they died TONIGHT.
                if not player.is_alive:
                    last_act = db.query(NightAction).filter(
                        NightAction.session_id == session_id,
                        NightAction.player_id == player.id,
                        NightAction.day_number == session.day_number
                    ).first()
                    if last_act:
                        target = db.query(Player).filter(Player.id == last_act.target_player_id).first()
                        if target and target.character:
                            info_char = target.character.name
                            if player.is_poisoned or player.is_drunk:
                                all_chars = db.query(Character).all()
                                info_char = random.choice(all_chars).name
                            secret_info = f"🦉 ผลการตรวจสอบ: {target.name} คือ {info_char}"
                    else:
                        secret_info = "🦉 คุณเสียชีวิตคืนนี้! โปรดเลือกผู้เล่น 1 คนเพื่อตรวจสอบอัตลักษณ์"
                else:
                    secret_info = "🦉 (คุณยังไม่เสียชีวิต ความสามารถยังไม่ทำงาน)"

            # 10. Butler Info
            elif char_name == "Butler":
                last_act = db.query(NightAction).filter(
                    NightAction.session_id == session_id,
                    NightAction.player_id == player.id,
                    NightAction.day_number == session.day_number
                ).first()
                if last_act:
                    master = db.query(Player).filter(Player.id == last_act.target_player_id).first()
                    if master:
                        secret_info = f"👔 เจ้านายของคุณคืนนี้คือ: {master.name} (คุณต้องโหวตตามเขาเท่านั้น)"
                else:
                    secret_info = "👔 โปรดเลือกผู้เล่น 1 คนเพื่อเป็นเจ้านายในคืนนี้"

            # 💾 Save persistent info for these specific roles
            persistent_roles = ["Washerwoman", "Librarian", "Investigator", "Chef", "Imp", "Poisoner", "Spy"]
            if (char_name in persistent_roles or player.character.char_type in [CharacterType.DEMON, CharacterType.MINION]) and secret_info:
                player.secret_info = secret_info
                db.commit()

    # บังคับดึงข้อมูลล่าสุดเพื่อให้ได้คำอธิบายไทย
    char_info = db.query(Character).filter(Character.id == player.character_id).first()
    
    return {
        "player_id": player.id,
        "name": player.name,
        "character": char_info.name if char_info else "Unknown",
        "alignment": char_info.alignment.value if char_info else "Unknown",
        "is_alive": player.is_alive,
        "is_drunk": player.is_drunk,
        "is_poisoned": player.is_poisoned,
        "has_used_dead_vote": player.has_used_dead_vote,
        "ability": char_info.ability_description if char_info else "รอรับบทบาท...",
        "secret_info": secret_info
    }

@router.get("/grimoire")
async def get_grimoire(session_id: int, role: Optional[str] = None, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    players = db.query(Player).filter(Player.session_id == session_id).order_by(Player.seat_number).all()
    player_data = []
    
    for p in players:
        p_dict = {
            "id": p.id,
            "name": p.name,
            "seat_number": p.seat_number,
            "is_alive": p.is_alive,
            "has_used_dead_vote": p.has_used_dead_vote,
            "pos_x": p.pos_x,
            "pos_y": p.pos_y,
        }
        if role == "storyteller":
            p_dict["character_name"] = p.character.name if p.character else "Unknown"
            p_dict["alignment"] = p.character.alignment.value if p.character else "Unknown"
            p_dict["is_drunk"] = p.is_drunk
            p_dict["is_poisoned"] = p.is_poisoned
            p_dict["ability_description"] = p.character.ability_description if p.character else ""
        else:
            p_dict["character_name"] = "Unknown"
            p_dict["alignment"] = "Unknown"
            p_dict["is_drunk"] = False
            p_dict["is_poisoned"] = False
            p_dict["ability_description"] = ""
            
        player_data.append(p_dict)
        
    active_nom = db.query(Nomination).filter(
        Nomination.session_id == session_id,
        Nomination.day_number == session.day_number,
        Nomination.is_closed == False
    ).first()
    
    active_nom_data = None
    if active_nom:
        active_nom_data = {
            "nomination_id": active_nom.id,
            "nominator": active_nom.nominator.name,
            "nominee": active_nom.nominee.name,
            "votes_received": active_nom.votes_received
        }
        
    # Query logs
    from app.db.models import GameLog
    logs_query = db.query(GameLog).filter(GameLog.session_id == session_id).order_by(GameLog.timestamp.desc())
    if role != "storyteller":
        logs_query = logs_query.filter(~GameLog.action_detail.like("🔮%"))
        
    logs = logs_query.all()
    log_data = [{"detail": log.action_detail, "timestamp": log.timestamp.isoformat()} for log in logs]
    
    # Find everyone who has submitted an action tonight
    acted_player_ids = []
    actions = db.query(NightAction).filter(
        NightAction.session_id == session_id,
        NightAction.day_number == session.day_number
    ).all()
    acted_player_ids = [act.player_id for act in actions]

    return {
        "session": {"room_code": session.room_code, "current_phase": session.current_phase.value, "day_number": session.day_number},
        "players": player_data,
        "active_nomination": active_nom_data,
        "logs": log_data,
        "acted_player_ids": acted_player_ids
    }

@router.post("/narrate")
async def narrate_text(data: dict, db: Session = Depends(get_db)):
    text = data.get("text")
    room_code = data.get("room_code")
    if not text: raise HTTPException(status_code=400, detail="Text required")
    from app.narration.engine import ThaiNarrator
    narrator = ThaiNarrator()
    audio_path = narrator.generate_speech(text)
    await manager.broadcast(room_code, {"event": "play_audio", "data": {"audio_url": f"/{audio_path}", "text": text}})
    return {"status": "success", "audio_url": audio_path}

@router.post("/player-action")
async def player_action(data: PlayerAction, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session or "NIGHT" not in session.current_phase.value:
        raise HTTPException(status_code=400, detail="Actions only allowed during Night")

    acting_player = db.query(Player).filter(Player.id == data.player_id).first()
    target_player = db.query(Player).filter(Player.id == data.target_id).first()
    target_player_2 = db.query(Player).filter(Player.id == data.target_id_2).first() if data.target_id_2 else None

    existing = db.query(NightAction).filter(NightAction.session_id == data.session_id, NightAction.player_id == data.player_id, NightAction.day_number == session.day_number).first()
    if existing:
        existing.target_player_id = data.target_id
        existing.target_player_id_2 = data.target_id_2
    else:
        db.add(NightAction(session_id=data.session_id, player_id=data.player_id, target_player_id=data.target_id, target_player_id_2=data.target_id_2, day_number=session.day_number, action_type=data.action_type))

    # 🚀 AUTO ADVANCE: If automated, move to next step
    if session.is_automated:
        from app.core.night_manager import NightManager
        manager_logic = NightManager(db)
        manager_logic.advance_step(session.id)

    # Write a secret log for Storyteller
    engine = GameEngine(db)
    role_name = acting_player.character.name if acting_player and acting_player.character else "Unknown"
    act_name = acting_player.name if acting_player else "Unknown"
    t_name = target_player.name if target_player else "None"

    if data.action_type == "confirm_info":
        log_detail = f"✅ {role_name} ({act_name}) ยืนยันรับทราบข้อมูลแล้ว"
    else:
        log_detail = f"🔮 {role_name} ({act_name}) เลือกเป้าหมาย: {t_name}"
        if target_player_2:
            log_detail += f" และ {target_player_2.name}"

    engine.log_action(session.id, session.current_phase, session.day_number, log_detail)
    db.commit()

    await manager.broadcast(session.room_code, {"event": "player_acted", "data": { "player_id": data.player_id }})
    await broadcast_game_state(session.room_code, session.id, db)
    return {"status": "success"}

@router.post("/set-phase")
async def set_phase(data: SetPhaseRequest, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    try:
        from app.db.models import GamePhase
        new_phase = GamePhase(data.phase.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid phase")
        
    session.current_phase = new_phase
    if "NIGHT" in new_phase.value:
        session.night_action_step = 0
        
    db.commit()
    await broadcast_game_state(session.room_code, session.id, db)
    return {"status": "success", "new_phase": session.current_phase.value}

@router.post("/next-phase")
async def next_phase(data: PhaseChange, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    room_code = session.room_code
    
    result = engine.next_phase(data.session_id)
    if result.get("success"):
        db.refresh(session)
        
        # Play narration voice if announcement is generated
        if result.get("announcement"):
            from app.narration.engine import ThaiNarrator
            narrator = ThaiNarrator()
            text = result["announcement"]
            audio_path = narrator.generate_speech(text)
            await manager.broadcast(room_code, {"event": "play_audio", "data": {"audio_url": f"/{audio_path}", "text": text}})
            
        await broadcast_game_state(room_code, data.session_id, db)
        winner = engine.check_win_conditions(data.session_id)
        if winner: await manager.broadcast(room_code, {"event": "game_over", "data": { "winner": winner }})
        return {"status": "success", "new_phase": session.current_phase.value}
    return {"status": "failed"}

@router.post("/nominate")
async def nominate(data: NominationCreate, db: Session = Depends(get_db)):
    # 🚫 Check if there is already an active nomination
    active_nom = db.query(Nomination).filter(
        Nomination.session_id == data.session_id,
        Nomination.is_closed == False
    ).first()
    if active_nom:
        raise HTTPException(status_code=400, detail="ยังมีศาลที่กำลังพิจารณาคดีอยู่ โปรดปิดคดีเก่าก่อน")

    engine = GameEngine(db)
    nomination = engine.create_nomination(data.session_id, data.nominator_id, data.nominee_id)
    if nomination == "ALREADY_DEAD": return {"status": "ALREADY_DEAD"}
    if nomination == "ALREADY_NOMINATED": return {"status": "ALREADY_NOMINATED"}
    if nomination == "NOMINEE_ALREADY_TARGETED": return {"status": "NOMINEE_ALREADY_TARGETED"}
    if not nomination: return {"status": "virgin_triggered"}
    
    await manager.broadcast(db.query(GameSession).filter(GameSession.id == data.session_id).first().room_code, {"event": "new_nomination", "data": {"nomination_id": nomination.id, "nominator": nomination.nominator.name, "nominee": nomination.nominee.name}})
    return {"status": "success", "nomination_id": nomination.id}

@router.post("/close-voting")
async def close_voting(data: PhaseChange, db: Session = Depends(get_db)):
    # Find the active nomination
    active_nom = db.query(Nomination).filter(
        Nomination.session_id == data.session_id,
        Nomination.is_closed == False
    ).first()
    if not active_nom:
        raise HTTPException(status_code=404, detail="No active nomination found")

    engine = GameEngine(db)
    engine.finalize_nomination(active_nom.id)
    
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    await broadcast_game_state(session.room_code, data.session_id, db)
    await manager.broadcast(session.room_code, {"event": "vote_closed", "data": {"nomination_id": active_nom.id}})
    return {"status": "success"}

@router.post("/vote")
async def vote(data: VoteSubmit, db: Session = Depends(get_db)):
    # 🚫 ตรวจสอบว่าโหวตไปแล้วหรือยัง (ป้องกัน Double Vote)
    from app.db.models import GameLog
    existing_vote = db.query(GameLog).filter(
        GameLog.session_id == db.query(Nomination).filter(Nomination.id == data.nomination_id).first().session_id,
        GameLog.action_detail.like(f"🗳️ Player ID {data.player_id} voted on Nomination {data.nomination_id}")
    ).first()
    
    if existing_vote:
        raise HTTPException(status_code=400, detail="คุณได้ลงคะแนนโหวตไปแล้ว")

    engine = GameEngine(db)
    if not engine.handle_dead_vote(data.player_id): raise HTTPException(status_code=400, detail="No votes left")
    
    nomination = db.query(Nomination).filter(Nomination.id == data.nomination_id).first()
    nomination.votes_received += 1
    
    # บันทึก log การโหวตเพื่อกันการโหวตซ้ำ
    engine.log_action(nomination.session_id, nomination.session.current_phase, nomination.session.day_number, 
                      f"🗳️ Player ID {data.player_id} voted on Nomination {data.nomination_id}")
    
    db.commit()
    await manager.broadcast(nomination.session.room_code, {"event": "vote_updated", "data": {"nomination_id": nomination.id, "votes": nomination.votes_received, "is_closed": nomination.is_closed}})
    return {"status": "success", "current_votes": nomination.votes_received}

@router.post("/slayer-shot")
async def slayer_shot(data: SlayerShot, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    success = engine.slayer_shot(data.session_id, data.slayer_id, data.target_id)
    return {"status": "success", "hit": success}

@router.post("/player/update")
async def update_player(data: PlayerUpdate, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == data.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    if data.is_alive is not None:
        player.is_alive = data.is_alive
    if data.is_poisoned is not None:
        player.is_poisoned = data.is_poisoned
    if data.is_drunk is not None:
        player.is_drunk = data.is_drunk
    if data.pos_x is not None:
        player.pos_x = data.pos_x
    if data.pos_y is not None:
        player.pos_y = data.pos_y
        
    db.commit()
    await broadcast_game_state(player.session.room_code, player.session_id, db)
    return {"status": "success"}

@router.delete("/player/{player_id}")
async def delete_player(player_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    session_id = player.session_id
    room_code = player.session.room_code
    db.delete(player)
    db.commit()
    await broadcast_game_state(room_code, session_id, db)
    return {"status": "success"}