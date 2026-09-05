from __future__ import annotations

from dataclasses import dataclass

import requests

USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass(frozen=True)
class OilSnapshot:
    brent_usd: float | None = None
    wti_usd: float | None = None


def _chart_price(payload: dict) -> float | None:
    try:
        result = payload["chart"]["result"][0]
        meta = result.get("meta") or {}
        value = meta.get("regularMarketPrice")
        if value is not None:
            return float(value)
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
        valid = [float(x) for x in closes if x is not None]
        return valid[-1] if valid else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _fetch_symbol(symbol: str, session=requests) -> float | None:
    response = session.get(
        YAHOO_CHART.format(symbol=symbol),
        params={"interval": "5m", "range": "1d"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    return _chart_price(response.json())


def fetch_oil_snapshot(session=requests) -> OilSnapshot:
    """Fetch current global benchmark crude prices in USD/barrel, best effort."""
    brent = None
    wti = None
    try:
        brent = _fetch_symbol("BZ=F", session=session)
    except Exception:
        pass
    try:
        wti = _fetch_symbol("CL=F", session=session)
    except Exception:
        pass
    return OilSnapshot(brent_usd=brent, wti_usd=wti)


def format_oil_lines(snapshot: OilSnapshot) -> list[str]:
    lines: list[str] = []
    if snapshot.brent_usd is not None:
        lines.append(f"🛢 نفت برنت: ${snapshot.brent_usd:,.2f} / بشکه")
    if snapshot.wti_usd is not None:
        lines.append(f"🛢 نفت WTI: ${snapshot.wti_usd:,.2f} / بشکه")
    return lines
