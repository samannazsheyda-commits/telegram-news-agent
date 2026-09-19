from __future__ import annotations


def builder_tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "name": "builder_ci_status",
            "description": "وضعیت CI آخرین تغییر Builder یا یک PR مشخص را بررسی می‌کند. هیچ تغییری ایجاد نمی‌کند.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "builder_prepare_merge",
            "description": "اگر CI تغییر Builder کاملاً سبز باشد، merge آن به main را برای تأیید کاربر آماده می‌کند. بدون تأیید merge انجام نمی‌شود.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
        },
    ]
