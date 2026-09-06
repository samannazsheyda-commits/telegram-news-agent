from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .persian_datetime import format_persian_number, tehran_persian_date_time, to_persian_digits

MOBILE_PRICE_URL = "https://www.mobile.ir/phones/prices.aspx"
CHANNEL_URL = "https://t.me/bikhabaar"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
TEHRAN = ZoneInfo("Asia/Tehran")
TELEGRAPH_API_URL = "https://api.telegra.ph"
PHONE_BANNER_URL = (
    "https://raw.githubusercontent.com/samannazsheyda-commits/telegram-news-agent/"
    "main/assets/phone_price_banner.jpg"
)

_PERSIAN_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬", "0123456789,")

_SEARCH_TERMS = (
    "iPhone",
    "Samsung Galaxy S",
    "Samsung Galaxy Z",
    "Xiaomi",
    "Google Pixel",
    "Honor Magic",
    "OnePlus",
    "Huawei",
    "Oppo Find",
    "vivo X",
    "Nothing Phone",
    "Motorola Edge",
    "Sony Xperia",
)

_OTHER_PREFIXES = (
    "Google Pixel",
    "Honor Magic",
    "OnePlus",
    "Huawei ",
    "Oppo Find",
    "vivo X",
    "Vivo X",
    "Nothing Phone",
    "Motorola Edge",
    "Sony Xperia",
)


@dataclass(frozen=True)
class FlagshipPhonePrice:
    name: str
    price_toman: int
    registered_toman: int | None = None
    unregistered_toman: int | None = None


def _parse_price(text: str) -> int | None:
    normalized = (text or "").translate(_PERSIAN_TO_ASCII).replace(" ", "")
    match = re.search(r"([0-9][0-9,]{5,})", normalized)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _registry_status(text: str) -> str | None:
    value = " ".join((text or "").split())
    unregistered_terms = (
        "بدون رجیستر", "بدون ریجستر", "بدون رجیستری", "بدون ریجستری",
    )
    if any(term in value for term in unregistered_terms):
        return "unregistered"
    registered_terms = ("رجیستر", "ریجستر", "رجیستری", "ریجستری")
    if any(term in value for term in registered_terms):
        return "registered"
    return None


def _bucket(name: str) -> str | None:
    value = (name or "").strip()
    if value.startswith("Apple iPhone"):
        return "apple"
    if re.match(r"^Samsung Galaxy (?:S\d|Z (?:Fold|Flip)\d)", value, re.I):
        return "samsung"
    if value.startswith("Xiaomi "):
        return "xiaomi"
    if value.startswith(_OTHER_PREFIXES):
        return "other"
    return None


def _variant_weight(name: str) -> int:
    value = name.lower()
    if "pro max" in value:
        return 50
    if "ultra" in value:
        return 45
    if "pro" in value:
        return 40
    if "fold" in value:
        return 38
    if "air" in value:
        return 35
    if "+" in value or "plus" in value:
        return 30
    if "flip" in value:
        return 28
    return 20


def _priority_score(item: FlagshipPhonePrice, bucket: str) -> int:
    name = item.name
    if bucket == "apple":
        match = re.search(r"iPhone\s+(\d+)", name, re.I)
        series = int(match.group(1)) if match else 0
        return series * 100 + _variant_weight(name)

    if bucket == "samsung":
        sm = re.search(r"Galaxy S(\d+)", name, re.I)
        if sm:
            return int(sm.group(1)) * 100 + _variant_weight(name)
        zm = re.search(r"Galaxy Z (?:Fold|Flip)(\d+)", name, re.I)
        if zm:
            return 2500 + int(zm.group(1)) * 10 + _variant_weight(name)
        return 0

    if bucket == "xiaomi":
        match = re.search(r"^Xiaomi\s+(\d+)", name, re.I)
        if match:
            return int(match.group(1)) * 100 + _variant_weight(name)
        mix = re.search(r"MIX\s+(?:Fold|Flip)\s*(\d+)", name, re.I)
        if mix:
            return 1500 + int(mix.group(1)) * 10 + _variant_weight(name)
        return 0

    return 0


def parse_flagship_phone_prices(html: str) -> list[FlagshipPhonePrice]:
    """Return up to 10 Apple, 10 Samsung, 10 Xiaomi and 10 other premium models with real prices."""
    soup = BeautifulSoup(html or "", "html.parser")
    by_name: dict[str, dict[str, int | None]] = {}
    order: list[str] = []

    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        for index, cell in enumerate(cells):
            name = cell.strip()
            if _bucket(name) is None:
                continue

            price = next(
                (value for value in (_parse_price(x) for x in cells[index + 1 :]) if value),
                None,
            )
            if not price:
                break

            if name not in by_name:
                order.append(name)
                by_name[name] = {
                    "lowest": price,
                    "registered": None,
                    "unregistered": None,
                }
            else:
                by_name[name]["lowest"] = min(int(by_name[name]["lowest"] or price), price)

            status = _registry_status(" ".join(cells[index + 1 :]))
            if status:
                current = by_name[name][status]
                by_name[name][status] = price if current is None else min(int(current), price)
            break

    items = [
        FlagshipPhonePrice(
            name=name,
            price_toman=int(by_name[name]["lowest"] or 0),
            registered_toman=(int(by_name[name]["registered"]) if by_name[name]["registered"] is not None else None),
            unregistered_toman=(int(by_name[name]["unregistered"]) if by_name[name]["unregistered"] is not None else None),
        )
        for name in order
        if int(by_name[name]["lowest"] or 0) > 0
    ]
    grouped: dict[str, list[FlagshipPhonePrice]] = {"apple": [], "samsung": [], "xiaomi": [], "other": []}
    for item in items:
        bucket = _bucket(item.name)
        if bucket:
            grouped[bucket].append(item)

    for bucket in ("apple", "samsung", "xiaomi"):
        grouped[bucket].sort(key=lambda item: _priority_score(item, bucket), reverse=True)

    selected = (
        grouped["apple"][:10]
        + grouped["samsung"][:10]
        + grouped["xiaomi"][:10]
        + grouped["other"][:10]
    )
    if not selected:
        raise ValueError("flagship phone prices not found")
    return selected


def fetch_flagship_phone_prices(session=requests) -> list[FlagshipPhonePrice]:
    pages: list[str] = []
    last_error: Exception | None = None
    for term in _SEARCH_TERMS:
        try:
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
                    "sort": "name",
                    "terms": term,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            response.raise_for_status()
            pages.append(response.text)
        except Exception as exc:
            last_error = exc
            continue

    if not pages:
        if last_error:
            raise last_error
        raise RuntimeError("mobile.ir returned no flagship pages")

    return parse_flagship_phone_prices("\n".join(pages))


def phone_flagships_due(state: dict, now) -> bool:
    local = now.astimezone(TEHRAN)
    return local.hour >= 12 and state.get("phone_flagships_last_sent_date") != local.date().isoformat()


def format_flagship_phone_prices(prices: list[FlagshipPhonePrice]) -> str:
    lines = ["📱 <b>پرچمدارهای موبایل | بازار ایران</b>"]
    for item in prices:
        if item.price_toman <= 0:
            continue
        lines += ["", f"▫️ <b>{escape(to_persian_digits(item.name))}</b>: از {format_persian_number(item.price_toman)} تومان"]
    lines += [
        "",
        f'📌 <a href="{MOBILE_PRICE_URL}">منبع: mobile.ir</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ]
    return "\n".join(lines)


def _section_for(item: FlagshipPhonePrice) -> str:
    bucket = _bucket(item.name)
    return {
        "apple": "آیفون",
        "samsung": "سامسونگ",
        "xiaomi": "شیائومی",
        "other": "سایر برندها",
    }.get(bucket or "", "سایر برندها")


def _has_price(item: FlagshipPhonePrice) -> bool:
    return any((item.price_toman > 0, (item.registered_toman or 0) > 0, (item.unregistered_toman or 0) > 0))


def _phone_price_children(item: FlagshipPhonePrice) -> list:
    children: list = [{"tag": "strong", "children": [to_persian_digits(item.name)]}]
    if item.registered_toman:
        children.extend([{"tag": "br"}, f"با رجیستر: {format_persian_number(item.registered_toman)} تومان"])
    if item.unregistered_toman:
        children.extend([{"tag": "br"}, f"بدون رجیستر: {format_persian_number(item.unregistered_toman)} تومان"])
    if not item.registered_toman and not item.unregistered_toman and item.price_toman > 0:
        children.extend([{"tag": "br"}, f"قیمت بازار: {format_persian_number(item.price_toman)} تومان"])
    return children


def _phone_summary(prices: list[FlagshipPhonePrice], date_text: str) -> str:
    visible = [item for item in prices if _has_price(item)]
    if not visible:
        return f"در فهرست قیمت روز موبایل ({date_text}) قیمت قابل انتشار در منبع ثبت نشده است."

    def peak(item: FlagshipPhonePrice) -> int:
        return max(item.registered_toman or 0, item.unregistered_toman or 0, item.price_toman or 0)

    highest = max(visible, key=peak)
    amount = peak(highest)
    status = " (با رجیستر)" if highest.registered_toman and amount == highest.registered_toman else ""
    return (
        f"در فهرست قیمت روز موبایل ({date_text})، گران‌ترین مدل دارای قیمت "
        f"{to_persian_digits(highest.name)} با قیمت {format_persian_number(amount)} تومان{status} ثبت شده است. "
        f"این فهرست فقط مدل‌هایی را نمایش می‌دهد که قیمت واقعی در منبع دارند. منبع: mobile.ir"
    )


def _telegraph_phone_nodes(prices: list[FlagshipPhonePrice], now: datetime | None = None) -> list[dict]:
    date_text, time_text = tehran_persian_date_time(now)
    visible = [item for item in prices if _has_price(item)]
    nodes: list[dict] = [
        {"tag": "figure", "children": [{"tag": "img", "attrs": {"src": PHONE_BANNER_URL}}]},
        {"tag": "p", "children": [{"tag": "strong", "children": [f"آخرین به‌روزرسانی: {date_text}، ساعت {time_text}"]}]},
        {"tag": "blockquote", "children": [_phone_summary(visible, date_text)]},
        {"tag": "hr"},
    ]
    sections = ("آیفون", "سامسونگ", "شیائومی", "سایر برندها")
    for section in sections:
        rows = [item for item in visible if _section_for(item) == section]
        if not rows:
            continue
        nodes.append({"tag": "h3", "children": [section]})
        for item in rows:
            nodes.append({"tag": "p", "children": _phone_price_children(item)})
        nodes.append({"tag": "hr"})

    nodes.extend([
        {
            "tag": "p",
            "children": [
                "منبع: ",
                {"tag": "a", "attrs": {"href": MOBILE_PRICE_URL}, "children": ["mobile.ir"]},
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


def create_phone_telegraph_page(
    prices: list[FlagshipPhonePrice],
    *,
    session=requests,
    now: datetime | None = None,
) -> str:
    date_text, _ = tehran_persian_date_time(now)
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
            "title": f"قیمت روز موبایل | {date_text}",
            "author_name": "بی‌خبر",
            "author_url": CHANNEL_URL,
            "content": json.dumps(_telegraph_phone_nodes(prices, now), ensure_ascii=False),
            "return_content": "false",
        },
        timeout=30,
    ))
    url = str(page.get("url") or "")
    if not url.startswith("https://telegra.ph/"):
        raise RuntimeError("Telegraph page URL missing")
    return url


def format_phone_telegraph_post(
    page_url: str,
    count: int,
    *,
    now: datetime | None = None,
) -> str:
    del count
    date_text, time_text = tehran_persian_date_time(now)
    return "\n".join([
        f'📱 <a href="{escape(page_url, quote=True)}"><b>قیمت روز موبایل | {date_text}</b></a>',
        f"آخرین به‌روزرسانی: ساعت {time_text} به وقت ایران",
        "",
        f'📌 <a href="{MOBILE_PRICE_URL}">منبع: mobile.ir</a>',
        "",
        f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ])
