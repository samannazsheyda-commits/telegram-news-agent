from datetime import datetime, timezone

import src.newsroom_hybrid_runtime as hybrid


def test_ancillary_cycle_disables_legacy_news_and_truth(monkeypatch):
    seen = {}
    legacy = hybrid.v13.v12.v11.v10.v9.v8
    original_news = lambda: ["legacy-news"]
    original_truth = lambda: ["legacy-truth"]
    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_news_items", original_news)
    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_truth_posts", original_truth)
    monkeypatch.setattr(hybrid.v13, "install_production_policies", lambda: None)
    monkeypatch.setattr(hybrid.v13, "expire_previous_day_queue", lambda now: 0)
    monkeypatch.setattr(hybrid.v13, "_publish_phone_once_per_day", lambda now: seen.setdefault("phone", True))
    monkeypatch.setattr(legacy, "install_strict_dedup_policy", lambda: None)

    def ancillary(now):
        seen["news"] = hybrid.v13.base.agent.fetch_news_items()
        seen["truth"] = hybrid.v13.base.agent.fetch_truth_posts()
        seen["now"] = now
        return 0

    monkeypatch.setattr(legacy, "run", ancillary)
    now = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
    assert hybrid.run_ancillary_cycle(now) == 0
    assert seen["news"] == []
    assert seen["truth"] == []
    assert seen["phone"] is True
    assert hybrid.v13.base.agent.fetch_news_items is original_news
    assert hybrid.v13.base.agent.fetch_truth_posts is original_truth


def test_ancillary_cycle_installs_legacy_hooks_before_disabling_news(monkeypatch):
    seen = {}
    legacy = hybrid.v13.v12.v11.v10.v9.v8
    pre_install_news = lambda: ["pre-install-news"]
    installed_news = lambda: ["legacy-installed-news"]
    installed = {"done": False}

    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_news_items", pre_install_news)
    monkeypatch.setattr(hybrid.v13.base.agent, "fetch_truth_posts", lambda: ["legacy-truth"])
    monkeypatch.setattr(hybrid.v13, "install_production_policies", lambda: None)
    monkeypatch.setattr(hybrid.v13, "expire_previous_day_queue", lambda now: 0)
    monkeypatch.setattr(hybrid.v13, "_publish_phone_once_per_day", lambda now: None)

    def install_legacy_hooks():
        if installed["done"]:
            return
        hybrid.v13.base.agent.fetch_news_items = installed_news
        installed["done"] = True

    def legacy_run(now):
        install_legacy_hooks()
        seen["news_during_ancillary"] = hybrid.v13.base.agent.fetch_news_items()
        return 0

    monkeypatch.setattr(legacy, "install_strict_dedup_policy", install_legacy_hooks)
    monkeypatch.setattr(legacy, "run", legacy_run)

    now = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)
    assert hybrid.run_ancillary_cycle(now) == 0
    assert seen["news_during_ancillary"] == []
    assert hybrid.v13.base.agent.fetch_news_items is installed_news


def test_hybrid_cycle_runs_ancillary_then_v2(monkeypatch):
    order = []
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: order.append("ancillary") or 0)
    monkeypatch.setattr(hybrid, "run_v2_once", lambda **kwargs: order.append("v2") or {"published": 2, "telegram_writes": 2})
    result = hybrid.run_cycle(shadow=False, now=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    assert order == ["ancillary", "v2"]
    assert result["published"] == 2


def test_hybrid_uses_configured_v2_data_dir(monkeypatch):
    seen = {}
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 0)

    def v2(**kwargs):
        seen.update(kwargs)
        return {"published": 0, "telegram_writes": 0}

    monkeypatch.setattr(hybrid, "run_v2_once", v2)
    monkeypatch.setenv("DATA_DIR", "/var/lib/bikhabar/data")
    hybrid.run_cycle(shadow=True, now=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    assert seen["data_dir"] == "/var/lib/bikhabar/data"


def test_hybrid_stops_if_ancillary_cycle_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 7)
    monkeypatch.setattr(hybrid, "run_v2_once", lambda **kwargs: calls.append("v2") or {})
    result = hybrid.run_cycle(shadow=False, now=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    assert result["rc"] == 7
    assert calls == []


def test_zero_session_runs_until_real_failure(monkeypatch):
    calls = []

    def cycle(*, shadow):
        calls.append(shadow)
        if len(calls) == 1:
            return {"rc": 0, "published": 0}
        return {"rc": 9, "published": 0}

    monkeypatch.setattr(hybrid, "run_cycle", cycle)
    monkeypatch.setattr(hybrid.time, "sleep", lambda _: None)
    assert hybrid.monitor(shadow=False, poll_seconds=1, session_seconds=0) == 9
    assert calls == [False, False]
