import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
from typing import Dict, List
import os

BASE_URL = "https://www.prydwen.gg"
STAR_RAIL_URL = f"{BASE_URL}/star-rail/characters"
CACHE_FILE = "data/cache.json"
CACHE_TTL_HOURS = 24

def load_cache() -> Dict:
    if not os.path.exists(CACHE_FILE):
        print("[parser] Кэш не найден")
        return {"last_updated": None, "characters": []}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            print("[parser] Кэш успешно загружен")
            return json.load(f)
    except Exception as e:
        print(f"[parser] Ошибка при загрузке кэша: {e}")
        return {"last_updated": None, "characters": []}

def save_cache(cache: Dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print("[parser] Кэш успешно сохранён")
    except Exception as e:
        print(f"[parser] Ошибка при сохранении кэша: {e}")

def is_cache_valid(cache: Dict) -> bool:
    try:
        if not cache or not cache.get("last_updated"):
            print("[parser] Кэш невалиден: нет last_updated")
            return False
        last = datetime.fromisoformat(cache["last_updated"])
        valid = datetime.now() - last < timedelta(hours=CACHE_TTL_HOURS)
        print(f"[parser] Кэш валиден: {valid}")
        return valid
    except Exception as e:
        print(f"[parser] Ошибка при проверке валидности кэша: {e}")
        return False

def get_elements(cache: Dict) -> List[str]:
    try:
        elements = sorted(set(c.get("element") for c in cache.get("characters", []) if c.get("element")))
        print(f"[parser] Найдено путей: {elements}")
        return elements
    except Exception as e:
        print(f"[parser] Ошибка при получении путей: {e}")
        return []

def get_characters_by_element(cache: Dict, element: str) -> List[str]:
    try:
        chars = [c["name"] for c in cache.get("characters", []) if c.get("element") == element]
        print(f"[parser] Для пути {element} найдено персонажей: {chars}")
        return chars
    except Exception as e:
        print(f"[parser] Ошибка при получении персонажей по пути: {e}")
        return []

def get_character_data(cache: Dict, name: str) -> Dict:
    try:
        for c in cache.get("characters", []):
            if c.get("name") == name:
                print(f"[parser] Данные для персонажа {name} найдены")
                return c
        print(f"[parser] Данные для персонажа {name} не найдены")
        return {}
    except Exception as e:
        print(f"[parser] Ошибка при получении данных персонажа: {e}")
        return {}

async def update_cache():
    print("[parser] Начинаю обновление кэша...")
    try:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(STAR_RAIL_URL) as resp:
                    print(f"[parser] Ответ от {STAR_RAIL_URL}: {resp.status}")
                    if resp.status != 200:
                        print(f"[parser] Ошибка HTTP: {resp.status}")
                        return
                    html = await resp.text()
            except Exception as e:
                print(f"[parser] Ошибка при запросе к {STAR_RAIL_URL}: {e}")
                return
            soup = BeautifulSoup(html, "lxml")
            char_links = []
            for a in soup.select("a[href^='/star-rail/characters/']"):
                href = a.get("href")
                if href and href.count("/") == 4:
                    char_links.append(BASE_URL + href)
            char_links = list(set(char_links))
            print(f"[parser] Найдено ссылок на персонажей: {len(char_links)}")
            characters = []
            for link in char_links:
                try:
                    async with session.get(link) as resp:
                        print(f"[parser] Ответ от {link}: {resp.status}")
                        if resp.status != 200:
                            print(f"[parser] Ошибка HTTP для {link}: {resp.status}")
                            continue
                        html = await resp.text()
                    soup = BeautifulSoup(html, "lxml")
                    script = soup.find("script", id="__NEXT_DATA__", type="application/json")
                    if not script:
                        print(f"[parser] Не найден JSON на странице {link}")
                        continue
                    data = json.loads(script.string)
                    # Здесь нужно адаптировать под реальную структуру JSON prydwen.gg
                    # Пример:
                    char_data = {
                        "name": data.get("props", {}).get("pageProps", {}).get("character", {}).get("name", "Unknown"),
                        "element": data.get("props", {}).get("pageProps", {}).get("character", {}).get("element", "Unknown"),
                        "relics": data.get("props", {}).get("pageProps", {}).get("character", {}).get("relics", []),
                        "planar": data.get("props", {}).get("pageProps", {}).get("character", {}).get("planarOrnaments", []),
                        "cones": data.get("props", {}).get("pageProps", {}).get("character", {}).get("lightCones", []),
                        "main_stats": data.get("props", {}).get("pageProps", {}).get("character", {}).get("mainStats", []),
                        "sub_stats": data.get("props", {}).get("pageProps", {}).get("character", {}).get("subStats", []),
                    }
                    print(f"[parser] Добавлен персонаж: {char_data['name']}")
                    characters.append(char_data)
                except Exception as e:
                    print(f"[parser] Ошибка при парсинге {link}: {e}")
            cache = {
                "last_updated": datetime.now().isoformat(),
                "characters": characters
            }
            save_cache(cache)
            print("[parser] Кэш обновлён, персонажей сохранено:", len(characters))
    except Exception as e:
        print(f"[parser] Критическая ошибка при обновлении кэша: {e}")
