from pathlib import Path


def test_update_vps_runs_checkout_git_reads_as_bikhabar_user():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert 'CURRENT_SHA="$(runuser -u bikhabar -- git -C "${APP_DIR}" rev-parse HEAD)"' in script
    assert 'TARGET_SHA="$(runuser -u bikhabar -- git -C "${APP_DIR}" rev-parse "origin/${BRANCH}")"' in script
    assert 'CURRENT_SHA="$(git -C "${APP_DIR}" rev-parse HEAD)"' not in script
    assert 'TARGET_SHA="$(git -C "${APP_DIR}" rev-parse "origin/${BRANCH}")"' not in script
