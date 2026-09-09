# Realtime publish recovery, weather preview, and light panel

## Goal
Restore continuous fresh Telegram publication on the VPS-first runtime, keep stale discovery noise out of the event ledger/live feed, make direct realtime sources primary, expose an exact weather-message preview in the panel, and replace the overly dark UI with a light newsroom theme.

## Tasks
1. Add regression tests proving direct X intake is wired into Newsroom V2 and stale items are dropped before ledger/live-feed creation.
2. Wire managed/direct FxTwitter timelines into the raw intake while retaining Google/system queries as fallback. Make direct X sources visible/controllable in Source Manager.
3. Add an early freshness gate using the configured `freshness_hours` so old RSS/Google results never create events or panel rows.
4. Add weather preview generation/storage with no Telegram write, plus an authenticated panel refresh endpoint and exact preview display alongside the existing publish-now action.
5. Convert the panel skin to a light professional newsroom palette while keeping red breaking/priority accents and readable status colors.
6. Extend tests for weather preview and light-theme UI contract.
7. Run full CI + deploy-script validation, merge only on green, verify the exact tested commit is promoted to `production`.

## Verification
- Full pytest suite passes.
- Deployment-script validation passes.
- PR verification workflow passes.
- Main promotion to `production` succeeds.
- Production branch points at the merged tested SHA.
- VPS runtime remains a separate verification step; do not claim live deployment until the VPS is observed on that SHA.
