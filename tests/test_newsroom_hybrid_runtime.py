from datetime import datetime, timezone

import src.newsroom_hybrid_runtime as hybrid


def test_ancillary_cycle_disables_legacy_news_and_truth(monkeypatch):
    seen = {}
    original_news = lambda: ["legacy-news"]
    original_truth = lambda: ["legacy-truth"]
    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_news_items", original_news)
    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_truth_posts", original_truth)
    monkeypatch.setattr(hybrid.v13, "install_production_policies", lambda: None)
    monkeypatch.setattr(hybrid.v13, "expire_previous_day_queue", lambda now: 0)
    monkeypatch.setattr(hybrid.v13, "_publish_phone_once_per_day", lambda now: seen.setdefault("phone", True))

    def ancillary(now):
        seen["news"] = hybrid.v13.base.agent.fetch_news_items()
        seen["truth"] = hybrid.v13.base.agent.fetch_truth_posts()
        seen["now"] = now
        return 0

    monkeypatch.setattr(hybrid.v13.v12.v11.v10.v9.v8, "run", ancillary)
    now = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
    assert hybrid.run_ancillary_cycle(now) == 0
    assert seen["news"] == []
    assert seen["truth"] == []
    assert seen["phone"] is True
    assert hybrid.v13.base.agent.fetch_news_items is original_news
    assert hybrid.v13.base.agent.fetch_truth_posts is original_truth


def test_hybrid_cycle_runs_ancillary_then_v2(monkeypatch):
    order = []
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: order.append("ancillary") or 0)
    monkeypatch.setattr(hybrid, "run_v2_once", lambda **kwargs: order.append("v2") or {"published": 2, "telegram_writes": 2})
    result = hybrid.run_cycle(shadow=False, now=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    assert order == ["ancillary", "v2"]
    assert result["published"] == 2


def test_hybrid_stops_if_ancillary_cycle_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 7)
    monkeypatch.setattr(hybrid, "run_v2_once", lambda **kwargs: calls.append("v2") or {})
    result = hybrid.run_cycle(shadow=False, now=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    assert result["rc"] == 7
    assert calls == []
