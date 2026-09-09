from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests

from .editorial_store import LocalEditorialStore
from .formatters import format_news
from .newsroom_publisher import _published_rfc2822, _safe_source_for_final
from .persian_editor import has_forbidden_latin_body
from .services import has_persian
from .sources import NewsItem


API_ROOT = "https://api.telegram.org/bot{token}/{method}"
ADMIN_STATUSES = {"creator", "administrator"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_authorized_member(
    user_id: int,
    bot_token: str,
    *,
    channel: str = "@bikhabaar",
    session=requests,
) -> bool:
    try:
        response = session.post(
            API_ROOT.format(token=bot_token, method="getChatMember"),
            data={"chat_id": channel, "user_id": int(user_id)},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        return bool(payload.get("ok") and isinstance(result, dict) and result.get("status") in ADMIN_STATUSES)
    except Exception:
        return False


def parse_edit_text(text: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(text or "").replace("\r", "").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return "", ""
    title = lines[0]
    body = "\n".join(lines[1:]).strip()
    combined = f"{title} {body}".strip()
    if not has_persian(title) or has_forbidden_latin_body(combined):
        return "", ""
    return title, body


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class EditorBot:
    def __init__(
        self,
        bot_token: str,
        *,
        channel: str = "@bikhabaar",
        store: LocalEditorialStore | None = None,
        command_dir: str | Path | None = None,
        state_path: str | Path | None = None,
        session=requests,
    ):
        self.bot_token = str(bot_token or "").strip()
        self.channel = str(channel or "@bikhabaar").strip()
        runtime_root = Path(os.environ.get("BIKHABAR_RUNTIME_ROOT", "/var/lib/bikhabar/runtime"))
        self.store = store or LocalEditorialStore(
            os.environ.get("EDITORIAL_QUEUE_PATH", str(runtime_root / "data" / "editorial_queue.json")),
            os.environ.get("EDITORIAL_HISTORY_PATH", str(runtime_root / "data" / "editorial_history.json")),
        )
        self.command_dir = Path(command_dir or os.environ.get("PANEL_COMMAND_DIR", str(runtime_root / "panel_commands")))
        self.state_path = Path(state_path or runtime_root / "editor_bot_state.json")
        self.session = session
        self.editing: dict[int, str] = {}

    def _api(self, method: str, payload: dict) -> dict:
        response = self.session.post(
            API_ROOT.format(token=self.bot_token, method=method),
            data=payload,
            timeout=35,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _authorized(self, user_id: int) -> bool:
        return is_authorized_member(user_id, self.bot_token, channel=self.channel, session=self.session)

    def _send(self, chat_id: int, text: str, *, keyboard: list[list[dict]] | None = None) -> None:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
        if keyboard is not None:
            payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False)
        self._api("sendMessage", payload)

    def _answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:180]})
        except Exception:
            pass

    def _queue_command(self, action: str, item, *, title: str = "", body: str = "") -> str:
        command_id = uuid4().hex
        payload = {
            "command_id": command_id,
            "action": action,
            "item_id": item.id,
            "title": title,
            "body": body,
            "created_at": _now(),
        }
        _atomic_json(self.command_dir / f"{command_id}.json", payload)
        return command_id

    @staticmethod
    def _preview(item) -> str:
        title = str(item.persian_title or item.final_persian_title or "").strip()
        body = str(item.persian_body or item.final_persian_body or "").strip()
        if not title or has_forbidden_latin_body(f"{title} {body}"):
            return "پیش‌نمایش نهایی هنوز آماده نیست."
        source_item = NewsItem(
            key=item.news_key,
            source=_safe_source_for_final(item.source),
            title=item.original_title,
            summary=item.original_summary,
            link=item.source_url,
            published=_published_rfc2822(item.published_at_source),
        )
        return format_news(source_item, title, body)

    def _item_keyboard(self, item) -> list[list[dict]]:
        return [
            [
                {"text": "👁 پیش‌نمایش", "callback_data": f"preview:{item.id}"},
                {"text": "✏️ ویرایش", "callback_data": f"edit:{item.id}"},
            ],
            [
                {"text": "✅ انتشار", "callback_data": f"publish:{item.id}"},
                {"text": "🗑 رد", "callback_data": f"reject:{item.id}"},
            ],
            [{"text": "🔗 منبع", "url": item.source_url}] if item.source_url else [],
        ]

    def _send_queue(self, chat_id: int) -> None:
        pending = [self.store.get_pending(str(row.get("id") or "")) for row in self.store.queue()]
        pending = [item for item in pending if item is not None]
        if not pending:
            self._send(chat_id, "صف سردبیری خالی است.")
            return
        self._send(chat_id, f"📰 <b>صف سردبیری: {len(pending)} خبر</b>")
        for item in pending[:10]:
            title = item.persian_title or "عنوان فارسی هنوز آماده نیست"
            self._send(chat_id, f"<b>{title}</b>\n{_safe_source_for_final(item.source)}", keyboard=self._item_keyboard(item))

    def handle_message(self, message: dict) -> None:
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        try:
            user_id = int(user.get("id"))
            chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            return
        text = str(message.get("text") or "").strip()
        if not self._authorized(user_id):
            self._send(chat_id, "⛔ این بخش فقط برای مدیران کانال بی‌خبر فعال است.")
            return

        if user_id in self.editing and text and not text.startswith("/"):
            item_id = self.editing[user_id]
            item = self.store.get_pending(item_id)
            if item is None:
                self.editing.pop(user_id, None)
                self._send(chat_id, "این خبر دیگر در صف نیست.")
                return
            title, body = parse_edit_text(text)
            if not title:
                self._send(chat_id, "متن پذیرفته نشد. خط اول تیتر فارسی باشد و هیچ واژه انگلیسی در خروجی نماند.")
                return
            updated = replace(item, persian_title=title, persian_body=body, updated_at=_now())
            self.store.upsert_queue(updated)
            self.editing.pop(user_id, None)
            self._send(chat_id, "✅ ویرایش ذخیره شد.\n\n" + self._preview(updated), keyboard=self._item_keyboard(updated))
            return

        command = text.split()[0].lower() if text else ""
        if command in {"/start", "/help"}:
            self._send(chat_id, "🛰 <b>ویراستار بی‌خبر</b>\n/queue — صف خبرها\n/status — وضعیت صف\nهر خبر را می‌توانی پیش‌نمایش، ویرایش، منتشر یا رد کنی.")
        elif command in {"/queue", "/news"}:
            self._send_queue(chat_id)
        elif command == "/status":
            self._send(chat_id, f"✅ ویراستار فعال است.\nخبرهای منتظر بررسی: {len(self.store.queue())}")
        elif command:
            self._send(chat_id, "دستور شناخته نشد. /queue را بزن.")

    def handle_callback(self, callback: dict) -> None:
        user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        callback_id = str(callback.get("id") or "")
        try:
            user_id = int(user.get("id"))
            chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            return
        if not self._authorized(user_id):
            self._answer_callback(callback_id, "دسترسی نداری")
            return
        data = str(callback.get("data") or "")
        action, sep, item_id = data.partition(":")
        if not sep or action not in {"preview", "edit", "publish", "reject"}:
            self._answer_callback(callback_id, "فرمان نامعتبر")
            return
        item = self.store.get_pending(item_id)
        if item is None:
            self._answer_callback(callback_id, "خبر دیگر در صف نیست")
            return

        if action == "preview":
            self._answer_callback(callback_id)
            self._send(chat_id, self._preview(item), keyboard=self._item_keyboard(item))
            return
        if action == "edit":
            self.editing[user_id] = item.id
            self._answer_callback(callback_id, "منتظر متن جدید")
            self._send(chat_id, "✏️ متن جدید را بفرست.\nخط اول: تیتر فارسی\nخط‌های بعد: متن خبر\nلغو: /queue")
            return
        if action == "publish":
            if not item.persian_title or has_forbidden_latin_body(f"{item.persian_title} {item.persian_body}"):
                self._answer_callback(callback_id, "خروجی فارسی معتبر نیست")
                return
            command_id = self._queue_command("publish", item, title=item.persian_title, body=item.persian_body)
            self._answer_callback(callback_id, "برای انتشار ارسال شد")
            self._send(chat_id, f"✅ فرمان انتشار ثبت شد.\nشناسه: <code>{command_id[:10]}</code>")
            return
        command_id = self._queue_command("reject", item)
        self._answer_callback(callback_id, "برای رد ارسال شد")
        self._send(chat_id, f"🗑 فرمان رد خبر ثبت شد.\nشناسه: <code>{command_id[:10]}</code>")

    def _load_offset(self) -> int:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return int(payload.get("offset") or 0) if isinstance(payload, dict) else 0
        except Exception:
            return 0

    def _save_offset(self, offset: int) -> None:
        _atomic_json(self.state_path, {"offset": int(offset), "updated_at": _now()})

    def run_forever(self) -> int:
        if not self.bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        offset = self._load_offset()
        while True:
            try:
                response = self.session.post(
                    API_ROOT.format(token=self.bot_token, method="getUpdates"),
                    data={"timeout": 25, "offset": offset, "allowed_updates": json.dumps(["message", "callback_query"])},
                    timeout=35,
                )
                response.raise_for_status()
                payload = response.json()
                updates = payload.get("result") if isinstance(payload, dict) else []
                if not isinstance(updates, list):
                    updates = []
                for update in updates:
                    if not isinstance(update, dict):
                        continue
                    update_id = int(update.get("update_id") or 0)
                    if update.get("message"):
                        self.handle_message(update["message"])
                    elif update.get("callback_query"):
                        self.handle_callback(update["callback_query"])
                    offset = max(offset, update_id + 1)
                    self._save_offset(offset)
            except KeyboardInterrupt:
                return 0
            except Exception as exc:
                print(f"EDITOR_BOT_ERROR {type(exc).__name__}:{exc}", flush=True)
                time.sleep(3)


def main() -> int:
    bot = EditorBot(
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        channel=os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
    )
    return bot.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
