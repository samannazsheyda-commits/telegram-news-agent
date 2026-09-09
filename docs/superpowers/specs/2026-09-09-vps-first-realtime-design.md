# Bikhabar VPS-First Realtime Architecture

## Goal
Run Bikhabar as a true VPS-first newsroom where the VPS owns live state, panel commands, source configuration, polling, publishing and health; GitHub is only the versioned code/deployment source and never sits in the hot path of a breaking-news cycle.

## Core runtime model
- Production code lives at `/opt/bikhabar/app` and follows branch `production`.
- Mutable runtime state lives outside the Git checkout at `/var/lib/bikhabar/runtime`.
- The panel and the agent read/write the same runtime root.
- Git deployments may replace code, but must never overwrite live queue/history/settings/source state.
- Breaking-news polling target remains 5 seconds; individual source fetchers execute concurrently so one slow source does not block others.

## Mutable VPS runtime files
The runtime root owns:
- `state.json`
- `data/newsroom_settings.json`
- `data/custom_sources.json`
- `data/editorial_queue.json`
- `data/editorial_history.json`
- `data/event_ledger.json`
- `data/panel_live_feed.json`
- `panel_commands/*.json`

On first install/upgrade, seed files that do not yet exist from repository defaults. Never copy repository defaults over an existing runtime file.

## Hot-path configuration
Systemd exposes:
- `DATA_DIR=/var/lib/bikhabar/runtime/data`
- `STATE_PATH=/var/lib/bikhabar/runtime/state.json`
- `CUSTOM_SOURCES_PATH=/var/lib/bikhabar/runtime/data/custom_sources.json`
- `NEWSROOM_SETTINGS_PATH=/var/lib/bikhabar/runtime/data/newsroom_settings.json`
- `PANEL_LOCAL_ROOT=/var/lib/bikhabar/runtime`
- `PANEL_COMMAND_DIR=/var/lib/bikhabar/runtime/panel_commands`
- `POLL_SECONDS=5`
- `SESSION_SECONDS=0`

## Polling and source fanout
`build_raw_fetchers()` remains the source registry, but each cycle fans out the independent fetchers concurrently with bounded workers and a bounded cycle deadline. Results are merged after completion. A failing/slow source contributes an empty result and is logged; it does not delay every other source.

## Command Center
The panel uses the local repository backend pointed at the runtime root, so stop/resume, source edits, freshness settings, quiet mode and manual commands are instant local writes. Panel commands are consumed from the same runtime root by the agent.

## Deployment and self-heal
`update-vps.sh` fetches and tests the target commit, updates dependencies and systemd units, then restarts services. Runtime state is outside the checkout, so no snapshot/restore loop is required for mutable newsroom data. A local health check must verify:
1. `bikhabar-agent` active
2. `bikhabar-panel` active
3. HTTP `/login` responds locally on port 80

Rollback reverts code only; live runtime data remains untouched.

## Security
- No tokens/passwords rendered in panel HTML or logs.
- Runtime root mode is private to service user/root.
- Panel remains authenticated and CSRF protected.
- Port 80 remains the panel bind target; public firewall/provider networking is an infrastructure concern outside application code.

## Success criteria
- A deployment cannot erase panel settings, source edits, queue/history, live feed, event ledger or dedup state.
- The agent and panel share one local runtime root.
- Production source polling target is 5 seconds and fetchers do not run serially.
- Panel commands are local VPS operations, not GitHub writes.
- CI regression suite and deployment-script validation pass before promotion to `production`.
