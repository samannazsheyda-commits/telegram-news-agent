from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import requests

from src.newsroom_v5_identity import reject_story as reject_v5_story
from src.newsroom_v5_jobs import enqueue_once
from src.newsroom_v5_publish import prepare_publication
from src.services import has_persian

from .luna_proposals import proposal_fingerprint
from .luna_publish import publish_story
from .luna_translation import translate_story_in_repository


def _text(value) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LunaControlRuntime:
    """One policy path for Luna reads, mutation proposals, confirmations and audit."""

    SOURCE_CAPABILITIES = {
        "rename_source",
        "enable_source",
        "disable_source",
        "delete_source",
        "set_source_review_only",
    }
    STORY_CAPABILITIES = {
        "get_story",
        "translate_story",
        "publish_story",
        "reject_and_block_story",
        "move_story_to_review",
        "edit_story_copy",
    }
    V5_EDITABLE_STATES = {"review", "editorial_ready"}

    def __init__(
        self,
        *,
        registry,
        toolbox,
        resolver,
        proposals,
        provider_client=None,
        enqueue=None,
        builder=None,
        builder_release_factory=None,
        events=None,
    ) -> None:
        self.events = events
        self.registry = registry
        self.toolbox = toolbox
        self.resolver = resolver
        self.proposals = proposals
        self.provider_client = provider_client
        self.enqueue = enqueue
        self.builder = builder
        self.builder_release_factory = builder_release_factory

    def _mutate(self, path: str, default, transform, message: str):
        data = self.toolbox.data
        for attempt in range(3):
            value, sha = data.read_json(path, default)
            updated = transform(deepcopy(value))
            try:
                data.write_json(path, updated, sha, message)
                return updated
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < 2 and status in {409, 422}:
                    continue
                raise
        raise RuntimeError("luna_control_write_conflict")

    def _resolve(self, name: str, args: dict, context: dict) -> dict:
        if name in self.SOURCE_CAPABILITIES:
            resolved = self.resolver.resolve_source(args, context)
            if not resolved.get("ok"):
                return resolved
            clean = dict(args)
            clean["source_id"] = resolved["source"]["id"]
            clean.pop("query", None)
            return {"ok": True, "args": clean, "row": dict(resolved["row"]), "public": dict(resolved["source"])}
        if name in self.STORY_CAPABILITIES:
            resolved = self.resolver.resolve_story(args, context)
            if not resolved.get("ok"):
                return resolved
            clean = dict(args)
            clean["story_id"] = resolved["story"]["id"]
            return {"ok": True, "args": clean, "row": dict(resolved["row"]), "public": dict(resolved["story"])}
        return {"ok": True, "args": dict(args)}

    @staticmethod
    def _source_snapshot(row: dict) -> dict:
        return {
            "id": _text(row.get("id")),
            "name": _text(row.get("name") or row.get("display_name") or row.get("id")),
            "identity": _text(row.get("identity") or row.get("handle") or row.get("channel") or row.get("website_url") or row.get("feed_url")),
            "active": bool(row.get("active", True)),
            "system": bool(row.get("system", False)),
            "review_only": bool(row.get("review_only", False)),
        }

    @staticmethod
    def _story_snapshot(row: dict) -> dict:
        return {
            "id": _text(row.get("id") or row.get("item_id") or row.get("story_id")),
            "source": _text(row.get("source")),
            "source_url": _text(row.get("source_url") or row.get("link")),
            "panel_status": _text(row.get("panel_status") or row.get("status")),
            "persian_title": _text(row.get("persian_title")),
            "persian_body": _text(row.get("persian_body")),
            "final_persian_title": _text(row.get("final_persian_title")),
            "final_persian_body": _text(row.get("final_persian_body")),
            "luna_translation_status": _text(row.get("luna_translation_status")),
        }

    def _preview(self, name: str, resolved: dict) -> dict:
        args = dict(resolved["args"])
        if name == "rename_source":
            row = dict(resolved["row"])
            before = self._source_snapshot(row)
            after = dict(before)
            after["name"] = _text(args.get("display_name"))
            return {
                "target": {"type": "source", "id": before["id"]},
                "payload": args,
                "summary_fa": f"نام نمایشی {before['name']} به «{after['name']}» تغییر کند؟",
                "before": before,
                "after": after,
                "target_fingerprint": proposal_fingerprint(before),
            }
        if name in {"enable_source", "disable_source", "delete_source", "set_source_review_only"}:
            row = dict(resolved["row"])
            before = self._source_snapshot(row)
            after = dict(before)
            if name == "enable_source":
                after["active"] = True
                summary = f"منبع «{before['name']}» فعال شود؟"
            elif name == "disable_source":
                after["active"] = False
                summary = f"منبع «{before['name']}» غیرفعال شود؟"
            elif name == "delete_source":
                after["deleted"] = True
                summary = f"منبع «{before['name']}» از رصد حذف شود؟"
            else:
                after["review_only"] = bool(args.get("enabled"))
                summary = f"خبرهای منبع «{before['name']}» {'فقط برای بررسی بروند' if after['review_only'] else 'از حالت فقط بررسی خارج شوند'}؟"
            return {
                "target": {"type": "source", "id": before["id"]},
                "payload": args,
                "summary_fa": summary,
                "before": before,
                "after": after,
                "target_fingerprint": proposal_fingerprint(before),
            }
        if name in self.STORY_CAPABILITIES:
            row = dict(resolved["row"])
            before = self._story_snapshot(row)
            title = _text(row.get("final_persian_title") or row.get("persian_title") or row.get("original_title") or row.get("title"))
            if name == "edit_story_copy":
                return self._edit_copy_preview(row, before, args)
            if name == "publish_story":
                mode = _text(args.get("copy_mode")) or "machine"
                args["copy_mode"] = mode
                summary = f"{'نسخه Luna' if mode == 'luna' else 'همین ترجمه ماشینی'} منتشر شود؟ «{title}»"
            elif name == "translate_story":
                summary = f"Luna خبر «{title}» را ترجمه و نسخه نهایی را ذخیره کند؟"
            elif name == "reject_and_block_story":
                summary = f"خبر «{title}» رد و برای انتشارهای بعدی مسدود شود؟"
            else:
                summary = f"خبر «{title}» به صف بررسی منتقل شود؟"
            return {
                "target": {"type": "story", "id": before["id"]},
                "payload": args,
                "summary_fa": summary,
                "before": before,
                "after": {},
                "target_fingerprint": proposal_fingerprint(before),
            }
        if name == "set_newsroom_alarm":
            settings, _ = self.toolbox.data.read_json("data/panel_settings.json", {})
            settings = dict(settings) if isinstance(settings, dict) else {}
            before = {"newsroom_alarm_enabled": bool(settings.get("newsroom_alarm_enabled", True))}
            after = {"newsroom_alarm_enabled": bool(args.get("enabled"))}
            return {
                "target": {"type": "setting", "id": "newsroom_alarm_enabled"},
                "payload": {"enabled": bool(args.get("enabled"))},
                "summary_fa": f"صدای آلارم خبر جدید {'فعال' if after['newsroom_alarm_enabled'] else 'بی‌صدا'} شود؟",
                "before": before,
                "after": after,
                "target_fingerprint": proposal_fingerprint(before),
            }
        if name == "add_source":
            return {
                "target": {"type": "source", "id": "new"},
                "payload": args,
                "summary_fa": f"منبع «{_text(args.get('display_name') or args.get('identifier'))}» به رصد اضافه شود؟",
                "before": {},
                "after": dict(args),
                "target_fingerprint": proposal_fingerprint({}),
            }
        if name in {"builder_prepare", "builder_prepare_merge"}:
            summary = (
                "Luna این تغییر کدنویسی را روی branch جدا بسازد، تست اضافه کند و Draft PR باز کند؟"
                if name == "builder_prepare"
                else f"PR #{int(args.get('pr_number') or 0)} با CI سبز به main merge شود؟"
            )
            return {
                "target": {"type": "builder", "id": str(args.get("pr_number") or "new")},
                "payload": args,
                "summary_fa": summary,
                "before": {},
                "after": {},
                "target_fingerprint": proposal_fingerprint({}),
            }
        raise ValueError(f"unsupported_mutation:{name}")

    def _edit_copy_preview(self, row: dict, before: dict, args: dict) -> dict:
        if not row.get("_v5"):
            raise ValueError("ویرایش تیتر و متن فقط برای خبرهای اتاق خبر V5 در دسترس است.")
        if _text(row.get("status")) not in self.V5_EDITABLE_STATES:
            raise ValueError("این خبر دیگر در صف بررسی نیست و قابل ویرایش نیست.")
        new_title = _text(args.get("title_fa"))
        if not new_title or not has_persian(new_title):
            raise ValueError("تیتر فارسی جدید لازم است.")
        payload = {"story_id": before["id"], "title_fa": new_title}
        after = dict(before)
        after["persian_title"] = new_title
        if "body_fa" in args:
            payload["body_fa"] = _text(args.get("body_fa"))
            after["persian_body"] = payload["body_fa"]
        summary = f"تیتر خبر به «{new_title}» تغییر کند؟"
        if "body_fa" in payload:
            summary = f"تیتر به «{new_title}» و متن خبر به نسخه جدید تغییر کند؟"
        return {
            "target": {"type": "story", "id": before["id"]},
            "payload": payload,
            "summary_fa": summary,
            "before": before,
            "after": after,
            "target_fingerprint": proposal_fingerprint(before),
        }

    def invoke(self, name: str, args: dict | None = None, context: dict | None = None) -> dict:
        try:
            capability = self.registry.get(name)
        except KeyError:
            return {"ok": False, "error": "unknown_capability", "message": "این قابلیت برای Luna تعریف نشده است."}
        resolved = self._resolve(name, dict(args or {}), dict(context or {}))
        if not resolved.get("ok"):
            return resolved
        if not capability.mutates:
            return self._execute(name, resolved["args"], confirmed=True)
        try:
            preview = self._preview(name, resolved)
        except ValueError as exc:
            return {"ok": False, "error": "invalid_capability_arguments", "message": str(exc)}
        proposal = self.proposals.create(
            capability=name,
            target=preview["target"],
            payload=preview["payload"],
            summary_fa=preview["summary_fa"],
            before=preview["before"],
            after=preview["after"],
            target_fingerprint=preview["target_fingerprint"],
        )
        return {
            "ok": True,
            "confirmation_required": True,
            "action_id": proposal["id"],
            "summary_fa": proposal["summary_fa"],
            "target": deepcopy(proposal["target"]),
            "before": deepcopy(proposal["before"]),
            "after": deepcopy(proposal["after"]),
        }

    def _current_target_snapshot(self, proposal: dict) -> dict:
        target = dict(proposal.get("target") or {})
        target_type = _text(target.get("type"))
        target_id = _text(target.get("id"))
        if target_type == "source":
            if target_id == "new":
                return {}
            resolved = self.resolver.resolve_source({"source_id": target_id}, {})
            return self._source_snapshot(resolved["row"]) if resolved.get("ok") else {"missing": True}
        if target_type == "story":
            resolved = self.resolver.resolve_story({"story_id": target_id}, {})
            return self._story_snapshot(resolved["row"]) if resolved.get("ok") else {"missing": True}
        if target_type == "setting":
            settings, _ = self.toolbox.data.read_json("data/panel_settings.json", {})
            settings = dict(settings) if isinstance(settings, dict) else {}
            return {"newsroom_alarm_enabled": bool(settings.get("newsroom_alarm_enabled", True))}
        return {}

    def confirm(self, action_id: str) -> dict:
        proposal = self.proposals.get_pending(action_id)
        if proposal.get("status") != "pending":
            return {"ok": False, "error": "proposal_not_pending", "message": "این تأیید دیگر معتبر نیست."}
        current = self._current_target_snapshot(proposal)
        if proposal_fingerprint(current) != _text(proposal.get("target_fingerprint")):
            result = {"ok": False, "error": "target_changed", "message": "هدف بعد از پیشنهاد تغییر کرده؛ درخواست را دوباره به Luna بگو."}
            self.proposals.complete(action_id, "failed", result)
            self._audit(proposal, result, "failed")
            return result
        if not self.proposals.claim(action_id):
            return {"ok": False, "error": "proposal_not_pending", "message": "این تأیید قبلاً مصرف شده یا دیگر معتبر نیست."}
        try:
            result = self._execute(
                _text(proposal.get("capability")),
                dict(proposal.get("payload") or {}),
                confirmed=True,
                action_id=action_id,
            )
        except Exception as exc:
            result = {"ok": False, "error": "execution_failed", "message": f"اجرای عملیات ناموفق بود: {type(exc).__name__}"}
            self.proposals.complete(action_id, "failed", result)
            self._audit(proposal, result, "failed")
            raise
        status = "success" if result.get("ok") else "failed"
        self.proposals.complete(action_id, status, result)
        self._audit(proposal, result, status)
        return result

    def _v5_story(self, args: dict) -> dict | None:
        store = getattr(self.toolbox, "v5_store", None)
        if store is None or not _text(args.get("story_id")):
            return None
        return store.get_story(_text(args.get("story_id")))

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.events is None:
            return
        try:
            self.events.publish(event_type, payload)
        except Exception:
            pass

    def _emit_story_change(self, story_id: str, state: str) -> None:
        store = self.toolbox.v5_store
        self._emit("story_updated", {"story_id": story_id, "state": state})
        rows = store.conn.execute("SELECT state, COUNT(*) FROM stories GROUP BY state").fetchall()
        counts = {str(row[0]): int(row[1]) for row in rows}
        self._emit("counts_changed", {
            key: counts.get(key, 0) for key in ("review", "publishing", "published", "rejected", "failed")
        })

    def _execute_v5(self, name: str, story: dict, args: dict, action_id: str) -> dict | None:
        store = self.toolbox.v5_store
        story_id = _text(story.get("id"))
        title = _text(story.get("title_fa") or story.get("original_title"))
        if name == "edit_story_copy":
            if _text(story.get("state")) not in self.V5_EDITABLE_STATES:
                return {"ok": False, "error": "story_not_editable", "message": "این خبر دیگر در صف بررسی نیست و قابل ویرایش نیست."}
            new_title = _text(args.get("title_fa"))
            if not new_title or not has_persian(new_title):
                return {"ok": False, "error": "persian_title_required", "message": "تیتر فارسی جدید لازم است."}
            body = _text(args.get("body_fa")) if "body_fa" in args else _text(story.get("body_fa"))
            store.set_translation(story_id, title_fa=new_title, body_fa=body, backend="luna", quality_passed=True, last_error=None)
            store.append_audit("story_copy_edited", actor="luna_operator", entity_type="story", entity_id=story_id,
                               detail={"copy_mode": "luna", "action_id": action_id})
            self._emit_story_change(story_id, _text(story.get("state")))
            return {"ok": True, "message": "تیتر خبر به‌روزرسانی شد.", "story": {"id": story_id, "title": new_title}}
        if name == "publish_story":
            mode = _text(args.get("copy_mode")) or "machine"
            try:
                publication = prepare_publication(store, story_id, idempotency_key=f"luna:{action_id}", copy_mode=mode)
            except (KeyError, ValueError) as exc:
                return {"ok": False, "error": "story_not_publishable", "message": f"این خبر قابل انتشار نیست: {exc}"}
            self._emit_story_change(story_id, "publishing")
            return {"ok": True, "message": "خبر در صف امن انتشار قرار گرفت.", "publication_id": publication["id"],
                    "story": {"id": story_id, "title": title}}
        if name == "reject_and_block_story":
            if _text(story.get("state")) == "rejected":
                return {"ok": True, "message": "این خبر قبلاً رد شده بود.", "story": {"id": story_id, "title": title}}
            try:
                reject_v5_story(store, story_id, actor="luna_operator")
            except (KeyError, ValueError) as exc:
                return {"ok": False, "error": "story_not_rejectable", "message": f"رد این خبر ممکن نشد: {exc}"}
            self._emit("story_rejected", {"story_id": story_id})
            self._emit_story_change(story_id, "rejected")
            return {"ok": True, "message": "خبر رد شد و دوباره برنمی‌گردد.", "story": {"id": story_id, "title": title}}
        if name == "move_story_to_review":
            if not store.transition_story(story_id, {"editorial_ready", "failed"}, "review"):
                return {"ok": False, "error": "story_not_movable", "message": "این خبر در وضعیتی نیست که به صف بررسی برگردد."}
            self._emit_story_change(story_id, "review")
            return {"ok": True, "message": "خبر به صف بررسی منتقل شد.", "story": {"id": story_id, "title": title}}
        if name == "translate_story":
            enqueue_once(store, "translate_story", story_id=story_id, key=f"luna-translate:{action_id}")
            return {"ok": True, "message": "ترجمه این خبر در صف قرار گرفت.", "story": {"id": story_id, "title": title}}
        return None

    def _execute(self, name: str, args: dict, *, confirmed: bool, action_id: str = "") -> dict:
        if name in self.STORY_CAPABILITIES and name != "get_story":
            story = self._v5_story(args)
            if story is not None:
                result = self._execute_v5(name, story, args, action_id or uuid4().hex)
                if result is not None:
                    return result
            elif name == "edit_story_copy":
                return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        if name == "rename_source":
            resolved = self.resolver.resolve_source({"source_id": args.get("source_id")}, {})
            if not resolved.get("ok"):
                return resolved
            row = dict(resolved["row"])
            source_id = _text(resolved["source"]["id"])
            display_name = _text(args.get("display_name"))
            if not display_name:
                return {"ok": False, "error": "display_name_required", "message": "نام نمایشی جدید لازم است."}
            if row.get("system"):
                def transform(value):
                    overrides = dict(value) if isinstance(value, dict) else {}
                    state = dict(overrides.get(source_id) or {})
                    state.update(display_name=display_name, updated_at=_now())
                    overrides[source_id] = state
                    return overrides
                self._mutate("data/source_overrides.json", {}, transform, "panel v4.2: Luna rename system source")
            else:
                def transform(value):
                    rows = list(value) if isinstance(value, list) else []
                    for item in rows:
                        if isinstance(item, dict) and _text(item.get("id")) == source_id:
                            item["name"] = display_name
                            item["updated_at"] = _now()
                            return rows
                    raise ValueError("منبع پیدا نشد.")
                self._mutate("data/custom_sources.json", [], transform, "panel v4.2: Luna rename custom source")
            return {"ok": True, "message": f"نام نمایشی منبع به «{display_name}» تغییر کرد.", "source_id": source_id, "display_name": display_name}
        if name == "set_source_review_only":
            resolved = self.resolver.resolve_source({"source_id": args.get("source_id")}, {})
            if not resolved.get("ok"):
                return resolved
            row = dict(resolved["row"])
            source_id = _text(resolved["source"]["id"])
            enabled = bool(args.get("enabled"))
            if row.get("system"):
                def transform(value):
                    overrides = dict(value) if isinstance(value, dict) else {}
                    state = dict(overrides.get(source_id) or {})
                    state.update(review_only=enabled, updated_at=_now())
                    overrides[source_id] = state
                    return overrides
                self._mutate("data/source_overrides.json", {}, transform, "panel v4.2: Luna source review policy")
            else:
                def transform(value):
                    rows = list(value) if isinstance(value, list) else []
                    for item in rows:
                        if isinstance(item, dict) and _text(item.get("id")) == source_id:
                            item["review_only"] = enabled
                            item["updated_at"] = _now()
                            return rows
                    raise ValueError("منبع پیدا نشد.")
                self._mutate("data/custom_sources.json", [], transform, "panel v4.2: Luna source review policy")
            return {"ok": True, "message": "سیاست منبع به‌روزرسانی شد.", "source_id": source_id, "review_only": enabled}
        if name == "set_newsroom_alarm":
            enabled = bool(args.get("enabled"))
            def transform(value):
                settings = dict(value) if isinstance(value, dict) else {}
                settings["newsroom_alarm_enabled"] = enabled
                settings["updated_at"] = _now()
                return settings
            self._mutate("data/panel_settings.json", {}, transform, "panel v4.2: Luna newsroom alarm setting")
            return {"ok": True, "message": f"صدای آلارم خبر جدید {'فعال' if enabled else 'بی‌صدا'} شد.", "enabled": enabled}
        if name == "publish_story":
            if self.enqueue is None:
                return {"ok": False, "error": "publish_queue_unavailable", "message": "صف امن انتشار در دسترس نیست."}
            return publish_story(
                self.toolbox.data,
                _text(args.get("story_id")),
                enqueue=self.enqueue,
                confirmed=True,
                copy_mode=_text(args.get("copy_mode")) or "machine",
            )
        if name == "translate_story":
            if self.provider_client is None:
                return {"ok": False, "error": "translation_provider_required", "message": "اتصال Luna برای ترجمه در دسترس نیست."}
            return translate_story_in_repository(self.toolbox.data, _text(args.get("story_id")), self.provider_client)
        if name == "builder_prepare":
            if self.builder is None:
                return {"ok": False, "error": "builder_unavailable", "message": "Builder در دسترس نیست."}
            return self.builder.start_change(_text(args.get("request")))
        if name in {"builder_ci_status", "builder_prepare_merge"}:
            if self.builder_release_factory is None:
                return {"ok": False, "error": "builder_release_unavailable", "message": "مسیر بررسی Builder در دسترس نیست."}
            release = self.builder_release_factory()
            pr_number = int(args.get("pr_number") or 0)
            if pr_number <= 0:
                return {"ok": False, "error": "builder_pr_required", "message": "شماره PR لازم است."}
            status = release.status(pr_number)
            if name == "builder_ci_status":
                return status
            if not status.get("ci_green"):
                return {**status, "ok": False, "error": "builder_ci_not_green", "message": "CI هنوز کامل سبز نیست؛ merge متوقف شد."}
            expected = _text(args.get("expected_head_sha") or status.get("head_sha"))
            return release.merge(pr_number, expected_head_sha=expected)
        return self.toolbox.execute(name, args, confirmed=confirmed)

    def _audit(self, proposal: dict, result: dict, status: str) -> None:
        target = deepcopy(dict(proposal.get("target") or {}))
        record = {
            "id": uuid4().hex,
            "at": _now(),
            "actor": "luna_operator",
            "capability": _text(proposal.get("capability")),
            "target": target,
            "confirmation_required": True,
            "action_id": _text(proposal.get("id")),
            "status": status,
            "summary": _text(proposal.get("summary_fa"))[:500],
            "result": {
                key: value
                for key, value in dict(result or {}).items()
                if key in {"ok", "error", "message", "command_id", "pr_number", "merge_sha"}
            },
        }
        self._mutate(
            "data/panel_audit_log.json",
            [],
            lambda rows: ([record] + [dict(row) for row in list(rows or []) if isinstance(row, dict)])[:300],
            "panel v4.2: Luna capability audit",
        )
