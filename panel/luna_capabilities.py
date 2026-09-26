from __future__ import annotations

from dataclasses import dataclass


_EMPTY_OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}


@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description: str
    parameters: dict
    mutates: bool
    requires_confirmation: bool
    executor_name: str

    def tool_schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        by_name: dict[str, Capability] = {}
        for capability in capabilities:
            if capability.name in by_name:
                raise ValueError(f"duplicate_capability:{capability.name}")
            if capability.mutates and not capability.requires_confirmation:
                raise ValueError(f"mutation_without_confirmation:{capability.name}")
            by_name[capability.name] = capability
        self._by_name = by_name

    def get(self, name: str) -> Capability:
        return self._by_name[str(name)]

    def all(self) -> list[Capability]:
        return list(self._by_name.values())

    def tool_schemas(self) -> list[dict]:
        return [capability.tool_schema() for capability in self.all()]


def _cap(
    name: str,
    domain: str,
    description: str,
    parameters: dict,
    *,
    mutates: bool = False,
    executor_name: str | None = None,
) -> Capability:
    return Capability(
        name=name,
        domain=domain,
        description=description,
        parameters=parameters,
        mutates=mutates,
        requires_confirmation=mutates,
        executor_name=executor_name or name,
    )


_STORY_ID_DESCRIPTION = "شناسه دقیق خبر؛ اگر کاربر به خبر جاری اشاره می‌کند («همین خبر»، «تیترش») خالی بگذار تا از context استفاده شود."


def _story_id_params(*, copy_mode: bool = False, extra: dict | None = None) -> dict:
    properties: dict = {"story_id": {"type": "string", "description": _STORY_ID_DESCRIPTION}}
    if copy_mode:
        properties["copy_mode"] = {"type": "string", "enum": ["visible", "machine", "luna"]}
    properties.update(extra or {})
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def _source_target_params(extra: dict | None = None, required: list[str] | None = None) -> dict:
    properties = {
        "source_id": {"type": "string"},
        "query": {"type": "string"},
    }
    properties.update(extra or {})
    return {
        "type": "object",
        "properties": properties,
        "required": list(required or []),
        "additionalProperties": False,
    }


def build_capability_registry() -> CapabilityRegistry:
    capabilities = [
        _cap(
            "search_stories",
            "stories",
            "جست‌وجوی خبرهای پنل بر اساس متن، منبع یا وضعیت. برای پیدا کردن خبر دقیق قبل از عملیات استفاده کن.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
        ),
        _cap("get_story", "stories", "دریافت یک خبر مشخص با شناسه دقیق.", _story_id_params()),
        _cap(
            "translate_story",
            "stories",
            "ساخت و ذخیره نسخه فارسی Luna برای یک خبر مشخص؛ چون رکورد خبر را تغییر می‌دهد قبل از اجرا تأیید لازم است.",
            _story_id_params(),
            mutates=True,
        ),
        _cap(
            "publish_story",
            "stories",
            "انتشار نسخه فارسی انتخاب‌شده یک خبر از مسیر امن انتشار؛ قبل از اجرا تأیید لازم است.",
            _story_id_params(copy_mode=True),
            mutates=True,
        ),
        _cap(
            "reject_and_block_story",
            "stories",
            "رد دائمی یک خبر و جلوگیری از ورود دوباره آن به چرخه انتشار.",
            _story_id_params(extra={"reason": {"type": "string"}}),
            mutates=True,
        ),
        _cap(
            "edit_story_copy",
            "stories",
            "ویرایش تیتر یا متن فارسی یک خبر در صف بررسی (مثلاً کوتاه‌کردن تیتر)؛ متن جدید را خودت بنویس. قبل از ذخیره تأیید لازم است.",
            _story_id_params(extra={
                "title_fa": {"type": "string", "minLength": 1, "maxLength": 300},
                "body_fa": {"type": "string", "maxLength": 4000},
            }),
            mutates=True,
        ),
        _cap(
            "move_story_to_review",
            "stories",
            "فرستادن یک خبر مشخص به صف بررسی/ویرایش.",
            _story_id_params(),
            mutates=True,
        ),
        _cap(
            "list_recent_published",
            "stories",
            "نمایش خبرهای منتشرشده اخیر، در صورت نیاز فیلترشده بر اساس منبع.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                    "source": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        _cap("diagnose_newsroom", "diagnostics", "بررسی وضعیت اتاق خبر، صف‌ها، خطاهای منابع و انتشار.", _EMPTY_OBJECT),
        _cap(
            "list_sources",
            "sources",
            "فهرست و جست‌وجوی منابع خبری پنل؛ برای پیدا کردن منبع دقیق قبل از تغییر استفاده کن.",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "active": {"type": "boolean"},
                    "query": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        _cap(
            "add_source",
            "sources",
            "اضافه کردن منبع خبری جدید.",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["telegram", "x", "truth", "website"]},
                    "identifier": {"type": "string"},
                    "display_name": {"type": "string"},
                    "feed_url": {"type": "string"},
                },
                "required": ["kind", "identifier"],
                "additionalProperties": False,
            },
            mutates=True,
        ),
        _cap(
            "rename_source",
            "sources",
            "تغییر نام نمایشی یک منبع، مثلاً فارسی‌کردن نام ClashReports.",
            _source_target_params(
                {"display_name": {"type": "string", "minLength": 1, "maxLength": 120}},
                required=["display_name"],
            ),
            mutates=True,
        ),
        _cap("enable_source", "sources", "فعال کردن یک منبع مشخص.", _source_target_params(), mutates=True),
        _cap("disable_source", "sources", "غیرفعال کردن یک منبع مشخص.", _source_target_params(), mutates=True),
        _cap("delete_source", "sources", "حذف یا مخفی کردن یک منبع مشخص از رصد.", _source_target_params(), mutates=True),
        _cap(
            "set_source_review_only",
            "sources",
            "تنظیم اینکه خبرهای یک منبع فقط وارد صف بررسی شوند و خودکار منتشر نشوند.",
            _source_target_params({"enabled": {"type": "boolean"}}, required=["enabled"]),
            mutates=True,
        ),
        _cap("inspect_panel_state", "diagnostics", "خلاصه وضعیت پنل و سرویس‌های اتاق خبر.", _EMPTY_OBJECT),
        _cap(
            "set_newsroom_alarm",
            "settings",
            "فعال یا غیرفعال کردن صدای آلارم خبر جدید در تنظیمات پنل.",
            {
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "required": ["enabled"],
                "additionalProperties": False,
            },
            mutates=True,
        ),
        _cap(
            "builder_prepare",
            "builder",
            "آماده‌کردن تغییر کد یا UI روی branch جدا با تست و Draft PR؛ production مستقیم ویرایش نمی‌شود.",
            {
                "type": "object",
                "properties": {"request": {"type": "string", "minLength": 1}},
                "required": ["request"],
                "additionalProperties": False,
            },
            mutates=True,
        ),
        _cap(
            "builder_ci_status",
            "builder",
            "بررسی وضعیت CI آخرین تغییر Builder یا یک PR مشخص؛ هیچ تغییری ایجاد نمی‌کند.",
            {
                "type": "object",
                "properties": {"pr_number": {"type": "integer", "minimum": 1}},
                "additionalProperties": False,
            },
        ),
        _cap(
            "builder_prepare_merge",
            "builder",
            "اگر CI سبز باشد merge یک PR Builder را برای تأیید و اجرا آماده می‌کند.",
            {
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer", "minimum": 1},
                    "expected_head_sha": {"type": "string"},
                },
                "additionalProperties": False,
            },
            mutates=True,
        ),
    ]
    return CapabilityRegistry(capabilities)
