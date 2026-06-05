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
# กำหนด Base URL สำหรับสร้างลิงก์เชิญเข้าห้องเกม
BASE_URL = "https://botc-assistant.onrender.com"

# --- Models ---

class CreateRoom(BaseModel):
    room_code: str

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

# --- Endpoints ---

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.post("/create-room")
async def create_room(data: CreateRoom, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    session = engine.create_room(data.room_code)
    
    # สร้างลิงก์แชร์สำหรับส่งเข้ากลุ่ม Line / Discord
    join_link = f"{BASE_URL}/join/{session.id}"
    
    return {
        "status": "success", 
        "session_id": session.id,
        "join_link": join_link
    }

@router.post("/join")
async def join_room(data: JoinRoom, db: Session = Depends(get_db)):
    # เช็คก่อนว่าห้องเกมนี้มีอยู่จริงไหม
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Game session not found")
        
    # ค้นหาผู้เล่นปัจจุบันในเซสชันนีเพื่อคำนวณหาเลขที่นั่งถัดไปแบบอัตโนมัติ
    current_players_count = db.query(Player).filter(Player.session_id == data.session_id).count()
    auto_assigned_seat = current_players_count + 1

    engine = GameEngine(db)
    player = engine.add_player(data.session_id, data.name, auto_assigned_seat)
    
    return {
        "status": "success", 
        "player_id": player.id,
        "assigned_seat": auto_assigned_seat
    }

@router.post("/start")
async def start_game(data: PhaseChange, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    success = engine.start_game(data.session_id)
    if success:
        session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
        await manager.broadcast(session.room_code, {
            "event": "phase_change",
            "data": {
                "phase": session.current_phase.value,
                "day": session.day_number
            }
        })
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

@router.get("/grimoire")
async def get_grimoire(session_id: int, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    players = db.query(Player).filter(Player.session_id == session_id).order_by(Player.seat_number).all()
    
    player_data = []
    for p in players:
        player_data.append({
            "id": p.id,
            "name": p.name,
            "seat_number": p.seat_number,
            "character_name": p.character.name if p.character else "Unknown",
            "alignment": p.character.alignment.value if p.character else "Unknown",
            "is_alive": p.is_alive,
            "is_drunk": p.is_drunk,
            "is_poisoned": p.is_poisoned,
            "ability_description": p.character.ability_description if p.character else ""
        })
    
    return {
        "session": {
            "room_code": session.room_code,
            "current_phase": session.current_phase.value,
            "day_number": session.day_number
        },
        "players": player_data
    }

@router.post("/player-action")
async def player_action(data: PlayerAction, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session or "NIGHT" not in session.current_phase.value:
        raise HTTPException(status_code=400, detail="Actions only allowed during Night phase")
    
    existing = db.query(NightAction).filter(
        NightAction.session_id == data.session_id,
        NightAction.player_id == data.player_id,
        NightAction.day_number == session.day_number
    ).first()
    
    if existing:
        existing.target_player_id = data.target_id
        existing.target_player_id_2 = data.target_id_2
    else:
        new_action = NightAction(
            session_id=data.session_id,
            player_id=data.player_id,
            target_player_id=data.target_id,
            target_player_id_2=data.target_id_2,
            day_number=session.day_number,
            action_type=data.action_type
        )
        db.add(new_action)
    
    db.commit()
    await manager.broadcast(session.room_code, {
        "event": "player_acted",
        "data": { "player_id": data.player_id }
    })
    return {"status": "success"}

@router.post("/next-phase")
async def next_phase(data: PhaseChange, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    session = db.query(GameSession).filter(GameSession.id == data.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    room_code = session.room_code
    success = engine.next_phase(data.session_id)
    
    if success:
        db.refresh(session)
        timer_iso = session.timer_expires_at.isoformat() + "Z" if session.timer_expires_at else None
        
        await manager.broadcast(room_code, {
            "event": "phase_change",
            "data": {
                "phase": session.current_phase.value,
                "day": session.day_number,
                "timer_expires": timer_iso
            }
        })
        
        winner = engine.check_win_conditions(data.session_id)
        if winner:
            await manager.broadcast(room_code, {
                "event": "game_over",
                "data": { "winner": winner }
            })
            
        return {"status": "success", "new_phase": session.current_phase.value}
    return {"status": "failed"}

@router.post("/nominate")
async def nominate(data: NominationCreate, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    nomination = engine.create_nomination(data.session_id, data.nominator_id, data.nominee_id)
    
    if not nomination: 
        return {"status": "virgin_triggered"}

    room_code = db.query(GameSession).filter(GameSession.id == data.session_id).first().room_code
    await manager.broadcast(room_code, {
        "event": "new_nomination",
        "data": {
            "nomination_id": nomination.id,
            "nominator": nomination.nominator.name,
            "nominee": nomination.nominee.name
        }
    })
    return {"status": "success", "nomination_id": nomination.id}

@router.post("/vote")
async def vote(data: VoteSubmit, db: Session = Depends(get_db)):
    engine = GameEngine(db)

    if not engine.handle_dead_vote(data.player_id):
        raise HTTPException(status_code=400, detail="Dead player has no votes left")

    nomination = db.query(Nomination).filter(Nomination.id == data.nomination_id).first()
    nomination.votes_received += 1
    db.commit()

    room_code = nomination.session.room_code
    await manager.broadcast(room_code, {
        "event": "vote_updated",
        "data": {
            "nomination_id": nomination.id,
            "votes": nomination.votes_received,
            "is_closed": nomination.is_closed
        }
    })
    return {"status": "success", "current_votes": nomination.votes_received}

@router.post("/slayer-shot")
async def slayer_shot(data: SlayerShot, db: Session = Depends(get_db)):
    engine = GameEngine(db)
    success = engine.slayer_shot(data.session_id, data.slayer_id, data.target_id)
    return {"status": "success", "hit": success}