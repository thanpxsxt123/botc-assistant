from gtts import gTTS
import os
from datetime import datetime

class ThaiNarrator:
    def __init__(self, output_dir: str = "assets/narration"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate_speech(self, text: str, filename: str = None):
        if not filename:
            filename = f"narr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        
        filepath = os.path.join(self.output_dir, filename)
        tts = gTTS(text=text, lang='th')
        tts.save(filepath)
        return filepath

    def announce_night_start(self, night_num: int):
        text = f"ทุกคนหลับตาลง คืนที่ {night_num} ได้เริ่มขึ้นแล้ว"
        return self.generate_speech(text, f"night_start_{night_num}.mp3")

    def announce_execution(self, player_name: str):
        if player_name:
            text = f"ผลการโหวตเป็นเอกฉันท์ {player_name} ถูกประหารชีวิต"
        else:
            text = "ไม่มีใครถูกประหารชีวิตในวันนี้"
        return self.generate_speech(text)

    def announce_death(self, player_names: list):
        if not player_names:
            text = "เมื่อคืนนี้ไม่มีใครตาย ทุกคนยังอยู่ครบ"
        else:
            names = " และ ".join(player_names)
            text = f"เช้าวันนี้เราพบร่างของ {names} เสียชีวิตลง"
        return self.generate_speech(text)
