# Bikhabar Vision 5 final execution plan

Source of truth: `Bikhabar-Vision5-Handoff-2026-09-21.md` supplied by the project owner.

## Non-negotiables
- Legacy `/opt/bikhabar` remains untouched and rollback-safe until cutover.
- Final V5 runtime is isolated at `/opt/bikhabar-vision5`.
- Production data core is PostgreSQL; async queue is Redis.
- No production runtime dependency on newsroom v2/v3/v4.
- No placeholder controls. Every exposed UI action must have a real backend path.
- TDD for every batch; evidence before any Done status.
- Final requires real Collector -> DB -> Google translation -> Panel -> Luna -> Telegram E2E, reboot recovery, rollback test, alerts, and 24h post-cutover observation.

## Controlled batches
1. Production foundation: standalone package, strict config, PostgreSQL schema/store, Redis queue, migrations, health/preflight.
2. Canonical story state machine + immutable source timestamps + audit + dedup/permanent reject.
3. Collectors: RSS, X, Telegram, websites, manual; source health and media/original-link retention.
4. Translation pipeline: Google-first all non-Persian, retry isolation, Luna alternate, final copy selection.
5. Standalone V5 panel: auth/CSRF, mobile RTL, realtime inbox, search/filter/pagination, review editor, history.
6. Telegram publisher: media/text, idempotency, ambiguous-response reconciliation, controlled retry, immediate inbox removal.
7. Luna operator: newsroom context, tools, memory/rules, permission gates, voice, audit; Builder branch/TDD/CI/preview/confirm/deploy.
8. Sources/settings/dashboard/monitoring/security/backups/admin alerts.
9. Migration: import only healthy sources/channel config/rules/required history; parity evidence.
10. Staging systemd services under `/opt/bikhabar-vision5`, separate port/env/data/logs; reboot recovery.
11. Real E2E against approved Telegram target; backup + rollback drill.
12. Cutover, 24h monitoring, evidence ledger for all 27 handoff sections.

Each batch lands through a dedicated branch/PR or a clearly bounded PR series. Existing V5 stage 1-3 code is evidence/input only; it is not automatically accepted as final.