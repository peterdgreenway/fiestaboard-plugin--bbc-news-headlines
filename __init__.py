"""BBC News FiestaBoard plugin — latest headlines via RSS."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import unescape

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

FEED_URLS = {
    "top": "https://feeds.bbci.co.uk/news/rss.xml",
    "uk": "https://feeds.bbci.co.uk/news/uk/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "politics": "https://feeds.bbci.co.uk/news/politics/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
}

FEED_LABELS = {
    "top": "TOP",
    "uk": "UK",
    "world": "WORLD",
    "business": "BUSINESS",
    "politics": "POLITICS",
    "technology": "TECH",
    "science": "SCIENCE",
}

NOTE_WIDTH = 15
NOTE_ROWS = 3
USER_AGENT = "FiestaBoard-BBC-News/1.0 (+https://fiestaboard.app)"


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _vestaboard_safe(text: str) -> str:
    """Uppercase and keep characters that work well on Vestaboard flaps."""
    text = text.upper()
    # Keep letters, digits, spaces, and a few punctuation marks boards support
    text = re.sub(r"[^A-Z0-9 $&@.,:!?'\-/%]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _wrap_words(text: str, width: int, max_rows: int) -> List[str]:
    """Word-wrap text into up to max_rows lines of at most width chars."""
    words = text.split()
    if not words:
        return [""] * max_rows

    lines: List[str] = []
    current = ""
    for word in words:
        if len(word) > width:
            # Hard-break very long tokens
            if current:
                lines.append(current)
                current = ""
            for i in range(0, len(word), width):
                chunk = word[i : i + width]
                if len(lines) >= max_rows:
                    break
                if i + width < len(word) and len(lines) == max_rows - 1:
                    # Last row: truncate with no extra
                    lines.append(chunk[:width])
                    break
                lines.append(chunk)
            continue

        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_rows:
                current = ""
                break

    if current and len(lines) < max_rows:
        lines.append(current)

    # Truncate last line if we ran out of room mid-sentence
    while len(lines) > max_rows:
        lines.pop()

    while len(lines) < max_rows:
        lines.append("")

    return [line[:width].ljust(width) for line in lines[:max_rows]]


def _note_block(headline: str) -> Tuple[str, str, str, str]:
    """
    Build a Vestaboard Note block (15×3).

    Row 1: BBC NEWS + optional short feed tag
    Rows 2–3 (and overflow into row 1 if needed): wrapped headline

    Returns note_block (joined with newlines), row1, row2, row3.
    """
    safe = _vestaboard_safe(headline)
    # Prefer: line1 label, lines 2-3 body — but if headline is short, still fill
    body_lines = _wrap_words(safe, NOTE_WIDTH, NOTE_ROWS)

    # If first body line is empty, fall back to BBC NEWS header style
    if not body_lines[0].strip():
        r1 = "BBC NEWS".ljust(NOTE_WIDTH)
        r2 = "".ljust(NOTE_WIDTH)
        r3 = "".ljust(NOTE_WIDTH)
    else:
        r1, r2, r3 = body_lines[0], body_lines[1], body_lines[2]

    block = f"{r1}\n{r2}\n{r3}"
    return block, r1, r2, r3


def _parse_pub_date(raw: Optional[str]) -> Tuple[str, str]:
    if not raw:
        return "", ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        full = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        short = dt.astimezone(timezone.utc).strftime("%d %b %H:%M")
        return full, short
    except Exception:
        return raw[:25], raw[:12]


class BbcNewsPlugin(PluginBase):
    """Fetch BBC News RSS and expose Note-sized headline blocks."""

    @property
    def plugin_id(self) -> str:
        return "bbc_news"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        feed = config.get("feed", "top")
        if feed not in FEED_URLS:
            errors.append(f"feed must be one of: {', '.join(FEED_URLS)}")
        refresh = config.get("refresh_seconds", 300)
        if not isinstance(refresh, int) or refresh < 120:
            errors.append("refresh_seconds must be an integer >= 120")
        idx = config.get("headline_index", 0)
        if not isinstance(idx, int) or idx < 0 or idx > 9:
            errors.append("headline_index must be an integer 0-9")
        return errors

    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        try:
            self.clear_cache()
            logger.info("BBC News: cache cleared after config change")
        except Exception as e:
            logger.warning("BBC News: clear_cache failed: %s", e)

    def fetch_data(self) -> PluginResult:
        feed_key = self.config.get("feed", "top")
        if feed_key not in FEED_URLS:
            feed_key = "top"
        idx = int(self.config.get("headline_index", 0) or 0)
        idx = max(0, min(9, idx))
        url = FEED_URLS[feed_key]
        feed_name = FEED_LABELS.get(feed_key, "BBC")

        try:
            items = self._fetch_items(url)
            if not items:
                return PluginResult(
                    available=False,
                    error="No headlines returned from BBC RSS",
                )

            idx = min(idx, len(items) - 1)
            top = items[idx]
            headline = top["title"]
            note_block, r1, r2, r3 = _note_block(headline)
            lines = _wrap_words(_vestaboard_safe(headline), NOTE_WIDTH, NOTE_ROWS)

            # Secondary short form (single line, 45 chars for Flagship-style use)
            short = _vestaboard_safe(headline)[:45]

            headlines_out = []
            for it in items[:10]:
                headlines_out.append(
                    {
                        "title": it["title"][:80],
                        "title_short": _vestaboard_safe(it["title"])[:22],
                        "link": it.get("link", "")[:80],
                        "published": it.get("published", "")[:25],
                    }
                )

            data = {
                "headline": headline[:80],
                "headline_short": short,
                "headline_line1": lines[0],
                "headline_line2": lines[1],
                "headline_line3": lines[2],
                "note_block": note_block,
                "note_row1": r1,
                "note_row2": r2,
                "note_row3": r3,
                "description": top.get("description", "")[:100],
                "link": top.get("link", "")[:80],
                "published": top.get("published", "")[:25],
                "published_short": top.get("published_short", "")[:12],
                "feed_name": feed_name[:12],
                "source": "BBC",
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "headlines": headlines_out,
            }
            return PluginResult(available=True, data=data)

        except requests.Timeout:
            logger.warning("BBC News: request timed out")
            return PluginResult(available=False, error="BBC RSS request timed out")
        except requests.RequestException as e:
            logger.warning("BBC News: network error: %s", e)
            return PluginResult(available=False, error="Network error fetching BBC RSS")
        except ET.ParseError as e:
            logger.warning("BBC News: XML parse error: %s", e)
            return PluginResult(available=False, error="Invalid RSS XML from BBC")
        except Exception as e:
            logger.exception("BBC News: unexpected error")
            return PluginResult(available=False, error=str(e)[:120])

    def _fetch_items(self, url: str) -> List[Dict[str, str]]:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        channel = root.find("channel")
        if channel is None:
            # Atom fallback (unlikely for BBC)
            return []

        items: List[Dict[str, str]] = []
        for item in channel.findall("item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pub_el = item.find("pubDate")

            title = _clean_text(title_el.text if title_el is not None else "")
            if not title:
                continue
            description = _clean_text(desc_el.text if desc_el is not None else "")
            link = (link_el.text or "").strip() if link_el is not None else ""
            pub_raw = (pub_el.text or "").strip() if pub_el is not None else ""
            published, published_short = _parse_pub_date(pub_raw)

            items.append(
                {
                    "title": title,
                    "description": description,
                    "link": link,
                    "published": published,
                    "published_short": published_short,
                }
            )
            if len(items) >= 15:
                break

        return items
