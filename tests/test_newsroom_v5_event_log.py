from __future__ import annotations

import sqlite3
import threading
import time

from panel.app_v5 import create_app
from src.newsroom_v5_db import SCHEMA_VERSION, connect, initialize, transaction
from src.newsroom_v5_events import SqliteEventLog
from src.newsroom_v5_store import NewsroomV5Store


def test_event_published_by_one_process_is_visible_to_another(tmp_path):
    db = tmp_path / "newsroom.db"
    worker_side = SqliteEventLog(NewsroomV5Store(db))
    panel_side = SqliteEventLog(NewsroomV5Store(db))

    first = worker_side.publish("story_added", {"story_id": "a"})
    second = worker_side.publish("story_published", {"story_id": "b"})

    assert first.id < second.id
    assert [(e.type, e.payload["story_id"]) for e in panel_side.events_after(0)] == [
        ("story_added", "a"),
        ("story_published", "b"),
    ]
    assert [e.id for e in panel_side.events_after(first.id)] == [second.id]


def test_stream_delivers_cross_process_event_quickly(tmp_path):
    db = tmp_path / "newsroom.db"
    worker_side = SqliteEventLog(NewsroomV5Store(db))
    panel_side = SqliteEventLog(NewsroomV5Store(db), poll_seconds=0.05)
    stream = panel_side.stream(0, heartbeat_seconds=5)

    def later():
        time.sleep(0.1)
        worker_side.publish("story_added", {"story_id": "late"})

    threading.Thread(target=later).start()
    started = time.monotonic()
    chunk = next(stream)
    assert "event: story_added" in chunk
    assert '"story_id":"late"' in chunk
    assert time.monotonic() - started < 1.0


def test_retention_prunes_old_events_and_reports_replay_gap(tmp_path):
    log = SqliteEventLog(NewsroomV5Store(tmp_path / "n.db"), max_events=3)
    ids = [log.publish("story_added", {"story_id": str(i)}).id for i in range(6)]
    assert [e.id for e in log.events_after(0)] == ids[-3:]
    assert log.replay_gap(0) is True
    assert log.replay_gap(ids[-4]) is False
    chunk = next(log.stream(0))
    assert "event: refetch_required" in chunk


def test_app_uses_durable_event_log_for_file_backed_store(tmp_path):
    db = tmp_path / "newsroom.db"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
        "NEWSROOM_V5_STORE": NewsroomV5Store(db),
    })
    events = app.extensions["newsroom_v5_events"]
    assert isinstance(events, SqliteEventLog)
    SqliteEventLog(NewsroomV5Store(db)).publish("counts_changed", {"review": 3})
    assert [e.type for e in events.events_after(0)] == ["counts_changed"]


def test_schema_upgrades_v1_database_in_place(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_meta(version) VALUES (1)")
    conn.commit()
    conn.close()

    upgraded = connect(db)
    initialize(upgraded)
    assert upgraded.execute("SELECT version FROM schema_meta").fetchone()[0] == SCHEMA_VERSION
    assert upgraded.execute("SELECT name FROM sqlite_master WHERE name='events'").fetchone() is not None


def test_shared_connection_serializes_threads_around_transactions(tmp_path):
    store = NewsroomV5Store(tmp_path / "n.db")
    inside = threading.Event()
    other_done = threading.Event()

    def rolled_back_transaction():
        try:
            with transaction(store.conn):
                store.append_audit("doomed", entity_type="t", entity_id="1")
                inside.set()
                other_done.wait(0.3)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass

    def independent_write():
        inside.wait(2)
        store.append_audit("independent", entity_type="t", entity_id="2")
        other_done.set()

    a = threading.Thread(target=rolled_back_transaction)
    b = threading.Thread(target=independent_write)
    a.start(); b.start(); a.join(5); b.join(5)

    actions = {row[0] for row in store.conn.execute("SELECT action FROM audit_log")}
    assert "independent" in actions, "another thread's write must not be swallowed by a rollback"
    assert "doomed" not in actions
