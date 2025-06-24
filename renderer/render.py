from io import BytesIO
from typing import Dict, Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .layout import PanelSizes, ThemeColors
import os
from functools import lru_cache


FONT_PATH_PRIMARY = "assets/fonts/FirstWorld.ttf"
FONT_PATH_NUMBERS = "assets/fonts/ChimeraNumber.ttf"

# Mapping build key names -> (display label, icon filename, is_percent)
STAT_META = {
    "hp": ("HP", "IconMaxHP.webp", False),
    "atk": ("ATK", "IconAttack.webp", False),
    "def_": ("DEF", "IconDefence.webp", False),
    "spd": ("SPD", "IconSpeed.webp", False),
    "crit_rate": ("CRIT Rate", "IconCriticalChance.webp", True),
    "crit_dmg": ("CRIT DMG", "IconCriticalDamage.webp", True),
    "effect_hit_rate": ("Effect Hit Rate", "IconStatusProbability.webp", True),
    "effect_res": ("Effect RES", "IconStatusResistance.webp", True),
    "break_effect": ("Break Effect", "IconBreakUp.webp", True),
}

ICON_DIR = "hsr-optimizer-main/public/assets/icon/property"

# Relic icon directory guess
RELIC_ICON_DIR = "StarRailRes-master/image/relic"

ELEMENT_ICON_DIR = "hsr-optimizer-main/public/assets/icon/element"
PATH_ICON_DIR = "hsr-optimizer-main/public/assets/icon/path"


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        # fallback to default
        return ImageFont.load_default()


@lru_cache(maxsize=64)
def _load_icon(name: str, size: int) -> Image.Image:
    path = os.path.join(ICON_DIR, name)
    try:
        img = Image.open(path).convert("RGBA")
        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        return Image.new("RGBA", (size, size), (255, 0, 0, 0))


@lru_cache(maxsize=32)
def _load_generic_icon(dir_path: str, name: str, size: int) -> Image.Image:
    path = os.path.join(dir_path, name)
    if not os.path.exists(path):
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    try:
        return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def render_card(character_build: Dict[str, Any], *, theme: str = "optimizer-purple") -> bytes:
    """Render PNG card for a single character build.

    Parameters
    ----------
    character_build : dict
        Normalised build data combining Enka stats and local resources.
    theme : str
        Currently only one theme supported.
    Returns
    -------
    bytes
        PNG image bytes.
    """

    size_cfg = PanelSizes()
    colors = ThemeColors()

    # Base canvas
    canvas = Image.new("RGBA", (size_cfg.CANVAS_W, size_cfg.CANVAS_H))
    draw = ImageDraw.Draw(canvas)

    # Background gradient
    for y in range(size_cfg.CANVAS_H):
        ratio = y / size_cfg.CANVAS_H
        r = int(colors.bg_gradient_top[0] * (1 - ratio) + colors.bg_gradient_bottom[0] * ratio)
        g = int(colors.bg_gradient_top[1] * (1 - ratio) + colors.bg_gradient_bottom[1] * ratio)
        b = int(colors.bg_gradient_top[2] * (1 - ratio) + colors.bg_gradient_bottom[2] * ratio)
        draw.line([(0, y), (size_cfg.CANVAS_W, y)], fill=(r, g, b))

    # Draw semi-transparent panels (stats column + 6 relic tiles)
    def rounded_rectangle(draw_ctx: ImageDraw.ImageDraw, xy, radius, fill, outline=None, width=2):
        x0, y0, x1, y1 = xy
        draw_ctx.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

    # Coordinates
    art_x0 = 0
    art_y0 = 0

    stats_x0 = size_cfg.ART_W + 20  # small gap
    relics_x0 = stats_x0 + size_cfg.STATS_W + 20

    # Panel backgrounds
    rounded_rectangle(
        draw,
        (stats_x0, 40, stats_x0 + size_cfg.STATS_W, size_cfg.CANVAS_H - 40),
        radius=25,
        fill=colors.panel_bg,
        outline=colors.panel_border,
        width=4,
    )

    # Grid for relics: two columns, three rows
    relic_pad = 20
    tile_w = size_cfg.RELIC_W
    for idx in range(6):
        col = idx % 2
        row = idx // 2
        x = relics_x0 + col * (tile_w + relic_pad)
        y = 40 + row * (tile_w + relic_pad)
        rounded_rectangle(
            draw,
            (x, y, x + tile_w, y + tile_w),
            radius=20,
            fill=colors.panel_bg,
            outline=colors.panel_border,
            width=3,
        )

    # --- Draw portrait ---
    portrait_path = character_build.get("portrait_path")
    if portrait_path and os.path.exists(portrait_path):
        try:
            art_img = Image.open(portrait_path).convert("RGBA")
            art_resized = ImageOps.fit(art_img, (size_cfg.ART_W, size_cfg.CANVAS_H), method=Image.LANCZOS)
            canvas.alpha_composite(art_resized, (0, 0))
        except Exception:
            pass

    # --- Text: character name, level, eidolon, etc. ---
    font_name = _load_font(FONT_PATH_PRIMARY, 64)
    font_stats = _load_font(FONT_PATH_PRIMARY, 32)
    font_value = _load_font(FONT_PATH_NUMBERS, 32)
    font_small = _load_font(FONT_PATH_PRIMARY, 26)
    font_score = _load_font(FONT_PATH_PRIMARY, 30)

    name_text = character_build.get("name", "Unknown")
    level = character_build.get("level", 1)
    eidolon = character_build.get("eidolon", 0)

    text_x = stats_x0 + 40
    text_y = 70
    draw.text((text_x, text_y), name_text, font=font_name, fill=colors.text_primary)

    # Element icon
    elem_icon = _load_generic_icon(ELEMENT_ICON_DIR, f"{character_build.get('element','None').title()}.webp", 48)
    canvas.alpha_composite(elem_icon, (text_x, text_y - 10))

    draw.text((text_x + 60, text_y + 4), name_text, font=font_name, fill=colors.text_primary)

    # Stars (rarity) — assume 5
    star_color = (255, 215, 0)
    star_y = text_y + 80
    star_x0 = text_x
    for i_star in range(5):
        cx = star_x0 + i_star * 36
        cy = star_y
        draw.regular_polygon((cx, cy, 14), n_sides=5, fill=star_color)

    draw.text((text_x, text_y + 120), f"Lv{level} E{eidolon}", font=font_stats, fill=colors.text_secondary)

    # Path icon under stars
    path_name = character_build.get('path', 'None').title()
    path_icon = _load_generic_icon(PATH_ICON_DIR, f"{path_name}.webp", 48)
    canvas.alpha_composite(path_icon, (text_x, text_y + 160))

    # --- Stat list ---
    stats_block = character_build.get("stats", {})
    stat_start_y = text_y + 220
    line_h = 48
    icon_size = 32
    i = 0
    for key, (label, icon_file, is_pct) in STAT_META.items():
        val = stats_block.get(key)
        if val is None:
            continue
        y = stat_start_y + i * line_h
        icon_img = _load_icon(icon_file, icon_size)
        canvas.alpha_composite(icon_img, (text_x, y))

        val_str = f"{val:.1f}%" if is_pct else f"{int(val)}"
        draw.text((text_x + icon_size + 12, y), val_str, font=font_value, fill=colors.text_primary)
        i += 1

    # --- Relic tiles ---
    relics = character_build.get("relics", [])

    def _load_relic_icon(relic_id: int, size: int) -> Image.Image:
        fname = f"{relic_id}.png"
        path = os.path.join(RELIC_ICON_DIR, fname)
        if os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
            except Exception:
                pass
        return Image.new("RGBA", (size, size), (80, 80, 80, 255))

    relic_tile_positions = []
    for idx in range(6):
        col = idx % 2
        row = idx // 2
        x = relics_x0 + col * (tile_w + relic_pad)
        y = 40 + row * (tile_w + relic_pad)
        relic_tile_positions.append((x, y))

    for idx, relic in enumerate(relics[:6]):
        x, y = relic_tile_positions[idx]
        icon_size = 220
        icon_img = _load_relic_icon(relic.get("id", 0), icon_size)
        icon_x = x + (tile_w - icon_size) // 2
        icon_y = y + 20
        canvas.alpha_composite(icon_img, (icon_x, icon_y))

        # Level badge
        lvl = relic.get("level", 0)
        lvl_text = f"+{lvl}"
        bbox = draw.textbbox((0, 0), lvl_text, font=font_small)
        badge_w = bbox[2] - bbox[0]
        badge_h = bbox[3] - bbox[1]
        badge_x = icon_x + icon_size - badge_w - 8
        badge_y = icon_y + 8
        draw.rectangle((badge_x - 4, badge_y - 2, badge_x + badge_w + 4, badge_y + badge_h + 2),
                       fill=(30, 30, 30, 200))
        draw.text((badge_x, badge_y), lvl_text, font=font_small, fill=colors.text_primary)

        # Main stat
        main_stat = relic.get("main_stat", "")
        main_val = relic.get("main_value", 0)
        main_text = f"{main_stat}: {main_val:.1f}%" if "%" in str(main_stat) or main_stat.endswith("%") else f"{main_stat}: {int(main_val)}"
        draw.text((x + 20, icon_y + icon_size + 10), main_text, font=font_small, fill=colors.text_primary)

        # Sub-stats (up to 4)
        sub_start_y = icon_y + icon_size + 50
        sub_icon_size = 28
        for s_idx, sub in enumerate(relic.get("sub_stats", [])[:4]):
            sy = sub_start_y + s_idx * 34
            sub_name = sub.get("name", "")
            sub_val = sub.get("value", 0)
            percent = sub.get("is_percent", False)
            # try load icon by mapping name→file (fallback generic icon)
            icon_file = STAT_META.get(sub_name.lower().replace(" ", "_"), (None, None, False))[1]
            if icon_file:
                sub_icon = _load_icon(icon_file, sub_icon_size)
                canvas.alpha_composite(sub_icon, (x + 20, sy))
            val_str = f"{sub_val:.1f}%" if percent else f"{int(sub_val)}"
            draw.text((x + 20 + sub_icon_size + 8, sy), val_str, font=font_small, fill=colors.text_secondary)

        # Score bottom
        score = relic.get("score", 0)
        score_text = f"Score  {score:.1f}"
        sw, sh = draw.textbbox((0, 0), score_text, font=font_score)[2:]
        draw.text((x + tile_w - sw - 20, y + tile_w - sh - 20), score_text, font=font_score, fill=colors.text_secondary)

    # Downscale 2x for crisp image
    canvas_small = canvas.resize((size_cfg.CANVAS_W // 2, size_cfg.CANVAS_H // 2), Image.LANCZOS)

    bio = BytesIO()
    canvas_small.save(bio, format="PNG", optimize=True)
    return bio.getvalue() 