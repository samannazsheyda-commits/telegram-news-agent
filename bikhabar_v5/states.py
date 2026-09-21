from __future__ import annotations


class InvalidStateTransition(ValueError):
    pass


CANONICAL_STATES = (
    "NEW",
    "GOOGLE_TRANSLATING",
    "GOOGLE_TRANSLATED",
    "READY_FOR_REVIEW",
    "LUNA_TRANSLATED",
    "APPROVED",
    "PUBLISHING",
    "PUBLISHED",
    "REJECTED_PERMANENT",
    "PUBLISH_FAILED",
)

TERMINAL_STATES = frozenset({"PUBLISHED", "REJECTED_PERMANENT"})

_ALLOWED: dict[str, frozenset[str]] = {
    "NEW": frozenset({"GOOGLE_TRANSLATING", "REJECTED_PERMANENT"}),
    "GOOGLE_TRANSLATING": frozenset({"GOOGLE_TRANSLATED", "REJECTED_PERMANENT"}),
    "GOOGLE_TRANSLATED": frozenset({"READY_FOR_REVIEW", "REJECTED_PERMANENT"}),
    "READY_FOR_REVIEW": frozenset({"LUNA_TRANSLATED", "APPROVED", "REJECTED_PERMANENT"}),
    "LUNA_TRANSLATED": frozenset({"READY_FOR_REVIEW", "APPROVED", "REJECTED_PERMANENT"}),
    "APPROVED": frozenset({"PUBLISHING", "REJECTED_PERMANENT"}),
    "PUBLISHING": frozenset({"PUBLISHED", "PUBLISH_FAILED"}),
    "PUBLISH_FAILED": frozenset({"PUBLISHING", "REJECTED_PERMANENT"}),
    "PUBLISHED": frozenset(),
    "REJECTED_PERMANENT": frozenset(),
}


def _validate_state(value: str) -> str:
    state = str(value or "").strip().upper()
    if state not in _ALLOWED:
        raise InvalidStateTransition(f"unknown Vision 5 story state: {value!r}")
    return state


def transition_allowed(current: str, target: str) -> bool:
    source = _validate_state(current)
    destination = _validate_state(target)
    return destination in _ALLOWED[source]


def require_transition(current: str, target: str) -> tuple[str, str]:
    source = _validate_state(current)
    destination = _validate_state(target)
    if destination not in _ALLOWED[source]:
        raise InvalidStateTransition(f"invalid Vision 5 transition: {source} -> {destination}")
    return source, destination
