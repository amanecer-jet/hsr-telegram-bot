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

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

SUBSCRIBERS_FILE = "data/subscribers.json"
SPAM_FILE = "data/antispam.json"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="MarkdownV2")
dp = Dispatcher(storage=MemoryStorage())

md = MarkdownDecoration()

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

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот с актуальными билдами Honkai Star Rail.\n"
        "Команды:\n"
        "/latest — свежие билды\n"
        "/subscribe — подписаться на рассылку\n"
        "/unsubscribe — отписаться"
    )

@dp.message(Command("latest"))
async def cmd_latest(message: Message):
    # Антиспам: не чаще 1 раза в 30 секунд
    antispam = load_json(SPAM_FILE, {})
    user_id = str(message.from_user.id)
    now = datetime.utcnow()
    last = antispam.get(user_id)
    if last and (now - datetime.fromisoformat(last)) < timedelta(seconds=30):
        await message.answer("Пожалуйста, не спамьте! Попробуйте позже.")
        return
    antispam[user_id] = now.isoformat()
    save_json(SPAM_FILE, antispam)

    file = get_latest_build_file()
    if not file:
        await message.answer("Нет свежих билдов.")
        return
    with open(file, "r", encoding="utf-8") as f:
        builds = json.load(f)
    for build in builds[:10]:
        await message.answer(format_build(build))

@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    subs = set(load_json(SUBSCRIBERS_FILE, []))
    subs.add(message.from_user.id)
    save_json(SUBSCRIBERS_FILE, list(subs))
    await message.answer("Вы подписались на ежедневную рассылку!")

@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    subs = set(load_json(SUBSCRIBERS_FILE, []))
    subs.discard(message.from_user.id)
    save_json(SUBSCRIBERS_FILE, list(subs))
    await message.answer("Вы отписались от рассылки.")

@dp.errors()
async def error_handler(update, exception):
    logging.exception(f"Error: {exception}")
    if isinstance(update, Message):
        await update.answer("Произошла ошибка. Попробуйте позже.")
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(ADMIN_CHAT_ID, f"Error: {exception}")
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

async def main():
    asyncio.create_task(daily_broadcast())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
