from __future__ import annotations

import json


class MigrationStore:
    def __init__(self):
        self.sources = []
        self.rules = []
        self.history = []

    def upsert_source(self, source):
        self.sources.append(source)
        return source

    def upsert_newsroom_rule(self, key, value, *, actor):
        self.rules.append((key, value, actor))
        return {"rule_key": key}

    def import_legacy_story(self, story, *, actor):
        self.history.append((story, actor))
        return story


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_migration_imports_only_healthy_sources_rules_and_required_history(tmp_path):
    from bikhabar_v5.migration import LegacyMigrator

    data = tmp_path / "data"
    data.mkdir()
    _write(
        data / "custom_sources.json",
        [
            {"id": "ok", "kind": "telegram", "name": "سالم", "channel": "Healthy", "active": True, "status": "active"},
            {"id": "off", "kind": "x", "name": "خاموش", "handle": "broken", "active": False, "status": "error", "last_error": "down"},
        ],
    )
    _write(
        data / "newsroom_settings.json",
        {"freshness_hours": 4, "priority_terms": ["فوری"], "auto_publish": False},
    )
    _write(
        data / "editorial_history.json",
        [
            {"id": "published", "source": "Reuters", "source_url": "https://e/p", "original_title": "Published", "final_persian_title": "منتشر شده", "final_persian_body": "متن", "status": "published_manual", "telegram_message_id": 11},
            {"id": "rejected", "source": "AP", "source_url": "https://e/r", "original_title": "Rejected", "status": "rejected_manual", "rejection_reason": "ضعیف"},
            {"id": "queued", "source": "AP", "source_url": "https://e/q", "original_title": "Queued", "status": "pending"},
        ],
    )
    store = MigrationStore()
    report = LegacyMigrator(legacy_root=tmp_path, store=store).run()

    assert [source["identity"] for source in store.sources] == ["Healthy"]
    assert store.rules[0][0] == "legacy_newsroom_settings"
    assert {row[0]["status"] for row in store.history} == {"PUBLISHED", "REJECTED_PERMANENT"}
    assert report["sources"] == {"discovered": 2, "eligible": 1, "imported": 1}
    assert report["history"]["eligible"] == 2
    assert report["parity_ok"] is True
    assert len(report["input_sha256"]) == 64


def test_migration_dry_run_writes_nothing_but_reports_exact_counts(tmp_path):
    from bikhabar_v5.migration import LegacyMigrator

    data = tmp_path / "data"
    data.mkdir()
    _write(data / "custom_sources.json", [])
    _write(data / "newsroom_settings.json", {})
    _write(data / "editorial_history.json", [])
    store = MigrationStore()

    report = LegacyMigrator(legacy_root=tmp_path, store=store).run(dry_run=True)

    assert report["dry_run"] is True
    assert store.sources == [] and store.rules == [] and store.history == []
    assert report["parity_ok"] is True
