import requests, os, json, time

CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache_profiles")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # seconds

API_PRIORITY = [
    "https://api.mihomo.me/sr_info_parsed/{uid}?lang=ru",
    "https://api.mihomo.me/sr_info_parsed/{uid}?lang=en",
    "https://enka.network/api/hsr/v2/{uid}?lang=ru",
    "https://enka.network/api/hsr/v2/{uid}?lang=en",
]

def _load_cache(uid: int):
    f = os.path.join(CACHE_DIR, f"{uid}.json")
    if os.path.exists(f) and time.time() - os.path.getmtime(f) < CACHE_TTL:
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return None

def _save_cache(uid: int, data: dict):
    f = os.path.join(CACHE_DIR, f"{uid}.json")
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)

def fetch_profile(uid: int):
    cached = _load_cache(uid)
    if cached:
        return cached
    for template in API_PRIORITY:
        url = template.format(uid=uid)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("characters") or data.get("avatars"):
                    _save_cache(uid, data)
                    return data
        except Exception:
            continue
    return None 