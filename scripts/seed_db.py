import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal, engine, Base
from app.db.models import Character, Alignment, CharacterType

def seed_characters():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Clear existing to ensure correct orders
    db.query(Character).delete()

    trouble_brewing = [
        # Townsfolk
        ("Washerwoman", Alignment.GOOD, CharacterType.TOWNSFOLK, 33, None, "You learn that 1 of 2 specific players is a specific Townsfolk."),
        ("Librarian", Alignment.GOOD, CharacterType.TOWNSFOLK, 34, None, "You learn that 1 of 2 specific players is a specific Outsider."),
        ("Investigator", Alignment.GOOD, CharacterType.TOWNSFOLK, 35, None, "You learn that 1 of 2 specific players is a specific Minion."),
        ("Chef", Alignment.GOOD, CharacterType.TOWNSFOLK, 36, None, "You learn how many pairs of evil players are sitting next to each other."),
        ("Empath", Alignment.GOOD, CharacterType.TOWNSFOLK, 37, 53, "You learn how many of your 2 alive neighbors are evil."),
        ("Fortune Teller", Alignment.GOOD, CharacterType.TOWNSFOLK, 38, 54, "Each night, choose 2 players: you learn if either is a Demon. There is a good Red Herring."),
        ("Undertaker", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 68, "Each night, you learn which character died by execution today."),
        ("Monk", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 43, "Each night, choose a player (not yourself): they are safe from the Demon tonight."),
        ("Ravenkeeper", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 52, "If you die at night, you are woken to choose a player: you learn their character."),
        ("Virgin", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "The 1st time you are nominated, if the nominator is a Townsfolk, they are executed immediately."),
        ("Slayer", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "Once per game, during the day, publicly choose a player: if they are the Demon, they die."),
        ("Soldier", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "You are safe from the Demon."),
        ("Mayor", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "If only 3 players are alive and no execution occurred, your team wins. If you die at night, another player might die instead."),
        
        # Outsiders
        ("Butler", Alignment.GOOD, CharacterType.OUTSIDER, 39, 67, "Each night, choose a player (not yourself): tomorrow, you may only vote if they are voting."),
        ("Drunk", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "You do not know you are the Drunk. You think you are a Townsfolk character, but your ability does not work."),
        ("Recluse", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "You might register as evil & as a Minion or Demon, even if dead."),
        ("Saint", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "If you die by execution, your team loses."),
        
        # Minions
        ("Poisoner", Alignment.EVIL, CharacterType.MINION, 27, 44, "Each night, choose a player: they are poisoned tonight and tomorrow day."),
        ("Spy", Alignment.EVIL, CharacterType.MINION, 40, 69, "Each night, you see the Grimoire. You might register as good & as a Townsfolk or Outsider, even if dead."),
        ("Scarlet Woman", Alignment.EVIL, CharacterType.MINION, None, 42, "If there are 5 or more players alive and the Demon dies, you become the Demon."),
        ("Baron", Alignment.EVIL, CharacterType.MINION, None, None, "There are 2 extra Outsiders in play."),
        
        # Demon
        ("Imp", Alignment.EVIL, CharacterType.DEMON, None, 49, "Each night, choose a player: they die. If you kill yourself, a Minion becomes the Imp."),
    ]

    for name, align, ctype, f_order, o_order, desc in trouble_brewing:
        char = Character(
            name=name,
            alignment=align,
            char_type=ctype,
            first_night_order=f_order,
            other_night_order=o_order,
            ability_description=desc
        )
        db.add(char)
    
    db.commit()
    print("Successfully seeded Trouble Brewing characters with descriptions and night orders!")
    db.close()

if __name__ == "__main__":
    seed_characters()
