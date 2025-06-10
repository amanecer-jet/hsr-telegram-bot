class ParsingConfig:
    # Настройки для парсинга билдов
    STATS_MAIN_SLOTS = {
        "body": ["body", "torso", "chest"],
        "feet": ["feet", "shoes", "boots"],
        "sphere": ["sphere", "ring"],
        "rope": ["rope", "necklace"]
    }
    
    # Ключевые слова для определения лучшего варианта
    BEST_KEYWORDS = [
        "best", "primary", "main", "optimal", "recommended", "top"
    ]
    
    # Ключевые слова для определения альтернативного варианта
    ALTERNATIVE_KEYWORDS = [
        "alternative", "secondary", "backup", "substitute"
    ]
    
    # Форматы рейтинга
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
