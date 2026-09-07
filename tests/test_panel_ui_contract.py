from pathlib import Path

PANEL = Path("docs/panel.html")
JS = Path("docs/panel.js")
CSS = Path("docs/panel.css")


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


def test_panel_persists_token_and_can_resume_pending_action_after_connect():
    js = JS.read_text(encoding="utf-8")
    assert "localStorage" in js
    assert "pendingAuthAction" in js
    assert "resumePendingAuthAction" in js
    assert "queueAuthAction" in js
    assert "removeItem('bikhabar_contents_token')" not in js.split("async function connect", 1)[1].split("function disconnect", 1)[0]


def test_panel_keeps_local_drafts():
    js = JS.read_text(encoding="utf-8")
    assert "saveDraft" in js
    assert "restoreDraft" in js
    assert "clearDraft" in js


def test_panel_has_optimistic_and_result_polling_hooks():
    js = JS.read_text(encoding="utf-8")
    for hook in (
        "optimisticReject",
        "optimisticPublish",
        "restoreRejectedCard",
        "restorePublishCard",
        "pollCommandResult",
        "reconcileCommandResult",
    ):
        assert hook in js


def test_panel_assets_and_accessibility_contract():
    html = PANEL.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'href="panel.css"' in html
    assert 'src="panel.js"' in html
    assert "Vazirmatn" in css
    assert ":focus-visible" in css
    assert "position:sticky" in css or "position: sticky" in css
