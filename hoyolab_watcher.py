import os
import json
import asyncio
import logging
from datetime import datetime, date as _date
from typing import Dict, List, Set

import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot
import html
from aiogram import types

__all__ = ["start_hoyolab_watcher", "fetch_articles_for_date"]

# Base URLs for different listing categories
BASE_URLS: Dict[str, str] = {
    "news": "https://www.hoyolab.com/circles/6/39/official?page_type=39&page_sort=news",
    "events": "https://www.hoyolab.com/circles/6/39/official?page_type=39&page_sort=events",
    "notices": "https://www.hoyolab.com/circles/6/39/official?page_type=39&page_sort=notices",
}

STATE_FILE = os.path.join("data", "hoyolab_state.json")
DEFAULT_INTERVAL = 60 * 60 * 12  # 12 часов

# Subscribers file – list of chat ids (int)
SUBSCRIBERS_FILE = os.path.join("data", "subscribers.json")

# Не отправлять новости до этой даты (YYYY-MM-DD)
MIN_DATE_STR = "2025-06-19"
MIN_DATE = datetime.fromisoformat(MIN_DATE_STR)


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch raw HTML for a given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HSRHelperBot/1.0; +https://t.me/perpetuahsr)"
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        resp.raise_for_status()
        return await resp.text()


def _parse_listing(html: str) -> List[Dict[str, str]]:
    """Extract article id, title and href from listing page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    # The site uses <a href="/article/39501469"> around each card.
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/article/" not in href:
            continue
        # Ensure absolute URL
        url = href if href.startswith("http") else f"https://www.hoyolab.com{href}"
        article_id = href.split("/article/")[-1].split("?")[0].split("#")[0]
        title_tag = a.find("div") or a
        title = title_tag.get_text(" ", strip=True)[:120]  # trim overly long titles
        if not title:
            title = "Новая статья"
        articles.append({"id": article_id, "title": title, "url": url})
    return articles


def _load_state() -> Set[str]:
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception:
        logging.exception("[hoyolab] Не удалось загрузить состояние, создаю новое.")
    return set()


def _save_state(seen_ids: Set[str]):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, ensure_ascii=False, indent=2)


async def _load_subscribers() -> List[int]:
    """Load subscribers list from JSON file."""
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [int(x) for x in data]
    except Exception:
        logging.exception("[hoyolab] Ошибка при загрузке списка подписчиков")
    return []


async def _fetch_article_details(session: aiohttp.ClientSession, url: str) -> Dict[str, List[str]]:
    """Return {'text': str, 'images': [url, ...], 'date': datetime} for article."""
    try:
        html_page = await _fetch_html(session, url)
        soup = BeautifulSoup(html_page, "html.parser")
        # Дата публикации – в теге <time> с атрибутом datetime
        dt = MIN_DATE
        time_el = soup.find("time")
        if time_el and time_el.has_attr("datetime"):
            try:
                dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            except Exception:
                pass
        # Текст статьи
        article_div = soup.find("div", class_=lambda x: x and "article-detail" in x)
        text_parts: List[str] = []
        if article_div:
            # собираем p и h теги
            for tag in article_div.find_all(["p", "h1", "h2", "h3"]):
                txt = tag.get_text(" ", strip=True)
                if txt:
                    text_parts.append(txt)
        text_content = "\n\n".join(text_parts)
        # Images
        imgs = []
        for img_tag in article_div.find_all("img", src=True):
            src = img_tag["src"]
            if src and src.startswith("//"):
                src = "https:" + src
            elif src and src.startswith("/"):
                src = "https://www.hoyolab.com" + src
            imgs.append(src)
        return {"text": text_content, "images": imgs, "date": dt}
    except Exception as e:
        logging.warning(f"[hoyolab] Не удалось разобрать статью {url}: {e}")
        return {"text": "", "images": [], "date": MIN_DATE}


async def _send_article(bot: Bot, chat_ids: List[int], art: Dict[str, str], details: Dict[str, List[str]]):
    """Send article to all subscribers respecting Telegram limits."""
    caption = f"<b>{html.escape(art['title'])}</b>\n<a href='{art['url']}'>Источник HoYoLAB</a>"
    text_segments: List[str] = []
    if details["text"]:
        # Разбиваем по 4000 символов
        txt = details["text"]
        chunk_size = 4000
        text_segments = [txt[i:i+chunk_size] for i in range(0, len(txt), chunk_size)]
    # Prepare media group if more than one image
    for chat_id in chat_ids:
        try:
            if details["images"]:
                if len(details["images"]) == 1:
                    # single image with caption
                    await bot.send_photo(chat_id=chat_id, photo=details["images"][0], caption=caption, parse_mode="HTML")
                else:
                    media = [types.InputMediaPhoto(media=img) for img in details["images"][:10]]
                    # Telegram limits 10 in group
                    media[0].caption = caption
                    media[0].parse_mode = "HTML"
                    await bot.send_media_group(chat_id=chat_id, media=media)
            else:
                await bot.send_message(chat_id=chat_id, text=caption, disable_web_page_preview=False)
            # then send text parts if any
            for seg in text_segments:
                await bot.send_message(chat_id=chat_id, text=seg)
        except Exception as e:
            logging.error(f"[hoyolab] Ошибка отправки статьи в чат {chat_id}: {e}")


async def _check_updates(bot: Bot, seen_ids: Set[str]):
    async with aiohttp.ClientSession() as session:
        new_seen: Set[str] = set(seen_ids)
        subscribers = _load_subscribers()
        if not subscribers:
            return  # no one subscribed
        for category, url in BASE_URLS.items():
            try:
                page_html = await _fetch_html(session, url)
                articles = _parse_listing(page_html)
            except Exception as e:
                logging.warning(f"[hoyolab] Ошибка при обработке {category}: {e}")
                continue
            for art in articles:
                if art["id"] in new_seen:
                    continue
                # parse article details to get date
                details = await _fetch_article_details(session, art["url"])
                if details["date"] < MIN_DATE:
                    # skip old
                    new_seen.add(art["id"])
                    continue
                # Новая подходящая статья
                new_seen.add(art["id"])
                await _send_article(bot, subscribers, art, details)
        # Persist state after each round
        _save_state(new_seen)
        seen_ids.clear()
        seen_ids.update(new_seen)


async def start_hoyolab_watcher(bot: Bot, interval: int = DEFAULT_INTERVAL):
    """Background coroutine that periodically polls HoYoLAB and sends new article alerts."""
    logging.info("[hoyolab] Запуск watcher...")
    seen_ids = _load_state()
    while True:
        try:
            await _check_updates(bot, seen_ids)
        except Exception:
            logging.exception("[hoyolab] Ошибка в цикле watcher")
        await asyncio.sleep(interval)


async def fetch_articles_for_date(target_date: _date):
    """Return list of tuples (art_meta, details) for articles published on target_date (UTC)."""
    results = []
    async with aiohttp.ClientSession() as session:
        for category, url in BASE_URLS.items():
            try:
                page_html = await _fetch_html(session, url)
                articles = _parse_listing(page_html)
            except Exception as e:
                logging.warning(f"[hoyolab] fail list {url}: {e}")
                continue
            for art in articles:
                try:
                    details = await _fetch_article_details(session, art["url"])
                except Exception:
                    continue
                if details["date"].date() == target_date:
                    results.append((art, details))
    # deduplicate by article id
    seen = set()
    unique = []
    for art, det in results:
        if art["id"] in seen:
            continue
        seen.add(art["id"])
        unique.append((art, det))
    return unique 