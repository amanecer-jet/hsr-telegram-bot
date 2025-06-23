from PIL import Image, ImageDraw, ImageFont
import os
from typing import Dict
from assets import get_icon

BG = (32, 32, 36, 255)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def _font(sz):
    try:
        return ImageFont.truetype(FONT_PATH, sz)
    except Exception:
        return ImageFont.load_default()

def render_card(profile: Dict, char_idx: int = 0) -> Image.Image:
    chars = profile.get("characters") or profile.get("avatars") or []
    if not chars:
        raise ValueError("no characters")
    if char_idx >= len(chars):
        char_idx = 0
    ch = chars[char_idx]

    W, H = 1024, 768
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    # portrait
    portrait_url = ch.get("preview") or ch.get("icon") or ch.get("portrait")
    portrait = get_icon(portrait_url, (350, 350))
    img.paste(portrait, (20, 20))

    # user/uid stub
    d.rectangle((20, 380, 370, 440), fill=(48,48,52,255))
    d.text((30, 392), f"UID {profile.get('player',{}).get('nickname','User')}", font=_font(24), fill="white")

    # name lvl
    d.text((400, 30), ch.get("name","?"), font=_font(48), fill="white")
    d.text((400, 90), f"Lv. {ch.get('level',1)}/80", font=_font(32), fill="white")

    # cone icon
    lc = ch.get("light_cone") if isinstance(ch.get("light_cone"), dict) else {}
    lc_icon = get_icon(lc.get("icon"), (128,128))
    img.paste(lc_icon, (400,140), lc_icon)
    d.text((540, 140), lc.get("name","-"), font=_font(24), fill=(255,220,150))

    # simple stat list
    base_stats = [("HP", ch.get("hp")),("ATK", ch.get("atk")),("DEF", ch.get("def"))]
    for i,(label,val) in enumerate(base_stats):
        d.text((400, 300+i*28), f"{label}: {val}", font=_font(24), fill="white")

    return img 