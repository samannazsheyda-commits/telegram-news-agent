import pytest


@pytest.fixture(autouse=True)
def isolate_external_daily_services(monkeypatch, tmp_path):
    import src.main as main
    import src.runtime as runtime
    import src.runtime_v2 as v2
    import src.runtime_v5 as v5
    import src.runtime_v6 as v6
    import src.runtime_v7 as v7
    from src.editorial_store import LocalEditorialStore

    # Snapshot the runtime monkeypatch stack so one test cannot silently alter the
    # formatter/selector/policy used by a later test. This was a real CI failure.
    originals = {
        "v2_formatter": v2._format_news_with_flags,
        "v2_translate": v2.translate_news_to_fa,
        "v2_strict": v2._strict_rejection_reason,
        "agent_reason": v2.base.agent._news_rejection_reason,
        "agent_selector": v2.base.agent._select_top_stories,
        "fresh_fetch": v2.fetch_builtin_x_news_items,
        "preserved": set(v2._PRESERVED_SPECIAL_SOURCES),
        "custom_fetch": v2._original_custom_fetch,
        "v5_flag": v5._fresh_x_installed,
        "v6_flag": v6._output_policy_installed,
        "v7_flag": v7._easy_news_flow_installed,
    }

    # Unit tests must never read or mutate production runtime state tracked in the repo.
    monkeypatch.setattr(main, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(
        runtime,
        "_store",
        LocalEditorialStore(tmp_path / "editorial_queue.json", tmp_path / "editorial_history.json"),
    )
    monkeypatch.setattr(runtime, "_sent_news_items", [])

    # Existing unit tests should never make live HTTP calls. Feature-specific tests
    # can override these monkeypatches explicitly.
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "fetch_car_prices", lambda: (_ for _ in ()).throw(RuntimeError("car service disabled in unit tests")))
    monkeypatch.setattr(main, "fetch_weather_report", lambda: (_ for _ in ()).throw(RuntimeError("weather service disabled in unit tests")))

    yield

    # Some runtime installers mutate module globals directly rather than through the
    # pytest monkeypatch fixture. Restore all of those globals after every test.
    v2._format_news_with_flags = originals["v2_formatter"]
    v2.translate_news_to_fa = originals["v2_translate"]
    v2._strict_rejection_reason = originals["v2_strict"]
    v2.base.agent._news_rejection_reason = originals["agent_reason"]
    v2.base.agent._select_top_stories = originals["agent_selector"]
    v2.fetch_builtin_x_news_items = originals["fresh_fetch"]
    v2._PRESERVED_SPECIAL_SOURCES = originals["preserved"]
    v2._original_custom_fetch = originals["custom_fetch"]
    v5._fresh_x_installed = originals["v5_flag"]
    v6._output_policy_installed = originals["v6_flag"]
    v7._easy_news_flow_installed = originals["v7_flag"]
    v7._translation_cache.clear()
