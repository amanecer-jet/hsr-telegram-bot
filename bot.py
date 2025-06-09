import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
from flask import Flask, request

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '8069265891:AAGz-0Q_AXgxvfLhC1CPTTiOo6OBIh3kpcg')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'hsr-telegram-bot-production.up.railway.app/webhook')
PORT = int(os.getenv('PORT', 8080))

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
            ]
        }
    
    def parse_characters_data(self, data: Dict) -> Dict:
        """Парсинг данных персонажей"""
        characters = {}
        try:
            # Извлекаем данные из JSON структуры prydwen.gg
            if 'data' in data and 'allContentfulHsrCharacter' in data['data']:
                char_data = data['data']['allContentfulHsrCharacter']['nodes']
                
                for char in char_data:
                    char_name = char.get('name', '')
                    char_element = char.get('element', '').lower()
                    char_path = char.get('path', '')
                    char_rarity = char.get('rarity', 0)
                    
                    # Создаем базовую структуру билдов
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
        
        # Базовые билды в зависимости от пути
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
            # Универсальная сборка
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

class HSRBot:
    def __init__(self):
        self.data_parser = HSRDataParser()
        self.characters_data = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        keyboard = [
            [InlineKeyboardButton("🎮 Honkai Star Rail", callback_data="game_hsr")],
            [InlineKeyboardButton("🗡️ Genshin Impact", callback_data="game_gi")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            "👋 Добро пожаловать в бота для получения информации о сборках персонажей!\n\n"
            "Выберите игру, для которой нужна информация о персонажах:"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("game_"):
            await self.handle_game_selection(query, data)
        elif data.startswith("element_"):
            await self.handle_element_selection(query, data)
        elif data.startswith("char_"):
            await self.handle_character_selection(query, data)
        elif data == "back_to_games":
            await self.back_to_games(query)
        elif data == "back_to_elements":
            await self.back_to_elements(query)
    
    async def handle_game_selection(self, query, data: str):
        """Обработка выбора игры"""
        game = data.split("_")[1]
        
        if game == "hsr":
            # Загружаем данные персонажей если их еще нет
            if not self.characters_data:
                await query.edit_message_text("🔄 Загружаю данные персонажей...")
                self.characters_data = await self.data_parser.fetch_characters_data()
            
            # Показываем элементы
            keyboard = []
            for element_key, element_name in HSR_ELEMENTS.items():
                if element_key in self.characters_data:
                    keyboard.append([InlineKeyboardButton(
                        element_name, 
                        callback_data=f"element_{element_key}"
                    )])
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_games")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🎮 Honkai Star Rail\n\nВыберите элемент персонажа:",
                reply_markup=reply_markup
            )
        
        elif game == "gi":
            await query.edit_message_text(
                "🗡️ Genshin Impact\n\n⚠️ Функционал для Genshin Impact находится в разработке.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_games")
                ]])
            )
    
    async def handle_element_selection(self, query, data: str):
        """Обработка выбора элемента"""
        element = data.split("_")[1]
        
        if element in self.characters_data:
            characters = self.characters_data[element]
            keyboard = []
            
            for char in characters:
                rarity_stars = "⭐" * char.rarity
                keyboard.append([InlineKeyboardButton(
                    f"{char.name} {rarity_stars}",
                    callback_data=f"char_{element}_{char.name}"
                )])
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_elements")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            element_name = HSR_ELEMENTS.get(element, element.title())
            await query.edit_message_text(
                f"{element_name}\n\nВыберите персонажа:",
                reply_markup=reply_markup
            )
    
    async def handle_character_selection(self, query, data: str):
        """Обработка выбора персонажа"""
        parts = data.split("_", 2)
        element = parts[1]
        char_name = parts[2]
        
        # Находим персонажа
        character = None
        if element in self.characters_data:
            for char in self.characters_data[element]:
                if char.name == char_name:
                    character = char
                    break
        
        if character:
            # Формируем сообщение с информацией о сборке
            message = self.format_character_build(character)
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data=f"element_{element}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
    
    def format_character_build(self, character: Character) -> str:
        """Форматирование информации о сборке персонажа"""
        rarity_stars = "⭐" * character.rarity
        element_emoji = {
            'fire': '🔥', 'ice': '❄️', 'lightning': '⚡', 'wind': '💨',
            'physical': '⚔️', 'quantum': '🌌', 'imaginary': '🌠'
        }.get(character.element, '⚡')
        
        message = f"<b>{character.name}</b> {rarity_stars}\n"
        message += f"{element_emoji} {character.element.title()} • {character.path.title()}\n\n"
        
        for i, build in enumerate(character.builds):
            message += f"<b>📋 {build['name']}</b>\n\n"
            
            message += "<b>🎯 Реликвии:</b>\n"
            message += f"• Основные: {build['relics']['main']}\n"
            message += f"• Альтернативные: {build['relics']['alternative']}\n\n"
            
            message += "<b>📊 Характеристики:</b>\n"
            for slot, stat in build['stats'].items():
                message += f"• {slot.title()}: {stat}\n"
            
            message += f"\n<b>🔧 Приоритет подстатов:</b>\n{build['substats']}\n"
            
            if i < len(character.builds) - 1:
                message += "\n" + "─"*30 + "\n\n"
        
        return message
    
    async def back_to_games(self, query):
        """Возврат к выбору игры"""
        keyboard = [
            [InlineKeyboardButton("🎮 Honkai Star Rail", callback_data="game_hsr")],
            [InlineKeyboardButton("🗡️ Genshin Impact", callback_data="game_gi")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Выберите игру, для которой нужна информацию о персонажах:",
            reply_markup=reply_markup
        )
    
    async def back_to_elements(self, query):
        """Возврат к выбору элементов"""
        keyboard = []
        for element_key, element_name in HSR_ELEMENTS.items():
            if element_key in self.characters_data:
                keyboard.append([InlineKeyboardButton(
                    element_name, 
                    callback_data=f"element_{element_key}"
                )])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_games")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎮 Honkai Star Rail\n\nВыберите элемент персонажа:",
            reply_markup=reply_markup
        )

# Flask приложение для webhook
app = Flask(__name__)
bot_instance = HSRBot()
application = None

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик webhook"""
    try:
        json_data = request.get_json()
        if json_data:
            update = Update.de_json(json_data, application.bot)
            
            # Создаем новый event loop для обработки update
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(application.process_update(update))
            loop.close()
        
        return 'OK'
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")
        return 'Error', 500

@app.route('/')
def index():
    return 'HSR Bot is running!'

@app.route('/health')
def health():
    return {'status': 'ok', 'bot': 'HSR Telegram Bot'}

def create_app():
    """Создание и настройка приложения"""
    global application
    
    # Создаем приложение телеграм бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot_instance.start))
    application.add_handler(CallbackQueryHandler(bot_instance.button_callback))
    
    return app

def run_app():
    """Запуск приложения"""
    flask_app = create_app()
    
    # Настраиваем webhook
    async def setup_webhook():
        webhook_url = f"{WEBHOOK_URL}/webhook"
        try:
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}")
    
    # Запускаем настройку webhook в отдельном потоке
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    loop.close()
    
    logger.info("Бот запущен и готов к работе!")
    
    # Запускаем Flask приложение
    flask_app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == '__main__':
    run_app()