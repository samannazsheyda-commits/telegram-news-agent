from __future__ import annotations

from typing import Any

from .github_builder import BuilderError
from .github_builder_release import BuilderRelease, configured_builder
from .luna_translation import translate_story_in_repository


def _latest_builder_pr(data) -> int:
    rows, _ = data.read_json("data/panel_pending_actions.json", [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("status") or "") != "completed":
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        pr = result.get("pull_request") if isinstance(result.get("pull_request"), dict) else {}
        number = int(pr.get("number") or 0)
        if number > 0:
            return number
    return 0


def _builder_pr_number(toolbox, args: dict[str, Any]) -> int:
    number = int(args.get("pr_number") or 0)
    return number if number > 0 else _latest_builder_pr(toolbox.data)


def _builder_error(exc: BuilderError) -> dict:
    return {"ok": False, "error": "builder_release_failed", "message": str(exc)}


def execute_luna_tool(
    toolbox,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    provider_client=None,
    confirmed: bool = False,
) -> dict:
    """Execute one Luna tool while keeping shared cross-tool pipelines centralized.

    Translation is routed through the same guarded repository pipeline used by
    story cards. Builder release tools are CI-gated and never expose shell or
    direct production writes.
    """
    args = dict(arguments or {})
    if name == "translate_story":
        story_id = str(args.get("story_id") or "").strip()
        if not story_id:
            return {"ok": False, "error": "story_id_required", "message": "شناسه خبر لازم است."}
        if provider_client is None:
            return {
                "ok": False,
                "error": "translation_provider_required",
                "message": "Luna برای ترجمه به اتصال OpenAI نیاز دارد.",
            }
        return translate_story_in_repository(toolbox.data, story_id, provider_client)

    if name in {"builder_ci_status", "builder_prepare_merge"}:
        pr_number = _builder_pr_number(toolbox, args)
        if pr_number <= 0:
            return {
                "ok": False,
                "error": "builder_pr_not_found",
                "message": "هنوز تغییر Builder قابل بررسی پیدا نکردم. اول یک تغییر پنل/ماژول بساز.",
            }
        try:
            release = BuilderRelease(configured_builder())
            status = release.status(pr_number)
            if name == "builder_ci_status":
                if status.get("ci_green"):
                    status["message"] = "CI این تغییر کاملاً سبز است و برای merge آماده است."
                else:
                    status["message"] = "CI هنوز کامل سبز نیست؛ Luna اجازه merge ندارد."
                return status
            if not status.get("ci_green"):
                return {
                    **status,
                    "ok": False,
                    "error": "builder_ci_not_green",
                    "message": "CI هنوز کامل سبز نیست؛ merge متوقف شد.",
                }
            if not confirmed:
                return {
                    "ok": True,
                    "confirmation_required": True,
                    "pending_action": {
                        "action": "builder_prepare_merge",
                        "payload": {
                            "pr_number": pr_number,
                            "expected_head_sha": str(status.get("head_sha") or ""),
                        },
                        "summary_fa": f"PR #{pr_number} با CI سبز به main merge شود؟ بعد از آن CI اصلی نسخه تست‌شده را به production منتقل می‌کند.",
                    },
                }
            return release.merge(
                pr_number,
                expected_head_sha=str(args.get("expected_head_sha") or ""),
            )
        except BuilderError as exc:
            return _builder_error(exc)

    return toolbox.execute(name, args, confirmed=confirmed)
