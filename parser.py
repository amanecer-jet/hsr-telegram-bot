import aiohttp
from bs4 import BeautifulSoup

async def fetch_build_from_game8(character_name: str) -> dict:
    CHARACTER_LIST_URL = "https://game8.co/games/Honkai-Star-Rail/archives/404256"
    
    async def get_character_link(name):
        async with aiohttp.ClientSession() as session:
            async with session.get(CHARACTER_LIST_URL) as resp:
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a"):
            if name.lower() in link.text.lower():
                href = link.get("href")
                if href and href.startswith("/"):
                    return f"https://game8.co{href}"
        return None

    char_link = await get_character_link(character_name)
    if not char_link:
        return {
            "relics_recommended": [],
            "relics_alternative": [],
            "cones": {"5": [], "4": [], "other": []},
            "main_stats": [],
            "sub_stats": [],
            "evaluation": "",
            "tips": ""
        }

    async with aiohttp.ClientSession() as session:
        async with session.get(char_link) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    build = {
        "relics_recommended": [],
        "relics_alternative": [],
        "cones": {"5": [], "4": [], "other": []},
        "main_stats": [],
        "sub_stats": [],
        "evaluation": "",
        "tips": ""
    }

    # --- Relics ---
    def find_section(header_keywords):
        for tag in soup.find_all(["h2", "h3"]):
            if any(kw.lower() in tag.text.lower() for kw in header_keywords):
                return tag
        return None

    # Relics section
    relics_header = find_section(["Relics", "Реликвии"])
    if relics_header:
        section = relics_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                all_items = [li.get_text(strip=True) for li in section.find_all("li")]
                # Разделяем реликвии и планарные украшения
                build["relics_recommended"] = [r for r in all_items if "Ornament" not in r and ("Best" in r or "best" in r.lower())]
                build["relics_alternative"] = [r for r in all_items if "Ornament" not in r and r not in build["relics_recommended"]]
                build["ornaments_recommended"] = [r for r in all_items if "Ornament" in r and ("Best" in r or "best" in r.lower())]
                build["ornaments_alternative"] = [r for r in all_items if "Ornament" in r and r not in build["ornaments_recommended"]]
            elif section.name == "table":
                all_items = []
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        all_items.append(cells[0].get_text(strip=True))
                # Разделяем реликвии и планарные украшения
                build["relics_recommended"] = [r for r in all_items if "Ornament" not in r and ("Best" in r or "best" in r.lower())]
                build["relics_alternative"] = [r for r in all_items if "Ornament" not in r and r not in build["relics_recommended"]]
                build["ornaments_recommended"] = [r for r in all_items if "Ornament" in r and ("Best" in r or "best" in r.lower())]
                build["ornaments_alternative"] = [r for r in all_items if "Ornament" in r and r not in build["ornaments_recommended"]]

    # --- Light Cones ---
    cones_header = find_section(["Light Cone", "Световой конус"])
    if cones_header:
        section = cones_header.find_next(["ul", "table"])
        cones_raw = []
        if section:
            if section.name == "ul":
                cones_raw = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        cones_raw.append(cells[0].get_text(strip=True))

        # Группировка по звёздности (улучшено)
        for cone in cones_raw:
            cone_stripped = cone.strip()
            if cone_stripped.startswith("★★★★★") or "5★" in cone_stripped or "5*" in cone_stripped or "5-star" in cone_stripped.lower() or "signature" in cone_stripped.lower():
                build["cones"]["5"].append(cone)
            elif cone_stripped.startswith("★★★★☆") or "4★" in cone_stripped or "4*" in cone_stripped or "4-star" in cone_stripped.lower():
                build["cones"]["4"].append(cone)
            else:
                build["cones"]["other"].append(cone)

    # --- Main/Sub Stats ---
    stats_header = find_section(["Stats", "Характеристики"])
    if stats_header:
        section = stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                all_stats = [li.get_text(strip=True) for li in section.find_all("li")]
                # Разделяем на рекомендованные и приоритетные
                build["main_stats"] = [s for s in all_stats if any(char.isdigit() for char in s) or any(x in s for x in ["%", ":", "/"])]
                build["sub_stats"] = [s for s in all_stats if s not in build["main_stats"]]
            elif section.name == "table":
                all_stats = []
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        all_stats.append(cells[0].get_text(strip=True))
                # Разделяем на рекомендованные и приоритетные
                build["main_stats"] = [s for s in all_stats if any(char.isdigit() for char in s) or any(x in s for x in ["%", ":", "/"])]
                build["sub_stats"] = [s for s in all_stats if s not in build["main_stats"]]

    # --- Evaluation / Tips ---
    eval_header = find_section(["Evaluation", "Overview", "Оценка", "Обзор"])
    if eval_header:
        p = eval_header.find_next("p")
        if p:
            build["evaluation"] = p.get_text(strip=True)

    tips_header = find_section(["Tips", "General Tips", "Советы", "Рекомендации"])
    if tips_header:
        p = tips_header.find_next("p")
        if p:
            build["tips"] = p.get_text(strip=True)

    return build
