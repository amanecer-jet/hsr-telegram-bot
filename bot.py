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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BufferedInputFile
from dotenv import load_dotenv
from datetime import datetime, timedelta
from config import BotConfig
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import threading
import re
from aiogram.exceptions import TelegramBadRequest
import random
import html
import io
from generate_card import generate_card, generate_profile_card
from hsr_profile import fetch_profile
from card_renderer import render_card

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
CACHE_TTL_HOURS = 24

ART_DIR = "icon/character"
art_map = {
    "Ахерон": "Acheron.png",
    "Арлан": "Arlan.png",
    "Аста": "Asta.png",
    "Байлу": "Bailu.png",
    "Броня": "Bronya.png",
    "Герта": "Herta.png",
    "Гепард": "Gepard.png",
    "Гуйнайфэнь": "Guinaifei.png",
    "Дань Хэн": "Dan Heng.png",
    "Дань Хэн: Пожиратель Луны": "Imbibitor Lunae.png",
    "Зеле": "Seele.png",
    "Кафка": "Kafka.png",
    "Лука": "Luka.png",
    "Лоча": "Luocha.png",
    "Март 7": "march 7.png",
    "Март 7 (Воображение)": "Mart 7 Imaginary.png",
    "Наташа": "Natasha.png",
    "Пела": "Pela.png",
    "Сервал": "Serval.png",
    "Серебряный Волк": "Silver Wolf.png",
    "Топаз и Счетовод": "Topaz.png",
    "Тинъюнь": "Tingyung.png",
    "Цзин Юань": "Jing Yuan.png",
    "Цзинлю": "Jingliu.png",
    "Цинцюэ": "Qinque.png",
    "Ханья": "Hanua.png",
    "Химеко": "Himeko.png",
    "Хохо": "Huo-huo.png",
    "Хуохуо": "Huo-huo.png",
    "Хук": "Hook.png",
    "Рысь": "Lynx.png",
    "Сюэи": "Xuei.png",
    "Цзяоцю": "Jiaoqu.png",
    "Фэйсяо": "Feixiao.png",
    "Юньли": "Yunli.png",
    "Линша": "Lingsha.png",
    "Моцзэ": "Moze.png",
    "Фуга": "Fugue.png"
}

# --- переключатель пола для картинок Первопроходца ---
_tb_toggle = {}

def get_art_path(character_name, art_map=art_map, art_dir=ART_DIR):
    """Возвращает путь к картинке персонажа.
    1) По словарю art_map → icon/character/<filename>
    2) По id из StarRailRes → icon/character/<id>.png
    """
    # 1. явное соответствие
    filename = art_map.get(character_name)
    if filename:
        cand = os.path.join(art_dir, filename)
        if os.path.exists(cand):
            return cand
    # 2. пробуем по id из characters.json
    try:
        cache = load_cache()
        game_data = cache["game_data"].get("Honkai: Star Rail", {})
        char = next((c for c in game_data.get("characters", {}).values() if c.get("name") == character_name.split(" (",1)[0]), None)
        if char:
            cand2 = os.path.join("icon", "character", f"{char['id']}.png")
            if os.path.exists(cand2):
                return cand2
    except Exception:
        pass

    # --- Trailblazer особый случай ---
    if character_name.startswith("Первопроходец"):
        # Определяем стихию из скобок
        m = re.search(r"\(([^)]+)\)", character_name)
        elem = m.group(1).strip() if m else ""
        # пары (муж, жен)
        tb_pairs = {
            "Физический": ("8001", "8002"),
            "Огненный":   ("8003", "8004"),
            "Мнимый":     ("8005", "8006"),
            "Ледяной":    ("8007", "8008"),
        }
        pair = tb_pairs.get(elem)
        if pair:
            # чередуем муж/жен каждый вызов
            idx = _tb_toggle.get(elem, 0)
            _tb_toggle[elem] = 1 - idx  # flip
            tb_id = pair[idx]
            cand = os.path.join("icon", "character", f"{tb_id}.png")
            if not os.path.exists(cand):
                # fallback на второе
                tb_id = pair[1-idx]
                cand = os.path.join("icon", "character", f"{tb_id}.png")
            if os.path.exists(cand):
                return cand

    return None

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
    game_menu = State()  # новый хаб выбранной игры
    choose_element = State()
    choose_character = State()
    show_build = State()

# --- FSM для генерации карточки ---
class CardStates(StatesGroup):
    waiting_uid = State()

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
    """Скачивает справочную информацию по игре.

    1. Пытается взять актуальные json-файлы из GitHub (timeout=10 s).
    2. Если запрос упал или истёк таймаут, использует локальную копию из папки
       «data».  Благодаря этому бот сможет запуститься даже без доступа к сети,
       а платформа деплоя не застрянет в состоянии «Waiting for build to start».
    """
    urls = BotConfig.GITHUB_DATA_URLS["Honkai: Star Rail"]
    data: dict[str, dict] = {}
    for key, url in urls.items():
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data[key] = resp.json()
        except Exception as e:
            logging.warning(f"[cache] Не удалось скачать {url}: {e}. Пытаюсь загрузить локальный {key}.json…")
            fallback_path = os.path.join(DATA_DIR, f"{key}.json")
            try:
                with open(fallback_path, encoding="utf-8") as f:
                    data[key] = json.load(f)
            except FileNotFoundError:
                logging.error(f"[cache] Локальный файл {fallback_path} не найден; пропускаю.")
                data[key] = {}
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

# --- Сопоставление русских и английских имён персонажей ---
def build_tag_map(game_data, builds):
    # tag: {"ru": ..., "en": ...}
    tag_map = {}
    # ru: tag -> name
    for char in game_data["characters"].values():
        tag_map[char["tag"]] = {"ru": char["name"]}
    # en: tag -> name
    for build in builds:
        tag = build.get("tag")
        if tag and tag in tag_map:
            tag_map[tag]["en"] = build["name"]
    return tag_map

def find_build_for_character(character, builds):
    # character: объект из StarRailRes
    # builds: список билдов из fribbels
    tag = character.get("tag")
    for build in builds:
        if build.get("tag") == tag:
            return build
    return None

# --- Связывание и поиск данных ---
def get_elements(game_data):
    elements = set()
    for char in game_data["characters"].values():
        if "path" in char and char["path"]:
            elements.add(char["path"])
    return sorted(elements)

def get_path_name(game_data, path_id):
    for path in game_data["paths"].values():
        if path["id"] == path_id:
            return path["name"]
    return path_id

def get_element_name(game_data, element_id):
    for el in game_data["elements"].values():
        if el["id"] == element_id:
            return el["name"]
    return element_id

def get_characters_by_element(game_data, element):
    # Для мульти-путейных персонажей возвращаем имя с путём
    result = []
    for c in game_data["characters"].values():
        if c.get("path") == element:
            name = c["name"]
            # Для Март 7 и Первопроходца добавляем путь в скобках
            if name == "Март 7":
                # Показываем путь (Охота / Сохранение)
                path_name = get_path_name(game_data, c.get("path"))
                name = f"{name} ({path_name})"
            elif name == "Первопроходец" or name == "{NICKNAME}":
                # Для Первопроходца нужна стихия
                elem_name = get_element_name(game_data, c.get("element"))
                name = f"Первопроходец ({elem_name})"
            result.append(name)
    return result

def get_character_data(game_data, name):
    for c in game_data["characters"].values():
        if c.get("name") == name:
            return c
    return None

def get_relic_set_name(game_data, set_id):
    for s in game_data["relic_sets"].values():
        if s["id"] == set_id:
            return s["name"]
    return set_id

def get_planar_name(game_data, set_id):
    for s in game_data["relic_sets"].values():
        if s["id"] == set_id and s.get("type") == "Planar":
            return s["name"]
    return set_id

def get_cone_name(game_data, cone_id):
    for cone in game_data["light_cones"].values():
        if cone["id"] == cone_id:
            return cone["name"], cone.get("rarity", "")
    return cone_id, ""

def get_main_stat_name(game_data, stat_id):
    for stat in game_data["relic_main_affixes"].values():
        if stat["id"] == stat_id:
            # В ru это словарь affixes, но для отображения нужен property
            affixes = stat.get("affixes", {})
            if affixes:
                # Берём первый property
                for affix in affixes.values():
                    return affix.get("property", stat_id)
            return stat_id
    return stat_id

def get_sub_stat_name(game_data, stat_id):
    for stat in game_data["relic_sub_affixes"].values():
        if stat["id"] == stat_id:
            affixes = stat.get("affixes", {})
            if affixes:
                for affix in affixes.values():
                    return affix.get("property", stat_id)
            return stat_id
    return stat_id

# --- Клавиатуры ---
def game_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎮 Honkai: Star Rail", callback_data="game:Honkai: Star Rail")],
        [InlineKeyboardButton(text="🎮 Zenless Zone Zero", callback_data="game:Zenless Zone Zero")],
        [InlineKeyboardButton(text="📬 Подписаться/Отписаться", callback_data="sub:toggle")],
        [InlineKeyboardButton(text="ℹ️ Info", callback_data="info:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def hub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Билды", callback_data="hub:builds")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:game")],
    ])

def card_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="card:back")]
    ])

def info_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💖 Поддержать автора", url="https://www.donationalerts.com/r/perpetuajdh")],
        [InlineKeyboardButton(text="🏠 В начало", callback_data="back:home")]
    ])

def element_keyboard(elements, game_data):
    # Эмодзи для путей
    path_emojis = {
        "Охота": "🏹",
        "Разрушение": "🛤️",
        "Гармония": "🎶",
        "Сохранение": "🛡️",
        "Небытие": "💀",
        "Изобилие": "🌸",
        "Эрудиция": "📚",
        "Память": "🕯️",
        # ... другие пути ...
    }
    kb = []
    for el in elements:
        el_name = get_path_name(game_data, el)
        emoji = path_emojis.get(el_name, "")
        kb.append([InlineKeyboardButton(text=f"{emoji} {el_name}", callback_data=f"element:{el}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:game")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def character_keyboard(characters):
    kb = []
    for ch in characters:
        if "{NICKNAME}" in ch:
            continue
        kb.append([InlineKeyboardButton(text=f"👤 {ch}", callback_data=f"char:{ch}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:element")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_keyboard(show_team_button: bool = False):
    kb = []
    if show_team_button:
        kb.append([InlineKeyboardButton(text="⚔️ Отряды", callback_data="teams:show")])
    kb.append([InlineKeyboardButton(text="🔄 К выбору персонажа", callback_data="back:char")])
    kb.append([InlineKeyboardButton(text="🏠 В начало", callback_data="back:home")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def teams_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К билду", callback_data="teams:back")]
    ])

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

# --- Форматирование билда ---
def format_build_full(character, game_data, build):
    msg = f"<b>{character['name']}</b>\n"
    msg += f"Путь: {get_path_name(game_data, character.get('path'))}\n"
    msg += f"Элемент: {get_element_name(game_data, character.get('element'))}\n\n"
    if not build:
        msg += "<i>Билд не найден.</i>"
        return msg
    # Реликвии
    relics = build.get("relic_sets", [])
    if relics:
        msg += f"<b>Рекомендуемые реликвии:</b> {', '.join([get_relic_set_name(game_data, r) for r in relics])}\n"
    # Планары
    planars = build.get("planar_sets", [])
    if planars:
        msg += f"<b>Планарные украшения:</b> {', '.join([get_relic_set_name(game_data, p) for p in planars])}\n"
    # Конусы
    cones = build.get("light_cones", [])
    if cones:
        cones_str = []
        for cone in cones:
            name, rarity = get_cone_name(game_data, cone)
            cones_str.append(f"{name} ({rarity}★)" if rarity else name)
        msg += f"<b>Рекомендуемые конусы:</b> {', '.join(cones_str)}\n"
    # Основные статы
    main_stats = build.get("main_stats", {})
    if main_stats:
        msg += "<b>Основные статы реликвий:</b>\n"
        for slot, stat_ids in main_stats.items():
            stat_names = [get_main_stat_name(game_data, s) for s in stat_ids]
            msg += f"- {slot}: {', '.join(stat_names)}\n"
    # Субстаты
    sub_stats = build.get("sub_stats", [])
    if sub_stats:
        msg += "<b>Рекомендуемые субстаты:</b> " + ", ".join([get_sub_stat_name(game_data, s) for s in sub_stats]) + "\n"
    # Прочее
    notes = build.get("notes")
    if notes:
        msg += f"\n<i>{notes}</i>"
    return msg.strip()

# --- Генерация билда на основе справочника ---
def generate_build_for_character(character, game_data):
    # 1. Путь и элемент
    path_id = character.get("path")
    element_id = character.get("element")
    path = get_path_name(game_data, path_id)
    element = get_element_name(game_data, element_id)

    # 2. Реликвии (по элементу/роли)
    relic_sets = []
    for relic in game_data["relic_sets"].values():
        # Бонус на нужный элемент или универсальный бонус по роли
        desc = " ".join(relic.get("desc", []))
        if element in desc or path in desc or "урон" in desc or "лечение" in desc or "защита" in desc:
            relic_sets.append(relic["id"])
    # Сортируем по совпадению с элементом, затем по совпадению с ролью
    relic_sets = relic_sets[:2] if relic_sets else [list(game_data["relic_sets"].keys())[0]]

    # 3. Планарные украшения (ищем по универсальности или по ключевым словам)
    planar_sets = []
    for relic in game_data["relic_sets"].values():
        if relic.get("type") == "Planar":
            desc = " ".join(relic.get("desc", []))
            if element in desc or path in desc or "урон" in desc or "лечение" in desc or "защита" in desc:
                planar_sets.append(relic["id"])
    planar_sets = planar_sets[:2] if planar_sets else [r["id"] for r in list(game_data["relic_sets"].values()) if r.get("type") == "Planar"][:2]

    # 4. Конусы (по пути и редкости)
    cones = [cone["id"] for cone in game_data["light_cones"].values() if cone.get("path") == path_id]
    cones_5 = [c for c in cones if get_cone_name(game_data, c)[1] == 5]
    cones_4 = [c for c in cones if get_cone_name(game_data, c)[1] == 4]
    cones_3 = [c for c in cones if get_cone_name(game_data, c)[1] == 3]
    cones = cones_5[:1] + cones_4[:1] + cones_3[:1]

    # 5. Основные статы (по типу слота)
    main_stats = {
        "Голова": ["HPDelta"],
        "Руки": ["AttackDelta"],
        "Тело": ["AttackAddedRatio", "CriticalChanceBase", "CriticalDamageBase", "HealRatioBase", "StatusProbabilityBase"],
        "Ноги": ["SpeedDelta", "AttackAddedRatio"],
        "Сфера": [f"{element}AddedRatio", "HPAddedRatio", "AttackAddedRatio"],
        "Канат": ["SPRatioBase", "AttackAddedRatio", "HPAddedRatio"]
    }
    # 6. Субстаты (универсальные)
    sub_stats = ["CriticalChanceBase", "CriticalDamageBase", "SpeedDelta", "AttackAddedRatio", "HPAddedRatio", "StatusProbabilityBase"]

    # 7. Формируем краткое сообщение
    msg = f"<b>{character['name']}</b>\n"
    msg += f"Путь: {path}\n"
    msg += f"Элемент: {element}\n\n"
    msg += f"<b>Реликвии:</b> {', '.join([get_relic_set_name(game_data, r) for r in relic_sets])}\n"
    if planar_sets:
        msg += f"<b>Планарные украшения:</b> {', '.join([get_relic_set_name(game_data, p) for p in planar_sets])}\n"
    if cones:
        cones_str = []
        for cone in cones:
            name, rarity = get_cone_name(game_data, cone)
            cones_str.append(f"{name} ({rarity}★)" if rarity else name)
        msg += f"<b>Конусы:</b> {', '.join(cones_str)}\n"
    msg += "<b>Основные статы:</b>\n"
    for slot, stats in main_stats.items():
        stat_names = [get_main_stat_name(game_data, s) for s in stats]
        msg += f"- {slot}: {', '.join(stat_names)}\n"
    msg += "<b>Второстаты:</b> " + ", ".join([get_sub_stat_name(game_data, s) for s in sub_stats])
    return msg.strip()

# === ИНТЕГРАЦИЯ best_builds.json ===
BEST_BUILDS_PATH = "best_builds.json"
best_builds = []
builds_by_character = {}

# Потокобезопасная загрузка билдов
builds_lock = threading.Lock()
def load_best_builds():
    global best_builds, builds_by_character
    with builds_lock:
        try:
            with open(BEST_BUILDS_PATH, encoding="utf-8") as f:
                best_builds = json.load(f)
            builds_by_character = {}
            for build in best_builds:
                name = build["character"].strip().lower()
                builds_by_character.setdefault(name, []).append(build)
            logging.info(f"Загружено {len(best_builds)} билдов из {BEST_BUILDS_PATH}")
        except Exception as e:
            logging.warning(f"Не удалось загрузить {BEST_BUILDS_PATH}: {e}")
            best_builds = []
            builds_by_character = {}

# Загружаем при старте
load_best_builds()

def get_builds_for_character(name):
    key = name.strip().lower()
    builds = builds_by_character.get(key)
    if builds:
        return builds

    # --- Фолбэк для вариаций Первопроходца и близких имён ---
    base = key.split(" (", 1)[0]
    candidates = [v for k,v in builds_by_character.items() if k.startswith(base)]
    if candidates:
        # flatten and return first list (they are already list per key)
        return candidates[0]
    return []

def format_best_build(build, include_team: bool = True):
    # Заголовок: имя, редкость, путь, элемент
    name = build.get("character", "")
    rarity = build.get("analytics", {}).get("rarity", "")
    path = build.get("analytics", {}).get("path", "")
    element = build.get("analytics", {}).get("element", "")
    # Эмодзи для пути и элемента (можно расширить)
    path_emoji = "🛤️"
    element_emoji = "🌪️"
    rarity_emoji = "⭐️"
    header = f"<b>{name}</b> | {rarity_emoji} <b>{rarity}</b> | {path_emoji} <b>{path}</b> | {element_emoji} <b>{element}</b>"
    def to_html(text):
        if not text:
            return ""
        # Жирный: *текст* → <b>текст</b>
        text = re.sub(r'\*(.*?)\*', r'<b>\1</b>', text)
        # Курсив: _текст_ → <i>текст</i>, только если ровно по одному подчёркиванию с каждой стороны и не двойные
        text = re.sub(r'(?<!_)_(?!_)([^_]+?)(?<!_)_(?!_)', r'<i>\1</i>', text)
        # Убрать двойные подчёркивания в начале/конце (например, __Имя_ → <i>Имя</i>)
        text = re.sub(r'__([^_]+)_', r'<i>\1</i>', text)
        # Зачёркнутый: ~текст~ → текст
        text = re.sub(r'~(.*?)~', r' \1 ', text)
        # Код: ```код``` → <code>код</code>
        text = re.sub(r'```(.*?)```', r'<code>\1</code>', text, flags=re.DOTALL)
        # Ссылки: [текст](url) → <a href="url">текст</a>
        text = re.sub(r'\[(.*?)\]\((https?://[^\s]+)\)', r'<a href="\2">\1</a>', text)
        return text
    parts = [
        header,
        to_html(build.get("best_relic_pretty", "")),
        to_html(build.get("alt_relic_pretty", "")),
        to_html(build.get("best_5_lc_pretty", "")),
        to_html(build.get("best_4_lc_pretty", "")),
        to_html(build.get("best_planar_pretty", "")),
        to_html(build.get("alt_planar_pretty", "")),
        to_html(build.get("main_stats_pretty", "")),
        to_html(build.get("recommended_stats_pretty", "")),
        to_html(build.get("recommended_substats_pretty", "")),
        to_html(build.get("best_teammates_pretty", "")),
        to_html(build.get("team_pretty", "")) if include_team else "",
        to_html(build.get("role_pretty", ""))
    ]
    return "\n".join([p for p in parts if p])

# === Helper: sanitize caption for Telegram ===
def sanitize_caption(text: str) -> str:
    """Готовит текст для отправки в подписи Telegram.
    1. Экранирует случайные символы «<» перед цифрами/процентами, чтобы Telegram не
       пытался распознать их как HTML-теги (ошибка Unsupported start tag "95").
    2. Сохраняет допустимую HTML-разметку (<b>, <i>,  , <code>, <a>).
    """
    # & заменяем в первую очередь, чтобы не испортить уже экранированные последовательности
    text = text.replace("&lt;", "<").replace("&gt;", ">")  # откатываем двойное экранирование, если было
    # <число  / <%  / <±  → &lt;...
    text = re.sub(r"<(\d)" , r"&lt;\1", text)
    text = re.sub(r"<%", "&lt;%", text)
    # Аналогично для >, но только если перед ней цифра или % без пробела
    text = re.sub(r"(\d)>", r"\1&gt;", text)
    text = re.sub(r"%>", "%&gt;", text)
    return text

# --- FSM-логика через инлайн-кнопки ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>Привет, я Honkai Helper!</b>\nЯ помогу тебе подобрать билд на нужного тебе персонажа!\nВыберите игру:",
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
    await state.update_data(game=game)
    if game == "Zenless Zone Zero":
        await callback.message.edit_text("Zenless Zone Zero: модуль в разработке. Пожалуйста, подождите будущих обновлений!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back:game")]]))
        return
    # Для Honkai – показываем меню хаба
    await callback.message.edit_text("Выберите действие:", reply_markup=hub_keyboard())
    await state.set_state(BuildStates.game_menu)

@dp.callback_query(F.data == "hub:builds")
async def cb_hub_builds(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    cache = load_cache()
    if not is_cache_valid(cache):
        cache = update_cache()
    game_data = cache["game_data"].get(game)
    if not game_data:
        await callback.message.edit_text("Ошибка загрузки данных, повторите позже.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back:game")]]))
        return
    elements = get_elements(game_data)
    await callback.message.edit_text("<b>Выберите путь (элемент):</b>", reply_markup=element_keyboard(elements, game_data))
    await state.set_state(BuildStates.choose_element)

@dp.callback_query(F.data == "hub:card")
async def cb_hub_card(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CardStates.waiting_uid)
    await callback.message.edit_text("Введите UID игрока, чтобы создать карточку.", reply_markup=card_back_keyboard())

@dp.callback_query(F.data == "card:back")
async def cb_card_back(callback: types.CallbackQuery, state: FSMContext):
    # Всегда отправляем новое сообщение, чтобы избежать ошибки edit_text для photo message
    await bot.send_message(callback.message.chat.id, "Выберите действие:", reply_markup=hub_keyboard())
    await callback.answer()

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
    char_name = callback.data.split(":", 1)[1]
    builds = get_builds_for_character(char_name)
    if builds:
        # Используем первый найденный билд
        build = builds[0]
        build_text_raw = format_best_build(build, include_team=False)
        build_text = sanitize_caption(build_text_raw)

        # Пытаемся найти и отправить изображение персонажа вместе с билдом
        art_path = get_art_path(char_name)
        # Fallback: пробуем получить портрет из локального StarRailRes, если мапы нет
        if (not art_path) or (not os.path.exists(art_path)):
            try:
                # Берём данные игры из кэша для поиска пути к портрету
                data_state = await state.get_data()
                game_key = data_state.get("game")
                cache = load_cache()
                game_data = cache["game_data"].get(game_key, {}) if cache else {}
                char_data = get_character_data(game_data, char_name.split(" (", 1)[0]) if game_data else None
                if char_data and char_data.get("portrait"):
                    candidate = os.path.join("StarRailRes-master", char_data["portrait"])
                    if os.path.exists(candidate):
                        art_path = candidate
            except Exception:
                art_path = None

        if art_path and os.path.exists(art_path):
            photo = FSInputFile(art_path)
            try:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=photo,
                    caption=build_text,
                    reply_markup=build_keyboard(show_team_button=bool(build.get("team_pretty")))
                )
            except TelegramBadRequest:
                # Если подпись слишком длинная или другая HTML-ошибка – отправляем раздельно
                await bot.send_photo(chat_id=callback.message.chat.id, photo=photo)
                await bot.send_message(chat_id=callback.message.chat.id, text=build_text, reply_markup=build_keyboard(show_team_button=bool(build.get("team_pretty"))))
            # Удаляем предыдущее сообщение с кнопками, чтобы не дублировать интерфейс
            try:
                await callback.message.delete()
            except Exception:
                pass
        else:
            # Если картинку не нашли — выводим текст как раньше
            await callback.message.edit_text(build_text, reply_markup=build_keyboard(show_team_button=bool(build.get("team_pretty"))))
        # Сохраняем тексты в state для быстрого доступа к отрядам и билду
        await state.update_data(build_text=build_text, team_text=sanitize_caption(build.get("team_pretty", "Нет примеров отрядов.")))
        return
    await callback.message.edit_text("Приносим извинения, билд не был обнаружен в нашей базе данных! Ожидайте его появления в боте!", reply_markup=build_keyboard())

# --- Навигация назад ---
@dp.callback_query(F.data == "back:game")
async def cb_back_game(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "<b>Привет, я Honkai Helper!</b>\nЯ помогу тебе подобрать билд на нужного тебе персонажа!\nВыберите игру:",
        reply_markup=game_keyboard()
    )
    await state.set_state(BuildStates.choose_game)

@dp.callback_query(F.data == "back:element")
async def cb_back_element(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    cache = load_cache()
    game_data = cache["game_data"].get(game)
    if not game_data:
        # Попытка восстановить кэш
        cache = update_cache()
        game_data = cache["game_data"].get(game)
    if not game_data:
        await safe_edit_text(callback.message, "Ошибка загрузки данных, попробуйте позже.")
        return
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
    if not game_data:
        # Попытка восстановить кэш
        cache = update_cache()
        game_data = cache["game_data"].get(game)
    if not game_data:
        await safe_edit_text(callback.message, "Ошибка загрузки данных, попробуйте позже.")
        return
    characters = get_characters_by_element(game_data, element)
    await safe_edit_text(
        callback.message,
        f"<b>Выберите персонажа ({get_path_name(game_data, element)}):</b>",
        reply_markup=character_keyboard(characters)
    )
    await state.set_state(BuildStates.choose_character)

@dp.callback_query(F.data == "back:home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(
        callback.message,
        "<b>Привет, я Honkai Helper!</b>\nЯ помогу тебе подобрать билд на нужного тебе персонажа!\nВыберите игру:",
        reply_markup=game_keyboard()
    )

@dp.callback_query(F.data == "info:main")
async def cb_info_main(callback: types.CallbackQuery, state: FSMContext):
    info_text = (
        "<b>Привет!</b>\n"
        "Спасибо, что пользуешься моим ботом!\n\n"
        "Бот интегрирован с LLM и <b>генерирует билды самостоятельно</b> на основе базы данных игры: реликвии, персонажи, характеристики и многое другое.\n"
        "Билды <b>обновляются каждый патч</b> и сверяются с актуальными сайтами для максимальной точности.\n\n"
        "Сейчас доступна только Honkai: Star Rail. Мы постепенно добавляем:\n• ресурсы для прокачки\n• анализ патчноутов\n• новые функции.\n\n"
        "В будущем появится <b>Zenless Zone Zero</b> с аналогичным функционалом (модуль в разработке).\n\n"
        "Если у вас есть идеи — делитесь, мы обязательно учтём!\n\n"
        "Мой тгк: <a href=\"https://t.me/perpetuahsr\">перпетуя меж звезд</a>\n"
        "Мой тик-ток: <a href=\"https://www.tiktok.com/@perpetuya\">@perpetuya</a>\n"
        "<a href=\"https://t.me/+CsnFVzw7VxkyYjFi\">Мяу-мяу-мяу</a>"
    )
    await callback.message.edit_text(info_text, reply_markup=info_keyboard())

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

# --- утилита безопасного редактирования ---
async def safe_edit_text(msg: types.Message, text: str, reply_markup=None):
    """Пытается edit_text; если сообщение без текста (фото/док), удаляет и отправляет новое."""
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await msg.delete()
        except Exception:
            pass
        await msg.answer(text, reply_markup=reply_markup)

# === Показ / скрытие отрядов ===
@dp.callback_query(F.data == "teams:show")
async def cb_show_teams(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    team_text: str = data.get("team_text", "Нет примеров отрядов.")
    try:
        # Если сообщение – фото, изменяем подпись, сохраняем изображение
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=team_text,
            reply_markup=teams_keyboard()
        )
    except TelegramBadRequest:
        # Если это не фото-сообщение – используем безопасное редактирование текста
        await safe_edit_text(callback.message, team_text, reply_markup=teams_keyboard())

@dp.callback_query(F.data == "teams:back")
async def cb_back_to_build(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    build_text: str = data.get("build_text", "")
    if not build_text:
        await callback.answer()
        return
    try:
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=build_text,
            reply_markup=build_keyboard(show_team_button=True)
        )
    except TelegramBadRequest:
        await safe_edit_text(callback.message, build_text, reply_markup=build_keyboard(show_team_button=True))

# === ФАЙЛ ПОДПИСЧИКОВ ===
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")

# --- Работа с подписчиками ---

def load_subscribers() -> set[int]:
    """Читает файл подписчиков и возвращает множество chat_id."""
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            ids = json.load(f)
            return set(ids)
    except Exception:
        return set()


def save_subscribers(ids: set[int]):
    """Сохраняет множество chat_id подписчиков."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(ids)), f, ensure_ascii=False)

# --- FSM для админ-рассылки ---
class AdminPostState(StatesGroup):
    waiting_message = State()

# === КОМАНДЫ ПОДПИСКИ ===
@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    subs = load_subscribers()
    if message.chat.id in subs:
        await message.answer("Вы уже подписаны на рассылку ✅")
        return
    subs.add(message.chat.id)
    save_subscribers(subs)
    await message.answer("Вы успешно подписались на рассылку! 📨")


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: types.Message):
    subs = load_subscribers()
    if message.chat.id not in subs:
        await message.answer("Вы ещё не были подписаны на рассылку.")
        return
    subs.discard(message.chat.id)
    save_subscribers(subs)
    await message.answer("Вы успешно отписались от рассылки. ❌")

# === АДМИН-РАССЫЛКА ===
@dp.message(Command("admin_post"))
async def cmd_admin_post(message: types.Message, state: FSMContext):
    # Проверяем ID отправителя
    try:
        admin_id = int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else None
    except Exception:
        admin_id = None
    if admin_id is None or message.from_user.id != admin_id:
        await message.answer("Команда доступна только администратору.")
        return
    await message.answer("Отправьте текст (или фото/документ с подписью), который будет разослан подписчикам.")
    await state.set_state(AdminPostState.waiting_message)


@dp.message(AdminPostState.waiting_message)
async def admin_broadcast(message: types.Message, state: FSMContext):
    try:
        admin_id = int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else None
    except Exception:
        admin_id = None
    if admin_id is None or message.from_user.id != admin_id:
        await message.answer("Команда доступна только администратору.")
        return
    subs = load_subscribers()
    success = 0
    for chat_id in subs:
        try:
            if message.photo:
                # Отправляем последнюю (наибольшего размера) фотографию
                await bot.send_photo(chat_id, photo=message.photo[-1].file_id, caption=message.caption or "")
            elif message.document:
                await bot.send_document(chat_id, document=message.document.file_id, caption=message.caption or "")
            else:
                await bot.send_message(chat_id, message.text or "")
            success += 1
            await asyncio.sleep(0.05)  # небольшой пауза, чтобы избежать flood-limit
        except Exception:
            continue
    await message.answer(f"Рассылка завершена. Успешно отправлено: {success}/{len(subs)}")
    await state.clear()

# === КНОПКА ПОДПИСКИ В ГЛАВНОМ МЕНЮ ===
# Расширяем клавиатуру выбора игры дополнительной кнопкой

# (дублирующаяся функция game_keyboard удалена — используется определение выше)

# --- Обработчик кнопки подписки ---
@dp.callback_query(F.data == "sub:toggle")
async def cb_toggle_sub(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    subs = load_subscribers()
    if user_id in subs:
        subs.discard(user_id)
        save_subscribers(subs)
        await callback.answer("Вы отписались от рассылки.", show_alert=True)
    else:
        subs.add(user_id)
        save_subscribers(subs)
        await callback.answer("Вы подписались на рассылку!", show_alert=True)

# === UID → КАРТОЧКА ПЕРСОНАЖА ===
@dp.message(Command("uid"))
async def cmd_uid(message: types.Message):
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /uid <UID игрока>")
        return
    uid = parts[1]
    await message.answer("Получаю данные аккаунта, пожалуйста, подождите…")
    await send_uid_card(uid, message.chat.id)

# --- Получение профиля игрока по UID ---

def fetch_profile_data(uid: str):
    """Пытается получить публичные данные аккаунта через Enka.Network.

    Возвращает dict или None.
    Формат примера:
    {
        "player": {"nickname": "Имя", "level": 60},
        "characters": [
            {
                "name": "Ахерон",
                "portrait_id": 8002,
                "level": 80,
                "light_cone": "Песнь Двадцати",
                "relic_sets": ["Музыкальные Чары", "Пространство"],
                "stats_text": "АТК 3600 • СКР 150 • КРИТ 70/140"
            },
            ...
        ]
    }
    """
    api_urls = [
        # Mihomo parsed API (самый быстрый и стабильный)
        f"https://api.mihomo.me/sr_info_parsed/{uid}?lang=ru",
        f"https://api.mihomo.me/sr_info_parsed/{uid}?lang=en",
        # Enka legacy fallbacks
        f"https://enka.network/api/hsr/v2/{uid}?lang=ru",
        f"https://enka.network/api/hsr/v2/{uid}?lang=en",
        f"https://enka.network/api/hsr/v1/{uid}?lang=ru",
        f"https://enka.network/api/hsr/v1/{uid}?lang=en",
        f"https://enka.network/api/hsr/{uid}?lang=ru",
        f"https://enka.network/api/hsr/{uid}?lang=en",
    ]
    for url in api_urls:
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code != 200:
                continue
            data = resp.json()
            # Mihomo schema → characters inside data["characters"] (list of dict)
            # Enka schema already partially handled ниже.
            profile = {
                "player": {
                    "nickname": data.get("player", {}).get("name") or data.get("player", {}).get("nickname", "Игрок"),
                    "level": data.get("player", {}).get("level", 0),
                },
                "characters": []
            }
            # В Mihomo персонажи находятся в `characters`, в Enka найдём ниже.
            chars_candidates = [
                data.get("characters"),
                data.get("avatars"),
                data.get("avatarInfoList"),
                data.get("avatarDetailList"),
                data.get("avatar_list"),
                data.get("units")
            ]
            chars_raw = next((c for c in chars_candidates if isinstance(c, list) and c), [])
            if not chars_raw:
                continue  # переходим к следующему URL
            for ch in chars_raw:
                char_name = ch.get("name") or ch.get("characterName") or ch.get("character_name") or "?"
                portrait_id = ch.get("id") or ch.get("avatarId") or ch.get("avatar_id")
                # Light cone
                light_cone = "-"
                if isinstance(ch.get("light_cone"), dict):
                    light_cone = ch["light_cone"].get("name", "-")
                elif isinstance(ch.get("lightCone"), dict):
                    light_cone = ch["lightCone"].get("name", "-")
                relic_sets: list[str] = []
                # Mihomo: relics list inside character.relics
                if ch.get("relics") and isinstance(ch["relics"], list):
                    for r in ch["relics"]:
                        set_name = r.get("setName") or r.get("name") or r.get("set_name")
                        if set_name and set_name not in relic_sets:
                            relic_sets.append(set_name)
                # Stats block (упрощённо)
                stats_txt = ""
                props = ch.get("properties") or ch.get("propMap") or {}
                if isinstance(props, list):
                    props_map = {p.get("name") or p.get("propType"): p.get("value") for p in props}
                elif isinstance(props, dict):
                    props_map = {k: v.get("value") if isinstance(v, dict) else v for k, v in props.items()}
                else:
                    props_map = {}
                atk = int(props_map.get("Attack") or props_map.get("atk") or 0)
                cr = props_map.get("CriticalChance") or props_map.get("critRate") or 0
                cd = props_map.get("CriticalDamage") or props_map.get("critDamage") or 0
                if atk:
                    stats_txt = f"АТК {atk}"
                if cr or cd:
                    stats_txt += f" • КРИТ {round(float(cr),1)}%/{round(float(cd),1)}%"
                profile["characters"].append({
                    "name": char_name,
                    "portrait_id": portrait_id,
                    "level": ch.get("level", 1),
                    "light_cone": light_cone,
                    "relic_sets": relic_sets,
                    "stats_text": stats_txt,
                })
            if profile["characters"]:
                return profile
        except Exception:
            continue
    return None

# --- Обработчики генерации карточки через кнопку ---
@dp.callback_query(F.data == "card:start")
async def cb_card_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CardStates.waiting_uid)
    await callback.message.edit_text(
        "Введите UID игрока, чтобы создать карточку. Отправьте число в ответным сообщением.\n\n⬅️ /cancel для выхода.")

@dp.message(CardStates.waiting_uid)
async def msg_card_uid(message: types.Message, state: FSMContext):
    chat_id = message.chat.id

    # Получаем расширенный профиль (Mihomo)
    profile_raw = fetch_profile(int(message.text.strip()))
    if not profile_raw or not profile_raw.get("characters"):
        # fallback через старую логику
        await message.answer("Генерирую карточку, пожалуйста, подождите…")
        await send_uid_card(message.text.strip(), chat_id)
        await state.clear()
        return

    chars = profile_raw["characters"]
    if len(chars) == 1:
        await message.answer("Генерирую карточку, пожалуйста, подождите…")
        _cache_profile(chat_id, message.text.strip(), profile_raw)
        await send_uid_card(message.text.strip(), chat_id)
        await state.clear()
        return

    # Сохраняем в кеш и предлагаем выбор персонажа
    _cache_profile(chat_id, message.text.strip(), profile_raw)

    kb = []
    row = []
    for idx, ch in enumerate(chars):
        btn = InlineKeyboardButton(text=ch.get("name", f"№{idx+1}"), callback_data=f"cardgen:{message.text.strip()}:{idx}")
        row.append(btn)
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="card:back")])
    await message.answer("Выберите персонажа, для которого создать карточку:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

# --- Callback генерации выбранного персонажа ---
@dp.callback_query(F.data.startswith("cardgen:"))
async def cb_card_generate(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Неверные данные", show_alert=True)
        return
    uid, idx_str = parts[1], parts[2]
    if not idx_str.isdigit():
        await callback.answer("Неверные данные", show_alert=True)
        return
    char_idx = int(idx_str)
    chat_id = callback.message.chat.id
    profile = _get_cached_profile(chat_id, uid)
    if not profile:
        await callback.answer("Сессия устарела, попробуйте снова.", show_alert=True)
        return

    await callback.message.edit_text("Генерирую карточку, пожалуйста, подождите…")

    try:
        img = generate_profile_card(profile, uid, char_idx)
    except Exception:
        # fallback на старый метод
        await send_uid_card(uid, chat_id)
        return

    bio = io.BytesIO()
    img.save(bio, "PNG")
    photo_input = BufferedInputFile(bio.getvalue(), filename="card.png")
    await bot.send_photo(chat_id=chat_id, photo=photo_input, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="card:back")]]))

# --- Профильный кеш для выбора персонажей ---
from datetime import datetime, timedelta
PROFILE_CACHE: dict[tuple[int, str], tuple[dict, datetime]] = {}

# Время жизни данных профиля (минуты)
PROFILE_TTL = timedelta(minutes=5)


def _cache_profile(chat_id: int, uid: str, profile: dict):
    PROFILE_CACHE[(chat_id, uid)] = (profile, datetime.utcnow())


def _get_cached_profile(chat_id: int, uid: str):
    entry = PROFILE_CACHE.get((chat_id, uid))
    if not entry:
        return None
    profile, ts = entry
    if datetime.utcnow() - ts > PROFILE_TTL:
        PROFILE_CACHE.pop((chat_id, uid), None)
        return None
    return profile

# --- Админ-команда для теста карточки ---
@dp.message(Command("card"))
async def cmd_admin_card(message: types.Message):
    if message.from_user.id != int(os.getenv("ADMIN_CHAT_ID", "0")):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /card &lt;uid&gt; [index]", parse_mode="HTML")
        return
    uid = int(parts[1])
    idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    await message.answer("Генерирую карту…")
    profile = fetch_profile(uid)
    if not profile:
        await message.answer("Профиль недоступен")
        return
    img = render_card(profile, idx)
    bio = io.BytesIO()
    img.save(bio, "PNG")
    await bot.send_photo(chat_id=message.chat.id, photo=BufferedInputFile(bio.getvalue(), filename="card.png"))

if __name__ == "__main__":
    print("[bot] Запуск через __main__...")
    asyncio.run(main())
