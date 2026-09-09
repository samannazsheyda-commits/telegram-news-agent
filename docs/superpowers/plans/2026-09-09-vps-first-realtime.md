# Bikhabar VPS-First Realtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Bikhabar production runtime state fully onto the paid VPS and remove GitHub/file-checkout state from the breaking-news hot path while preserving 5-second polling and making source intake concurrent.

**Architecture:** Code remains versioned and deployed from `production`, but all mutable newsroom state moves to `/var/lib/bikhabar/runtime`. Panel and agent share that root. Independent source fetchers fan out concurrently each cycle so a slow source cannot hold the entire newsroom loop.

**Tech Stack:** Python 3.12, Flask/Gunicorn, systemd, Bash, pytest

**Spec:** `docs/superpowers/specs/2026-09-09-vps-first-realtime-design.md`

## Global Constraints

- Production code path: `/opt/bikhabar/app`.
- Mutable runtime root: `/var/lib/bikhabar/runtime`.
- Poll target: 5 seconds.
- Session duration: continuous (`SESSION_SECONDS=0`).
- GitHub is not in the runtime hot path.
- Existing authenticated/CSRF-protected panel behavior must remain intact.
- Existing live runtime data must never be overwritten by repository defaults.

---

### Task 1: Runtime-root configuration

**Files:**
- Modify: `src/runtime_v13.py`
- Modify: `src/newsroom_hybrid_runtime.py`
- Test: `tests/test_vps_first_runtime.py`

**Interfaces:**
- Consumes: environment values `NEWSROOM_SETTINGS_PATH`, `PANEL_COMMAND_DIR`.
- Produces: `newsroom_settings_path() -> Path`, command directory resolution from env.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
from src import newsroom_hybrid_runtime, runtime_v13


def test_newsroom_settings_path_can_live_outside_checkout(monkeypatch, tmp_path):
    target = tmp_path / "data" / "newsroom_settings.json"
    monkeypatch.setenv("NEWSROOM_SETTINGS_PATH", str(target))
    assert runtime_v13.newsroom_settings_path() == target


def test_panel_command_dir_can_live_outside_checkout(monkeypatch, tmp_path):
    target = tmp_path / "panel_commands"
    monkeypatch.setenv("PANEL_COMMAND_DIR", str(target))
    assert newsroom_hybrid_runtime.panel_command_dir() == target
```

- [ ] **Step 2: Run targeted tests and verify RED**

Run: `python -m pytest -q tests/test_vps_first_runtime.py`
Expected: FAIL because helper functions do not exist.

- [ ] **Step 3: Implement environment-aware paths**

```python
# runtime_v13.py
def newsroom_settings_path() -> Path:
    return Path(os.environ.get("NEWSROOM_SETTINGS_PATH", "data/newsroom_settings.json"))

# newsroom_hybrid_runtime.py
def panel_command_dir() -> Path:
    return Path(os.environ.get("PANEL_COMMAND_DIR", "panel_commands"))
```

Update `load_newsroom_settings()` and `_process_panel_commands()` to call those helpers.

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run: `python -m pytest -q tests/test_vps_first_runtime.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/runtime_v13.py src/newsroom_hybrid_runtime.py tests/test_vps_first_runtime.py
git commit -m "feat: isolate VPS runtime paths"
```

### Task 2: Concurrent source fanout

**Files:**
- Modify: `src/newsroom_v2.py`
- Test: `tests/test_newsroom_v2.py`

**Interfaces:**
- Consumes: iterable of independent zero-argument fetchers.
- Produces: cycle intake where fetchers execute concurrently and individual fetch failures are isolated.

- [ ] **Step 1: Write a failing timing/isolation test**

Add a test with two fetchers that each sleep ~0.15s and assert total fetch phase stays comfortably below serial duration, plus one fetcher that raises while another returns an item and verify the item still reaches the cycle.

- [ ] **Step 2: Run the specific tests and verify RED**

Run: `python -m pytest -q tests/test_newsroom_v2.py -k 'concurrent or fetch_failure'`
Expected: timing test FAIL with current serial loop.

- [ ] **Step 3: Implement bounded ThreadPoolExecutor fanout**

Use `concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(fetchers))))`; submit each fetcher, gather results independently, log failures and continue. Preserve deterministic downstream ordering by iterating futures in original fetcher index order when merging completed result lists.

- [ ] **Step 4: Run focused and full newsroom tests**

Run: `python -m pytest -q tests/test_newsroom_v2.py tests/test_newsroom_raw_intake.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/newsroom_v2.py tests/test_newsroom_v2.py
git commit -m "perf: fan out newsroom sources concurrently"
```

### Task 3: VPS systemd runtime root

**Files:**
- Modify: `deploy/bikhabar-agent.service`
- Modify: `deploy/bikhabar-panel.service`
- Modify: `deploy/agent.env.example`
- Test: `tests/test_vps_deploy_scripts.py`

**Interfaces:**
- Produces exact production environment paths under `/var/lib/bikhabar/runtime`.

- [ ] **Step 1: Add failing deployment assertions**

Assert agent service contains `DATA_DIR=/var/lib/bikhabar/runtime/data`, `STATE_PATH=/var/lib/bikhabar/runtime/state.json`, `CUSTOM_SOURCES_PATH=/var/lib/bikhabar/runtime/data/custom_sources.json`, `NEWSROOM_SETTINGS_PATH=/var/lib/bikhabar/runtime/data/newsroom_settings.json`, `PANEL_COMMAND_DIR=/var/lib/bikhabar/runtime/panel_commands`, `POLL_SECONDS=5`, `SESSION_SECONDS=0`. Assert panel service contains `PANEL_LOCAL_ROOT=/var/lib/bikhabar/runtime`.

- [ ] **Step 2: Run deployment tests and verify RED**

Run: `python -m pytest -q tests/test_vps_deploy_scripts.py`
Expected: FAIL on old `/opt/bikhabar/app` local root/missing envs.

- [ ] **Step 3: Update systemd units and env example**

Add the exact environment values from the spec. Keep Gunicorn on `0.0.0.0:80`.

- [ ] **Step 4: Run deployment tests and verify GREEN**

Run: `python -m pytest -q tests/test_vps_deploy_scripts.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/bikhabar-agent.service deploy/bikhabar-panel.service deploy/agent.env.example tests/test_vps_deploy_scripts.py
git commit -m "ops: run Bikhabar from VPS runtime root"
```

### Task 4: Safe runtime seeding and deploy persistence

**Files:**
- Modify: `deploy/install-vps.sh`
- Modify: `deploy/update-vps.sh`
- Test: `tests/test_vps_deploy_scripts.py`

**Interfaces:**
- Produces `/var/lib/bikhabar/runtime/{data,panel_commands}` owned by `bikhabar`.
- Seeds defaults only when destination files do not exist.

- [ ] **Step 1: Add failing script-content tests**

Assert scripts create the runtime directories, seed `custom_sources.json` and `newsroom_settings.json` only when absent, never copy live runtime files back into the Git checkout, and verify both systemd services plus local `/login` HTTP after deploy.

- [ ] **Step 2: Run deployment tests and verify RED**

Run: `python -m pytest -q tests/test_vps_deploy_scripts.py`
Expected: FAIL because updater still snapshots/restores mutable files inside the checkout.

- [ ] **Step 3: Refactor install/update scripts**

Create `RUNTIME_ROOT=/var/lib/bikhabar/runtime`; make `data` and `panel_commands`; seed repository defaults with `install -C`/guarded `cp` semantics only if destination missing. Remove checkout snapshot/restore for newsroom runtime files. Rollback only code/dependencies/systemd. Preserve panel password and env handling.

- [ ] **Step 4: Run deployment tests and shell syntax checks**

Run: `bash -n deploy/install-vps.sh deploy/update-vps.sh && python -m pytest -q tests/test_vps_deploy_scripts.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/install-vps.sh deploy/update-vps.sh tests/test_vps_deploy_scripts.py
git commit -m "ops: preserve live newsroom state across deploys"
```

### Task 5: Full verification and promotion

**Files:** none unless a regression requires a fix.

- [ ] **Step 1: Run complete regression suite**

Run: `python -m pytest -q`
Expected: zero failures.

- [ ] **Step 2: Validate shell scripts**

Run: `bash -n deploy/*.sh`
Expected: exit 0.

- [ ] **Step 3: Open PR to `main` and wait for both CI workflows**

Expected: Pull Request Check success; Telegram News Agent CI success.

- [ ] **Step 4: Merge only after green CI**

Expected: merge succeeds.

- [ ] **Step 5: Verify main CI promotes the exact merge SHA to `production`**

Expected: `production` points to the same merge SHA and `Promote tested main to production` is successful.
