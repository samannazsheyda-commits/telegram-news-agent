from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class CollectorService:
    def __init__(self, core: Any) -> None:
        self.core = core

    def ingest(self, candidates: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        received = 0
        inserted = 0
        for candidate in candidates:
            received += 1
            _story, was_inserted = self.core.ingest_story(candidate)
            inserted += int(bool(was_inserted))
        return {"received": received, "inserted": inserted, "duplicates": received - inserted}
