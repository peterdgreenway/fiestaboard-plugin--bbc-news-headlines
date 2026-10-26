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
NOTE_MAX_CHARS = NOTE_WIDTH * NOTE_ROWS  # 45 — full Vestaboard Note capacity
DEFAULT_MAX_HEADLINE = 45
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


# Phrase / word substitutions applied before length compression (order matters)
_PHRASE_SUBS = [
    (r"\bUnited States\b", "US"),
    (r"\bU\.S\.\b", "US"),
    (r"\bUnited Kingdom\b", "UK"),
    (r"\bGreat Britain\b", "UK"),
    (r"\bEuropean Union\b", "EU"),
    (r"\bPrime Minister\b", "PM"),
    (r"\bPresident\b", "Pres"),
    (r"\bMet Office\b", "Met"),
    (r"\bwithout power\b", "no power"),
    (r"\bgoing to the polls\b", "elections"),
    (r"\bthe consequences will be global\b", "may reshape world"),
    (r"\bconsequences will be global\b", "may reshape world"),
    (r"\bIndependent review announced into\b", "Review ordered into"),
    (r"\breview announced into\b", "review into"),
    (r"\bannounced into\b", "into"),
    (r"\bwhile racing\b", "racing"),
    (r"\bwho killed\b", "kill"),
    (r"\bhelped turn\b", "boosted"),
    (r"\bturn .+? election around\b", "boosted election"),
    (r"\belection around\b", "election"),
    (r"\bissues? new wind warning\b", "new warning"),
    (r"\bwind warning\b", "warning"),
    (r"\bleaves ([0-9][0-9,]*) without power\b", r"cuts power to \1"),
    (r"\bWhatsApp channel\b", "WhatsApp"),
    (r"\bmurder of student\b", "student murder"),
    (r"\bare both\b", "and"),
    (r"\bboth going\b", "going"),
    (r"\bas Met\b", "Met"),
    (r"\bissues new\b", "new"),
]

_FILLER = {
    "A", "AN", "THE", "OF", "TO", "IN", "ON", "AT", "FOR", "AND", "OR",
    "AS", "BY", "FROM", "WITH", "INTO", "OVER", "AFTER", "BEFORE",
    "THAT", "THIS", "THESE", "THOSE", "IS", "ARE", "WAS", "WERE", "BE",
    "BEEN", "BEING", "HAS", "HAVE", "HAD", "WILL", "WOULD", "COULD",
    "SHOULD", "MAY", "MIGHT", "MUST", "SHALL", "DO", "DOES", "DID",
    "ITS", "IT", "HIS", "HER", "THEIR", "OUR", "YOUR", "WHO", "WHOM",
    "WHICH", "WHILE", "WHEN", "WHERE", "HOW", "ABOUT", "AGAINST",
}


def _apply_phrase_subs(text: str) -> str:
    import re as _re
    out = text
    for pattern, repl in _PHRASE_SUBS:
        out = _re.sub(pattern, repl, out, flags=_re.IGNORECASE)
    out = _re.sub(r"\s+", " ", out).strip()
    return out


def _drop_fillers(text: str, max_chars: int) -> str:
    """Remove low-value words until under max_chars, keeping order."""
    words = text.split()
    if not words:
        return text
    # Never drop the first two content words if possible
    kept = list(words)
    # Pass: drop fillers from the middle/end first
    i = len(kept) - 1
    while i >= 2 and len(" ".join(kept)) > max_chars:
        w = kept[i].upper().strip(".,:;'!?-")
        if w in _FILLER:
            kept.pop(i)
        i -= 1
    # Still too long: drop remaining fillers from start side
    i = 0
    while i < len(kept) and len(" ".join(kept)) > max_chars:
        w = kept[i].upper().strip(".,:;'!?-")
        if w in _FILLER and i > 0:
            kept.pop(i)
            continue
        i += 1
    return " ".join(kept)


def _truncate_at_word(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    else:
        cut = text[:max_chars]
    return cut.strip()[:max_chars]


def _paraphrase_headline(text: str, max_chars: int) -> str:
    """Rework a headline to fit max_chars (hard cap 45 for Vestaboard Note).

    Pipeline:
      1. Phrase-level substitutions (common news patterns → shorter forms)
      2. Drop filler words while length exceeds limit
      3. Word-boundary truncate as last resort
      4. Re-apply Vestaboard-safe uppercase (subs may alter case)
    """
    max_chars = max(1, min(int(max_chars), NOTE_MAX_CHARS))
    text = (text or "").strip()
    if not text:
        return ""

    # Work in a readable form for phrase matching, then normalise
    text = _apply_phrase_subs(text)
    text = _vestaboard_safe(text)

    if len(text) <= max_chars:
        return text

    text = _drop_fillers(text, max_chars)
    text = _vestaboard_safe(text)
    if len(text) <= max_chars:
        return text

    return _vestaboard_safe(_truncate_at_word(text, max_chars))


def _truncate_headline(text: str, max_chars: int) -> str:
    """Back-compat alias: paraphrase then ensure hard cap."""
    return _paraphrase_headline(text, max_chars)


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


def _note_block(headline: str, max_chars: int = DEFAULT_MAX_HEADLINE) -> Tuple[str, str, str, str]:
    """
    Build a Vestaboard Note block (15×3) from a headline truncated to max_chars.

    Absolute maximum is 45 characters (full Note capacity). Text is uppercased, sanitised, paraphrased/abbreviated to max_chars
    (hard max 45), then word-wrapped into 3 rows of 15.

    Returns note_block (joined with newlines), row1, row2, row3.
    """
    safe = _vestaboard_safe(headline)
    safe = _truncate_headline(safe, max_chars)
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
        max_h = config.get("max_headline_chars", DEFAULT_MAX_HEADLINE)
        if not isinstance(max_h, int) or max_h < 10 or max_h > NOTE_MAX_CHARS:
            errors.append(
                f"max_headline_chars must be an integer 10-{NOTE_MAX_CHARS} "
                "(Vestaboard Note hard limit is 45)"
            )
        mode = config.get("shorten_mode", "paraphrase")
        if mode not in ("paraphrase", "truncate"):
            errors.append("shorten_mode must be 'paraphrase' or 'truncate'")
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
        max_chars = int(self.config.get("max_headline_chars", DEFAULT_MAX_HEADLINE) or DEFAULT_MAX_HEADLINE)
        max_chars = max(10, min(NOTE_MAX_CHARS, max_chars))
        shorten_mode = self.config.get("shorten_mode", "paraphrase")
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
            if shorten_mode == "truncate":
                truncated = _truncate_at_word(_vestaboard_safe(headline), max_chars)
            else:
                truncated = _paraphrase_headline(headline, max_chars)
            note_block, r1, r2, r3 = _note_block(headline, max_chars=max_chars)
            # When truncate mode, rebuild note from truncated only
            if shorten_mode == "truncate":
                lines = _wrap_words(truncated, NOTE_WIDTH, NOTE_ROWS)
                r1, r2, r3 = lines[0], lines[1], lines[2]
                note_block = f"{r1}\n{r2}\n{r3}"
            else:
                lines = _wrap_words(truncated, NOTE_WIDTH, NOTE_ROWS)

            short = truncated

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
                "headline_truncated": truncated,
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
