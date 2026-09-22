from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Mapping
from typing import Any


class PermissionDenied(RuntimeError):
    pass


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decoded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class PermissionGate:
    def __init__(
        self,
        *,
        secret: str,
        ttl_seconds: int = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.secret = str(secret or "").encode("utf-8")
        if len(self.secret) < 8:
            raise ValueError("permission secret must be at least 8 characters")
        self.ttl_seconds = max(30, min(int(ttl_seconds), 1800))
        self.clock = clock

    @staticmethod
    def _canonical(payload: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")))

    def issue(self, *, actor: str, action: str, payload: Mapping[str, Any]) -> str:
        now = int(self.clock())
        claims = {
            "actor": str(actor),
            "action": str(action),
            "payload": self._canonical(payload),
            "iat": now,
            "exp": now + self.ttl_seconds,
            "nonce": secrets.token_urlsafe(12),
        }
        body = _encoded(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _encoded(hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def verify(
        self,
        token: str,
        *,
        actor: str,
        action: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            body, supplied_signature = str(token).split(".", 1)
            expected_signature = _encoded(
                hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise PermissionDenied("invalid confirmation signature")
            claims = json.loads(_decoded(body).decode("utf-8"))
        except PermissionDenied:
            raise
        except Exception as exc:
            raise PermissionDenied("malformed confirmation token") from exc
        if int(claims.get("exp") or 0) < int(self.clock()):
            raise PermissionDenied("confirmation token expired")
        expected = (str(actor), str(action), self._canonical(payload))
        actual = (claims.get("actor"), claims.get("action"), claims.get("payload"))
        if not hmac.compare_digest(
            json.dumps(actual, sort_keys=True), json.dumps(expected, sort_keys=True)
        ):
            raise PermissionDenied("confirmation does not match the requested action")
        return claims
