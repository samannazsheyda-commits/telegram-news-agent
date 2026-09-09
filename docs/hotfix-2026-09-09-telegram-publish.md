# Telegram realtime publish hotfix — 2026-09-09

- Keep tier-one Telegram channels as persistent system-managed realtime sources, so mutable VPS source state cannot silently remove them.
- Deduplicate system/custom source identities in the panel.
- Retry `sendMessage` without HTML parse mode when Telegram rejects malformed HTML entities.
- Emit explicit `TELEGRAM_PUBLISH_FAILED` diagnostics for missing credentials, translation/format failures, and Telegram API failures.
