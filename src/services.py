from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")


def has_persian(text: str) -> bool:
    return bool(PERSIAN_RE.search(text or ""))


def _google_translate(text: str, session=requests) -> str:
    response = session.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": "fa", "dt": "t", "q": text},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return "".join(part[0] for part in payload[0] if part and part[0]).strip()


def _mymemory_translate(text: str, session=requests) -> str:
    response = session.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "en|fa"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return str((payload.get("responseData") or {}).get("translatedText") or "").strip()


def translate_to_fa(text: str, session=requests) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if has_persian(text):
        return text
    for translator in (_google_translate, _mymemory_translate):
        try:
            translated = translator(text, session=session)
            if translated and translated != text and has_persian(translated):
                return translated
        except Exception:
            continue
    return ""


def split_message(text: str, max_len: int = 3900) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = remaining.rfind(" ", 0, max_len)
        if cut <= 0:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_telegram(text: str, bot_token: str, chat_id: str, session=requests) -> None:
    if not bot_token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chunk in split_message(text):
        response = session.post(
            url,
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram rejected message: {data}")
        time.sleep(3.2)


def load_state(path: str | Path = "state.json") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"truth_last_id": None, "news_seen": [], "market_last_sent_at": None}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("truth_last_id", None)
    if "news_seen" not in data:
        data["news_seen"] = list(data.pop("axios_seen", []))
    data.setdefault("market_last_sent_at", None)
    return data


def save_state(state: dict[str, Any], path: str | Path = "state.json") -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
