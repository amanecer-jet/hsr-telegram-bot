import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp
from models import CharacterBuild, StatBlock, LightCone, Relic, RelicSubStat

CACHE_DIR = os.path.join("/tmp", "enka_cache")
CACHE_TTL = timedelta(minutes=30)
BASE_URL = "https://enka.network/api/uid/{uid}"


class EnkaAPIError(Exception):
    """Raised when the Enka API returns an unexpected status."""


async def _ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(uid: int) -> str:
    return os.path.join(CACHE_DIR, f"{uid}.json")


def _is_cache_valid(uid: int) -> bool:
    path = _cache_path(uid)
    if not os.path.exists(path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    return datetime.now() - mtime < CACHE_TTL


def _load_cache(uid: int) -> Dict[str, Any]:
    with open(_cache_path(uid), encoding="utf-8") as f:
        return json.load(f)


def _save_cache(uid: int, data: Dict[str, Any]):
    with open(_cache_path(uid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


async def fetch_profile(uid: int, *, force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch Enka profile JSON for a UID (with 30-minute local cache)."""
    await _ensure_cache_dir()
    if not force_refresh and _is_cache_valid(uid):
        return _load_cache(uid)

    url = BASE_URL.format(uid=uid)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise EnkaAPIError(f"Enka API returned status {resp.status} for UID {uid}")
            data = await resp.json()
            _save_cache(uid, data)
            return data


# Convenience sync wrapper (for unit tests or sync code)

def fetch_profile_sync(uid: int, *, force_refresh: bool = False) -> Dict[str, Any]:
    return asyncio.run(fetch_profile(uid, force_refresh=force_refresh))


# Mapping utils to be implemented

# ---- Load character meta (name/element/path) from StarRailRes ----
_CHAR_META: dict[int, dict] = {}
try:
    with open("StarRailRes-master/index_new/en/characters.json", encoding="utf-8") as f:
        _CHAR_META = json.load(f)
except FileNotFoundError:
    pass

def _guess_resource_path(icon_name: str) -> str:
    # Simplified path mapping: search in StarRailRes master icon folders
    return f"icon/relic/{icon_name}.png"


# Mapping property ID -> our StatBlock field & percentage flag
_PROP_MAP = {
    7: ("hp", False),
    8: ("atk", False),
    9: ("def_", False),
    10: ("spd", False),
    20: ("crit_rate", True),
    22: ("crit_dmg", True),
    23: ("effect_hit_rate", True),
    24: ("effect_res", True),
    27: ("break_effect", True),
}


def _parse_avatar_info(uid: int, av_json: dict) -> CharacterBuild:
    cid = av_json.get("avatarId") or av_json.get("id")
    meta = _CHAR_META.get(str(cid)) or {}

    # Stats
    prop_map = av_json.get("propertyMap", {}) or av_json.get("propMap", {})
    stats_kwargs = {}
    for pid_str, prop in prop_map.items():
        pid = int(pid_str)
        field = _PROP_MAP.get(pid)
        if not field:
            continue
        key, is_pct = field
        val = prop.get("value", 0)
        stats_kwargs[key] = float(val) if is_pct else int(val)

    stats = StatBlock(**stats_kwargs)

    # Light cone
    lc = av_json.get("equipList", [{}])[0]
    light_cone = LightCone(
        id=lc.get("tid", 0),
        icon_path=_guess_resource_path(lc.get("tid", "")),
        level=lc.get("level", 1),
        superimpose=lc.get("superimpose", 1),
    )

    # Relics
    relics_list = []
    for r in av_json.get("relicList", []):
        relics_list.append(
            Relic(
                id=r.get("tid", 0),
                icon_path=_guess_resource_path(r.get("tid", "")),
                main_stat="",
                main_value=0,
                level=r.get("level", 0),
            )
        )

    return CharacterBuild(
        uid=uid,
        character_id=cid,
        name=meta.get("name", str(cid)),
        element=meta.get("element", "Unknown"),
        path=meta.get("path", "Unknown"),
        level=av_json.get("level", 1),
        eidolon=av_json.get("rank", 0),
        stats=stats,
        light_cone=light_cone,
        relics=relics_list,
        portrait_path=_guess_resource_path(cid),
    )


def build_from_profile(json_data: dict, uid: int, character_id: int | None = None) -> CharacterBuild:
    """Return CharacterBuild for first or specified character in profile json."""

    chars = (
        json_data.get("characters")
        or json_data.get("avatars")
        or json_data.get("player", {}).get("avatarInfoList")
        or []
    )

    if character_id is None:
        char_json = chars[0] if isinstance(chars, list) else next(iter(chars.values()))
    else:
        # search by id
        if isinstance(chars, list):
            char_json = next((c for c in chars if c.get("id") == character_id), None)
        else:
            char_json = chars.get(str(character_id)) or chars.get(character_id)
        if char_json is None:
            raise ValueError(f"Character id {character_id} not found")

    # Determine parser by presence of keys
    if "avatarId" in char_json or "propertyMap" in char_json or "propMap" in char_json:
        return _parse_avatar_info(uid, char_json)
    return _parse_character(uid, char_json) 
