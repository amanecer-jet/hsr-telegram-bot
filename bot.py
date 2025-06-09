import os
import logging
import json
import asyncio
import aiohttp
from typing import Dict, List, Optional
from dataclasses import dataclass
from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import time
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '8069265891:AAGz-0Q_AXgxvfLhC1CPTTiOo6OBIh3kpcg')
WEBHOOK_URL = f"https://hsr-telegram-bot-production.up.railway.app/webhook"
PORT = int(os.getenv('PORT', 8080))
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Данные для игр и элементов
GAMES = {
    'hsr': 'Honkai Star Rail',
    'gi': 'Genshin Impact'
}

HSR_ELEMENTS = {
    'fire': '🔥 Огонь',
    'ice': '❄️ Лёд', 
    'lightning': '⚡ Молния',
    'wind': '💨 Ветер',
    'physical': '⚔️ Физический',
    'quantum': '🌌 Квант',
    'imaginary': '🌠 Мнимый'
}

@dataclass
class Character:
    name: str
    element: str
    path: str
    rarity: int
    builds: List[Dict]

class HSRDataParser:
    def __init__(self):
        self.characters_data = {}
        self.base_url = "https://www.prydwen.gg"
        
    async def fetch_characters_data(self) -> Dict:
        """Получение данных о персонажах с API"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://www.prydwen.gg/page-data/sq/d/2951347825.json"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self.parse_characters_data(data)
                    else:
                        logger.error(f"Ошибка при получении данных: {response.status}")
                        return self.get_fallback_data()
        except Exception as e:
            logger.error(f"Ошибка при парсинге данных: {e}")
            return self.get_fallback_data()
    
    def get_fallback_data(self) -> Dict:
        """Резервные данные персонажей"""
        return {
            'fire': [
                Character(
                    name="Himeko",
                    element="fire",
                    path="Erudition",
                    rarity=5,
                    builds=self.create_default_builds("fire", "erudition")
                ),
                Character(
                    name="Hook",
                    element="fire",
                    path="Destruction",
                    rarity=4,
                    builds=self.create_default_builds("fire", "destruction")
                )
            ],
            'ice': [
                Character(
                    name="Gepard",
                    element="ice",
                    path="Preservation",
                    rarity=5,
                    builds=self.create_default_builds("ice", "preservation")
                ),
                Character(
                    name="Herta",
                    element="ice",
                    path="Erudition",
                    rarity=4,
                    builds=self.create_default_builds("ice", "erudition")
                )
            ],
            'lightning': [
                Character(
                    name="Kafka",
                    element="lightning",
                    path="Nihility",
                    rarity=5,
                    builds=self.create_default_builds("lightning", "nihility")
                ),
                Character(
                    name="Arlan",
                    element="lightning",
                    path="Destruction",
                    rarity=4,
                    builds=self.create_default_builds("lightning", "destruction")
                )
            ],
            'wind': [
                Character(
                    name="Dan Heng",
                    element="wind",
                    path="Hunt",
                    rarity=4,
                    builds=self.create_default_builds("wind", "hunt")
                )
            ],
            'physical': [
                Character(
                    name="Clara",
                    element="physical",
                    path="Destruction",
                    rarity=5,
                    builds=self.create_default_builds("physical", "destruction")
                )
            ],
            'quantum': [
                Character(
                    name="Seele",
                    element="quantum",
                    path="Hunt",
                    rarity=5,
                    builds=self.create_default_builds("quantum", "hunt")
                )
            ],
            'imaginary': [
                Character(
                    name="Welt",
                    element="imaginary",
                    path="Nihility",
                    rarity=5,
                    builds=self.create_default_builds("imaginary", "nihility")
                )
            ]
        }
    
    def parse_characters_data(self, data: Dict) -> Dict:
        """Парсинг данных персонажей"""
        characters = {}
        try:
            if 'data' in data and 'allContentfulHsrCharacter' in data['data']:
                char_data = data['data']['allContentfulHsrCharacter']['nodes']
                
                for char in char_data:
                    char_name = char.get('name', '')
                    char_element = char.get('element', '').lower()
                    char_path = char.get('path', '')
                    char_rarity = char.get('rarity', 0)
                    try:
                        char_rarity = int(char_rarity)
                    except Exception:
                        char_rarity = 0
                    
                    builds = self.create_default_builds(char_element, char_path)
                    
                    character = Character(
                        name=char_name,
                        element=char_element,
                        path=char_path,
                        rarity=char_rarity,
                        builds=builds
                    )
                    
                    if char_element not in characters:
                        characters[char_element] = []
                    characters[char_element].append(character)
                    
        except Exception as e:
            logger.error(f"Ошибка при парсинге персонажей: {e}")
            return self.get_fallback_data()
            
        return characters if characters else self.get_fallback_data()
    
    def create_default_builds(self, element: str, path: str) -> List[Dict]:
        """Создание дефолтных билдов на основе элемента и пути"""
        builds = []
        
        if path.lower() in ['destruction', 'hunt']:
            builds.append({
                'name': 'DPS Build',
                'relics': {
                    'main': 'Champion of Streetwise Boxing / Musketeer of Wild Wheat',
                    'alternative': 'Wastelander of Banditry Desert'
                },
                'stats': {
                    'body': 'CRIT Rate / CRIT DMG',
                    'feet': 'ATK% / Speed',
                    'sphere': 'ATK% / Elemental DMG',
                    'rope': 'ATK% / Energy Regen'
                },
                'substats': 'CRIT Rate > CRIT DMG > ATK% > Speed > Break Effect'
            })
        elif path.lower() == 'nihility':
            builds.append({
                'name': 'DOT Build',
                'relics': {
                    'main': 'Prisoner in Deep Confinement',
                    'alternative': 'Musketeer of Wild Wheat'
                },
                'stats': {
                    'body': 'Effect Hit Rate / ATK%',
                    'feet': 'ATK% / Speed',
                    'sphere': 'ATK% / Elemental DMG',
                    'rope': 'ATK% / Energy Regen'
                },
                'substats': 'Effect Hit Rate > ATK% > Speed > CRIT Rate > CRIT DMG'
            })
        elif path.lower() in ['abundance', 'preservation']:
            builds.append({
                'name': 'Support Build',
                'relics': {
                    'main': 'Passerby of Wandering Cloud / Musketeer of Wild Wheat',
                    'alternative': 'Knight of Purity Palace'
                },
                'stats': {
                    'body': 'HP% / DEF% / Healing Bonus',
                    'feet': 'Speed / HP% / DEF%',
                    'sphere': 'HP% / DEF%',
                    'rope': 'Energy Regen / HP% / DEF%'
                },
                'substats': 'Speed > HP% > DEF% > Effect RES > Energy Regen'
            })
        elif path.lower() == 'harmony':
            builds.append({
                'name': 'Buffer Build',
                'relics': {
                    'main': 'Messenger Traversing Hackerspace / Musketeer of Wild Wheat',
                    'alternative': 'Passerby of Wandering Cloud'
                },
                'stats': {
                    'body': 'HP% / DEF% / Effect Hit Rate',
                    'feet': 'Speed',
                    'sphere': 'HP% / DEF%',
                    'rope': 'Energy Regen / HP%'
                },
                'substats': 'Speed > HP% > DEF% > Effect Hit Rate > Energy Regen'
            })
        else:
            builds.append({
                'name': 'Universal Build',
                'relics': {
                    'main': 'Musketeer of Wild Wheat',
                    'alternative': 'Passerby of Wandering Cloud'
                },
                'stats': {
                    'body': 'ATK% / HP%',
                    'feet': 'Speed / ATK%',
                    'sphere': 'ATK% / HP%',
                    'rope': 'Energy Regen / ATK%'
                },
                'substats': 'Speed > ATK% > HP% > CRIT Rate > CRIT DMG'
            })
        
        return builds

    def fetch_character_build(self, slug: str) -> dict:
        """Получает билд персонажа с prydwen.gg через JSON, поддерживает оба формата: currentUnit и contentfulHsrCharacter"""
        url = f"{self.base_url}/page-data/star-rail/characters/{slug}/page-data.json"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            logger.info(f"[Prydwen] Запрос по адресу: {url}")
            resp = requests.get(url, headers=headers, timeout=10)
            logger.info(f"[Prydwen] Статус-код: {resp.status_code}")
            logger.info(f"[Prydwen] Ответ (первые 1000 символов): {resp.text[:1000]}")
            resp.raise_for_status()
            data = resp.json()
            result_data = data.get('result', {}).get('data', {})
            # Новый формат (currentUnit)
            if 'currentUnit' in result_data and result_data['currentUnit'].get('nodes'):
                char_data = result_data['currentUnit']['nodes'][0]
            # Старый формат (contentfulHsrCharacter)
            elif 'contentfulHsrCharacter' in result_data:
                char_data = result_data['contentfulHsrCharacter']
            else:
                char_data = {}
            logger.info(f"[Prydwen] char_data: {str(char_data)[:1000]}")
            result = {}
            # 1. Пробуем брать из builds
            builds = char_data.get('builds', [])
            if builds:
                build = builds[0]
                if 'relics' in build:
                    result['relics'] = [r.get('name', '') for r in build['relics'] if r.get('name')]
                if 'lightCones' in build:
                    result['light_cones'] = [lc.get('name', '') for lc in build['lightCones'] if lc.get('name')]
                if 'mainStats' in build:
                    result['main_stats'] = [ms for ms in build['mainStats'] if ms]
                if 'subStats' in build:
                    result['sub_stats'] = [ss for ss in build['subStats'] if ss]
                if 'priority' in build:
                    result['priority'] = [p for p in build['priority'] if p]
            # 2. Если нет builds, пробуем recommended*
            if not result:
                if 'recommendedRelics' in char_data:
                    result['relics'] = [r.get('name', '') for r in char_data.get('recommendedRelics', []) if r.get('name')]
                if 'recommendedLightCones' in char_data:
                    result['light_cones'] = [lc.get('name', '') for lc in char_data.get('recommendedLightCones', []) if lc.get('name')]
                if 'recommendedMainStats' in char_data:
                    result['main_stats'] = [ms for ms in char_data.get('recommendedMainStats', []) if ms]
                if 'recommendedSubStats' in char_data:
                    result['sub_stats'] = [ss for ss in char_data.get('recommendedSubStats', []) if ss]
                if 'recommendedPriority' in char_data:
                    result['priority'] = [p for p in char_data.get('recommendedPriority', []) if p]
            # 3. Добавляем текстовые гайды, если есть
            if 'guide' in char_data and char_data['guide']:
                result['guide'] = char_data['guide']
            if 'review' in char_data and char_data['review']:
                result['review'] = char_data['review']
            if result:
                return result
            return {"error": "No build or recommendations found in JSON."}
        except Exception as e:
            logger.error(f"Ошибка парсинга билдов для {slug}: {e}")
            return {"error": str(e)}

class HSRBot:
    def __init__(self):
        self.data_parser = HSRDataParser()
        self.characters_data = {}
        
    def send_message(self, chat_id, text, reply_markup=None):
        """Отправка сообщения"""
        url = f"{TELEGRAM_API_URL}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return None
    
    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        """Редактирование сообщения"""
        url = f"{TELEGRAM_API_URL}/editMessageText"
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            return None
    
    def answer_callback(self, callback_query_id, text=""):
        """Ответ на callback query"""
        url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
        data = {
            "callback_query_id": callback_query_id
        }
        if text:
            data["text"] = text
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка ответа на callback: {e}")
            return None
    
    async def load_characters_data(self):
        """Загрузка данных персонажей"""
        if not self.characters_data:
            self.characters_data = await self.data_parser.fetch_characters_data()
            logger.info("Данные персонажей загружены")
    
    def handle_start(self, message):
        """Обработчик команды /start"""
        chat_id = message['chat']['id']
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "🎮 Honkai Star Rail", "callback_data": "game_hsr"}],
                [{"text": "🗡️ Genshin Impact", "callback_data": "game_gi"}]
            ]
        }
        
        welcome_text = (
            "👋 Добро пожаловать в бота для получения информации о сборках персонажей!\n\n"
            "Выберите игру, для которой нужна информация о персонажах:"
        )
        
        self.send_message(chat_id, welcome_text, keyboard)
    
    async def handle_callback(self, callback_query):
        """Обработчик callback запросов"""
        chat_id = callback_query['message']['chat']['id']
        message_id = callback_query['message']['message_id']
        data = callback_query['data']
        callback_id = callback_query['id']
        
        self.answer_callback(callback_id)
        
        if data.startswith("game_"):
            await self.handle_game_selection(chat_id, message_id, data)
        elif data.startswith("element_"):
            await self.handle_element_selection(chat_id, message_id, data)
        elif data.startswith("char_"):
            await self.handle_character_selection(chat_id, message_id, data)
        elif data == "back_to_games":
            await self.back_to_games(chat_id, message_id)
        elif data == "back_to_elements":
            await self.back_to_elements(chat_id, message_id)
    
    async def handle_game_selection(self, chat_id, message_id, data: str):
        """Обработка выбора игры"""
        game = data.split("_")[1]
        
        if game == "hsr":
            # Загружаем данные персонажей если их еще нет
            await self.load_characters_data()
            
            # Показываем элементы
            keyboard = {"inline_keyboard": []}
            for element_key, element_name in HSR_ELEMENTS.items():
                if element_key in self.characters_data:
                    keyboard["inline_keyboard"].append([{
                        "text": element_name,
                        "callback_data": f"element_{element_key}"
                    }])
            
            keyboard["inline_keyboard"].append([{
                "text": "◀️ Назад",
                "callback_data": "back_to_games"
            }])
            
            self.edit_message(
                chat_id, message_id,
                "🎮 Honkai Star Rail\n\nВыберите элемент персонажа:",
                keyboard
            )
        
        elif game == "gi":
            keyboard = {"inline_keyboard": [[{
                "text": "◀️ Назад",
                "callback_data": "back_to_games"
            }]]}
            
            self.edit_message(
                chat_id, message_id,
                "🗡️ Genshin Impact\n\n⚠️ Функционал для Genshin Impact находится в разработке.",
                keyboard
            )
    
    async def handle_element_selection(self, chat_id, message_id, data: str):
        """Обработка выбора элемента"""
        element = data.split("_")[1]
        
        if element in self.characters_data:
            characters = self.characters_data[element]
            keyboard = {"inline_keyboard": []}
            
            for char in characters:
                rarity_stars = "⭐" * char.rarity
                keyboard["inline_keyboard"].append([{
                    "text": f"{char.name} {rarity_stars}",
                    "callback_data": f"char_{element}_{char.name}"
                }])
            
            keyboard["inline_keyboard"].append([{
                "text": "◀️ Назад",
                "callback_data": "back_to_elements"
            }])
            
            element_name = HSR_ELEMENTS.get(element, element.title())
            self.edit_message(
                chat_id, message_id,
                f"{element_name}\n\nВыберите персонажа:",
                keyboard
            )
    
    async def handle_character_selection(self, chat_id, message_id, data: str):
        """Обработка выбора персонажа"""
        parts = data.split("_", 2)
        element = parts[1]
        char_name = parts[2]
        
        # Получаем slug для prydwen.gg с помощью функции
        slug = get_prydwen_slug(char_name)
        
        # Парсим билд с сайта
        build = self.data_parser.fetch_character_build(slug)
        
        if build and not build.get("error"):
            message = self.format_parsed_build(char_name, build)
        else:
            message = f"Не удалось получить билд для {char_name}."
            if build and build.get("error"):
                message += f"\nОшибка: {build['error']}"
        
        keyboard = {"inline_keyboard": [[{
            "text": "◀️ Назад",
            "callback_data": f"element_{element}"
        }]]}
        
        self.edit_message(chat_id, message_id, message, keyboard)
    
    def format_parsed_build(self, char_name: str, build: dict) -> str:
        """Форматирует билд, полученный с prydwen.gg"""
        message = f"<b>{char_name}</b>\n\n"
        if build.get('relics'):
            message += "<b>Relics:</b>\n" + "\n".join(f"• {r}" for r in build['relics']) + "\n\n"
        if build.get('light_cones'):
            message += "<b>Light Cones:</b>\n" + "\n".join(f"• {c}" for c in build['light_cones']) + "\n\n"
        if build.get('main_stats'):
            message += "<b>Main Stats:</b>\n" + "\n".join(f"• {s}" for s in build['main_stats']) + "\n\n"
        if build.get('sub_stats'):
            message += "<b>Sub Stats:</b>\n" + "\n".join(f"• {s}" for s in build['sub_stats']) + "\n\n"
        if build.get('priority'):
            message += "<b>Priority:</b>\n" + "\n".join(f"• {p}" for p in build['priority']) + "\n\n"
        if isinstance(build.get('guide'), str) and build['guide']:
            message += "<b>Guide:</b>\n" + build['guide'][:1500] + ("..." if len(build['guide']) > 1500 else "") + "\n\n"
        if isinstance(build.get('review'), str) and build['review']:
            message += "<b>Review:</b>\n" + build['review'][:1500] + ("..." if len(build['review']) > 1500 else "") + "\n\n"
        return message.strip()
    
    async def back_to_games(self, chat_id, message_id):
        """Возврат к выбору игры"""
        keyboard = {
            "inline_keyboard": [
                [{"text": "🎮 Honkai Star Rail", "callback_data": "game_hsr"}],
                [{"text": "🗡️ Genshin Impact", "callback_data": "game_gi"}]
            ]
        }
        
        self.edit_message(
            chat_id, message_id,
            "Выберите игру, для которой нужна информация о персонажах:",
            keyboard
        )
    
    async def back_to_elements(self, chat_id, message_id):
        """Возврат к выбору элементов"""
        keyboard = {"inline_keyboard": []}
        for element_key, element_name in HSR_ELEMENTS.items():
            if element_key in self.characters_data:
                keyboard["inline_keyboard"].append([{
                    "text": element_name,
                    "callback_data": f"element_{element_key}"
                }])
        
        keyboard["inline_keyboard"].append([{
            "text": "◀️ Назад",
            "callback_data": "back_to_games"
        }])
        
        self.edit_message(
            chat_id, message_id,
            "🎮 Honkai Star Rail\n\nВыберите элемент персонажа:",
            keyboard
        )

def get_prydwen_slug(char_name: str) -> str:
    # Удаляем спецсимволы и лишние пробелы
    slug = char_name.lower()
    slug = re.sub(r'[•.,\'’]', '', slug)
    slug = re.sub(r'\s+', ' ', slug)
    slug = slug.strip().replace(' ', '-')
    return slug

# Flask приложение
app = Flask(__name__)
bot = HSRBot()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Обработчик webhook"""
    if request.method == 'GET':
        return 'Webhook работает! ✅', 200
    
    if request.method == 'POST':
        try:
            update = request.get_json()
            
            if not update:
                return 'OK', 200
            
            logger.info(f"Получен update: {json.dumps(update, ensure_ascii=False, indent=2)}")
            
            # Обработка обычных сообщений
            if 'message' in update:
                message = update['message']
                text = message.get('text', '')
                
                if text == '/start':
                    bot.handle_start(message)
                else:
                    # Обычные сообщения
                    chat_id = message['chat']['id']
                    response_text = f"Вы написали: <b>{text}</b>\n\nИспользуйте /start для начала работы с ботом."
                    bot.send_message(chat_id, response_text)
            
            # Обработка callback запросов
            elif 'callback_query' in update:
                callback_query = update['callback_query']
                
                # Создаем event loop для async функций
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(bot.handle_callback(callback_query))
                loop.close()
            
            return 'OK', 200
            
        except Exception as e:
            logger.error(f"Ошибка обработки webhook: {e}")
            return 'Error', 500

@app.route('/')
def index():
    """Главная страница"""
    return """
    <h1>HSR Telegram Bot</h1>
    <p>Бот для получения информации о сборках персонажей Honkai Star Rail</p>
    <p><a href="/webhook">Проверить webhook</a></p>
    <p><a href="/status">Проверить статус</a></p>
    """

@app.route('/status')
def status():
    """Проверка статуса бота"""
    try:
        response = requests.get(f"{TELEGRAM_API_URL}/getMe")
        bot_info = response.json()
        
        webhook_response = requests.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
        webhook_info = webhook_response.json()
        
        return jsonify({
            "bot_status": "active",
            "bot_info": bot_info,
            "webhook_info": webhook_info
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def setup_webhook():
    """Установка webhook"""
    try:
        # Удаляем старый webhook
        delete_response = requests.post(f"{TELEGRAM_API_URL}/deleteWebhook")
        logger.info(f"Удаление webhook: {delete_response.json()}")
        
        # Устанавливаем новый webhook
        webhook_data = {
            "url": WEBHOOK_URL,
            "max_connections": 40,
            "allowed_updates": ["message", "callback_query"]
        }
        
        response = requests.post(f"{TELEGRAM_API_URL}/setWebhook", json=webhook_data)
        result = response.json()
        
        if result.get('ok'):
            logger.info(f"Webhook установлен: {WEBHOOK_URL}")
        else:
            logger.error(f"Ошибка установки webhook: {result}")
            
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при установке webhook: {e}")
        return None

if __name__ == '__main__':
    # Установка webhook при запуске
    logger.info("Запуск HSR бота...")
    setup_result = setup_webhook()
    
    if setup_result and setup_result.get('ok'):
        logger.info("Бот запущен и готов к работе!")
    else:
        logger.error("Ошибка при запуске бота!")
    
    # Запуск Flask приложения
    app.run(host='0.0.0.0', port=PORT, debug=False)