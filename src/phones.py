from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

MOBILE_PRICE_URL = "https://www.mobile.ir/phones/prices.aspx"
CHANNEL_URL = "https://t.me/bikhabaar"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
TEHRAN = ZoneInfo("Asia/Tehran")

_PERSIAN_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬", "0123456789,")

# Ordered by how the list should appear in Telegram. The numeric series is
# intentionally discovered from the source so the post rolls forward when a
# new generation replaces the current flagship.
_FLAGSHIP_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Apple", re.compile(r"^Apple iPhone (?P<series>\d+) Pro Max$", re.I)),
    ("Samsung", re.compile(r"^Samsung Galaxy S(?P<series>\d+) Ultra$", re.I)),
    ("Xiaomi", re.compile(r"^Xiaomi (?P<series>\d+) Ultra$", re.I)),
    ("Google", re.compile(r"^Google Pixel (?P<series>\d+) Pro XL$", re.I)),
)

_SEARCH_TERMS = ("iPhone", "Galaxy S", "Xiaomi", "Pixel")


@dataclass(frozen=True)
class FlagshipPhonePrice:
    name: str
    price_toman: int


def _parse_price(text: str) -> int | None:
    normalized = (text or "").translate(_PERSIAN_TO_ASCII).replace(" ", "")
    match = re.search(r"([0-9][0-9,]{5,})", normalized)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_flagship_phone_prices(html: str) -> list[FlagshipPhonePrice]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[tuple[str, int]] = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].strip()
        price = _parse_price(cells[1])
        if name and price:
            rows.append((name, price))

    selected: list[FlagshipPhonePrice] = []
    for _, pattern in _FLAGSHIP_FAMILIES:
        matches: list[tuple[int, str, int]] = []
        for name, price in rows:
            match = pattern.match(name)
            if match:
                matches.append((int(match.group("series")), name, price))
        if not matches:
            continue
        latest_series = max(series for series, _, _ in matches)
        current = [(name, price) for series, name, price in matches if series == latest_series]
        # mobile.ir can contain multiple sellers for the same phone; publishing
        # the lowest listed price makes the daily card deterministic and useful.
        name = current[0][0]
        price = min(price for _, price in current)
        selected.append(FlagshipPhonePrice(name, price))

    if not selected:
        raise ValueError("flagship phone prices not found")
    return selected


def fetch_flagship_phone_prices(session=requests) -> list[FlagshipPhonePrice]:
    pages: list[str] = []
    for term in _SEARCH_TERMS:
        response = session.get(
            MOBILE_PRICE_URL,
            params={
                "brandid": 0,
                "duration": 14,
                "pagesize": 200,
                "price_from": -1,
                "price_to": -1,
                "provinceid": 0,
                "shopid": 0,
                "sort": "date",
                "terms": term,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        pages.append(response.text)
    return parse_flagship_phone_prices("\n".join(pages))


def phone_flagships_due(state: dict, now) -> bool:
    local = now.astimezone(TEHRAN)
    return local.hour >= 12 and state.get("phone_flagships_last_sent_date") != local.date().isoformat()


def format_flagship_phone_prices(prices: list[FlagshipPhonePrice]) -> str:
    lines = ["📱 <b>پرچمدارهای موبایل | بازار ایران</b>"]
    for item in prices:
        lines += ["", f"▫️ <b>{escape(item.name)}</b>: از {item.price_toman:,} تومان"]
    lines += [
        "",
        f'📌 <a href="{MOBILE_PRICE_URL}">منبع: mobile.ir</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ]
    return "\n".join(lines)
