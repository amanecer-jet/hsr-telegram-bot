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

# Проверка обязательных переменных окружения
required_vars = ["TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID"]
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    error_msg = f"Ошибка: Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}"
    print(error_msg)
    if os.getenv("RAILWAY_ENVIRONMENT"):
        # В Railway логируем в stderr, чтобы увидеть в логах
        import sys
        print(error_msg, file=sys.stderr)
    exit(1)

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
EXAMPLE_CHARACTERS = {
    "Fire": ["March 7th", "Bronya", "Herta"],
    "Ice": ["Silver Wolf", "Seele", "Yanqing"],
    "Wind": ["Clara", "Himeko", "Bailu"],
    "Quantum": ["Gepard", "Kepler", "Vermillion"],
    "Physical": ["Ningguang", "Herta", "Gepard"],
    "Imaginary": ["Gepard", "Bronya", "Herta"],
    "Lightning": ["Bronya", "Herta", "Gepard"]
}

# Функции работы с кэшем
def load_cache():
    """Загружает кэш из файла"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "elements": {},
            "characters": {},
            "links": {},
            "updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logging.error(f"Ошибка при загрузке кэша: {str(e)}")
        return {
            "elements": {},
            "characters": {},
            "links": {},
            "updated": datetime.utcnow().isoformat()
        }

def save_cache(data):
    """Сохраняет кэш в файл"""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Ошибка при сохранении кэша: {str(e)}")

# --- Эмодзи для элементов ---
ELEMENT_EMOJI = {
    "Огонь": "🔥",
    "Лёд": "❄️",
    "Ветер": "🌪️",
    "Квант": "⚛️",
    "Физика": "💪",
    "Мнимость": "🌈",
    "Электро": "⚡"
}

# --- URLs ---
CHARACTER_LIST_URL = "https://www.prydwen.gg/star-rail/characters"
CHARACTER_BASE_URL = "https://www.prydwen.gg/star-rail/characters/"

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

def format_build(build_data: dict) -> str:
    """Форматирует билд в читаемый текст"""
    if not build_data or not build_data.get("builds"):
        return "Данные о билде не найдены"
    
    text = []
    
    # Информация о персонаже
    char = build_data["character"]
    text.append(f"*{char['name']}*\n")
    
    # Элемент и путь с эмодзи
    element = ParsingConfig.ELEMENTS.get(char.get("element", "Unknown"))
    element_text = element["emoji"] + " " + element["name"] if element else "❓ Неизвестный элемент"
    text.append(f"Элемент: {element_text}\n")
    
    if char.get("path"):
        text.append(f"Путь: {char['path']}\n")
    
    # Форматируем каждый билд
    for build in build_data["builds"]:
        text.append("\n")
        text.append(f"*{build['name']}*\n")
        
        # Описание
        if build.get("description"):
            text.append(f"{build['description']}\n")
        
        # Рейтинг
        if build.get("rating"):
            stars = "⭐" * build["rating"]["stars"]
            text.append(f"Рейтинг: {stars} ({build['rating']['text']})\n")
        
        # Оружие
        if build.get("weapon"):
            weapon = build["weapon"]
            text.append(f"\n*Оружие:*\n")
            text.append(f"{weapon['name']}\n")
            if weapon.get("rank"):
                text.append(f"Уровень: {weapon['rank']}\n")
        
        # Артефакты
        if build.get("artifacts"):
            text.append("\n*Артефакты:*\n")
            for artifact in build["artifacts"]:
                text.append(f"\n*{artifact['name']}*\n")
                if artifact.get("set"):
                    text.append(f"Сет: {artifact['set']}\n")
                if artifact.get("slot"):
                    text.append(f"Слот: {artifact['slot']}\n")
                
                # Основной стат
                if artifact.get("main_stat"):
                    main_stat = artifact["main_stat"]
                    text.append(f"Основной стат: {main_stat['name']}")
                    if main_stat.get("type"):
                        text.append(f" [{main_stat['type']}]")
                    text.append("\n")
                
                # Дополнительные статы
                if artifact.get("sub_stats"):
                    text.append("Дополнительные статы:\n")
                    for sub in artifact["sub_stats"]:
                        stat_text = sub["name"]
                        if sub.get("type"):
                            stat_text += f" [{sub['type']}]"
                        text.append(f"- {stat_text}\n")
        
        # Команда
        if build.get("team"):
            text.append("\n*Команда:*\n")
            for member in build["team"]:
                text.append(f"- {member['name']}\n")
    
    return ''.join(text)

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

async def cmd_build(message: Message):
    character_name = message.text.replace("/build", "").strip()
    if not character_name:
        await message.answer(md.quote("Укажите имя персонажа после команды /build"))
        return
    
    try:
        # Получаем билд из кэша или загружаем новый
        build = await get_build(character_name)
        if build:
            formatted = format_build(character_name, build)
            await message.answer(formatted)
        else:
            await message.answer(md.quote("Персонаж не найден или информация о билде недоступна"))
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /build: {e}")
        await message.answer(md.quote("Произошла ошибка при получении информации о билде"))

async def update_cache_on_demand():
    """Обновляет кэш при необходимости"""
    cache = load_cache()
    current_time = datetime.utcnow()
    
    # Проверяем, не устарел ли кэш
    cache_age = current_time - datetime.fromisoformat(cache.get("updated", "1970-01-01"))
    if cache_age > timedelta(days=CACHE_TTL_DAYS):
        try:
            await update_full_cache()
            logging.info("Кэш персонажей и элементов обновлён по запросу")
        except Exception as e:
            logging.warning(f"Ошибка обновления кэша по запросу: {e}")

@dp.message(Command("build"))
async def cmd_build(message: Message):
    character_name = message.text.replace("/build", "").strip()
    if not character_name:
        await message.answer(md.quote("Укажите имя персонажа после команды /build"))
        return
    
    try:
        # Получаем билд из кэша или загружаем новый
        build = await get_build(character_name)
        if build:
            formatted = format_build(character_name, build)
            await message.answer(formatted)
        else:
            await message.answer(md.quote("Персонаж не найден или информация о билде недоступна"))
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /build: {e}")
        await message.answer(md.quote("Произошла ошибка при получении информации о билде"))

@dp.message(Command("update_cache"))
async def cmd_update_cache(message: Message):
    """Обновляет кэш персонажей и элементов"""
    try:
        await update_full_cache()
        await message.answer(md.quote("Кэш обновлен успешно!"))
    except Exception as e:
        logging.error(f"Ошибка при обновлении кэша: {e}")
        await message.answer(md.quote(f"Ошибка при обновлении кэша: {str(e)}"))

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

async def parse_build_prydwen(soup: BeautifulSoup) -> list:
    """Парсит билды из HTML страницы на prydwen.gg"""
    builds = []
    
    try:
        # Базовая информация о персонаже
        base_info = {
            "character": {
                "name": "",
                "element": "",
                "path": ""
            },
            "builds": []
        }
        
        # Имя персонажа
        name_elem = soup.find("h1", class_="character-name")
        if name_elem:
            base_info["character"]["name"] = name_elem.text.strip()
        
        # Элемент
        element_elem = soup.find("img", class_="element-icon")
        if element_elem:
            element_text = element_elem["alt"].strip()
            # Используем конфиг для перевода элемента
            for eng, data in ParsingConfig.ELEMENTS.items():
                if data["name"] == element_text:
                    base_info["character"]["element"] = eng
                    break
            else:
                base_info["character"]["element"] = "Unknown"
        
        # Путь
        path_elem = soup.find("img", class_="path-icon")
        if path_elem:
            base_info["character"]["path"] = path_elem["alt"].strip()
        
        # Ищем все блоки с билдами
        build_blocks = soup.find_all("div", class_="build-block")
        
        for block in build_blocks:
            build = {
                "name": "",
                "description": "",
                "weapon": {"name": "", "rank": ""},
                "artifacts": [],
                "team": [],
                "stats": {},
                "rating": {"stars": 0, "text": ""},
                "type": "main",
                "source": "prydwen.gg"
            }
            
            # Определяем тип билда (основной или альтернативный)
            title = block.find("h2")
            if title:
                title_text = title.text.strip().lower()
                build["name"] = title.text.strip()
                
                # Проверяем на наличие ключевых слов
                if any(keyword in title_text for keyword in ParsingConfig.BEST_KEYWORDS):
                    build["type"] = "main"
                elif any(keyword in title_text for keyword in ParsingConfig.ALTERNATIVE_KEYWORDS):
                    build["type"] = "alternative"
            
            # Ищем описание
            description = block.find("p", class_="description")
            if description:
                build["description"] = description.text.strip()
            
            # Ищем оружие
            weapon = block.find("div", class_="weapon")
            if weapon:
                build["weapon"]["name"] = weapon.text.strip()
                # Проверяем уровень оружия
                rank = weapon.find("span", class_="rank")
                if rank:
                    rank_text = rank.text.lower()
                    if any(keyword in rank_text for keyword in ParsingConfig.RANK_KEYWORDS):
                        build["weapon"]["rank"] = rank_text.strip()
            
            # Ищем артефакты
            artifacts = block.find_all("div", class_="artifact")
            for art in artifacts:
                artifact = {
                    "name": "",
                    "set": "",
                    "slot": "",
                    "main_stat": {"name": "", "type": ""},
                    "sub_stats": []
                }
                
                # Имя артефакта
                name = art.find("h3")
                if name:
                    artifact["name"] = name.text.strip()
                    
                    # Определяем слот по имени
                    for slot, keywords in ParsingConfig.STATS_MAIN_SLOTS.items():
                        if any(keyword in artifact["name"].lower() for keyword in keywords):
                            artifact["slot"] = slot
                            break
                
                # Ищем сет артефакта
                set_name = art.find("span", class_="set")
                if set_name:
                    artifact["set"] = set_name.text.strip()
                
                # Ищем основной стат
                main_stat = art.find("div", class_="main-stat")
                if main_stat:
                    artifact["main_stat"]["name"] = main_stat.text.strip()
                    # Определяем тип стата
                    stat_text = main_stat.text.lower()
                    for stat_key, keywords in ParsingConfig.STAT_KEYWORDS.items():
                        if any(keyword in stat_text for keyword in keywords):
                            artifact["main_stat"]["type"] = stat_key
                            break
                
                # Ищем дополнительные статы
                sub_stats = art.find_all("div", class_="sub-stat")
                for stat in sub_stats:
                    stat_text = stat.text.strip()
                    # Определяем тип стата
                    stat_type = next((stat_key for stat_key, keywords in ParsingConfig.STAT_KEYWORDS.items() 
                                    if any(keyword in stat_text.lower() for keyword in keywords)), "")
                    artifact["sub_stats"].append({
                        "name": stat_text,
                        "type": stat_type
                    })
                
                build["artifacts"].append(artifact)
            
            # Ищем команду
            team = block.find("div", class_="team")
            if team:
                for char in team.find_all("div", class_="character"):
                    build["team"].append({
                        "name": char.text.strip(),
                        "element": "",  # Будет заполнено позже
                        "role": ""  # Будет заполнено позже
                    })
            
            # Ищем рейтинг
            rating = block.find("div", class_="rating")
            if rating:
                build["rating"] = {
                    "stars": 0,
                    "text": "",
                    "numeric": 0
                }
                
                # Проверяем звезды
                stars = rating.find_all("span", class_="star")
                build["rating"]["stars"] = len(stars)
                
                # Проверяем текстовый рейтинг
                text_rating = rating.find("span", class_="text")
                if text_rating:
                    text = text_rating.text.strip()
                    # Проверяем, если это число
                    if text.isdigit():
                        build["rating"]["numeric"] = int(text)
                        build["rating"]["text"] = f"{text}/5"
                    # Проверяем, если это буквенная оценка
                    elif text in ParsingConfig.RATING_FORMATS["text"]:
                        build["rating"]["text"] = text
                        build["rating"]["numeric"] = ParsingConfig.RATING_FORMATS["text"].index(text) + 1
            
            builds.append(build)
        
        # Если не нашли билды, используем старый формат
        if not builds:
            # Билд
            build_elem = soup.find("div", class_="build-guide")
            if build_elem:
                builds.append({
                    "name": "Основной билд",
                    "description": build_elem.text.strip(),
                    "type": "main",
                    "source": "prydwen.gg"
                })
            
            # Реликты (старый формат)
            relic_containers = soup.find_all("div", class_="relic-set")
            if relic_containers:
                for container in relic_containers:
                    relic = {
                        "name": container.find("h3").text.strip(),
                        "main_stat": container.find("div", class_="main-stat").text.strip() if container.find("div", class_="main-stat") else "",
                        "sub_stats": [stat.text.strip() for stat in container.find_all("div", class_="sub-stat")]
                    }
                    builds[0]["artifacts"].append(relic)
            
            # Конус (старый формат)
            cone_elem = soup.find("div", class_="light-cone")
            if cone_elem:
                builds[0]["weapon"] = {
                    "name": cone_elem.find("h3").text.strip(),
                    "stats": [stat.text.strip() for stat in cone_elem.find_all("div", class_="stat")]
                }
    
    except Exception as e:
        logging.error(f"Ошибка при парсинге билда: {str(e)}")
        return None
    
    return builds if builds else None

async def get_build(character_name: str) -> dict:
    """Получает билд для персонажа, загружая страницу при необходимости"""
    # Получаем элемент персонажа из кэша
    cache = load_cache()
    element = None
    for elem, chars in cache.get("elements", {}).items():
        if character_name.lower() in [char.lower() for char in chars]:
            element = elem
            break
    
    if not element:
        return None
    
    # Сначала проверяем кэш
    cache_file = f"cache/{character_name.lower()}.json"
    
    # Проверяем кэш в файловой системе
    if os.path.exists(cache_file):
        try:
            # Загружаем из кэша
            build_data = load_json(cache_file, default=None)
            if build_data:
                # Проверяем, что данные валидны
                if "character" in build_data and "builds" in build_data:
                    # Проверяем, не устарел ли кэш (более 24 часов)
                    cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
                    if cache_age.total_seconds() < 24 * 3600:
                        return build_data
        except Exception as e:
            logging.warning(f"Ошибка при чтении кэша для {character_name}: {str(e)}")
            # Удаляем поврежденный кэш
            try:
                os.remove(cache_file)
            except:
                pass
    
    # Если нет в кэше, загружаем с сайта
    try:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{CHARACTER_BASE_URL}{character_name.lower()}") as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "html.parser")
                        
                        # Парсим билды
                        builds = await parse_build_prydwen(soup)
                        if builds and isinstance(builds, list):
                            # Создаем структуру данных
                            build_data = {
                                "character": {
                                    "name": character_name,
                                    "element": element
                                },
                                "builds": builds
                            }
                            
                            # Обновляем элемент из страницы
                            element_elem = soup.find("img", class_="element-icon")
                            if element_elem:
                                element_text = element_elem["alt"].strip()
                                for eng, data in ParsingConfig.ELEMENTS.items():
                                    if data["name"] == element_text:
                                        build_data["character"]["element"] = eng
                                        break
                                else:
                                    build_data["character"]["element"] = "Unknown"
                            
                            # Обновляем путь
                            path_elem = soup.find("img", class_="path-icon")
                            if path_elem:
                                build_data["character"]["path"] = path_elem["alt"].strip()
                            
                            # Сохраняем в кэш
                            save_json(cache_file, build_data)
                            return build_data
                        else:
                            logging.error(f"Ошибка при парсинге билдов для {character_name}")
                            return None
                    elif resp.status == 404:
                        logging.warning(f"Страница для {character_name} не найдена")
                        return None
                    else:
                        logging.error(f"Ошибка при загрузке страницы для {character_name}: {resp.status}")
                        return None
            except Exception as e:
                logging.error(f"Ошибка при загрузке билда для {character_name}: {str(e)}")
                return None
    except Exception as e:
        logging.error(f"Ошибка при получении билда для {character_name}: {str(e)}")
        return None

async def fetch_characters_and_elements() -> dict:
    """Получает список персонажей и их элементов с сайта"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CHARACTER_BASE_URL) as resp:
                if resp.status != 200:
                    logging.error(f"Ошибка при загрузке списка персонажей: {resp.status}")
                    return {"elements": {}, "characters": {}, "links": {}}
                
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Ищем контейнер с персонажами
                characters_container = soup.find("div", class_="characters-list")
                if not characters_container:
                    logging.error("Не найден контейнер с персонажами!")
                    return {"elements": {}, "characters": {}, "links": {}}
                
                elements = {}
                characters = {}
                links = {}
                
                # Ищем все карточки персонажей
                for char_card in characters_container.find_all("div", class_="character-card"):
                    # Ищем ссылку на персонажа
                    char_a = char_card.find("a")
                    if not char_a:
                        continue
                    
                    char_name = char_a.text.strip()
                    char_link = CHARACTER_BASE_URL + char_a["href"].split('/')[-1]  # Формируем полный URL
                    
                    # Ищем элемент персонажа
                    element_img = char_card.find("img", class_="element-icon")
                    if not element_img or not element_img.get("alt"):
                        logging.warning(f"Не найден элемент для персонажа {char_name}")
                        continue
                    
                    element_text = element_img["alt"].strip()
                    # Преобразуем элемент в английское название
                    element = next((eng for eng, data in ParsingConfig.ELEMENTS.items() 
                                  if data.get("name") == element_text), None)
                    if not element:
                        logging.warning(f"Неизвестный элемент для персонажа {char_name}: {element_text}")
                        continue
                    
                    # Заполняем структуры
                    if element not in elements:
                        elements[element] = []
                    elements[element].append(char_name)
                    characters[char_name] = element
                    links[char_name] = char_link
                
                # Логируем результат
                logging.info(f"Найдено персонажей: {len(characters)}")
                for element, chars in elements.items():
                    logging.info(f"Элемент {element} ({ParsingConfig.ELEMENTS[element]['emoji']}): {len(chars)} персонажей")
                
                return {"elements": elements, "characters": characters, "links": links}
    except Exception as e:
        logging.error(f"Ошибка при загрузке списка персонажей: {str(e)}")
        return {"elements": {}, "characters": {}, "links": {}}

def format_build_v2(character_name: str, build_data: dict) -> str:
    """Форматирует билд в читаемый формат для Telegram"""
    if not build_data or not build_data.get("builds"):
        return ""

    character_info = build_data.get("character", {})
    builds = build_data.get("builds", [])

    # Формируем основную информацию о персонаже
    element_emoji = ELEMENT_EMOJI.get(character_info.get("element", ""), "")
    path = character_info.get("path", "")
    
    result = []
    result.append(f"*{character_name}* {element_emoji}")
    if path:
        result.append(f"*Путь:* {path}")
    
    # Форматируем каждый билд
    for build in builds:
        if build.get("type") == "main":
            result.append("\n*Основной билд:*")
        else:
            result.append("\n*Альтернативный билд:*")
        
        if build.get("name"):
            result.append(f"\- *Название:* {build['name']}")
        
        if build.get("description"):
            result.append(f"\- *Описание:* {build['description']}")
        
        # Оружие
        weapon = build.get("weapon", {})
        if weapon.get("name"):
            weapon_text = f"\- *Оружие:* {weapon['name']}"
            if weapon.get("rank"):
                weapon_text += f" ({weapon['rank']})"
            result.append(weapon_text)
        
        # Артефакты
        if build.get("artifacts"):
            result.append("\- *Артефакты:*")
            for artifact in build["artifacts"]:
                if artifact.get("name"):
                    artifact_text = f"\-\- {artifact['name']}"
                    if artifact.get("set"):
                        artifact_text += f" ({artifact['set']})"
                    if artifact.get("main_stat"):
                        artifact_text += f"\n\-\-\- *Основной стат:* {artifact['main_stat']['name']}"
                    if artifact.get("sub_stats"):
                        artifact_text += "\n\-\-\- *Дополнительные статы:* " + ", ".join(artifact['sub_stats'])
                    result.append(artifact_text)
        
        # Команда
        if build.get("team"):
            result.append("\- *Команда:*")
            for teammate in build["team"]:
                if teammate.get("name"):
                    result.append(f"\-\- {teammate['name']}")
        
        # Рейтинг
        rating = build.get("rating", {})
        if rating.get("stars") or rating.get("text"):
            rating_text = "\- *Рейтинг:* "
            if rating.get("stars"):
                rating_text += f"{rating['stars']}⭐"
            if rating.get("text"):
                rating_text += f" ({rating['text']})"
            result.append(rating_text)
    
    return "\n".join(result)

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

def is_cache_expired(cache_data: dict, ttl_days: int = 10) -> bool:
    """Проверяет, истек ли срок действия кэша"""
    if not cache_data or "updated" not in cache_data:
        return True
    last_updated = datetime.fromisoformat(cache_data["updated"])
    return (datetime.now() - last_updated) > timedelta(days=ttl_days)

async def cache_auto_updater():
    """Автоматически обновляет кэш раз в 10 дней"""
    while True:
        cache = load_cache()
        if is_cache_expired(cache) or not cache.get("elements"):
            await update_full_cache()
        # Ждем 1 день до следующей проверки
        await asyncio.sleep(24 * 60 * 60)  # 1 день

# --- запуск автообновления в main ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(daily_broadcast())
    asyncio.create_task(cache_auto_updater())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
