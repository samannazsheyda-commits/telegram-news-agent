# Newsroom V5 rollback

V5 stays off until an operator explicitly enables it. `deploy/agent.env.example` is the safe default:

- `NEWSROOM_STORE_BACKEND=github`
- `NEWSROOM_V5_SHADOW_PIPELINE=false`
- `NEWSROOM_V5_UI_ENABLED=false`
- `NEWSROOM_V5_TELEGRAM_WRITES_ENABLED=false`
- `NEWSROOM_AUTO_PUBLISH_ENABLED=false`

`deploy/update-vps.sh` does not enable `bikhabar-newsroom-v5-worker.service`. The worker unit can be installed later, during an approved cutover, and must stay stopped while Telegram writes are off.

## Activation order

Do not skip to automatic publishing.

1. Ship storage and migration code with the legacy GitHub backend still selected.
2. Dry-run migration and the parity verifier against a copy of production data.
3. Enable the V5 shadow pipeline with Telegram writes disabled.
4. Confirm stories are not dropped.
5. Run the final-delta migration.
6. Switch `NEWSROOM_STORE_BACKEND` to `sqlite`.
7. Check Review, Published, and terminal states.
8. Enable the V5 app shell.
9. Check SSE, the service worker, and HTTPS.
10. Enable Luna on the V5 store.
11. Burn in.
12. Only after a separate operator confirmation, set `NEWSROOM_AUTO_PUBLISH_ENABLED=true`.

## Roll back a cutover

1. Set `NEWSROOM_AUTO_PUBLISH_ENABLED=false` and `NEWSROOM_V5_TELEGRAM_WRITES_ENABLED=false`.
2. Stop `bikhabar-newsroom-v5-worker.service` if it was started. Do not leave it enabled.
3. Set `NEWSROOM_V5_UI_ENABLED=false` and `NEWSROOM_V5_SHADOW_PIPELINE=false`.
4. Set `NEWSROOM_STORE_BACKEND=github` and restart the panel and agent.
5. Leave the SQLite file in place. It is not deleted by rollback, so a later cutover can resume from the last migrated copy.
