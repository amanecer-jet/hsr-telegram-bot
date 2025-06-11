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

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
CACHE_TTL_HOURS = 24

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
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

def fetch_characters():
    url = BotConfig.GITHUB_DATA_URLS["Honkai: Star Rail"]["characters"]
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def update_cache():
    data = fetch_characters()
    cache = {
        "last_updated": datetime.now().isoformat(),
        "game_data": {
            "Honkai: Star Rail": {
                "characters": data
            }
        }
    }
    save_cache(cache)
    return cache

def get_elements(game_data):
    # Собираем уникальные элементы (пути) из данных персонажей
    elements = set()
    for char in game_data["characters"]:
        if "path" in char and char["path"]:
            elements.add(char["path"])
    return sorted(elements)

def get_characters_by_element(game_data, element):
    return [c["name"] for c in game_data["characters"] if c.get("path") == element]

def get_character_data(game_data, name):
    for c in game_data["characters"]:
        if c.get("name") == name:
            return c
    return None

# --- Клавиатуры ---
def game_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎮 Honkai: Star Rail", callback_data="game:Honkai: Star Rail")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def element_keyboard(elements):
    kb = []
    for el in elements:
        emoji = ""  # Можно добавить эмодзи по названию пути
        kb.append([InlineKeyboardButton(text=f"{emoji}{el}", callback_data=f"element:{el}")])
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
def format_build(character):
    msg = f"<b>{character['name']}</b>\n\n"
    # Реликвии
    relics = character.get("relics", [])
    if relics:
        msg += f"<b>Рекомендуемые реликвии:</b> {relics[0]['name']}\n"
        if len(relics) > 1:
            msg += f"<b>Альтернатива:</b> {relics[1]['name']}\n"
    # Планарные украшения
    planars = character.get("planarOrnaments", [])
    if planars:
        msg += f"<b>Планарные украшения:</b> {planars[0]['name']}\n"
        if len(planars) > 1:
            msg += f"<b>Альтернатива:</b> {planars[1]['name']}\n"
    # Конусы
    cones = character.get("lightCones", [])
    cone_5 = next((c for c in cones if c.get("rarity") == 5), None)
    cone_4 = next((c for c in cones if c.get("rarity") == 4), None)
    cone_3 = next((c for c in cones if c.get("rarity") == 3), None)
    if cone_5:
        msg += f"<b>5★ конус:</b> {cone_5['name']}\n"
    if cone_4:
        msg += f"<b>4★ конус:</b> {cone_4['name']}\n"
    if cone_3:
        msg += f"<b>3★ конус:</b> {cone_3['name']}\n"
    else:
        # Если нет 3★, показать второй 4★, если есть
        cones_4 = [c for c in cones if c.get("rarity") == 4]
        if len(cones_4) > 1:
            msg += f"<b>4★ конус (альтернатива):</b> {cones_4[1]['name']}\n"
    # Параметры реликвий (основные характеристики)
    main_stats = character.get("mainStats", [])
    if main_stats:
        msg += "<b>Параметры реликвий:</b>\n"
        for stat in main_stats:
            slot = stat.get("slot", "")
            values = stat.get("values", [])
            if slot and values:
                msg += f"- {slot}: {', '.join(values)}\n"
    # Рекомендуемые параметры персонажа
    rec_stats = character.get("recommendedStats", [])
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
        reply_markup=element_keyboard(elements)
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
        f"<b>Выберите персонажа ({element}):</b>",
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
    msg = format_build(character)
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
        reply_markup=element_keyboard(elements)
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
        f"<b>Выберите персонажа ({element}):</b>",
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

async def main():
    print("[bot] Запуск main()...")
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
