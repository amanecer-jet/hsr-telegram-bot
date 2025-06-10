from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import os

BASE_URL = "https://www.prydwen.gg"
STAR_RAIL_URL = f"{BASE_URL}/star-rail/characters"
CACHE_FILE = "data/cache.json"
CACHE_TTL_HOURS = 24

async def fetch_html_playwright(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state('networkidle')
        html = await page.content()
        await browser.close()
        return html

def load_cache() -> dict:
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

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print("[parser] Кэш успешно сохранён")
    except Exception as e:
        print(f"[parser] Ошибка при сохранении кэша: {e}")

def is_cache_valid(cache: dict) -> bool:
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

def get_elements(cache: dict) -> list:
    try:
        elements = sorted(set(c.get("element") for c in cache.get("characters", []) if c.get("element")))
        print(f"[parser] Найдено путей: {elements}")
        return elements
    except Exception as e:
        print(f"[parser] Ошибка при получении путей: {e}")
        return []

def get_characters_by_element(cache: dict, element: str) -> list:
    try:
        chars = [c["name"] for c in cache.get("characters", []) if c.get("element") == element]
        print(f"[parser] Для пути {element} найдено персонажей: {chars}")
        return chars
    except Exception as e:
        print(f"[parser] Ошибка при получении персонажей по пути: {e}")
        return []

def get_character_data(cache: dict, name: str) -> dict:
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
    print("[parser] Начинаю обновление кэша через Playwright...")
    try:
        html = await fetch_html_playwright(STAR_RAIL_URL)
        print("[parser] HTML начало:", html[:1000])
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
                char_html = await fetch_html_playwright(link)
                print(f"[parser] HTML персонажа начало {link}:", char_html[:500])
                soup = BeautifulSoup(char_html, "lxml")
                script = soup.find("script", id="__NEXT_DATA__", type="application/json")
                if not script:
                    print(f"[parser] Не найден JSON на странице {link}")
                    continue
                data = json.loads(script.string)
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
