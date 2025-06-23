import requests
from typing import Optional, Dict, Any


def fetch_profile(uid: int) -> Optional[Dict[str, Any]]:
    """Получить JSON-ответ Mihomo API как словарь."""
    url = f"https://api.mihomo.me/sr_info_parsed/{uid}?lang=ru"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None 