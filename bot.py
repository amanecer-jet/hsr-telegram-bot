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

def make_keyboard(options):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=o)] for o in options],
        resize_keyboard=True
    )

# --- Динамические кнопки из кэша ---
def get_elements_from_cache():
    cache = load_cache()
    return list(cache.get("elements", {}).keys())

def get_characters_from_cache(element):
    cache = load_cache()
    return cache.get("elements", {}).get(element, [])

# --- FSM-диалог с динамическими кнопками ---
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
    await message.answer(md.quote("Выбери элемент персонажа:"), reply_markup=make_keyboard(elements))
    await state.set_state(BuildStates.choose_element)

@dp.message(BuildStates.choose_element)
async def choose_element(message: Message, state: FSMContext):
    elements = get_elements_from_cache()
    if message.text not in elements:
        await message.answer(md.quote("Пожалуйста, выбери элемент с помощью кнопки."), reply_markup=make_keyboard(elements))
        return
    await state.update_data(element=message.text)
    chars = get_characters_from_cache(message.text)
    await message.answer(md.quote("Выбери персонажа:"), reply_markup=make_keyboard(chars))
    await state.set_state(BuildStates.choose_character)

@dp.message(BuildStates.choose_character)
async def choose_character(message: Message, state: FSMContext):
    data = await state.get_data()
    chars = get_characters_from_cache(data.get("element"))
    if message.text not in chars:
        await message.answer(md.quote("Пожалуйста, выбери персонажа с помощью кнопки."), reply_markup=make_keyboard(chars))
        return
    await state.update_data(character=message.text)
    await message.answer(md.quote(f"Ищу свежий билд для {message.text}..."), reply_markup=types.ReplyKeyboardRemove())
    build = await get_build(message.text)
    relics = build.get("relics", [])
    cones = build.get("cones", [])
    stats = build.get("stats", [])
    text = ""
    if relics:
        text += "*Рекомендованные реликвии:*\n" + "\n".join(f"- {md.quote(r)}" for r in relics) + "\n\n"
    if cones:
        text += "*Рекомендованные конусы:*\n" + "\n".join(f"- {md.quote(c)}" for c in cones) + "\n\n"
    if stats:
        text += "*Приоритетные характеристики:*\n" + "\n".join(f"- {md.quote(s)}" for s in stats) + "\n"
    if not text:
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
    logging.exception(f"Error: {error}")
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
        return {"relics": [], "cones": [], "stats": []}
    async with aiohttp.ClientSession() as session:
        async with session.get(char_link) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    # Парсим реликвии
    relics = []
    relic_section = soup.find(lambda tag: tag.name in ["h2", "h3"] and "Recommended Relics" in tag.text)
    if relic_section:
        ul = relic_section.find_next("ul")
        if ul:
            relics = [li.get_text(strip=True) for li in ul.find_all("li")]
    # Парсим конусы (Light Cones)
    cones = []
    cone_section = soup.find(lambda tag: tag.name in ["h2", "h3"] and "Recommended Light Cones" in tag.text)
    if cone_section:
        ul = cone_section.find_next("ul")
        if ul:
            cones = [li.get_text(strip=True) for li in ul.find_all("li")]
    # Парсим характеристики (Main Stats)
    stats = []
    stat_section = soup.find(lambda tag: tag.name in ["h2", "h3"] and ("Main Stats" in tag.text or "Recommended Main Stats" in tag.text))
    if stat_section:
        ul = stat_section.find_next("ul")
        if ul:
            stats = [li.get_text(strip=True) for li in ul.find_all("li")]
    return {"relics": relics, "cones": cones, "stats": stats}

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
    # Парсим таблицу с персонажами
    table = soup.find("table")
    if not table:
        return {"elements": {}, "characters": {}, "links": {}}
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
