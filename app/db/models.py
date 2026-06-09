from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, Text
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from app.db.database import Base

class GamePhase(enum.Enum):
    SETUP = "SETUP"
    FIRST_NIGHT = "FIRST_NIGHT"
    DAY_CHITCHAT = "DAY_CHITCHAT"
    DAY_NOMINATION = "DAY_NOMINATION"
    DAY_VOTING = "DAY_VOTING"
    NIGHT = "NIGHT"
    GAME_OVER = "GAME_OVER"

class Alignment(enum.Enum):
    GOOD = "GOOD"
    EVIL = "EVIL"

class CharacterType(enum.Enum):
    TOWNSFOLK = "TOWNSFOLK"
    OUTSIDER = "OUTSIDER"
    MINION = "MINION"
    DEMON = "DEMON"

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    alignment = Column(Enum(Alignment), nullable=False)
    char_type = Column(Enum(CharacterType), nullable=False)
    ability_description = Column(Text)
    first_night_order = Column(Integer, nullable=True) # Order in which they wake up on night 1
    other_night_order = Column(Integer, nullable=True) # Order on subsequent nights
    
    players = relationship("Player", back_populates="character")

class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String, unique=True, index=True, nullable=False)
    current_phase = Column(Enum(GamePhase), default=GamePhase.SETUP)
    day_number = Column(Integer, default=0)
    night_action_step = Column(Integer, default=0)
    timer_expires_at = Column(DateTime, nullable=True) # Countdown end time
    is_automated = Column(Boolean, default=False) # If True, phases advance automatically
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    players = relationship("Player", back_populates="session")
    logs = relationship("GameLog", back_populates="session")

class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"))
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    name = Column(String, nullable=False)
    is_alive = Column(Boolean, default=True)
    has_voted_this_day = Column(Boolean, default=False)
    has_used_dead_vote = Column(Boolean, default=False)
    seat_number = Column(Integer) # Physical position at the table
    is_poisoned = Column(Boolean, default=False)
    is_drunk = Column(Boolean, default=False)
    is_red_herring = Column(Boolean, default=False)
    pos_x = Column(Integer, nullable=True)
    pos_y = Column(Integer, nullable=True)

    session = relationship("GameSession", back_populates="players")
    character = relationship("Character", back_populates="players")

class GameLog(Base):
    __tablename__ = "game_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"))
    phase = Column(Enum(GamePhase))
    day_number = Column(Integer)
    action_detail = Column(Text) # JSON or descriptive text of what happened
    timestamp = Column(DateTime, default=datetime.utcnow)

    session = relationship("GameSession", back_populates="logs")

class Nomination(Base):
    __tablename__ = "nominations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"))
    nominator_id = Column(Integer, ForeignKey("players.id"))
    nominee_id = Column(Integer, ForeignKey("players.id"))
    day_number = Column(Integer)
    votes_received = Column(Integer, default=0)
    is_executed = Column(Boolean, default=False)
    is_closed = Column(Boolean, default=False)

    session = relationship("GameSession")
    nominator = relationship("Player", foreign_keys=[nominator_id])
    nominee = relationship("Player", foreign_keys=[nominee_id])

class NightAction(Base):
    __tablename__ = "night_actions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"))
    player_id = Column(Integer, ForeignKey("players.id"))
    target_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    target_player_id_2 = Column(Integer, ForeignKey("players.id"), nullable=True) # For Fortune Teller
    day_number = Column(Integer)
    action_type = Column(String) # e.g., "POISON", "KILL", "PROTECT"

    session = relationship("GameSession")
    player = relationship("Player", foreign_keys=[player_id])
    target = relationship("Player", foreign_keys=[target_player_id])
