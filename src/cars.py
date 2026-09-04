from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

import requests
from bs4 import BeautifulSoup

CAR_PRICE_URL = "https://www.mashin3.com/price.html"
CAR_SOURCE_NAME = "ماشین۳"
CHANNEL_URL = "https://t.me/bikhabaar"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"

# Curated high-volume / high-liquidity models commonly traded in Iran. Each entry
# is only posted when a matching live row exists on the source page.
TARGET_MODELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("پراید ۱۵۱", ("پراید 151", "سایپا 151")),
    ("پژو ۲۰۷ دنده‌ای", ("پژو 207 دنده‌ای (برقی)", "پژو 207 دنده‌ای (هیدرولیک)", "پژو 207 دنده‌ای")),
    ("پژو ۲۰۷ اتومات", ("پژو 207 اتوماتیک", "پژو 207 اتومات")),
    ("پژو ۲۰۷ TU3", ("پژو 207 TU3", "207 TU3")),
    ("دنا پلاس توربو اتومات", ("دنا پلاس اتوماتیک", "دنا پلاس توربو اتوماتیک")),
    ("دنا پلاس ۶ دنده", ("دنا پلاس MT6", "دنا پلاس 6 دنده")),
    ("تارا V1", ("تارا دستی V1", "تارا V1")),
    ("تارا V4 اتومات", ("تارا اتوماتیک V4", "تارا V4")),
    ("سورن پلاس", ("سورن پلاس TU5P", "سورن پلاس XU7P", "سورن پلاس")),
    ("سورن پلاس دوگانه‌سوز", ("سورن پلاس دوگانه سوز", "سورن دوگانه")),
    ("رانا پلاس", ("رانا پلاس",)),
    ("شاهین G", ("شاهین G",)),
    ("شاهین اتومات", ("شاهین اتومات", "شاهین اتوماتیک")),
    ("شاهین پلاس", ("شاهین پلاس",)),
    ("کوییک S", ("کوییک S", "کوییک اس")),
    ("کوییک GX", ("کوییک GX",)),
    ("کوییک GXR", ("کوییک GXR",)),
    ("ساینا S", ("ساینا S",)),
    ("ساینا GX", ("ساینا GX", "ساینا دوگانه GX")),
    ("اطلس G", ("اطلس G", "اطلس")),
    ("سهند S", ("سهند S", "سهند")),
    ("ری‌را", ("ری را", "ری‌را", "ریرا")),
    ("هایما S5", ("هایما S5",)),
    ("هایما S7", ("هایما S7",)),
    ("هایما 8S", ("هایما 8S", "هایما S8")),
    ("فیدلیتی پرایم", ("فیدلیتی پرایم", "فیدلیتی 5 نفره", "فیدلیتی 7 نفره")),
    ("دیگنیتی پرایم", ("دیگنیتی پرایم", "دیگنیتی")),
    ("آریزو ۵", ("آریزو 5", "آریزو5")),
    ("ام‌وی‌ام X22 Pro", ("X22 Pro", "X22 پرو", "ام وی ام X22")),
    ("آریسان ۲", ("آریسان 2", "آریسان")),
)

PERSIAN_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬", "0123456789,")


@dataclass(frozen=True)
class CarPrice:
    name: str
    market_toman: int


def _norm(text: str) -> str:
    text = (text or "").translate(PERSIAN_TO_ASCII)
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_price(text: str) -> int | None:
    normalized = (text or "").translate(PERSIAN_TO_ASCII).replace(" ", "")
    match = re.search(r"([0-9][0-9,]{5,})", normalized)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_car_prices(html: str) -> list[CarPrice]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[tuple[str, int]] = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        price = _parse_price(cells[1])
        if price:
            rows.append((cells[0], price))
    if not rows:
        raise ValueError("car price table not found")

    result: list[CarPrice] = []
    used_rows: set[int] = set()
    for display, aliases in TARGET_MODELS:
        best: tuple[int, int] | None = None
        for idx, (row_name, price) in enumerate(rows):
            if idx in used_rows:
                continue
            rn = _norm(row_name)
            for rank, alias in enumerate(aliases):
                an = _norm(alias)
                if an == rn or an in rn:
                    candidate = (rank, idx)
                    if best is None or candidate < best:
                        best = candidate
                    break
        if best is not None:
            _, idx = best
            used_rows.add(idx)
            result.append(CarPrice(display, rows[idx][1]))
    if len(result) < 8:
        raise ValueError(f"too few target car prices found: {len(result)}")
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


def format_car_prices(prices: list[CarPrice], previous: dict[str, int] | None = None) -> str:
    previous = previous or {}
    lines = ["🚗 <b>قیمت روز خودرو | بازار آزاد</b>"]
    for item in prices:
        lines += ["", f"▫️ <b>{escape(item.name)}</b>: {item.market_toman:,} تومان{_change_line(item.market_toman, previous.get(item.name))}"]
    lines += [
        "",
        f'📌 <a href="{CAR_PRICE_URL}">منبع: {CAR_SOURCE_NAME}</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ]
    return "\n".join(lines)
