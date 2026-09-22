# Bikhabar Vision 5 evidence checklist

This checklist is the release gate. A code-complete item is not treated as production-proven until its required live evidence exists under `/var/lib/bikhabar/vision5/evidence`.

| # | Acceptance area | Automated evidence | Live gate |
|---:|---|---|---|
| 1 | Legacy/runtime isolation | `test_vision5_production_foundation.py`, `test_vision5_deployment.py` | Verify legacy units remain active during staging |
| 2 | Strict production configuration | `test_vision5_health_preflight.py`, `test_vision5_deployment.py` | Successful preflight JSON |
| 3 | PostgreSQL source of truth | `test_vision5_postgres_redis_integration.py` | PostgreSQL backup and restore sample |
| 4 | Redis Streams queue | `test_vision5_postgres_redis_integration.py`, `test_vision5_workers.py` | Pending-job recovery after worker restart |
| 5 | Canonical story states | `test_vision5_core_contract.py` | State/event query from staging |
| 6 | Audit trail | `test_vision5_postgres_redis_integration.py` | Panel and Luna audit rows |
| 7 | Canonical identity/dedup | `test_vision5_identity.py` | Duplicate source sample |
| 8 | Permanent rejection blocklist | `test_vision5_postgres_redis_integration.py` | Rejected story cannot re-enter |
| 9 | RSS collection | `test_vision5_collectors.py`, `test_vision5_source_runtime.py` | Healthy live RSS run |
| 10 | X collection | `test_vision5_collectors.py`, `test_vision5_source_runtime.py` | Authenticated X run |
| 11 | Telegram collection | `test_vision5_collectors.py`, `test_vision5_source_runtime.py` | Public channel run |
| 12 | Website/manual intake | `test_vision5_collectors.py`, `test_vision5_source_runtime.py` | One operator manual item |
| 13 | Google-first translation | `test_vision5_translation_pipeline.py`, `test_vision5_workers.py` | Live provider translation |
| 14 | Luna alternate/final-copy choice | `test_vision5_luna.py`, `test_vision5_panel.py` | Human comparison in panel |
| 15 | Panel auth and CSRF | `test_vision5_panel.py` | HTTPS/session check |
| 16 | Mobile RTL realtime inbox | `test_vision5_panel.py` | Mobile browser screenshot/check |
| 17 | Search/filter/review/history | `test_vision5_panel.py` | Operator acceptance |
| 18 | Telegram text/media publishing | `test_vision5_publisher.py` | Approved target message |
| 19 | Idempotency/ambiguity/reconciliation | `test_vision5_publisher.py`, integration tests | Forced timeout drill |
| 20 | Luna context/memory/tools/voice | `test_vision5_luna.py`, `test_vision5_panel.py` | Live text and voice request |
| 21 | Builder branch/test/preview/confirm/deploy | `test_vision5_luna.py` | Non-production preview and confirmed deployment |
| 22 | Sources/settings/dashboard | `test_vision5_panel.py`, integration tests | Operator acceptance |
| 23 | Monitoring/alerts/backups/security | `test_vision5_operations.py` | Alert receipt and restore drill |
| 24 | Controlled legacy migration/parity | `test_vision5_migration.py` | Dry-run report, then signed import report |
| 25 | Isolated staging and reboot recovery | `test_vision5_deployment.py` | Host reboot and service/queue recovery record |
| 26 | Collector → DB → Google → Panel → Luna → Telegram E2E and rollback | `test_vision5_e2e.py` | `runtime e2e` evidence plus rollback drill |
| 27 | Cutover and 24-hour observation | `test_vision5_observation.py` | `runtime verify-observation` returns `ok: true` after 24 hours |

## Release rule

Cutover is allowed only when all automated tests pass, items 25 and 26 have live evidence, a current backup exists, and the exact Telegram target and cutover command have been explicitly approved. Completion is declared only after item 27 passes.
