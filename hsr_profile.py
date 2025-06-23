import asyncio
from typing import Optional, Dict, Any
from mihomo import MihomoAPI, Language

_api = MihomoAPI(language=Language.RU)

async def _fetch(uid: int) -> Optional[Dict[str, Any]]:
    try:
        data = await _api.fetch_user(uid, replace_icon_name_with_url=False)
        return data.model_dump(by_alias=True)
    except Exception:
        return None

def fetch_profile(uid: int) -> Optional[Dict[str, Any]]:
    """Синхронная обёртка вокруг асинхронного клиента Mihomo."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_fetch(uid)) 