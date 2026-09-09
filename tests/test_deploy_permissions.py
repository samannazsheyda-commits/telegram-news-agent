from pathlib import Path
import subprocess


def test_updater_repairs_checkout_ownership_before_fetch():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    repair = 'chown -R bikhabar:bikhabar "${APP_DIR}"'
    fetch = 'runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin'
    assert repair in script
    assert fetch in script
    assert script.index(repair) < script.index(fetch)


def test_systemd_deploy_scripts_are_tracked_executable():
    output = subprocess.check_output(
        ["git", "ls-files", "-s", "deploy/update-vps.sh", "deploy/install-vps.sh"],
        text=True,
    )
    modes = {
        line.split()[3]: line.split()[0]
        for line in output.splitlines()
        if len(line.split()) >= 4
    }
    assert modes["deploy/update-vps.sh"] == "100755"
    assert modes["deploy/install-vps.sh"] == "100755"
