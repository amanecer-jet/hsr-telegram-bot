import os
import logging
import asyncio
import requests
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from datetime import datetime, timedelta
from config import BotConfig
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
CACHE_TTL_HOURS = 24

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# --- FSM States ---
class BuildStates(StatesGroup):
    choose_game = State()
    choose_element = State()
    choose_character = State()
    show_build = State()

# --- Кэширование и загрузка данных ---
def load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {"last_updated": None, "game_data": {}}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_updated": None, "game_data": {}}

def save_cache(cache: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def is_cache_valid(cache: dict) -> bool:
    try:
        if not cache or not cache.get("last_updated"):
            return False
        last = datetime.fromisoformat(cache["last_updated"])
        return datetime.now() - last < timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return False

def fetch_all_data():
    urls = BotConfig.GITHUB_DATA_URLS["Honkai: Star Rail"]
    data = {}
    for key, url in urls.items():
        resp = requests.get(url)
        resp.raise_for_status()
        data[key] = resp.json()
    return data

def update_cache():
    data = fetch_all_data()
    cache = {
        "last_updated": datetime.now().isoformat(),
        "game_data": {
            "Honkai: Star Rail": data
        }
    }
    save_cache(cache)
    return cache

# --- Связывание и поиск данных ---
def get_elements(game_data):
    # Собираем уникальные пути (элементы) из данных персонажей
    elements = set()
    for char in game_data["characters"]:
        if "path" in char and char["path"]:
            elements.add(char["path"])
    return sorted(elements)

def get_path_name(game_data, path_id):
    for path in game_data["paths"]:
        if path["id"] == path_id:
            return path["name"]
    return path_id

def get_element_name(game_data, element_id):
    for el in game_data["elements"]:
        if el["id"] == element_id:
            return el["name"]
    return element_id

def get_characters_by_element(game_data, element):
    return [c["name"] for c in game_data["characters"] if c.get("path") == element]

def get_character_data(game_data, name):
    for c in game_data["characters"]:
        if c.get("name") == name:
            return c
    return None

def get_relic_set_name(game_data, set_id):
    for s in game_data["relic_sets"]:
        if s["id"] == set_id:
            return s["name"]
    return set_id

def get_planar_name(game_data, set_id):
    # Планарные украшения — это сеты типа "Planar"
    for s in game_data["relic_sets"]:
        if s["id"] == set_id and s.get("type") == "Planar":
            return s["name"]
    return set_id

def get_cone_name(game_data, cone_id):
    for cone in game_data["light_cones"]:
        if cone["id"] == cone_id:
            return cone["name"], cone.get("rarity", "")
    return cone_id, ""

def get_main_stat_name(game_data, stat_id):
    for stat in game_data["relic_main_affixes"]:
        if stat["id"] == stat_id:
            return stat["name"]
    return stat_id

def get_sub_stat_name(game_data, stat_id):
    for stat in game_data["relic_sub_affixes"]:
        if stat["id"] == stat_id:
            return stat["name"]
    return stat_id

# --- Клавиатуры ---
def game_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎮 Honkai: Star Rail", callback_data="game:Honkai: Star Rail")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def element_keyboard(elements, game_data):
    kb = []
    for el in elements:
        emoji = ""  # Можно добавить эмодзи по названию пути
        el_name = get_path_name(game_data, el)
        kb.append([InlineKeyboardButton(text=f"{emoji}{el_name}", callback_data=f"element:{el}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:game")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def character_keyboard(characters):
    kb = []
    for ch in characters:
        kb.append([InlineKeyboardButton(text=f"👤 {ch}", callback_data=f"char:{ch}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:element")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_keyboard():
    kb = [
        [InlineKeyboardButton(text="🔄 К выбору персонажа", callback_data="back:char")],
        [InlineKeyboardButton(text="🏠 В начало", callback_data="back:home")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- Форматирование билда по ТЗ ---
def format_build(character, game_data):
    msg = f"<b>{character['name']}</b>\n"
    msg += f"Путь: {get_path_name(game_data, character.get('path'))}\n"
    msg += f"Элемент: {get_element_name(game_data, character.get('element'))}\n\n"
    # Реликвии (основной и альтернатива)
    relics = character.get("relic_sets", [])
    if relics:
        msg += f"<b>Рекомендуемые реликвии:</b> {get_relic_set_name(game_data, relics[0])}\n"
        if len(relics) > 1:
            msg += f"<b>Альтернатива:</b> {get_relic_set_name(game_data, relics[1])}\n"
    # Планарные украшения (основной и альтернатива)
    planars = character.get("planar_sets", [])
    if planars:
        msg += f"<b>Планарные украшения:</b> {get_planar_name(game_data, planars[0])}\n"
        if len(planars) > 1:
            msg += f"<b>Альтернатива:</b> {get_planar_name(game_data, planars[1])}\n"
    # Конусы (5★, 4★, 3★/4★)
    cones = character.get("light_cones", [])
    cone_5 = next((c for c in cones if get_cone_name(game_data, c)[1] == 5), None)
    cone_4 = next((c for c in cones if get_cone_name(game_data, c)[1] == 4), None)
    cone_3 = next((c for c in cones if get_cone_name(game_data, c)[1] == 3), None)
    if cone_5:
        name, _ = get_cone_name(game_data, cone_5)
        msg += f"<b>5★ конус:</b> {name}\n"
    if cone_4:
        name, _ = get_cone_name(game_data, cone_4)
        msg += f"<b>4★ конус:</b> {name}\n"
    if cone_3:
        name, _ = get_cone_name(game_data, cone_3)
        msg += f"<b>3★ конус:</b> {name}\n"
    else:
        cones_4 = [c for c in cones if get_cone_name(game_data, c)[1] == 4]
        if len(cones_4) > 1:
            name, _ = get_cone_name(game_data, cones_4[1])
            msg += f"<b>4★ конус (альтернатива):</b> {name}\n"
    # Параметры реликвий (основные характеристики)
    main_stats = character.get("main_stats", {})
    if main_stats:
        msg += "<b>Параметры реликвий:</b>\n"
        for slot, stat_ids in main_stats.items():
            stat_names = [get_main_stat_name(game_data, s) for s in stat_ids]
            msg += f"- {slot}: {', '.join(stat_names)}\n"
    # Рекомендуемые параметры персонажа
    rec_stats = character.get("recommended_stats", [])
    if rec_stats:
        msg += "<b>Рекомендуемые параметры персонажа:</b>\n"
        for stat in rec_stats:
            msg += f"- {stat}\n"
    return msg.strip()

# --- FSM-логика через инлайн-кнопки ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>Привет!</b>\nЯ помогу подобрать лучший билд для персонажа.\nВыберите игру:",
        reply_markup=game_keyboard()
    )
    await state.set_state(BuildStates.choose_game)

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Диалог сброшен.\nВыберите игру:",
        reply_markup=game_keyboard()
    )
    await state.set_state(BuildStates.choose_game)

@dp.callback_query(F.data.startswith("game:"))
async def cb_choose_game(callback: types.CallbackQuery, state: FSMContext):
    game = callback.data.split(":", 1)[1]
    cache = load_cache()
    if not is_cache_valid(cache):
        cache = update_cache()
    game_data = cache["game_data"].get(game)
    if not game_data:
        await callback.message.edit_text("Данные по игре не найдены. Попробуйте позже.")
        return
    elements = get_elements(game_data)
    await state.update_data(game=game)
    await callback.message.edit_text(
        "<b>Выберите путь (элемент):</b>",
        reply_markup=element_keyboard(elements, game_data)
    )
    await state.set_state(BuildStates.choose_element)

@dp.callback_query(F.data.startswith("element:"))
async def cb_choose_element(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    cache = load_cache()
    game_data = cache["game_data"].get(game)
    element = callback.data.split(":", 1)[1]
    characters = get_characters_by_element(game_data, element)
    await state.update_data(element=element)
    await callback.message.edit_text(
        f"<b>Выберите персонажа ({get_path_name(game_data, element)}):</b>",
        reply_markup=character_keyboard(characters)
    )
    await state.set_state(BuildStates.choose_character)

@dp.callback_query(F.data.startswith("char:"))
async def cb_choose_character(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    element = data.get("element")
    cache = load_cache()
    game_data = cache["game_data"].get(game)
    name = callback.data.split(":", 1)[1]
    character = get_character_data(game_data, name)
    if not character:
        await callback.message.edit_text("Персонаж не найден.")
        await state.clear()
        return
    await state.update_data(character=name)
    msg = format_build(character, game_data)
    await callback.message.edit_text(
        msg,
        reply_markup=build_keyboard()
    )
    await state.set_state(BuildStates.show_build)

# --- Навигация назад ---
@dp.callback_query(F.data == "back:game")
async def cb_back_game(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "<b>Выберите игру:</b>",
        reply_markup=game_keyboard()
    )
    await state.set_state(BuildStates.choose_game)

@dp.callback_query(F.data == "back:element")
async def cb_back_element(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    cache = load_cache()
    game_data = cache["game_data"].get(game)
    elements = get_elements(game_data)
    await callback.message.edit_text(
        "<b>Выберите путь (элемент):</b>",
        reply_markup=element_keyboard(elements, game_data)
    )
    await state.set_state(BuildStates.choose_element)

@dp.callback_query(F.data == "back:char")
async def cb_back_char(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    element = data.get("element")
    cache = load_cache()
    game_data = cache["game_data"].get(game)
    characters = get_characters_by_element(game_data, element)
    await callback.message.edit_text(
        f"<b>Выберите персонажа ({get_path_name(game_data, element)}):</b>",
        reply_markup=character_keyboard(characters)
    )
    await state.set_state(BuildStates.choose_character)

@dp.callback_query(F.data == "back:home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "<b>Выберите игру:</b>",
        reply_markup=game_keyboard()
    )
    await state.set_state(BuildStates.choose_game)

# --- Автообновление данных ---
async def auto_update_cache():
    while True:
        update_cache()
        await asyncio.sleep(60 * 60 * 24)

async def start_webhook():
    # Получаем параметры из окружения
    webhook_url = os.getenv("WEBHOOK_URL")
    webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
    host = os.getenv("WEBAPP_HOST", "0.0.0.0")
    port = int(os.getenv("WEBAPP_PORT", 8080))

    print(f"[bot] Запуск в режиме webhook: {webhook_url}{webhook_path}")
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = load_cache()
    if not is_cache_valid(cache):
        print("[bot] Кэш невалиден, обновляю...")
        update_cache()
    else:
        print("[bot] Кэш валиден, запуск бота...")
    asyncio.create_task(auto_update_cache())

    await bot.set_webhook(f"{webhook_url}{webhook_path}")
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=host, port=port)

async def main():
    print("[bot] Запуск main()...")
    if os.getenv("WEBHOOK_URL"):
        await start_webhook()
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        cache = load_cache()
        if not is_cache_valid(cache):
            print("[bot] Кэш невалиден, обновляю...")
            update_cache()
        else:
            print("[bot] Кэш валиден, запуск бота...")
        asyncio.create_task(auto_update_cache())
        await dp.start_polling(bot)

if __name__ == "__main__":
    print("[bot] Запуск через __main__...")
    asyncio.run(main())
