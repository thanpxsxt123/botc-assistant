from fastapi import APIRouter, Depends, HTTPException
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
            "character_name": p.character.name if p.character else "Unknown",
            "alignment": p.character.alignment.value if p.character else "Unknown"
        })

    await manager.broadcast(room_code, {
        "event": "state_update",
        "data": {
            "phase": session.current_phase.value,
            "round": session.day_number,
            "players": player_list,
            "timer_expires": session.timer_expires_at.isoformat() + "Z" if session.timer_expires_at else None
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
    return manager_logic.advance_step(data.session_id)

@router.get("/player-info")
async def get_player_info(session_id: int, name: str, db: Session = Depends(get_db)):
    player = db.query(Player).filter(
        Player.session_id == session_id,
        Player.name == name
    ).first()
    
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
        
    secret_info = ""
    if player.character:
        if player.character.char_type == CharacterType.DEMON:
            minions = db.query(Player).join(Character).filter(
                Player.session_id == session_id,
                Character.char_type == CharacterType.MINION
            ).all()
            if minions:
                secret_info = f"😈 สมุนของคุณคือ: {', '.join([m.name for m in minions])}"
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
async def get_grimoire(session_id: int, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    players = db.query(Player).filter(Player.session_id == session_id).order_by(Player.seat_number).all()
    player_data = []
    for p in players:
        player_data.append({
            "id": p.id, "name": p.name, "seat_number": p.seat_number,
            "character_name": p.character.name if p.character else "Unknown",
            "alignment": p.character.alignment.value if p.character else "Unknown",
            "is_alive": p.is_alive, "is_drunk": p.is_drunk, "is_poisoned": p.is_poisoned,
            "has_used_dead_vote": p.has_used_dead_vote,
            "ability_description": p.character.ability_description if p.character else ""
        })
    return {
        "session": {"room_code": session.room_code, "current_phase": session.current_phase.value, "day_number": session.day_number},
        "players": player_data
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
    existing = db.query(NightAction).filter(NightAction.session_id == data.session_id, NightAction.player_id == data.player_id, NightAction.day_number == session.day_number).first()
    if existing:
        existing.target_player_id = data.target_id
        existing.target_player_id_2 = data.target_id_2
    else:
        db.add(NightAction(session_id=data.session_id, player_id=data.player_id, target_player_id=data.target_id, target_player_id_2=data.target_id_2, day_number=session.day_number, action_type=data.action_type))
    db.commit()
    await manager.broadcast(session.room_code, {"event": "player_acted", "data": { "player_id": data.player_id }})
    return {"status": "success"}

@router.post("/next-phase")
async def next_phase(data: PhaseChange, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    room_code = session.room_code
    success = engine.next_phase(data.session_id)
    if success:
        db.refresh(session)
        await broadcast_game_state(room_code, data.session_id, db)
        winner = engine.check_win_conditions(data.session_id)
        if winner: await manager.broadcast(room_code, {"event": "game_over", "data": { "winner": winner }})
        return {"status": "success", "new_phase": session.current_phase.value}
    return {"status": "failed"}

@router.post("/nominate")
async def nominate(data: NominationCreate, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    nomination = engine.create_nomination(data.session_id, data.nominator_id, data.nominee_id)
    if not nomination: return {"status": "virgin_triggered"}
    await manager.broadcast(db.query(GameSession).filter(GameSession.id == data.session_id).first().room_code, {"event": "new_nomination", "data": {"nomination_id": nomination.id, "nominator": nomination.nominator.name, "nominee": nomination.nominee.name}})
    return {"status": "success", "nomination_id": nomination.id}

@router.post("/vote")
async def vote(data: VoteSubmit, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    if not engine.handle_dead_vote(data.player_id): raise HTTPException(status_code=400, detail="No votes left")
    nomination = db.query(Nomination).filter(Nomination.id == data.nomination_id).first()
    nomination.votes_received += 1
    db.commit()
    await manager.broadcast(nomination.session.room_code, {"event": "vote_updated", "data": {"nomination_id": nomination.id, "votes": nomination.votes_received, "is_closed": nomination.is_closed}})
    return {"status": "success", "current_votes": nomination.votes_received}

@router.post("/slayer-shot")
async def slayer_shot(data: SlayerShot, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    success = engine.slayer_shot(data.session_id, data.slayer_id, data.target_id)
    return {"status": "success", "hit": success}