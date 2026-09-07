from pathlib import Path

PANEL = Path("docs/panel.html")
JS = Path("docs/panel.js")
CSS = Path("docs/panel.css")
NEWSROOM_CSS = Path("docs/newsroom-v1.css")


def test_panel_has_newsroom_controls_and_no_blocking_dialogs():
    html = PANEL.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8") if JS.exists() else html
    combined = html + "\n" + js

    assert 'dir="rtl"' in html
    assert 'name="viewport"' in html
    assert 'data-view="pending"' in html
    assert 'data-view="processing"' in html
    assert 'data-view="published"' in html
    assert 'data-view="rejected"' in html
    assert 'data-view="system"' in html
    assert 'id="queueSearch"' in html
    assert 'id="sourceFilter"' in html
    assert 'id="sortOrder"' in html
    assert 'id="reasonFilter"' in html
    assert 'alert(' not in combined
    assert 'confirm(' not in combined
    assert 'prompt(' not in combined


def test_panel_uses_bikhabar_agent_connection_wording():
    html = PANEL.read_text(encoding="utf-8")
    assert "اتصال به ایجنت بی‌خبر" in html


def test_panel_persists_token_and_resumes_pending_action_after_connect():
    js = JS.read_text(encoding="utf-8")
    assert "localStorage" in js
    assert "pendingAuthAction" in js
    assert "requireConnection" in js
    connect_block = js.split("async function connect", 1)[1].split("function disconnect", 1)[0]
    assert "pendingAuthAction=null" in connect_block
    assert "pending?.type==='refresh'" in connect_block
    assert "pending?.type==='reject'" in connect_block
    assert "pending?.type==='publish'" in connect_block
    assert "removeItem('bikhabar_contents_token')" not in connect_block


def test_panel_keeps_local_drafts():
    js = JS.read_text(encoding="utf-8")
    assert "saveDraft" in js
    assert "restoreDraft" in js
    assert "clearDraft" in js


def test_panel_has_optimistic_publish_reject_and_result_polling_behavior():
    js = JS.read_text(encoding="utf-8")
    assert "hiddenItems.add(item.id)" in js
    assert "hiddenItems.delete(item.id)" in js
    assert "pollCommandResult" in js
    assert "executeReject" in js
    assert "executePublish" in js


def test_panel_refresh_runs_real_scan_and_only_shows_today_queue():
    js = JS.read_text(encoding="utf-8")
    assert "forceRefresh" in js
    assert "action:'refresh'" in js
    assert "todayQueueItem" in js
    assert "day(stamp)===day(new Date().toISOString())" in js


def test_panel_persian_headline_is_multiline_and_autogrows():
    js = JS.read_text(encoding="utf-8")
    assert '<textarea class="title-input"' in js
    assert "autoGrow" in js
    assert "growAllTitles" in js


def test_panel_assets_and_accessibility_contract():
    html = PANEL.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8") + "\n" + NEWSROOM_CSS.read_text(encoding="utf-8")
    assert 'href="panel.css?v=' in html
    assert 'href="newsroom-v1.css?v=' in html
    assert 'src="panel.js?v=' in html
    assert 'src="newsroom-v1.js?v=' in html
    assert "Doran NoEn ExtraBold" in css
    assert ":focus-visible" in css
    assert "position:sticky" in css or "position: sticky" in css
