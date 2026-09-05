from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape

import requests
from bs4 import BeautifulSoup

CAR_PRICE_URL = "https://www.mashin3.com/price.html"
CAR_SOURCE_NAME = "ماشین۳"
CHANNEL_URL = "https://t.me/bikhabaar"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
TELEGRAPH_API_URL = "https://api.telegra.ph"
CAR_BANNER_URL = (
    "https://raw.githubusercontent.com/samannazsheyda-commits/telegram-news-agent/"
    "main/assets/car_price_banner.svg"
)

PERSIAN_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬", "0123456789,")
_RLI = "\u2067"
_PDI = "\u2069"


@dataclass(frozen=True)
class CarPrice:
    name: str
    market_toman: int


def _parse_price(text: str) -> int | None:
    normalized = (text or "").translate(PERSIAN_TO_ASCII).replace(" ", "")
    match = re.search(r"([0-9][0-9,]{5,})", normalized)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_car_prices(html: str) -> list[CarPrice]:
    soup = BeautifulSoup(html or "", "html.parser")
    result: list[CarPrice] = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].strip()
        price = _parse_price(cells[1])
        if name and price:
            result.append(CarPrice(name, price))
    if not result:
        raise ValueError("car price table not found")
    return result


def fetch_car_prices(session=requests) -> list[CarPrice]:
    response = session.get(CAR_PRICE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return parse_car_prices(response.text)


def _change_line(current: int, previous: int | None) -> str:
    if not previous or previous <= 0:
        return ""
    diff = current - previous
    pct = abs(diff) / previous * 100
    if diff > 0:
        return f" ▲ {abs(diff):,} تومان | {pct:.2f}٪"
    if diff < 0:
        return f" ▼ {abs(diff):,} تومان | {pct:.2f}٪"
    return " — بدون تغییر"


def _isolated_name(name: str) -> str:
    return f"{_RLI}<b>{escape(name)}</b>{_PDI}"


def format_car_prices(prices: list[CarPrice], previous: dict[str, int] | None = None) -> str:
    """Full Telegram-style list retained for fallback/tests; source names are never rewritten."""
    previous = previous or {}
    lines = ["🚗 <b>قیمت روز خودرو | بازار آزاد</b>"]
    for item in prices:
        lines += ["", f"▫️ {_isolated_name(item.name)}: {item.market_toman:,} تومان{_change_line(item.market_toman, previous.get(item.name))}"]
    lines += [
        "",
        f'📌 <a href="{CAR_PRICE_URL}">منبع: {CAR_SOURCE_NAME}</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ]
    return "\n".join(lines)


def _telegraph_car_nodes(prices: list[CarPrice], previous: dict[str, int] | None = None) -> list[dict]:
    previous = previous or {}
    nodes: list[dict] = [
        {"tag": "figure", "children": [{"tag": "img", "attrs": {"src": CAR_BANNER_URL}}]},
        {"tag": "p", "children": [f"لیست کامل {len(prices)} خودروی موجود در منبع؛ نام مدل‌ها عیناً مطابق منبع نمایش داده می‌شوند."]},
        {"tag": "hr"},
    ]
    for item in prices:
        change = _change_line(item.market_toman, previous.get(item.name))
        children: list = [
            {"tag": "strong", "children": [item.name]},
            f": {item.market_toman:,} تومان{change}",
        ]
        nodes.append({"tag": "p", "children": children})
    nodes.extend([
        {"tag": "hr"},
        {
            "tag": "p",
            "children": [
                "منبع: ",
                {"tag": "a", "attrs": {"href": CAR_PRICE_URL}, "children": [CAR_SOURCE_NAME]},
            ],
        },
        {
            "tag": "p",
            "children": [
                {"tag": "a", "attrs": {"href": CHANNEL_URL}, "children": ["📡 بی‌خبر"]},
                " ← مانیتور تحولات ایران",
            ],
        },
    ])
    return nodes


def _telegraph_result(response) -> dict:
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error") or "Telegraph API error"))
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Telegraph API returned no result")
    return result


def create_car_telegraph_page(
    prices: list[CarPrice],
    previous: dict[str, int] | None = None,
    *,
    session=requests,
) -> str:
    """Create a fresh Telegraph page containing every current source row and the approved banner."""
    account = _telegraph_result(session.post(
        f"{TELEGRAPH_API_URL}/createAccount",
        data={"short_name": "BiKhabaar", "author_name": "بی‌خبر", "author_url": CHANNEL_URL},
        timeout=30,
    ))
    token = str(account.get("access_token") or "")
    if not token:
        raise RuntimeError("Telegraph access token missing")

    page = _telegraph_result(session.post(
        f"{TELEGRAPH_API_URL}/createPage",
        data={
            "access_token": token,
            "title": "قیمت روز خودرو | بازار آزاد",
            "author_name": "بی‌خبر",
            "author_url": CHANNEL_URL,
            "content": json.dumps(_telegraph_car_nodes(prices, previous), ensure_ascii=False),
            "return_content": "false",
        },
        timeout=30,
    ))
    url = str(page.get("url") or "")
    if not url.startswith("https://telegra.ph/"):
        raise RuntimeError("Telegraph page URL missing")
    return url


def format_car_telegraph_post(page_url: str, count: int) -> str:
    return "\n".join([
        "🚗 <b>قیمت روز خودرو | بازار آزاد</b>",
        "",
        f"لیست کامل قیمت {count} خودروی موجود در منبع آماده است.",
        "",
        f'👉🏻 <a href="{escape(page_url, quote=True)}"><b>مشاهده لیست کامل قیمت خودروها</b></a>',
        "",
        f'📌 <a href="{CAR_PRICE_URL}">منبع: {CAR_SOURCE_NAME}</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ])
