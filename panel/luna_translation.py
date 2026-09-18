from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

from src.strict_translation import _preserves_key_entities


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?%?")
_URL_RE = re.compile(r"https?://[^\s)\]}]+", re.I)
_HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,}")
_MECHANICAL = (
    "به یک نقطه خفه کننده",
    "به قتل رسید و",
    "ترجمه ماشینی",
    "به عنوان یک مدل",
)

_SCHEMA = {
    "type": "json_schema",
    "name": "luna_news_translation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title_fa": {"type": "string"},
            "body_fa": {"type": "string"},
            "source_language": {"type": "string"},
            "quality_notes": {"type": "string"},
        },
        "required": ["title_fa", "body_fa", "source_language", "quality_notes"],
        "additionalProperties": False,
    },
}

_INSTRUCTIONS = """تو مترجم و ویراستار دقیق خبر برای رسانه فارسی بی‌خبر هستی.
فقط ترجمه خبری طبیعی و وفادار بده؛ هیچ تحلیل، قضاوت، توصیه انتشار یا اطلاعات تازه اضافه نکن.
نام اشخاص/کشورها/سازمان‌ها، اعداد، تاریخ‌ها، واحدها، نسبت‌ها، نقل‌قول‌ها، منبع انتساب و میزان قطعیت را دقیق حفظ کن.
چیزی را که در متن منبع نیست اضافه نکن و هیچ واقعیت مهمی را حذف نکن.
فارسی باید روان، کوتاه، خبری و با نشانه‌گذاری درست باشد. خروجی را فقط طبق schema بده."""


def _persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _numbers(value: str) -> set[str]:
    normalized = str(value or "").translate(_PERSIAN_DIGITS)
    return {item.replace(",", "") for item in _NUMBER_RE.findall(normalized)}


def _parse(client, response: dict) -> dict:
    raw = client.output_text(response)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _quality_failures(source_title: str, source_body: str, translated: dict) -> list[str]:
    title = str(translated.get("title_fa") or "").strip()
    body = str(translated.get("body_fa") or "").strip()
    source = "\n".join(x for x in (source_title.strip(), source_body.strip()) if x)
    output = "\n".join(x for x in (title, body) if x)
    failures: list[str] = []
    if not title or not _persian(title):
        failures.append("تیتر فارسی معتبر نیست")
    if source_body.strip() and (not body or not _persian(body)):
        failures.append("بدنه فارسی معتبر نیست")
    source_numbers = _numbers(source)
    output_numbers = _numbers(output)
    missing_numbers = sorted(source_numbers - output_numbers)
    if missing_numbers:
        failures.append("اعداد منبع حذف یا تغییر کرده‌اند: " + ", ".join(missing_numbers[:8]))
    source_urls = set(_URL_RE.findall(source))
    extra_urls = set(_URL_RE.findall(output)) - source_urls
    if extra_urls:
        failures.append("لینک جدید ساخته شده است")
    source_handles = set(_HANDLE_RE.findall(source))
    extra_handles = set(_HANDLE_RE.findall(output)) - source_handles
    if extra_handles:
        failures.append("هندل جدید ساخته شده است")
    if source and output and not _preserves_key_entities(source, output):
        failures.append("یک بازیگر/موجودیت کلیدی منبع حفظ نشده است")
    if any(pattern in output for pattern in _MECHANICAL):
        failures.append("عبارت مکانیکی/نامطمئن در ترجمه دیده شد")
    source_len = len(re.sub(r"\s+", "", source))
    output_len = len(re.sub(r"\s+", "", output))
    if source_len > 80 and (output_len < source_len * 0.22 or output_len > source_len * 3.2):
        failures.append("طول ترجمه نسبت به منبع مشکوک است")
    return failures


class LunaTranslationService:
    def __init__(self, client) -> None:
        self.client = client

    def _request(self, source_title: str, source_body: str, *, repair_reasons: list[str] | None = None) -> dict:
        source = f"TITLE:\n{source_title}\n\nBODY:\n{source_body}".strip()
        if repair_reasons:
            prompt = (
                "ترجمه قبلی کنترل کیفیت را رد کرد. از ابتدا ترجمه کن و این خطاها را حتماً اصلاح کن:\n- "
                + "\n- ".join(repair_reasons)
                + "\n\nSOURCE:\n"
                + source
            )
            model = self.client.complex_model
        else:
            prompt = "این خبر را دقیق و طبیعی به فارسی ترجمه کن.\n\nSOURCE:\n" + source
            model = self.client.fast_model
        response = self.client.create_response(
            input_items=prompt,
            model=model,
            instructions=_INSTRUCTIONS,
            text_format=_SCHEMA,
        )
        return _parse(self.client, response)

    def translate(self, source_title: str, source_body: str = "") -> dict:
        source_title = str(source_title or "").strip()
        source_body = str(source_body or "").strip()
        if not source_title and not source_body:
            return {"quality_passed": False, "title_fa": "", "body_fa": "", "source_language": "", "quality_notes": "متن منبع خالی است", "repaired": False}

        first = self._request(source_title, source_body)
        failures = _quality_failures(source_title, source_body, first)
        repaired = False
        candidate = first
        if failures:
            repaired = True
            candidate = self._request(source_title, source_body, repair_reasons=failures)
            failures = _quality_failures(source_title, source_body, candidate)
        if failures:
            return {
                "quality_passed": False,
                "title_fa": "",
                "body_fa": "",
                "source_language": str(candidate.get("source_language") or first.get("source_language") or ""),
                "quality_notes": "؛ ".join(failures),
                "repaired": repaired,
            }
        return {
            "quality_passed": True,
            "title_fa": str(candidate.get("title_fa") or "").strip(),
            "body_fa": str(candidate.get("body_fa") or "").strip(),
            "source_language": str(candidate.get("source_language") or "").strip(),
            "quality_notes": str(candidate.get("quality_notes") or "").strip(),
            "repaired": repaired,
        }


def _write_list(data, path: str, transform, message: str):
    for attempt in range(3):
        rows, sha = data.read_json(path, [])
        rows = rows if isinstance(rows, list) else []
        updated = transform([dict(row) for row in rows if isinstance(row, dict)])
        try:
            data.write_json(path, updated, sha, message)
            return updated
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and status in {409, 422}:
                continue
            raise
    raise RuntimeError("translation_write_conflict")


def translate_story_in_repository(data, story_id: str, client) -> dict:
    wanted = str(story_id or "").strip()
    if not wanted:
        return {"ok": False, "error": "story_id_required", "message": "شناسه خبر لازم است."}
    found = None
    found_path = ""
    for path in ("data/panel_live_feed.json", "data/editorial_queue.json"):
        rows, _ = data.read_json(path, [])
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and str(row.get("id") or row.get("item_id") or row.get("story_id") or "") == wanted:
                found = dict(row)
                found_path = path
                break
        if found is not None:
            break
    if found is None:
        return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
    original_title = str(found.get("original_title") or found.get("title") or "").strip()
    original_body = str(found.get("original_summary") or found.get("summary") or found.get("body") or "").strip()
    result = LunaTranslationService(client).translate(original_title, original_body)
    if not result.get("quality_passed"):
        def mark_failed(rows):
            for row in rows:
                if str(row.get("id") or row.get("item_id") or row.get("story_id") or "") == wanted:
                    row["luna_translation_status"] = "needs_review"
                    row["luna_translation_quality_notes"] = result.get("quality_notes")
                    row["luna_translation_checked_at"] = datetime.now(timezone.utc).isoformat()
            return rows
        _write_list(data, found_path, mark_failed, "panel v4.1: mark Luna translation for review")
        return {"ok": False, "error": "translation_quality_failed", "message": "ترجمه نیاز به بررسی دارد و به‌عنوان متن نهایی ذخیره نشد.", **result}

    now = datetime.now(timezone.utc).isoformat()
    def save(rows):
        for row in rows:
            if str(row.get("id") or row.get("item_id") or row.get("story_id") or "") == wanted:
                row["final_persian_title"] = result["title_fa"]
                row["final_persian_body"] = result["body_fa"]
                row["persian_title"] = result["title_fa"]
                row["persian_body"] = result["body_fa"]
                row["luna_translation_status"] = "passed"
                row["luna_translation_quality_notes"] = result.get("quality_notes") or ""
                row["luna_translation_repaired"] = bool(result.get("repaired"))
                row["luna_translation_checked_at"] = now
                row["updated_at"] = now
        return rows
    _write_list(data, found_path, save, "panel v4.1: save guarded Luna translation")
    return {"ok": True, "message": "ترجمه Luna با کنترل کیفیت ذخیره شد.", **result}
