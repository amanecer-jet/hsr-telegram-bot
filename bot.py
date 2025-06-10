import os
import glob
import json
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.utils.text_decorations import MarkdownDecoration
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp
from bs4 import BeautifulSoup
from config import ParsingConfig

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

SUBSCRIBERS_FILE = "data/subscribers.json"
SPAM_FILE = "data/antispam.json"
CACHE_FILE = "data/cache.json"
CACHE_TTL_DAYS = 10

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="MarkdownV2"))
dp = Dispatcher(storage=MemoryStorage())

md = MarkdownDecoration()

# --- FSM States ---
class BuildStates(StatesGroup):
    choose_game = State()
    choose_element = State()
    choose_character = State()

# --- Кнопки ---
GAMES = ["Honkai: Star Rail"]
ELEMENTS = ["Огонь", "Лёд", "Ветер", "Квант", "Физика", "Мнимость", "Электро"]
# Примерные персонажи, потом будет динамически
CHARACTERS = {
    "Огонь": ["Аста", "Химеко", "Марч 7th"],
    "Лёд": ["Гепард", "Пела", "Яньцин"],
    # ... остальные элементы
}

CHARACTER_LIST_URL = "https://game8.co/games/Honkai-Star-Rail/archives/404256"

# --- Эмодзи для элементов ---
ELEMENT_EMOJI = {
    "Fire": "🔥",
    "Ice": "❄️",
    "Wind": "🌪️",
    "Quantum": "⚛️",
    "Physical": "💪",
    "Imaginary": "🌈",
    "Lightning": "⚡"
}

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def get_latest_build_file():
    files = glob.glob("data/builds_*.json")
    if not files:
        return None
    return max(files, key=os.path.getctime)

def format_build(build):
    name = md.quote(build.get("name", ""))
    build_type = md.quote(build.get("build_type", ""))
    weapon = md.quote(build.get("weapon", ""))
    artifacts = build.get("artifacts", {})
    art_str = "\n".join([f"*{md.quote(k)}*: {md.quote(v)}" for k, v in artifacts.items()])
    return (
        f"*{name}*\n"
        f"_{build_type}_\n"
        f"*Оружие*: {weapon}\n"
        f"*Артефакты*:\n{art_str}\n"
        "----------------------"
    )

def make_keyboard(options, add_back=False):
    keyboard = [[KeyboardButton(text=o)] for o in options]
    if add_back:
        keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- Динамические кнопки из кэша ---
def get_elements_from_cache():
    cache = load_cache()
    return list(cache.get("elements", {}).keys())

def get_characters_from_cache(element):
    cache = load_cache()
    return cache.get("elements", {}).get(element, [])

# --- FSM-диалог с динамическими кнопками и кнопкой 'Назад' ---
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(md.quote("Привет! Для какой игры тебе нужна сборка?"), reply_markup=make_keyboard(GAMES))
    await state.set_state(BuildStates.choose_game)

@dp.message(BuildStates.choose_game)
async def choose_game(message: Message, state: FSMContext):
    if message.text not in GAMES:
        await message.answer(md.quote("Пожалуйста, выбери игру с помощью кнопки."), reply_markup=make_keyboard(GAMES))
        return
    await state.update_data(game=message.text)
    elements = get_elements_from_cache()
    # Добавляем эмодзи к элементам
    elements_with_emoji = [f"{ELEMENT_EMOJI.get(e, '')} {e}".strip() for e in elements]
    await message.answer(md.quote("Выбери элемент персонажа:"), reply_markup=make_keyboard(elements_with_emoji, add_back=True))
    await state.set_state(BuildStates.choose_element)

@dp.message(BuildStates.choose_element)
async def choose_element(message: Message, state: FSMContext):
    elements = get_elements_from_cache()
    elements_with_emoji = [f"{ELEMENT_EMOJI.get(e, '')} {e}".strip() for e in elements]
    # Обработка кнопки 'Назад'
    if message.text == "⬅️ Назад":
        await message.answer(md.quote("Для какой игры тебе нужна сборка?"), reply_markup=make_keyboard(GAMES))
        await state.set_state(BuildStates.choose_game)
        return
    # Убираем эмодзи для сопоставления
    element_map = {f"{ELEMENT_EMOJI.get(e, '')} {e}".strip(): e for e in elements}
    if message.text not in element_map:
        await message.answer(md.quote("Пожалуйста, выбери элемент с помощью кнопки."), reply_markup=make_keyboard(elements_with_emoji, add_back=True))
        return
    element = element_map[message.text]
    await state.update_data(element=element)
    chars = get_characters_from_cache(element)
    await message.answer(md.quote("Выбери персонажа:"), reply_markup=make_keyboard(chars, add_back=True))
    await state.set_state(BuildStates.choose_character)

def mdv2_list(items):
    return "\n".join(f"\\- {md.quote(i)}" for i in items)

@dp.message(BuildStates.choose_character)
async def choose_character(message: Message, state: FSMContext):
    data = await state.get_data()
    chars = get_characters_from_cache(data.get("element"))
    # Обработка кнопки 'Назад'
    if message.text == "⬅️ Назад":
        elements = get_elements_from_cache()
        elements_with_emoji = [f"{ELEMENT_EMOJI.get(e, '')} {e}".strip() for e in elements]
        await message.answer(md.quote("Выбери элемент персонажа:"), reply_markup=make_keyboard(elements_with_emoji, add_back=True))
        await state.set_state(BuildStates.choose_element)
        return
    if message.text not in chars:
        await message.answer(md.quote("Пожалуйста, выбери персонажа с помощью кнопки."), reply_markup=make_keyboard(chars, add_back=True))
        return
    await state.update_data(character=message.text)
    await message.answer(md.quote(f"Ищу свежий билд для {message.text}..."), reply_markup=types.ReplyKeyboardRemove())
    build = await get_build(message.text)
    # Новый формат выдачи
    text = format_build_v2(message.text, build)
    if not text.strip():
        text = md.quote("Нет данных по билду этого персонажа.")
    await message.answer(text)
    await state.clear()

@dp.message(Command("latest"))
async def cmd_latest(message: Message):
    # Антиспам: не чаще 1 раза в 30 секунд
    antispam = load_json(SPAM_FILE, {})
    user_id = str(message.from_user.id)
    now = datetime.utcnow()
    last = antispam.get(user_id)
    if last and (now - datetime.fromisoformat(last)) < timedelta(seconds=30):
        await message.answer(md.quote("Пожалуйста, не спамьте! Попробуйте позже."))
        return
    antispam[user_id] = now.isoformat()
    save_json(SPAM_FILE, antispam)

    file = get_latest_build_file()
    if not file:
        await message.answer(md.quote("Нет свежих билдов."))
        return
    with open(file, "r", encoding="utf-8") as f:
        builds = json.load(f)
    for build in builds[:10]:
        await message.answer(md.quote(format_build(build)))

@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    subs = set(load_json(SUBSCRIBERS_FILE, []))
    subs.add(message.from_user.id)
    save_json(SUBSCRIBERS_FILE, list(subs))
    await message.answer(md.quote("Вы подписались на ежедневную рассылку!"))

@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    subs = set(load_json(SUBSCRIBERS_FILE, []))
    subs.discard(message.from_user.id)
    save_json(SUBSCRIBERS_FILE, list(subs))
    await message.answer(md.quote("Вы отписались от рассылки."))

@dp.error()
async def error_handler(event, error):
    logging.error(f"Ошибка: {error}")
    if isinstance(event, Message):
        await event.answer(md.quote("Произошла ошибка. Попробуйте позже."))
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(ADMIN_CHAT_ID, md.quote(f"Error: {error}"))
        except Exception:
            pass

async def daily_broadcast():
    while True:
        subs = set(load_json(SUBSCRIBERS_FILE, []))
        file = get_latest_build_file()
        if file:
            with open(file, "r", encoding="utf-8") as f:
                builds = json.load(f)
            text = "\n\n".join([format_build(b) for b in builds[:3]])
            for uid in subs:
                try:
                    await bot.send_message(uid, text)
                except Exception as e:
                    logging.warning(f"Can't send to {uid}: {e}")
        await asyncio.sleep(24 * 3600)

async def fetch_build_from_game8(character_name: str) -> dict:
    cache = load_cache()
    char_link = cache.get("links", {}).get(character_name)
    if not char_link:
        logging.warning(f"Нет ссылки на персонажа {character_name}")
        return {
            "relics": {"best": "", "alternative": ""},
            "light_cones": {"best": "", "alternative_4": "", "alternative_3": ""},
            "stats": {"main": {"body": "", "feet": "", "sphere": "", "rope": ""}},
            "priority_stats": {},
            "ornaments": {"best": "", "alternative": ""},
            "tips": ""
        }
    async with aiohttp.ClientSession() as session:
        async with session.get(char_link) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    build = {
        "relics": {"best": "", "alternative": ""},
        "light_cones": {"best": "", "alternative_4": "", "alternative_3": ""},
        "stats": {"main": {"body": "", "feet": "", "sphere": "", "rope": ""}},
        "priority_stats": {},
        "ornaments": {"best": "", "alternative": ""},
        "tips": ""
    }
    
    # --- Relics ---
    def find_section(header_keywords):
        for tag in soup.find_all(["h2", "h3"]):
            if any(kw.lower() in tag.text.lower() for kw in header_keywords):
                return tag
        return None
    
    # Relics
    relics_header = find_section(["Relics and Ornaments", "Реликвии и украшения"])
    if relics_header:
        section = relics_header.find_next(["ul", "table"])
        if section:
            relics = []
            if section.name == "ul":
                # Извлекаем текст и ссылки
                for li in section.find_all("li"):
                    text = li.get_text(strip=True)
                    # Проверяем наличие ссылки
                    link = li.find("a")
                    if link and link.get("href"):
                        text += f" ([ссылка]({link.get('href')})"
                    relics.append(text)
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        text = cells[0].get_text(strip=True)
                        # Проверяем наличие ссылки
                        link = cells[0].find("a")
                        if link and link.get("href"):
                            text += f" ([ссылка]({link.get('href')})"
                        relics.append(text)
            
            # Извлекаем лучший и альтернативный сеты
            build["relics"]["best"] = extract_best(relics)
            build["relics"]["alternative"] = extract_alternative(relics)
    
    # Light Cones
    cones_header = find_section(ParsingConfig.SECTIONS["light_cones"])
    if cones_header:
        section = cones_header.find_next(["ul", "table"])
        if section:
            cones = []
            if section.name == "ul":
                # Извлекаем текст и ссылки
                for li in section.find_all("li"):
                    text = li.get_text(strip=True)
                    # Проверяем наличие ссылки
                    link = li.find("a")
                    if link and link.get("href"):
                        text += f" ([ссылка]({link.get('href')})"
                    cones.append(text)
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        text = cells[0].get_text(strip=True)
                        # Проверяем наличие ссылки
                        link = cells[0].find("a")
                        if link and link.get("href"):
                            text += f" ([ссылка]({link.get('href')})"
                        cones.append(text)
            
            # Извлекаем лучший 5★ конус
            build["light_cones"]["best"] = extract_best(cones)
            # Извлекаем альтернативный 4★ конус
            build["light_cones"]["alternative_4"] = extract_alternative(cones)
            # Извлекаем альтернативный 3★ конус
            for cone in cones:
                if "3★" in cone or "3*" in cone or "3-star" in cone.lower():
                    build["light_cones"]["alternative_3"] = cone
                    break
            # Если не нашли 3★ конус, ищем первый подходящий по рейтингу
            if not build["light_cones"]["alternative_3"]:
                for cone in cones:
                    if "★" in cone:
                        rating = cone.count("★")
                        if rating <= 3:
                            build["light_cones"]["alternative_3"] = cone
                            break
            # Если все еще не нашли, используем стандартное значение
            if not build["light_cones"]["alternative_3"]:
                build["light_cones"]["alternative_3"] = "Cruising in the Stellar Sea"
    
    # Stats
    stats_header = find_section(ParsingConfig.SECTIONS["stats"])
    if stats_header:
        section = stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["stats"].append(cells[0].get_text(strip=True))
    else:
        # Если не нашли секцию с рекомендованными статами, используем стандартные значения
        build["stats"]["main"] = {
            "body": "Break Effect",
            "feet": "SPD",
            "sphere": "CRIT Rate",
            "rope": "Energy Regen"
        }
    
    # Priority Stats
    priority_header = find_section(ParsingConfig.SECTIONS["priority"])
    if priority_header:
        section = priority_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                for li in section.find_all("li"):
                    text = li.get_text(strip=True)
                    # Извлекаем рейтинг и характеристику более гибко
                    parts = text.split(" - ")
                    if len(parts) >= 2:
                        rating_text = parts[0].strip().lower()
                        stat = parts[1].strip()
                        
                        # Обработка разных форматов рейтинга
                        if "★" in rating_text:
                            rating = rating_text.count("★")
                        elif "star" in rating_text:
                            rating = int(rating_text.split("-star")[0])
                        elif any(num in rating_text for num in "12345"):
                            rating = int(rating_text[0])
                        else:
                            # Проверяем текстовые оценки
                            for text_rating in ParsingConfig.RATING_TEXT_TO_NUM:
                                if text_rating in rating_text:
                                    rating = ParsingConfig.RATING_TEXT_TO_NUM[text_rating]
                                    break
                            else:
                                # Если не нашли подходящий формат, используем 3 звезды по умолчанию
                                rating = 3
                        build["priority_stats"][stat] = rating
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        rating_text = cells[0].get_text(strip=True).lower()
                        stat = cells[1].get_text(strip=True)
                        # Обработка рейтинга как в списке
                        if "★" in rating_text:
                            rating = rating_text.count("★")
                        elif "star" in rating_text:
                            rating = int(rating_text.split("-star")[0])
                        elif any(num in rating_text for num in "12345"):
                            rating = int(rating_text[0])
                        else:
                            # Проверяем текстовые оценки
                            for text_rating in ParsingConfig.RATING_TEXT_TO_NUM:
                                if text_rating in rating_text:
                                    rating = ParsingConfig.RATING_TEXT_TO_NUM[text_rating]
                                    break
                            else:
                                # Если не нашли подходящий формат, используем 3 звезды по умолчанию
                                rating = 3
                        build["priority_stats"][stat] = rating
    else:
        # Если не нашли секцию с рекомендованными статами, используем стандартные значения
        build["stats"]["main"] = {
            "body": "Break Effect",
            "feet": "SPD",
            "sphere": "CRIT Rate",
            "rope": "Energy Regen"
        }
    
    # Planar Ornaments
    planar_header = find_section(ParsingConfig.SECTIONS["ornaments"])
    if planar_header:
        section = planar_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                # Извлекаем текст и ссылки
                for li in section.find_all("li"):
                    text = li.get_text(strip=True)
                    # Проверяем наличие ссылки
                    link = li.find("a")
                    if link and link.get("href"):
                        text += f" ([ссылка]({link.get('href')})"
                    # Ищем лучший вариант по ключевым словам
                    if any(word in text.lower() for word in ParsingConfig.BEST_KEYWORDS):
                        build["ornaments"]["best"] = text
                    # Ищем альтернативный вариант по ключевым словам
                    elif any(word in text.lower() for word in ParsingConfig.ALTERNATIVE_KEYWORDS):
                        build["ornaments"]["alternative"] = text
                # Если не нашли явно, используем первый и второй элементы
                if not build["ornaments"]["best"] and len(section.find_all("li")) >= 1:
                    build["ornaments"]["best"] = section.find_all("li")[0].get_text(strip=True)
                if not build["ornaments"]["alternative"] and len(section.find_all("li")) >= 2:
                    build["ornaments"]["alternative"] = section.find_all("li")[1].get_text(strip=True)
            elif section.name == "table":
                rows = section.find_all("tr")
                if len(rows) >= 2:
                    # Берем первые два ряда как лучший и альтернативный варианты
                    build["ornaments"]["best"] = rows[0].find_all("td")[0].get_text(strip=True)
                    build["ornaments"]["alternative"] = rows[1].find_all("td")[0].get_text(strip=True)
    else:
        # Если не нашли секцию с украшениями, используем стандартные значения
        build["ornaments"]["best"] = ParsingConfig.DEFAULT_ORNAMENT
        build["ornaments"]["alternative"] = "Giant Tree of Rapt Brooding"
    
    # Tips
    tips_header = find_section(["Gameplay Guide", "Руководство по игре"])
    if tips_header:
        p = tips_header.find_next("p")
        if p:
            build["tips"] = p.get_text(strip=True)
    
    logging.info(f"Билд для {character_name}: {build}")
    return build
    # Stats
    stats_header = find_section(["Recommended Stats", "Рекомендуемые характеристики"])
    if stats_header:
        section = stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["stats"].append(cells[0].get_text(strip=True))
    # Planar Ornaments
    planar_header = find_section(["Planar Ornaments", "Планарные украшения"])
    if planar_header:
        section = planar_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                # Извлекаем текст и ссылки
                for li in section.find_all("li"):
                    text = li.get_text(strip=True)
                    # Проверяем наличие ссылки
                    link = li.find("a")
                    if link and link.get("href"):
                        text += f" ([ссылка]({link.get('href')}))"
                    build["planar"].append(text)
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        text = cells[0].get_text(strip=True)
                        # Проверяем наличие ссылки
                        link = cells[0].find("a")
                        if link and link.get("href"):
                            text += f" ([ссылка]({link.get('href')}))"
                        build["planar"].append(text)
    # Tips
    tips_header = find_section(["Gameplay Guide", "Руководство по игре"])
    if tips_header:
        p = tips_header.find_next("p")
        if p:
            build["tips"] = p.get_text(strip=True)
    logging.info(f"Билд для {character_name}: {build}")
    return build

# --- Новый форматтер и вспомогательные функции ---
def extract_best(items):
    """Ищет лучший вариант по ключевым словам, иначе возвращает первый элемент."""
    keywords = ["best", "recommended", "signature", "лучший", "рекомендуемый"]
    for item in items:
        text = item.lower()
        if any(kw in text for kw in keywords):
            return item
    return items[0] if items else ""

def extract_alternative(items):
    """Ищет альтернативный вариант по ключевым словам, иначе возвращает второй элемент."""
    keywords = ["alternative", "alt", "2nd", "second", "альтернатив", "второй"]
    best = extract_best(items)
    # Ищем альтернативный вариант, который не совпадает с лучшим
    for item in items:
        if item != best:
            text = item.lower()
            if any(kw in text for kw in keywords):
                return item
    # Если не нашли подходящий альтернативный вариант, берем первый, который не лучший
    for item in items:
        if item != best:
            return item
    return ""



def format_build_v2(character_name, build):
    lines = []
    lines.append(f"*Билд для {md.quote(character_name)}*")
    
    # Реликвии
    if build.get("relics"):
        best_relic = build["relics"]["best"]
        alt_relic = build["relics"]["alternative"]
        lines.append(f"\n*Рекомендуемые реликвии:*\n{md.quote(best_relic)}")
        lines.append(f"\n*Альтернативные реликвии:*\n{md.quote(alt_relic)}")
    
    # Конусы
    if build.get("light_cones"):
        best_5 = build["light_cones"]["best"]
        alt_4 = build["light_cones"]["alternative_4"]
        alt_3 = build["light_cones"]["alternative_3"]
        
        lines.append(f"\n*Конус 5★:*\n{md.quote(best_5)}")
        lines.append(f"\n*Конус 4★:*\n{md.quote(alt_4)}")
        lines.append(f"\n*Конус 3★:*\n{md.quote(alt_3)}")
    
    # Основные характеристики
    if build.get("stats"):
        main_stats = build["stats"]["main"]
        lines.append("\n*Основные характеристики:*")
        for slot, stat in main_stats.items():
            lines.append(f"\n*{slot}*: {md.quote(stat)}")
            
    # Приоритетные характеристики
    if build.get("priority_stats"):
        priority_stats = build["priority_stats"]
        lines.append("\n*Приоритетные характеристики:*")
        for stat, rating in priority_stats.items():
            stars = "★" * rating
            lines.append(f"\n*{md.quote(stat)}*: {stars}")
    
    # Планарные украшения
    if build.get("ornaments"):
        best_ornament = build["ornaments"]["best"]
        alt_ornament = build["ornaments"]["alternative"]
        lines.append(f"\n*Планарные украшения:*\n{md.quote(best_ornament)}")
        lines.append(f"\n*Альтернативные украшения:*\n{md.quote(alt_ornament)}")
    
    return "\n".join(lines)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated": "1970-01-01", "data": {}}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

def is_cache_expired(cache):
    updated = datetime.fromisoformat(cache.get("updated", "1970-01-01"))
    return datetime.utcnow() - updated > timedelta(days=CACHE_TTL_DAYS)

async def get_build(character_name: str) -> dict:
    cache = load_cache()
    if character_name in cache["data"] and not is_cache_expired(cache):
        return cache["data"][character_name]
    build = await fetch_build_from_game8(character_name)
    cache["data"][character_name] = build
    cache["updated"] = datetime.utcnow().isoformat()
    save_cache(cache)
    return build

async def fetch_characters_and_elements() -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(CHARACTER_LIST_URL) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    # Логируем все заголовки для отладки
    headers = list(soup.find_all(["h2", "h3"]))
    logging.info("Заголовки на странице:")
    for h in headers:
        logging.info(f"{h.name}: {h.text.strip()}")
    # Ищем таблицу с актуальными персонажами по заголовку
    table = None
    for header in headers:
        if any(x in header.text for x in ["All Playable Characters", "List of All Characters", "Playable Characters", "Все персонажи"]):
            table = header.find_next("table")
            break
    if not table:
        # fallback: ищем таблицу с наибольшим количеством строк
        tables = soup.find_all("table")
        if not tables:
            logging.error("На странице нет ни одной таблицы!")
            return {"elements": {}, "characters": {}, "links": {}}
        table = max(tables, key=lambda t: len(t.find_all("tr")))
        logging.warning("Не найден заголовок с актуальными персонажами, выбрана самая большая таблица на странице!")
    elements = {}
    characters = {}
    links = {}
    for row in table.find_all("tr")[1:]:  # пропускаем заголовок
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        char_a = cols[0].find("a")
        char_name = char_a.text.strip() if char_a else cols[0].text.strip()
        char_href = char_a["href"] if char_a and char_a.get("href") else None
        if char_href:
            if char_href.startswith("http"):
                char_link = char_href
            else:
                char_link = "https://game8.co" + char_href
        else:
            char_link = None
        element_img = cols[2].find("img")
        element = element_img["alt"].strip() if element_img and element_img.get("alt") else cols[2].text.strip()
        # Заполняем структуры
        if element not in elements:
            elements[element] = []
        elements[element].append(char_name)
        characters[char_name] = element
        if char_link:
            links[char_name] = char_link
    # Логируем для отладки
    logging.info(f"Найдено элементов: {list(elements.keys())}")
    for el, chars in elements.items():
        logging.info(f"Элемент {el}: {chars}")
    return {"elements": elements, "characters": characters, "links": links}

# Функция обновления кэша с персонажами и элементами
async def update_full_cache():
    cache = load_cache()
    char_data = await fetch_characters_and_elements()
    cache["elements"] = char_data["elements"]
    cache["characters"] = char_data["characters"]
    cache["links"] = char_data["links"]
    cache["updated"] = datetime.utcnow().isoformat()
    save_cache(cache)
    return cache

# --- Автообновление кэша раз в 10 дней ---
async def cache_auto_updater():
    while True:
        cache = load_cache()
        if is_cache_expired(cache) or not cache.get("elements"):
            try:
                await update_full_cache()
                logging.info("Кэш персонажей и элементов обновлён.")
            except Exception as e:
                logging.warning(f"Ошибка обновления кэша: {e}")
        await asyncio.sleep(24 * 3600)  # Проверять раз в сутки

# --- запуск автообновления в main ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(daily_broadcast())
    asyncio.create_task(cache_auto_updater())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
