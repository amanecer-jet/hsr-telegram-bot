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
        return {"last_updated": None, "characters": []}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_updated": None, "characters": []}

def save_cache(cache: Dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def is_cache_valid(cache: Dict) -> bool:
    if not cache.get("last_updated"):
        return False
    last_updated = datetime.fromisoformat(cache["last_updated"])
    return datetime.now() - last_updated < timedelta(hours=CACHE_TTL_HOURS)

async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Получение HTML страницы"""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            return ""
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def extract_json_data(html: str) -> Dict:
    """Извлечение JSON данных из страницы"""
    soup = BeautifulSoup(html, 'lxml')
    script = soup.find('script', id='__NEXT_DATA__')
    if script:
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            pass
    return {}

def parse_character_data(html: str) -> Dict:
    """Парсинг данных о билде персонажа"""
    soup = BeautifulSoup(html, 'lxml')
    
    # Парсинг JSON данных
    data = extract_json_data(html)
    character_data = data.get('props', {}).get('pageProps', {}).get('character', {})
    
    # Извлечение данных из JSON
    build_data = {
        'light_cones': character_data.get('recommendedLightCones', []),
        'relics': character_data.get('recommendedRelics', []),
        'planar_ornaments': character_data.get('recommendedPlanar', []),
        'main_stats': character_data.get('mainStats', {}),
        'sub_stats': character_data.get('subStats', [])
    }
    
    # Если JSON данных нет или они пустые, парсим HTML
    if not any(build_data.values()):
        build_data.update(parse_html_build_data(soup))
    
    return build_data

def parse_html_build_data(soup: BeautifulSoup) -> Dict:
    """Парсинг данных билда из HTML"""
    build_data = {
        'light_cones': {},
        'relics': {},
        'planar_ornaments': {},
        'main_stats': {},
        'sub_stats': []
    }
    
    # Парсинг световых конусов
    lightcone_section = soup.find('div', class_='lightcone-priorities')
    if lightcone_section:
        for priority_div in lightcone_section.find_all('div', class_='lightcone-priority'):
            rank = priority_div.find('div', class_='heading').text.strip()
            cones = [card.find('div', class_='name').text.strip() for card in priority_div.find_all('div', class_='lightcone-card')]
            build_data['light_cones'][rank] = cones
    
    # Парсинг реликвий
    relics_section = soup.find('div', class_='relic-sets-priorities')
    if relics_section:
        for priority_div in relics_section.find_all('div', class_='relic-sets-priority'):
            rank = priority_div.find('div', class_='heading').text.strip()
            sets = [card.find('div', class_='name').text.strip() for card in priority_div.find_all('div', class_='relics-card')]
            build_data['relics'][rank] = sets
    
    # Парсинг планарных украшений
    planar_section = soup.find('div', class_='planar-ornaments-priorities')
    if planar_section:
        for priority_div in planar_section.find_all('div', class_='planar-ornaments-priority'):
            rank = priority_div.find('div', class_='heading').text.strip()
            sets = [card.find('div', class_='name').text.strip() for card in priority_div.find_all('div', class_='planar-ornaments-card')]
            build_data['planar_ornaments'][rank] = sets
    
    # Парсинг основных характеристик
    main_stats_table = soup.find('table', class_='stat-priority-table')
    if main_stats_table:
        for row in main_stats_table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 2:
                slot = cells[0].text.strip()
                stats = [s.text.strip() for s in cells[1].find_all('div', class_='stat')]
                build_data['main_stats'][slot] = stats
    
    # Парсинг дополнительных характеристик
    sub_stats_table = soup.find('table', class_='sub-stats-priority')
    if sub_stats_table:
        for row in sub_stats_table.find_all('tr')[1:]:
            cell = row.find('td')
            if cell:
                build_data['sub_stats'].append(cell.text.strip())
    
    return build_data

async def fetch_character_list() -> List[Dict]:
    """Получение списка персонажей"""
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, STAR_RAIL_URL)
        if not html:
            return []
            
        data = extract_json_data(html)
        characters = data.get('props', {}).get('pageProps', {}).get('characters', [])
        
        # Если JSON данных нет или они пустые, парсим HTML
        if not characters:
            # fallback на HTML (редко потребуется)
            soup = BeautifulSoup(html, 'lxml')
            character_cards = soup.find_all('div', class_='character-card')
            for card in character_cards:
                name = card.find('div', class_='name').text.strip()
                path = card.find('div', class_='path').text.strip()
                url = card.find('a')['href'] if card.find('a') else ''
                characters.append({'name': name, 'path': path, 'url': url})
        
        return characters

def parse_html_character_list(soup: BeautifulSoup) -> List[Dict]:
    """Парсинг списка персонажей из HTML"""
    characters = []
    character_cards = soup.find_all('div', class_='character-card')
    for card in character_cards:
        name = card.find('div', class_='name').text.strip()
        path = card.find('div', class_='path').text.strip()
        url = card.find('a')['href'] if card.find('a') else ''
        characters.append({
            'name': name,
            'path': path,
            'url': url
        })
    return characters

async def update_cache():
    """Обновление кэша данных"""
    try:
        # Получаем список персонажей
        characters = await fetch_character_list()
        if not characters:
            print("Failed to fetch character list")
            return
            
        # Обновляем данные для каждого персонажа
        async with aiohttp.ClientSession() as session:
            for char in characters:
                print(f"Fetching build for {char['name']}...")
                full_url = f"{BASE_URL}{char['url']}"
                html = await fetch_page(session, full_url)
                if html:
                    build = parse_character_data(html)
                    char['build'] = build
                await asyncio.sleep(1)  # Чтобы не перегружать сайт
        
        # Сохраняем кэш
        cache = {
            'last_updated': datetime.now().isoformat(),
            'characters': characters
        }
        save_cache(cache)
        print("Cache updated successfully")
        
    except Exception as e:
        print(f"Error updating cache: {e}")

def get_elements(cache: Dict) -> List[str]:
    return sorted(set(char['path'] for char in cache.get('characters', [])))

def get_characters_by_element(cache: Dict, element: str) -> List[str]:
    return [char['name'] for char in cache.get('characters', []) if char['path'] == element]
