import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv
from parser import load_cache, is_cache_valid, update_cache, get_elements, get_characters_by_element

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM States ---
class BuildStates(StatesGroup):
    choose_element = State()
    choose_character = State()

# --- Кнопки ---
def make_keyboard(options, add_back=False):
    keyboard = [[KeyboardButton(text=o)] for o in options]
    if add_back:
        keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- Форматирование билда ---
def format_build(character):
    build = character.get("build", {})
    msg = f"<b>Билд для {character['name']}</b>\n\n"
    # Световые конусы
    cones = build.get("light_cones", {})
    if cones:
        msg += "<b>Световые конусы:</b>\n"
        for rank, names in cones.items():
            msg += f"{rank}: {', '.join(names)}\n"
        msg += "\n"
    # Реликвии
    relics = build.get("relics", {})
    if relics:
        msg += "<b>Реликвии:</b>\n"
        for rank, names in relics.items():
            msg += f"{rank}: {', '.join(names)}\n"
        msg += "\n"
    # Планарные украшения
    ornaments = build.get("planar_ornaments", {})
    if ornaments:
        msg += "<b>Планарные украшения:</b>\n"
        for rank, names in ornaments.items():
            msg += f"{rank}: {', '.join(names)}\n"
        msg += "\n"
    # Основные характеристики
    main_stats = build.get("main_stats", {})
    if main_stats:
        msg += "<b>Основные характеристики:</b>\n"
        for slot, stats in main_stats.items():
            msg += f"- {slot}: {', '.join(stats)}\n"
        msg += "\n"
    # Доп. характеристики
    sub_stats = build.get("sub_stats", [])
    if sub_stats:
        msg += "<b>Доп. характеристики (приоритет):</b>\n"
        for i, stat in enumerate(sub_stats, 1):
            msg += f"{i}. {stat}\n"
    return msg.strip()

# --- FSM-диалог ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    cache = load_cache()
    elements = get_elements(cache)
    if not elements:
        await message.answer("Данные ещё не загружены. Попробуйте позже.")
        return
    await message.answer("Выберите путь персонажа:", reply_markup=make_keyboard(elements))
    await state.set_state(BuildStates.choose_element)

@dp.message(BuildStates.choose_element)
async def choose_element(message: types.Message, state: FSMContext):
    cache = load_cache()
    elements = get_elements(cache)
    # Обработка кнопки 'Назад' (на этом этапе не нужна)
    if message.text not in elements:
        await message.answer("Пожалуйста, выберите путь с помощью кнопки.", reply_markup=make_keyboard(elements))
        return
    await state.update_data(element=message.text)
    chars = get_characters_by_element(cache, message.text)
    if not chars:
        await message.answer("Нет персонажей для этого пути.", reply_markup=make_keyboard(elements))
        return
    await message.answer("Выберите персонажа:", reply_markup=make_keyboard(chars, add_back=True))
    await state.set_state(BuildStates.choose_character)

@dp.message(BuildStates.choose_character)
async def choose_character(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cache = load_cache()
    chars = get_characters_by_element(cache, data.get("element"))
    # Обработка кнопки 'Назад'
    if message.text == "⬅️ Назад":
        elements = get_elements(cache)
        await message.answer("Выберите путь персонажа:", reply_markup=make_keyboard(elements))
        await state.set_state(BuildStates.choose_element)
        return
    if message.text not in chars:
        await message.answer("Пожалуйста, выберите персонажа с помощью кнопки.", reply_markup=make_keyboard(chars, add_back=True))
        return
    # Найти персонажа
    character = next((c for c in cache["characters"] if c["name"] == message.text and c["path"] == data.get("element")), None)
    if not character:
        await message.answer("Персонаж не найден.")
        await state.clear()
        return
    msg = format_build(character)
    await message.answer(msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await message.answer("Диалог отменён.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.message(Command("update"))
async def cmd_update(message: types.Message):
    if ADMIN_CHAT_ID and str(message.from_user.id) != str(ADMIN_CHAT_ID):
        await message.answer("Нет прав.")
        return
    await message.answer("Обновляю кэш, подождите...")
    await update_cache()
    await message.answer("Кэш обновлён!")

async def auto_update_cache():
    while True:
        await update_cache()
        await asyncio.sleep(60 * 60 * 24)  # раз в сутки

async def main():
    os.makedirs("data", exist_ok=True)  # Гарантируем наличие папки data
    cache = load_cache()
    if not is_cache_valid(cache):
        await update_cache()
    # Запускаем автообновление кэша
    asyncio.create_task(auto_update_cache())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
