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
        ("Washerwoman", Alignment.GOOD, CharacterType.TOWNSFOLK, 33, None, "คุณจะได้รู้ว่า 1 ใน 2 ผู้เล่นที่คุณเลือก เป็นตัวละครชาวเมืองบทหนึ่ง (ระบบจะสุ่มชื่อคนและบทมาให้)"),
        ("Librarian", Alignment.GOOD, CharacterType.TOWNSFOLK, 34, None, "คุณจะได้รู้ว่า 1 ใน 2 ผู้เล่นที่คุณเลือก เป็นตัวละครชาวบ้านนอกบทหนึ่ง"),
        ("Investigator", Alignment.GOOD, CharacterType.TOWNSFOLK, 35, None, "คุณจะได้รู้ว่า 1 ใน 2 ผู้เล่นที่คุณเลือก เป็นตัวละครสมุนบทหนึ่ง"),
        ("Chef", Alignment.GOOD, CharacterType.TOWNSFOLK, 36, None, "คุณจะได้รู้ว่ามีคู่ผู้เล่นฝั่งร้ายกี่คู่ที่นั่งติดกัน"),
        ("Empath", Alignment.GOOD, CharacterType.TOWNSFOLK, 37, 53, "ในแต่ละคืน คุณจะได้รู้ว่าเพื่อนบ้านที่ยังมีชีวิตอยู่ 2 คนข้างๆ คุณ มีฝั่งร้ายกี่คน"),
        ("Fortune Teller", Alignment.GOOD, CharacterType.TOWNSFOLK, 38, 54, "ในแต่ละคืน เลือกผู้เล่น 2 คน: คุณจะได้รู้ว่ามีใครเป็นปีศาจหรือไม่ (ระวัง! มีผู้เล่นฝั่งดี 1 คนที่จะถูกระบบหลอกว่าเป็นปีศาจ)"),
        ("Undertaker", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 68, "ในแต่ละคืน คุณจะได้รู้ว่าตัวละครที่ถูกประหารชีวิตในวันนี้คือบทอะไร"),
        ("Monk", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 43, "ในแต่ละคืน เลือกผู้เล่น 1 คน (ที่ไม่ใช่ตัวเอง): เขาจะปลอดภัยจากการโจมตีของปีศาจในคืนนี้"),
        ("Ravenkeeper", Alignment.GOOD, CharacterType.TOWNSFOLK, None, 52, "หากคุณตายในตอนกลางคืน คุณจะได้เลือกผู้เล่น 1 คนเพื่อดูบทบาทของเขา"),
        ("Virgin", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "ครั้งแรกที่คุณถูกเสนอชื่อประหารชีวิต หากผู้เสนอชื่อเป็นชาวเมือง เขาจะถูกประหารชีวิตทันทีและจบคืนนั้น"),
        ("Slayer", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "ครั้งหนึ่งต่อเกม ในช่วงกลางวัน คุณสามารถเลือกผู้เล่น 1 คนประกาศต่อสาธารณะ: หากเขาเป็นปีศาจ เขาจะตายทันที"),
        ("Soldier", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "คุณปลอดภัยจากการโจมตีของปีศาจ"),
        ("Mayor", Alignment.GOOD, CharacterType.TOWNSFOLK, None, None, "หากเหลือผู้เล่นเพียง 3 คนและไม่มีการประหารเกิดขึ้น ทีมของคุณชนะทันที หากคุณจะตายในตอนกลางคืน ระบบอาจเลือกให้คนอื่นตายแทน"),
        
        # Outsiders
        ("Butler", Alignment.GOOD, CharacterType.OUTSIDER, 39, 67, "ในแต่ละคืน เลือกผู้เล่น 1 คน (ที่ไม่ใช่ตัวเอง): ในวันถัดไป คุณจะลงคะแนนโหวตได้ก็ต่อเมื่อเขากำลังโหวตอยู่เท่านั้น"),
        ("Drunk", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "คุณจะไม่รู้ว่าตัวเองเป็นคนเมา คุณจะคิดว่าตัวเองเป็นชาวเมืองบทหนึ่ง แต่ความสามารถของคุณจะใช้งานไม่ได้จริง"),
        ("Recluse", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "คุณอาจถูกตรวจพบว่าเป็นฝั่งร้าย หรือเป็นสมุน/ปีศาจได้ แม้ว่าคุณจะตายแล้วก็ตาม"),
        ("Saint", Alignment.GOOD, CharacterType.OUTSIDER, None, None, "หากคุณตายจากการถูกประหารชีวิต ทีมของคุณจะแพ้ทันที"),
        
        # Minions
        ("Poisoner", Alignment.EVIL, CharacterType.MINION, 27, 44, "ในแต่ละคืน เลือกผู้เล่น 1 คน: เขาจะติดพิษในคืนนี้และวันถัดไป (ความสามารถของเขาจะใช้งานไม่ได้)"),
        ("Spy", Alignment.EVIL, CharacterType.MINION, 40, 69, "ในแต่ละคืน คุณจะได้เห็นคัมภีร์ (ข้อมูลทั้งหมด) คุณอาจถูกตรวจพบว่าเป็นฝั่งดี หรือเป็นชาวเมือง/ชาวบ้านนอกได้ แม้ว่าคุณจะตายแล้วก็ตาม"),
        ("Scarlet Woman", Alignment.EVIL, CharacterType.MINION, None, 42, "หากมีผู้เล่นเหลือมากกว่า 5 คนและปีศาจตาย คุณจะกลายเป็นปีศาจแทน"),
        ("Baron", Alignment.EVIL, CharacterType.MINION, None, None, "จะมีตัวละครชาวบ้านนอก (Outsider) เพิ่มเข้ามาในเกมอีก 2 ตัว"),
        
        # Demon
        ("Imp", Alignment.EVIL, CharacterType.DEMON, None, 49, "ในแต่ละคืน เลือกผู้เล่น 1 คนให้ตาย หากคุณเลือกฆ่าตัวเอง สมุนคนหนึ่งจะกลายเป็น Imp แทน"),
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
