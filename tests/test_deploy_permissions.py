from pathlib import Path


def test_updater_repairs_checkout_ownership_before_fetch():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    repair = 'chown -R bikhabar:bikhabar "${APP_DIR}"'
    fetch = 'runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin'
    assert repair in script
    assert fetch in script
    assert script.index(repair) < script.index(fetch)
