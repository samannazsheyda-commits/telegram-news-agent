from pathlib import Path


main_path = Path("src/main.py")
text = main_path.read_text(encoding="utf-8")
start = text.index("    try:\n        items = fetch_news_items()")
end = text.index("    if _car_due(state, now):", start)
replacement = '''    try:
        items = fetch_news_items()
        seen = list(state.get("news_seen") or [])
        seen_set = set(seen)
        new_items = [item for item in items if item.key not in seen_set]
        rejected: list[tuple[NewsItem, str]] = []
        candidates: list[NewsItem] = []
        retryable_rejections = {"invalid_publish_time", "missing_direct_source_link"}

        for item in new_items:
            reason = _news_rejection_reason(item, now)
            if reason is None:
                candidates.append(item)
            else:
                rejected.append((item, reason))

        for item, reason in rejected:
            _audit_news(state, item, reason, now)
            if reason not in retryable_rejections:
                seen.insert(0, item.key)
                seen_set.add(item.key)
            changed = True

        # Only previously accepted/currently eligible stories can suppress a new factual report.
        references = [
            item for item in items
            if item.key in seen_set and _news_rejection_reason(item, now) is None
        ]
        selected, duplicates = _select_top_stories(candidates, references)
        for item in duplicates:
            _audit_news(state, item, "duplicate_or_redundant", now)
            seen.insert(0, item.key)
            seen_set.add(item.key)
            changed = True

        if rejected or duplicates:
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)

        next_color = state.get("next_news_color", "red")
        for item in reversed(selected):
            try:
                title_fa = translate_to_fa(item.title)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=title_translation error={exc}", file=sys.stderr)
                _audit_news(state, item, "translation_failed_retry_later", now)
                changed = True
                continue
            if not title_fa:
                _audit_news(state, item, "translation_failed_retry_later", now)
                changed = True
                continue

            detail = ""
            try:
                detail = fetch_news_detail(item)
            except Exception as exc:
                # Detail is enrichment only; a headline must still be publishable without it.
                print(f"NEWS_DETAIL_FALLBACK key={item.key!r} error={exc}", file=sys.stderr)

            summary_fa = ""
            if detail:
                try:
                    summary_fa = translate_to_fa(detail[:1200]) or ""
                except Exception as exc:
                    print(f"NEWS_SUMMARY_FALLBACK key={item.key!r} error={exc}", file=sys.stderr)

            marker = _red_story_marker(item) if next_color == "red" else "⚪️"
            try:
                message = format_news(item, title_fa, summary_fa, marker_override=marker)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=format error={exc}", file=sys.stderr)
                _audit_news(state, item, "format_failed_retry_later", now)
                changed = True
                continue
            if not (message or "").strip():
                _audit_news(state, item, "format_failed_retry_later", now)
                changed = True
                continue

            try:
                send_telegram(message, token, chat_id)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=send error={exc}", file=sys.stderr)
                _audit_news(state, item, "send_failed_retry_later", now)
                changed = True
                continue

            next_color = "white" if next_color == "red" else "red"
            state["next_news_color"] = next_color
            seen.insert(0, item.key)
            seen_set.add(item.key)
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)
            changed = True

        if changed:
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)
    except Exception as exc:
        print(f"News error: {exc}", file=sys.stderr)

'''
main_path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


test_path = Path("tests/test_main.py")
test_text = test_path.read_text(encoding="utf-8")
test_start = test_text.index("def test_first_run_bootstraps_news_and_truth_but_sends_market")
test_end = test_text.index("\ndef test_truth_advances_state_but_sends_only_iran_related_posts", test_start)
new_test = '''def test_first_run_processes_current_news_and_bootstraps_truth(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "Iran talks", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: [NewsItem("a", "Axios", "Iran strike", "summary", "https://news/a", "Fri, 04 Sep 2026 10:00:00 GMT")])
    monkeypatch.setattr(main, "fetch_market_snapshot", lambda: MarketSnapshot(2_000_000, 200_000_000))
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))
    monkeypatch.setattr(main, "translate_to_fa", lambda text: f"FA:{text}")
    rc = main.run(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc))
    assert rc == 0
    assert len(sent) == 2
    assert any("دلار آزاد" in text for text in sent)
    assert any("Axios" in text or "اکسیوس" in text for text in sent)
    state = main.load_state(state_path)
    assert state["truth_last_id"] == "10"
    assert state["news_seen"] == ["a"]

'''
test_path.write_text(test_text[:test_start] + new_test + test_text[test_end + 1:], encoding="utf-8")
