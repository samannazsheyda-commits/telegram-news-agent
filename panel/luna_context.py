from __future__ import annotations


def _text(value) -> str:
    return str(value or "").strip()


def _norm(value) -> str:
    return " ".join(_text(value).casefold().lstrip("@").split())


class LunaContextResolver:
    """Resolve natural references to concrete newsroom entities without guessing."""

    def __init__(self, toolbox) -> None:
        self.toolbox = toolbox

    @staticmethod
    def _source_values(row: dict) -> set[str]:
        values = {
            _norm(row.get("id")),
            _norm(row.get("name")),
            _norm(row.get("identity")),
            _norm(row.get("handle")),
            _norm(row.get("channel")),
            _norm(row.get("website_url")),
            _norm(row.get("feed_url")),
        }
        return {value for value in values if value}

    def _source_ok(self, row: dict) -> dict:
        return {
            "ok": True,
            "source": self.toolbox._source_public(row),
            "row": dict(row),
        }

    def _source_by_id(self, source_id: str) -> dict:
        wanted = _text(source_id)
        matches = [row for row in self.toolbox._sources() if _text(row.get("id")) == wanted]
        if not matches:
            return {"ok": False, "error": "source_not_found", "message": "منبع پیدا نشد."}
        if len(matches) > 1:
            return {
                "ok": False,
                "error": "ambiguous_source",
                "message": "چند منبع با این شناسه پیدا شد؛ منبع دقیق را مشخص کن.",
                "matches": [self.toolbox._source_public(row) for row in matches[:8]],
            }
        return self._source_ok(matches[0])

    def _source_by_query(self, query: str) -> dict:
        wanted = _norm(query)
        if not wanted:
            return {"ok": False, "error": "source_target_required", "message": "منبع دقیق مشخص نیست."}
        rows = self.toolbox._sources()
        exact = [row for row in rows if wanted in self._source_values(row)]
        if len(exact) == 1:
            return self._source_ok(exact[0])
        if len(exact) > 1:
            return {
                "ok": False,
                "error": "ambiguous_source",
                "message": "چند منبع با این نام پیدا شد؛ منبع دقیق را مشخص کن.",
                "matches": [self.toolbox._source_public(row) for row in exact[:8]],
            }

        candidates = [
            row
            for row in rows
            if any(wanted in value for value in self._source_values(row))
        ]
        if len(candidates) == 1:
            return self._source_ok(candidates[0])
        if len(candidates) > 1:
            return {
                "ok": False,
                "error": "ambiguous_source",
                "message": "چند منبع شبیه این نام پیدا شد؛ یکی را دقیق مشخص کن.",
                "matches": [self.toolbox._source_public(row) for row in candidates[:8]],
            }
        return {"ok": False, "error": "source_not_found", "message": "منبع پیدا نشد."}

    def resolve_source(self, args: dict | None, context: dict | None) -> dict:
        values = dict(args or {})
        context = dict(context or {})
        source_id = _text(values.get("source_id"))
        if source_id:
            return self._source_by_id(source_id)
        query = _text(values.get("query"))
        if query:
            return self._source_by_query(query)
        previous = _text(context.get("last_source_id"))
        if previous:
            return self._source_by_id(previous)
        return {"ok": False, "error": "source_target_required", "message": "منبع دقیق مشخص نیست."}

    def _story_by_id(self, story_id: str) -> dict:
        row = self.toolbox._find_story(_text(story_id))
        if row is None:
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        return {
            "ok": True,
            "story": self.toolbox._story_public(row),
            "row": dict(row),
        }

    def resolve_story(self, args: dict | None, context: dict | None) -> dict:
        values = dict(args or {})
        context = dict(context or {})
        story_id = _text(values.get("story_id"))
        if story_id:
            return self._story_by_id(story_id)

        previous = _text(context.get("last_story_id"))
        if previous:
            return self._story_by_id(previous)

        query = _text(values.get("query"))
        if query:
            result = self.toolbox.execute("search_stories", {"query": query, "limit": 10}, confirmed=True)
            stories = list(result.get("stories") or []) if result.get("ok") else []
            if len(stories) == 1:
                return self._story_by_id(str(stories[0].get("id") or ""))
            if len(stories) > 1:
                return {
                    "ok": False,
                    "error": "ambiguous_story",
                    "message": "چند خبر مشابه پیدا شد؛ خبر دقیق را مشخص کن.",
                    "matches": stories[:8],
                }
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}

        return {"ok": False, "error": "story_target_required", "message": "خبر دقیق مشخص نیست."}
