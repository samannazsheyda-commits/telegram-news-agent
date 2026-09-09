# Translation + Telegram lane hotfix

Observed on VPS after f1eca678:
- production cycle has publish_failed caused by `translation_or_format_failed` on English X sources.
- DIRECT_TELEGRAM marker is still absent from the live cycle output.

Plan:
1. Add a third Google mobile translation fallback and explicit translation diagnostics without leaking content/secrets.
2. For urgent war alerts, never drop the story solely because machine translation is unavailable: fall back to source-language text as a last-resort continuity mode.
3. Add lane-start/lane-end diagnostics around the Telegram fetcher so production proves invocation and item count.
4. Keep the seven tier-one Telegram channels sourced from managed rows.
5. Add regression tests, run PR CI, merge only on green, promote to production.
