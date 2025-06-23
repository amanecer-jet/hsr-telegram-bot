from PIL import Image, ImageDraw, ImageFont
import textwrap
from typing import Dict, Tuple
import os

# --- Настройки ---
CARD_WIDTH = 800
CARD_HEIGHT = 450
BG_COLOR = (28, 28, 30, 255)
FONT_PATH = os.getenv("HBB_FONT_PATH", "C:\\Windows\\Fonts\\arial.ttf")  # Можно переопределить переменной окружения

# Позиции и стили для полей (ключ билда, размер шрифта, координаты, цвет)
FIELDS = [
    ("title", 36, (250, 20), (255, 255, 255)),
    ("level", 24, (250, 70), (200, 200, 200)),
    ("light_cone", 24, (250, 110), (255, 220, 120)),
    ("relics", 22, (250, 160), (120, 200, 255)),
    ("stats", 22, (250, 260), (180, 255, 180)),
]

# --- Вспомогательные функции ---

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def draw_multiline(draw: ImageDraw.ImageDraw, text: str, pos: Tuple[int, int], font: ImageFont.FreeTypeFont, color: Tuple[int, int, int], max_width: int):
    """Рисует текст с автоматическим переносом по словам."""
    if not text:
        return
    lines = []
    for paragraph in text.split("\n"):
        line = []
        for word in paragraph.split():
            test_line = " ".join(line + [word])
            if draw.textbbox((0, 0), test_line, font=font)[2] - pos[0] > max_width:
                lines.append(" ".join(line))
                line = [word]
            else:
                line.append(word)
        lines.append(" ".join(line))
    y_offset = 0
    for ln in lines:
        draw.text((pos[0], pos[1] + y_offset), ln, font=font, fill=color)
        y_offset += font.getsize("A")[1] + 4

# --- Основная функция ---

def generate_card(build: Dict, art_path: str) -> Image.Image:
    """Создаёт изображение карточки из данных билда.

    build: {
      title: str,
      level: str,
      light_cone: str,
      relics: str,
      stats: str,
    }
    art_path: путь к картинке персонажа
    """
    card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(card)

    # --- портрет персонажа ---
    try:
        art = Image.open(art_path).convert("RGBA")
        art = art.resize((220, 400), Image.LANCZOS)
        card.paste(art, (10, 20), art)
    except FileNotFoundError:
        # Если изображения нет – рисуем заглушку
        draw.rectangle((10, 20, 230, 420), fill=(60, 60, 60))
        draw.text((40, 210), "No\nImage", font=_get_font(20), fill=(255, 255, 255))

    # --- текстовые поля ---
    for field, size, pos, color in FIELDS:
        value = build.get(field)
        if not value:
            continue
        font = _get_font(size)
        draw_multiline(draw, str(value), pos, font, color, CARD_WIDTH - pos[0] - 20)

    return card

# --- Тестовый запуск ---
if __name__ == "__main__":
    sample_build = {
        "title": "Ахерон",
        "level": "Ур. 80, Эйдолон 0/6",
        "light_cone": "Песнь Двадцати, R1",
        "relics": "4× Музыкальные Чары, 2× Пространство",
        "stats": "АТК 3600 • СКР 150 • КРИТШ 70/140",
    }
    img = generate_card(sample_build, "StarRailRes-master/image/character_preview/8002.png")
    img.save("sample_card.png")
    print("Создан sample_card.png") 