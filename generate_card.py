from PIL import Image, ImageDraw, ImageFont
import textwrap
from typing import Dict, Tuple
import os
import requests
from io import BytesIO

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
            test_width = draw.textbbox((0, 0), test_line, font=font)[2]
            if test_width > max_width:
                lines.append(" ".join(line))
                line = [word]
            else:
                line.append(word)
        lines.append(" ".join(line))
    # Высота строки через метрики шрифта
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + 4  # дополнительный отступ 4 px
    y_offset = 0
    for ln in lines:
        draw.text((pos[0], pos[1] + y_offset), ln, font=font, fill=color)
        y_offset += line_height

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

# --- Новая продвинутая функция карточки профиля ---
STAT_MAP_RU = {
    "hp": "HP",
    "atk": "АТК",
    "def": "DEF",
    "speed": "Скорость",
    "crit_rate": "КРИТ%",
    "crit_dmg": "КРИТ УР%",
    "break_effect": "Break%",
    "energy_regen": "ER%",
    "effect_hit": "Эфф. шанс%",
    "effect_res": "Эфф. сопр%",
}

RELIC_ORDER = [1, 2, 3, 4, 5, 6]  # позиция согласно Mihomo


def _download_image(url: str, size: Tuple[int, int] | None = None) -> Image.Image:
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:
        # fallback заглушка
        ph = Image.new("RGBA", size or (80, 80), (60, 60, 60, 255))
        return ph


def generate_profile_card(profile: Dict, uid: str) -> Image.Image:
    """Создаёт «полную» карточку персонажа на основе Mihomo profile dict."""
    if not profile.get("characters"):
        raise ValueError("profile missing characters")
    ch = profile["characters"][0]

    # --- Размеры макета ---
    width = 1000
    height = 600
    bg = Image.new("RGBA", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(bg)

    # --- Портрет персонажа ---
    portrait_url = ch.get("preview") or ch.get("portrait") or ch.get("icon")
    portrait = _download_image(portrait_url, (300, 450))
    bg.paste(portrait, (20, 80), portrait)

    # --- Имя + уровень ---
    name_font = _get_font(48)
    level_font = _get_font(28)
    name_text = ch.get("name", "Персонаж")
    draw.text((350, 30), name_text, font=name_font, fill=(255, 255, 255))
    lvl = ch.get("level", 1)
    draw.text((350, 90), f"Ур. {lvl}", font=level_font, fill=(200, 200, 200))

    # --- UID & ник ---
    player = profile.get("player", {})
    nickname = player.get("nickname", "Игрок")
    draw.text((350, 130), f"UID {uid} — {nickname}", font=_get_font(24), fill=(180, 180, 180))

    # --- Световой конус ---
    lc = ch.get("light_cone", {})
    if isinstance(lc, dict):
        lc_name = lc.get("name", "-")
        lc_level = lc.get("level", 1)
        lc_rank = lc.get("rank", 1)
        draw.text((350, 180), f"Свет. конус: {lc_name} (Ур.{lc_level} R{lc_rank})", font=_get_font(26), fill=(255, 220, 120))
        if lc.get("icon"):
            lc_icon = _download_image(lc["icon"], (120, 120))
            bg.paste(lc_icon, (850, 30), lc_icon)

    # --- Основные характеристики ---
    stats_block_x = 350
    stats_block_y = 230
    stats_font = _get_font(24)
    attrs = ch.get("attributes") or ch.get("properties") or []
    if isinstance(attrs, dict):
        attrs = [
            {"field": k, "value": v.get("value") if isinstance(v, dict) else v}
            for k, v in attrs.items()
        ]
    shown = 0
    for item in attrs:
        key = item.get("field") or item.get("type") or item.get("name")
        val = item.get("display") or item.get("value")
        if key is None or val is None:
            continue
        # normalize key
        key_norm = str(key).lower().replace("_", "")
        for k in STAT_MAP_RU.keys():
            if k.replace("_", "") in key_norm:
                ru = STAT_MAP_RU[k]
                draw.text((stats_block_x, stats_block_y + shown * 32), f"{ru}: {val}", font=stats_font, fill=(180, 255, 180))
                shown += 1
                if shown >= 6:
                    break
        if shown >= 6:
            break

    # --- Реликвии ---
    relics = ch.get("relics", [])
    relic_size = (90, 90)
    start_x = 350
    start_y = height - relic_size[1] - 30
    gap = 10
    # сортируем по позиции
    relic_map = {r.get("position", r.get("pos", 0)): r for r in relics}
    for idx, pos in enumerate(RELIC_ORDER):
        relic = relic_map.get(pos)
        x = start_x + idx * (relic_size[0] + gap)
        if relic and relic.get("icon"):
            icon = _download_image(relic["icon"], relic_size)
            bg.paste(icon, (x, start_y), icon)
            # уровень +xx
            lvl = relic.get("level", 0)
            lvl_font = _get_font(18)
            draw.rectangle((x, start_y + relic_size[1] - 24, x + relic_size[0], start_y + relic_size[1]), fill=(0, 0, 0, 160))
            draw.text((x + 4, start_y + relic_size[1] - 22), f"+{lvl}", font=lvl_font, fill=(255, 255, 255))
        else:
            # пустая ячейка
            draw.rectangle((x, start_y, x + relic_size[0], start_y + relic_size[1]), outline=(120, 120, 120))

    return bg 