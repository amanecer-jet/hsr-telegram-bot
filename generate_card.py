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

# Попытаемся найти шрифт с поддержкой кириллицы/китайского
DEFAULT_FONT_CANDIDATES = [
    os.getenv("HBB_FONT_PATH"),
    "C:\\Windows\\Fonts\\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
]


def _choose_font_path() -> str:
    for p in DEFAULT_FONT_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    # fallback: Pillow default
    return ""


FONT_PATH = _choose_font_path()

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
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    # last resort
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

BASE_ASSETS_URL = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/"


def _resolve_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    # Убираем ведущие / если есть
    path = path.lstrip("/")
    return BASE_ASSETS_URL + path


def _download_image(path_or_url: str, size: Tuple[int, int] | None = None) -> Image.Image:
    if not path_or_url:
        return Image.new("RGBA", size or (80, 80), (60, 60, 60, 255))
    # локальный файл?
    if os.path.isfile(path_or_url):
        try:
            img = Image.open(path_or_url).convert("RGBA")
            if size:
                img = img.resize(size, Image.LANCZOS)
            return img
        except Exception:
            pass
    url = _resolve_url(path_or_url)
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:
        # fallback заглушка
        return Image.new("RGBA", size or (80, 80), (60, 60, 60, 255))


def generate_profile_card(profile: Dict, uid: str, char_idx: int = 0) -> Image.Image:
    """Создаёт карточку в стиле RailCard.

    Размер полотна 842×742 (как пример в README railcard). Используются простые прямоугольники вместо svg.
    Рендеруется: портрет, имя/уровень, UID, конус, 8 статов, 6 реликтов c +lvl.
    """
    if not profile.get("characters"):
        raise ValueError("profile missing characters")
    characters = profile["characters"]
    if char_idx >= len(characters):
        char_idx = 0
    ch = characters[char_idx]

    W, H = 842, 742
    canvas = Image.new("RGBA", (W, H), BG_COLOR)
    d = ImageDraw.Draw(canvas)

    # --- Секции ---
    LEFT_W = 350
    d.rectangle((0, 0, LEFT_W, H), fill=(24, 24, 26, 255))
    d.rectangle((LEFT_W, 0, W, H), fill=(36, 36, 40, 255))

    # --- Портрет  --
    # Предпочитаем square preview, затем icon, затем портрет (может быть вертикальным)
    port_url = ch.get("preview") or ch.get("icon") or ch.get("portrait")
    portrait = _download_image(port_url, (LEFT_W-20, LEFT_W-20))
    canvas.paste(portrait, (10, 10))

    # --- USER/UID блок под портретом ---
    player = profile.get("player", {})
    nickname = player.get("nickname", "Player")
    box_y = LEFT_W + 20
    d.rectangle((10, box_y, LEFT_W-10, box_y+60), fill=(40, 40, 45, 255))
    d.text((20, box_y+8), f"USER: {nickname}", font=_get_font(22), fill=(255, 255, 255))
    d.text((20, box_y+32), f"UID: {uid}", font=_get_font(22), fill=(200, 200, 200))

    # --- Имя + уровень сверху справа ---
    name_font = _get_font(44)
    level_font = _get_font(28)
    d.text((LEFT_W + 20, 10), ch.get("name", "Char"), font=name_font, fill=(255, 255, 255))
    d.text((LEFT_W + 20, 60), f"Lv. {ch.get('level', 1)}/80", font=level_font, fill=(200, 200, 200))

    # --- Конус ---
    lc = ch.get("light_cone", {}) if isinstance(ch.get("light_cone"), dict) else {}
    lc_icon = _download_image(lc.get("icon"), (140, 180)) if lc else None
    if lc_icon:
        canvas.paste(lc_icon, (LEFT_W + 20, 110), lc_icon)
    lc_txt = lc.get("name", "-")
    lc_lvl = lc.get("level", 1)
    lc_rank = lc.get("rank", 1)
    lc_line = f"{lc_txt}  S{lc_rank}  Lv. {lc_lvl}/80"
    d.text((LEFT_W + 180, 110), lc_line, font=_get_font(24), fill=(255, 220, 120))

    # small base stats from cone if available
    base_stats = [("HP", lc.get("hp")), ("ATK", lc.get("atk")), ("DEF", lc.get("def"))]
    for i, (label, val) in enumerate(base_stats):
        if not val:
            continue
        d.text((LEFT_W + 180, 140 + i*26), f"{label} {val}", font=_get_font(22), fill=(220, 220, 220))

    # --- Таблица статов персонажа ---
    attrs = ch.get("attributes") or ch.get("properties") or {}
    if isinstance(attrs, list):
        raw_pairs = [(item.get("field") or item.get("type") or item.get("name"), item.get("display") or item.get("value")) for item in attrs]
    else:
        raw_pairs = [(k, (v.get("display") if isinstance(v, dict) else v)) for k, v in attrs.items()]

    attr_map_norm = {str(k).lower().replace("_", "").replace(" ", ""): v for k, v in raw_pairs if k}

    stat_order = [
        ("hp", "HP"),
        ("atk", "ATK"),
        ("def", "DEF"),
        ("speed", "SPD"),
        ("crit_rate", "CRIT Rate"),
        ("crit_dmg", "CRIT DMG"),
        ("break_effect", "Break Effect"),
        ("energy_regen", "ERR"),
    ]
    table_x = LEFT_W + 20
    table_y = 310
    cell_h = 30
    for idx, (field, label) in enumerate(stat_order):
        key_norm = field.replace("_", "").lower()
        val = attr_map_norm.get(key_norm) or "-"
        d.text((table_x, table_y + idx*cell_h), f"{label}", font=_get_font(24), fill=(255, 255, 255))
        d.text((table_x+200, table_y + idx*cell_h), str(val), font=_get_font(24), fill=(255, 255, 255))

    # --- Реликты ---
    relics = ch.get("relics", [])
    slot_x = LEFT_W + 20
    slot_y = 580
    size = 100
    gap = 10
    for idx in range(6):
        x = slot_x + idx*(size+gap)
        d.rectangle((x, slot_y, x+size, slot_y+size), outline=(80, 80, 80))
    for relic in relics:
        pos = relic.get("position", relic.get("pos", 0)) - 1  # 0-index
        if 0 <= pos < 6:
            icon = _download_image(relic.get("icon"), (size, size))
            x = slot_x + pos*(size+gap)
            canvas.paste(icon, (x, slot_y), icon)
            # +lvl overlay
            lvl = relic.get("level", 0)
            d.rectangle((x, slot_y+size-22, x+size, slot_y+size), fill=(0,0,0,160))
            d.text((x+4, slot_y+size-22), f"+{lvl}", font=_get_font(20), fill=(255,255,255))

    return canvas 