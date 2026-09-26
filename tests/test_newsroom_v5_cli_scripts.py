from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _seed_repo(root: Path) -> None:
    (root / "data").mkdir()
    (root / "data" / "panel_live_feed.json").write_text(json.dumps([
        {
            "id": "s1",
            "news_key": "s1",
            "source": "reuters",
            "source_url": "https://example.com/s1",
            "title": "Iran story",
            "title_fa": "خبر ایران",
            "published": "2026-09-20T10:00:00+00:00",
        }
    ]), encoding="utf-8")
    (root / "state.json").write_text("{}", encoding="utf-8")


def test_migration_cli_runs_as_documented_from_repo_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_repo(repo)
    db = tmp_path / "v5.db"

    dry = _run("migrate_newsroom_v5.py", "--db", str(db), "--from-local-repo", str(repo), "--dry-run", cwd=ROOT)
    assert dry.returncode == 0, dry.stderr
    report = json.loads(dry.stdout)
    assert report["applied"] is False
    assert report["stories"] == 1
    assert not db.exists(), "--dry-run must not create or write the SQLite database"

    applied = _run("migrate_newsroom_v5.py", "--db", str(db), "--from-local-repo", str(repo), "--apply", cwd=ROOT)
    assert applied.returncode == 0, applied.stderr
    again = _run("migrate_newsroom_v5.py", "--db", str(db), "--from-local-repo", str(repo), "--apply", cwd=ROOT)
    assert again.returncode == 0, again.stderr

    verify = _run("verify_newsroom_v5_migration.py", "--db", str(db), "--from-local-repo", str(repo), cwd=ROOT)
    assert verify.returncode == 0, verify.stderr + verify.stdout
    assert json.loads(verify.stdout)["ok"] is True


def test_migration_cli_does_not_depend_on_current_directory(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_repo(repo)
    result = _run(
        "migrate_newsroom_v5.py", "--db", str(tmp_path / "v5.db"), "--from-local-repo", str(repo), "--dry-run",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
