from __future__ import annotations

import json
from typing import Any, Callable


def canonical_key(tool_name: str, arguments: Any) -> tuple[str, str]:
    normalized = arguments if isinstance(arguments, dict) else {}
    return (
        str(tool_name or ""),
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


class LunaTurnCache:
    """Completed tool results for one user turn, keyed by canonical (tool, args).

    Mutations are proposal-gated by the runtime, so a cached mutation result is
    the same pending proposal, never a second execution.
    """

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], dict] = {}
        self.executions = 0
        self.reuses = 0

    def run(self, tool_name: str, arguments: Any, invoke: Callable[[], dict]) -> tuple[dict, bool]:
        key = canonical_key(tool_name, arguments)
        if key in self._results:
            self.reuses += 1
            return self._results[key], True
        result = invoke()
        self.executions += 1
        self._results[key] = result
        return result, False
