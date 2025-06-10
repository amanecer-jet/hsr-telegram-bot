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
                if href:
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

    # Recommended relics
    relics_header = find_section(["Recommended Relics", "Best Relics", "Рекомендуемые реликвии"])
    if relics_header:
        section = relics_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["relics_recommended"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["relics_recommended"].append(cells[0].get_text(strip=True))

    # Alternative relics
    alt_relics_header = find_section(["Alternative Relics", "Alt Relics", "Альтернативные реликвии"])
    if alt_relics_header:
        section = alt_relics_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["relics_alternative"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["relics_alternative"].append(cells[0].get_text(strip=True))

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
    main_stats_header = find_section(["Main Stat", "Main Stats", "Основная характеристика"])
    if main_stats_header:
        section = main_stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["main_stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["main_stats"].append(cells[0].get_text(strip=True))

    sub_stats_header = find_section(["Sub Stat", "Sub Stats", "Второстепенные характеристики"])
    if sub_stats_header:
        section = sub_stats_header.find_next(["ul", "table"])
        if section:
            if section.name == "ul":
                build["sub_stats"] = [li.get_text(strip=True) for li in section.find_all("li")]
            elif section.name == "table":
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if cells:
                        build["sub_stats"].append(cells[0].get_text(strip=True))

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
