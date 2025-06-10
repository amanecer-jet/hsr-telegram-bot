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
            "relics_recommended": [],
            "relics_alternative": [],
            "cones": {"5": [], "4": [], "other": []},
            "main_stats": [],
            "sub_stats": [],
            "evaluation": "",
            "tips": ""
        }
    async with aiohttp.ClientSession() as session:
        async with session.get(char_link) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    build = {
        "relics_recommended": [],
        "relics_alternative": [],
        "cones": {"5": [], "4": [], "other": []},
        "main_stats": [],
        "sub_stats": [],
        "evaluation": "",
        "tips": ""
    }
    # --- Relics ---
    def find_section(header_keywords):
        for tag in soup.find_all(["h2", "h3"]):
            if any(kw.lower() in tag.text.lower() for kw in header_keywords):
                return tag
        return None
    # Recommended relics
    relics_header = find_section(["Recommended Relics", "Best Relics", "Рекомендуемые реликвии"])
    if relics_header:
        section = relics_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["relics_recommended"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["relics_recommended"].append(cells[0].get_text(strip=True))
    # Alternative relics
    alt_relics_header = find_section(["Alternative Relics", "Alt Relics", "Альтернативные реликвии"])
    if alt_relics_header:
        section = alt_relics_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["relics_alternative"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["relics_alternative"].append(cells[0].get_text(strip=True))
    # --- Light Cones ---
    cones_header = find_section(["Light Cone", "Световой конус"])
    if cones_header:
        section = cones_header.find_next(["ul", "table"])
        cones_raw = []
        if section:
            if section.name == "ul":
                cones_raw = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        cones_raw.append(cells[0].get_text(strip=True))
        # Группировка по звёздности (улучшено)
        for cone in cones_raw:
            cone_stripped = cone.strip()
            if cone_stripped.startswith("★★★★★") or "5★" in cone_stripped or "5*" in cone_stripped or "5-star" in cone_stripped.lower() or "signature" in cone_stripped.lower():
                build["cones"]["5"].append(cone)
            elif cone_stripped.startswith("★★★★☆") or "4★" in cone_stripped or "4*" in cone_stripped or "4-star" in cone_stripped.lower():
                build["cones"]["4"].append(cone)
            else:
                build["cones"]["other"].append(cone)
    # --- Main/Sub Stats ---
    main_stats_header = find_section(["Main Stat", "Main Stats", "Основная характеристика"])
    if main_stats_header:
        section = main_stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["main_stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["main_stats"].append(cells[0].get_text(strip=True))
    sub_stats_header = find_section(["Sub Stat", "Sub Stats", "Второстепенные характеристики"])
    if sub_stats_header:
        section = sub_stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["sub_stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["sub_stats"].append(cells[0].get_text(strip=True))
    # --- Evaluation / Tips ---
    eval_header = find_section(["Evaluation", "Overview", "Оценка", "Обзор"])
    if eval_header:
        p = eval_header.find_next("p")
        if p:
            build["evaluation"] = p.get_text(strip=True)
    tips_header = find_section(["Tips", "General Tips", "Советы", "Рекомендации"])
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
    for item in items:
        text = item.lower()
        if any(kw in text for kw in keywords):
            return item
    return items[1] if len(items) > 1 else ""

def split_stats(stats):
    """Разделяет характеристики на рекомендованные (с числами/значениями) и приоритетные (без чисел)."""
    recommended = []
    priority = []
    for s in stats:
        if any(char.isdigit() for char in s) or any(x in s for x in ["%", ":", "/"]):
            recommended.append(s)
        else:
            priority.append(s)
    return recommended, priority

def format_build_v2(character_name, build):
    lines = []
    lines.append(f"*Билд для {md.quote(character_name)}*")
    
    # Реликвии
    relics = build.get("relics_recommended", [])
    if relics:
        lines.append("\n*Рекомендуемые реликвии:*")
        for relic in relics:
            lines.append(md.quote(relic))
    
    # Альтернативные реликвии
    alt_relics = build.get("relics_alternative", [])
    if alt_relics:
        lines.append("\n*Альтернативные реликвии:*")
        for relic in alt_relics:
            lines.append(md.quote(relic))
    
    # Планарные украшения
    ornaments = build.get("ornaments_recommended", [])
    if ornaments:
        lines.append("\n*Рекомендуемые планарные украшения:*")
        for ornament in ornaments:
            lines.append(md.quote(ornament))
    
    # Альтернативные планарные украшения
    alt_ornaments = build.get("ornaments_alternative", [])
    if alt_ornaments:
        lines.append("\n*Альтернативные планарные украшения:*")
        for ornament in alt_ornaments:
            lines.append(md.quote(ornament))
    
    # Конусы
    cones = build.get("cones", {})
    best_5 = extract_best(cones.get("5", []))
    alt_5 = extract_alternative(cones.get("5", []))
    best_4 = extract_best(cones.get("4", []))
    alt_4 = extract_alternative(cones.get("4", []))
    
    if best_5:
        lines.append(f"\n*Конус 5★:*{md.quote(best_5)}")
    if alt_5 and alt_5 != best_5:
        lines.append(f"\n*Альтернативный конус 5★:*{md.quote(alt_5)}")
    if best_4:
        lines.append(f"\n*Конус 4★:*{md.quote(best_4)}")
    if alt_4 and alt_4 != best_4:
        lines.append(f"\n*Альтернативный конус 4★:*{md.quote(alt_4)}")
    
    # Характеристики
    main_stats = build.get("main_stats", [])
    sub_stats = build.get("sub_stats", [])
    if main_stats or sub_stats:
        lines.append("\n*Характеристики:")
        if main_stats:
            lines.append("\n*Рекомендованные:*")
            for stat in main_stats:
                lines.append(md.quote(stat))
        if sub_stats:
            lines.append("\n*Приоритетные:*")
            for stat in sub_stats:
                lines.append(md.quote(stat))
    
    # Оценка
    if build.get("evaluation"):
        lines.append(f"\n*Оценка полезности персонажа:*")
        lines.append(md.quote(build['evaluation']))
    
    # Рекомендации
    if build.get("tips"):
        lines.append(f"\n*Общие рекомендации по персонажу:*")
        lines.append(md.quote(build['tips']))
    
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
