class ParsingConfig:
    # Элементы и их эмодзи
    ELEMENTS = {
        "Fire": {"name": "Огонь", "emoji": "🔥"},
        "Ice": {"name": "Лёд", "emoji": "❄️"},
        "Wind": {"name": "Ветер", "emoji": "🌪️"},
        "Quantum": {"name": "Квант", "emoji": "⚛️"},
        "Physical": {"name": "Физика", "emoji": "💪"},
        "Imaginary": {"name": "Мнимость", "emoji": "🌈"},
        "Lightning": {"name": "Электро", "emoji": "⚡"}
    }

    # Настройки для парсинга билдов
    STATS_MAIN_SLOTS = {
        "body": ["body", "torso", "chest"],
        "feet": ["feet", "shoes", "boots"],
        "sphere": ["sphere", "ring"],
        "rope": ["rope", "necklace"]
    }
    
    # Ключевые слова для определения лучшего варианта
    BEST_KEYWORDS = [
        "best", "primary", "main", "optimal", "recommended", "top", "default"
    ]
    
    # Ключевые слова для определения альтернативного варианта
    ALTERNATIVE_KEYWORDS = [
        "alternative", "secondary", "backup", "substitute", "alternative build"
    ]
    
    # Форматы рейтинга
    RATING_FORMATS = {
        "stars": ["⭐", "★", "☆"],
        "numbers": ["1", "2", "3", "4", "5"],
        "text": ["S", "A", "B", "C", "D"]
    }
    
    # Ключевые слова для определения оружия
    WEAPON_KEYWORDS = [
        "weapon", "light cone", "cone", "light-cone"
    ]
    
    # Ключевые слова для определения артефактов
    ARTIFACT_KEYWORDS = [
        "artifact", "relic", "set", "planar", "planar set"
    ]
    
    # Ключевые слова для определения билда
    BUILD_KEYWORDS = [
        "build", "setup", "configuration", "guide"
    ]
    
    # Типы статов для артефактов
    STAT_KEYWORDS = {
        "hp": ["hp", "health", "hit points"],
        "atk": ["attack", "atk"],
        "def": ["defense", "def"],
        "crit": ["critical hit rate", "crit rate"],
        "crit_dmg": ["critical hit damage", "crit damage"],
        "speed": ["speed", "spd"],
        "effect_res": ["effect resistance", "effect res"],
        "effect_hit": ["effect hit rate", "effect hit"],
        "break": ["break damage", "break"],
        "skill": ["skill damage", "skill"],
        "talent": ["talent damage", "talent"],
        "normal": ["normal attack damage", "normal"],
        "charge": ["charge attack damage", "charge"],
        "dmg": ["all damage", "damage"],
        "heal": ["heal", "healing"],
        "energy": ["energy recharge", "energy"],
        "element": ["elemental damage", "element"],
        "status": ["status damage", "status"],
        "dot": ["dot damage", "dot"],
        "counter": ["counter damage", "counter"],
        "break_eff": ["break effect", "break eff"]
    }
    
    # Ключевые слова для определения команды
    TEAM_KEYWORDS = [
        "team", "party", "squad", "formation"
    ]
    
    # Ключевые слова для определения уровня
    RANK_KEYWORDS = [
        "rank", "level", "rarity", "★", "⭐"
    ]
    
    # Ключевые слова для определения статов
    STAT_KEYWORDS = {
        "atk": ["attack", "atk%", "atk%", "attack%"],
        "hp": ["health", "hp%", "hp%", "health%"],
        "def": ["defense", "def%", "def%", "defense%"],
        "crit_rate": ["crit rate", "crit%", "crit rate%", "crit rate%"],
        "crit_dmg": ["crit damage", "crit dmg%", "crit damage%", "crit damage%"],
        "spd": ["speed", "spd%", "speed%", "speed%"],
        "effect_hit": ["effect hit", "effect hit%", "effect hit%", "effect hit%"],
        "effect_res": ["effect resistance", "effect res%", "effect resistance%", "effect resistance%"],
        "break_dmg": ["break damage", "break dmg%", "break damage%", "break damage%"]
    }
    RATING_FORMATS = {
        "stars": ["★", "star"],  # Примеры: ★★★★★, 5-star
        "numbers": ["1", "2", "3", "4", "5"]  # Примеры: 5, 4.5
    }
    
    # Секции на странице
    SECTIONS = {
        "relics": ["Recommended Relics", "Рекомендуемые реликвии"],
        "light_cones": ["Light Cones", "Конусы света"],
        "stats": ["Recommended Stats", "Рекомендуемые характеристики"],
        "priority": ["Priority Stats", "Приоритетные характеристики"],
        "ornaments": ["Planar Ornaments", "Планарные украшения"]
    }

    # Стандартные значения
    DEFAULT_RELIQUOT_SET = "Iron Cavalry Against the Scourge"
    DEFAULT_LIGHT_CONE_5 = "Sailing Towards A Second Life"
    DEFAULT_LIGHT_CONE_4 = "Shadowed by Night"
    DEFAULT_LIGHT_CONE_3 = "Cruising in the Stellar Sea"
    DEFAULT_ORNAMENT = "Warrior Goddess of Sun and Thunder"
    DEFAULT_STATS = {
        "body": "Break Effect",
        "feet": "SPD",
        "sphere": "CRIT Rate",
        "rope": "Energy Regen"
    }
