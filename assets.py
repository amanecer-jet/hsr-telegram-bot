import os, requests
from PIL import Image
from io import BytesIO
from functools import lru_cache

CDN = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache_assets")
os.makedirs(CACHE_DIR, exist_ok=True)

@lru_cache(maxsize=512)
def get_icon(path: str, size=None) -> Image.Image:
    """Load icon from local cache or download from CDN. path can be http url or relative asset path."""
    if not path:
        return Image.new("RGBA", size or (64, 64), (60, 60, 60, 255))
    if path.startswith("http"):
        url = path
    else:
        url = CDN + path.lstrip("/")
    fname = os.path.join(CACHE_DIR, path.replace("/", "_"))
    if os.path.exists(fname):
        img = Image.open(fname).convert("RGBA")
    else:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            img.save(fname)
        except Exception:
            img = Image.new("RGBA", size or (64, 64), (60, 60, 60, 255))
    if size:
        img = img.resize(size, Image.LANCZOS)
    return img 