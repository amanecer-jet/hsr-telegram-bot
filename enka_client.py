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

def _guess_resource_path(icon_name: str) -> str:
    # Simplified path mapping: search in StarRailRes master icon folders
    return f"icon/relic/{icon_name}.png"


def _parse_character(uid: int, char_json: dict) -> CharacterBuild:
    # This parser is simplified; structure may need adjustments based on actual Enka response
    stats = StatBlock(**{
        "hp": char_json.get("hp", 0),
        "atk": char_json.get("atk", 0),
        "def": char_json.get("def", 0),
        "spd": char_json.get("spd", 0),
        "crit_rate": char_json.get("critRate", 0),
        "crit_dmg": char_json.get("critDmg", 0),
        "effect_hit_rate": char_json.get("effectHit", 0),
        "effect_res": char_json.get("effectRes", 0),
        "break_effect": char_json.get("breakEffect", 0),
    })

    lc_json = char_json.get("lightCone", {})
    light_cone = LightCone(
        id=lc_json.get("id", 0),
        icon_path=_guess_resource_path(lc_json.get("id", "")),
        level=lc_json.get("level", 1),
        superimpose=lc_json.get("superimpose", 1),
    )

    relics_list = []
    for rj in char_json.get("relics", []):
        sub_stats = [
            RelicSubStat(
                id=s.get("id", 0),
                name=s.get("name", ""),
                value=s.get("value", 0),
                is_percent=s.get("isPercent", False),
            )
            for s in rj.get("subStats", [])
        ]
        relics_list.append(
            Relic(
                id=rj.get("id", 0),
                icon_path=_guess_resource_path(rj.get("id", "")),
                main_stat=rj.get("main", {}).get("name", ""),
                main_value=rj.get("main", {}).get("value", 0),
                level=rj.get("level", 0),
                score=rj.get("score", 0),
                sub_stats=sub_stats,
            )
        )

    build = CharacterBuild(
        uid=uid,
        character_id=char_json.get("id", 0),
        name=char_json.get("name", ""),
        element=char_json.get("element", ""),
        path=char_json.get("path", ""),
        level=char_json.get("level", 1),
        eidolon=char_json.get("eidolon", 0),
        stats=stats,
        light_cone=light_cone,
        relics=relics_list,
        portrait_path=_guess_resource_path(char_json.get("id", "")),
    )
    return build


def build_from_profile(json_data: dict, uid: int, character_id: int | None = None) -> CharacterBuild:
    """Return CharacterBuild for first or specified character in profile json."""

    chars = json_data.get("characters") or json_data.get("avatars") or []
    if not chars:
        raise ValueError("No characters found in profile json")

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

    return _parse_character(uid, char_json) 