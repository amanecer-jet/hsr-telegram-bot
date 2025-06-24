import os
import shutil
from pathlib import Path

FONT_NAMES = ["FirstWorld.ttf", "ChimeraNumber.ttf"]
SRC_FONT_DIR = Path("StarRailRes-master") / "font"
DST_FONT_DIR = Path("assets") / "fonts"


def ensure_assets():
    DST_FONT_DIR.mkdir(parents=True, exist_ok=True)

    for fname in FONT_NAMES:
        src = SRC_FONT_DIR / fname
        dst = DST_FONT_DIR / fname
        if not src.exists():
            print(f"[prepare_assets] source font not found: {src}")
            continue
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"[prepare_assets] copied {fname} → assets/fonts/")
        else:
            print(f"[prepare_assets] {fname} already exists, skip")


if __name__ == "__main__":
    ensure_assets() 