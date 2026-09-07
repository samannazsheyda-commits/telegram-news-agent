# BiKhabar Browser Panel Redesign — Design Spec

## Goal

Replace the current low-utility GitHub Pages control panel with a fast, newsroom-style browser dashboard that is easy to read, fast to operate, resilient to GitHub workflow delays, and safe against duplicate/manual-command errors.

Primary success criteria:
- Reject feels instant in the UI: the card disappears immediately, with no modal/confirm popup.
- Publish feels instant in the UI: the card leaves the active queue immediately and shows a non-blocking publishing state.
- Real Telegram delivery is confirmed asynchronously; failures restore the item instead of silently losing it.
- The panel remains usable on desktop and mobile.
- No Telegram bot token or long-lived GitHub credential is embedded in public source code.
- No VPS and no Vercel are required.

## Product Direction

The panel should look and behave like a compact newsroom console, not a developer/debug page. The main screen prioritizes rapid editorial decisions over system internals.

Visual direction:
- Dark, calm newsroom UI.
- High-contrast Persian typography with a readable system-first stack; no tiny metadata.
- Clear hierarchy between title, body, source, timestamp, and actions.
- Compact but generous spacing; no visual clutter.
- Strong green Publish action and red Reject action, with neutral secondary actions.
- Responsive layout with large tap targets on mobile.

The default view opens directly to the review queue. System/debug information is secondary and moved into its own section.

## Architecture

The architecture keeps GitHub Pages as the frontend host and GitHub Actions as the secure execution environment, but removes the current coupling between editorial commands and the near-realtime monitor.

There are four units:

1. `docs/panel.html` — presentation shell and progressive UI.
2. Browser-side panel controller — queue loading, optimistic actions, filters, local draft persistence, command creation, status polling, and rollback.
3. Dedicated panel-command workflow — reacts only to panel command files and processes them independently of the long-running news monitor.
4. Server-side command processor — idempotent publish/reject logic, Telegram send confirmation, queue/history transitions, and command result recording.

The near-realtime news monitor and the browser command processor must not share a concurrency group. A panel command must never wait behind a 4–5 minute monitor session.

## Command Model

The browser writes a uniquely named command JSON file under `panel_commands/` using the GitHub Contents API.

Command shape:

```json
{
  "command_id": "uuid",
  "action": "publish | reject",
  "item_id": "editorial item id",
  "title": "final Persian title",
  "body": "final Persian body",
  "created_at": "ISO-8601 timestamp"
}
```

The dedicated workflow processes exactly the newly created command file.

A command must be idempotent by `command_id` and by editorial item state. Re-running the same workflow must never publish the same Telegram message twice.

For publish:
- If the item is already terminal/published, do not send again.
- If the original source link is already found in the channel publication history, do not send again; reconcile the queue/history state instead.
- Telegram success occurs before the final editorial state mutation.
- On Telegram failure, the item stays pending and the result is marked failed.

For reject:
- Reject is safe to run repeatedly.
- If already terminal, return a successful no-op result.
- No Telegram API call occurs.

## Command Results

Each command gets a result record under `panel_results/<command_id>.json`.

Result shape:

```json
{
  "command_id": "uuid",
  "item_id": "editorial item id",
  "action": "publish | reject",
  "status": "processing | succeeded | failed | reconciled",
  "message": "short Persian-readable status",
  "updated_at": "ISO-8601 timestamp"
}
```

The browser polls only the result for commands it initiated. This avoids refreshing the whole queue every few seconds.

Processed command files are deleted or moved out of the active command directory after a terminal result is persisted. No old publish command may remain executable indefinitely.

## Optimistic UI Behavior

### Reject

When Reject is clicked:
- Remove the card from the active list immediately.
- Update the pending counter immediately.
- Show a small non-modal toast with an Undo action for approximately 5 seconds.
- Send the reject command in the background.
- If GitHub rejects the command creation, restore the card and show an inline error.
- If the server-side result fails, restore the card automatically.

Undo behavior:
- Undo only exists before the command has reached a terminal server-side result.
- Undo cancels the local optimistic removal and prevents command submission when still inside the local grace window.
- Once the command has been submitted and completed, Undo is no longer offered.

### Publish

When Publish is clicked:
- Validate non-empty title and source URL before submission.
- Move the card immediately out of the active queue into a small `در حال انتشار` lane/status.
- Disable duplicate clicks for that item.
- Submit the command in the background.
- Poll the specific command result.
- On `succeeded` or `reconciled`, remove the temporary publishing indicator and update counters.
- On `failed`, return the card to its prior queue position with the edited draft intact and show an inline failure state.

The UI must never claim “منتشر شد” merely because the GitHub command file was created. Telegram-confirmed success is the only real publish success.

## Main Screen

Top area:
- Brand: `بی‌خبر` and `مانیتور تحولات ایران`.
- Connection indicator.
- Last refresh / health indicator.
- Compact refresh control.

Primary stats:
- در انتظار
- در حال انتشار
- منتشرشده امروز
- ردشده امروز

Queue toolbar:
- Search across title/body/source.
- Source filter.
- Sort: newest / oldest.
- Optional reason filter for rejection/flag reason.
- Clear filters control.

News card:
- Prominent editable Persian headline.
- Editable body/summary.
- Source chip.
- Original publication time in Tehran/Persian display.
- Rejection/attention reason.
- Open-source button.
- Publish button.
- Reject button.
- Local “edited” indicator when draft differs from loaded value.

The source link opens in a new tab without losing panel state.

## Tabs / Views

1. `در انتظار` — primary work queue.
2. `در حال انجام` — commands currently awaiting terminal result.
3. `منتشرشده` — recent manual/auto published items.
4. `ردشده` — recent rejected/superseded items.
5. `سیستم` — health, last workflow result, last successful monitor time, current runtime version, and compact diagnostics.

System view must not dominate the initial experience.

## Draft Persistence

Edited title/body drafts are saved automatically to browser local storage by item ID.

Rules:
- Save after short debounce, not on every keystroke synchronously.
- Restore drafts when the panel reloads.
- Clear draft after successful publish/reconcile/reject.
- Keep draft after failed publish.
- Provide a small “بازگشت به متن اولیه” control when a draft exists.

No GitHub token is stored in localStorage. Authentication credential storage remains session-scoped.

## Authentication

The current fine-grained GitHub token model is retained for the no-backend design.

Required repository permission:
- Contents: Read and write.

The token is stored only in `sessionStorage` for the active browser tab/session.

The panel should not show a large permanent token box after successful connection. Instead:
- Show a compact connection badge.
- Offer `تغییر اتصال` / `قطع اتصال` in a small settings area.
- On first use without a token, show a clean inline connect sheet rather than browser `alert()` dialogs.

No browser `alert()`, `confirm()`, or blocking prompt is allowed in normal editorial flow.

## Performance

Frontend requirements:
- Single lightweight static page or a very small set of static assets.
- No large frontend framework required.
- Initial queue render should not wait for system/workflow diagnostics.
- Load queue/history first; load diagnostics lazily.
- Use DOM event delegation instead of many global inline handlers.
- Render only the first working set of cards and progressively reveal more when the queue is large.
- Poll command results individually; do not reload 1+ MB history on every short interval.
- Full queue refresh target: every 20–30 seconds while visible, slower when tab is hidden.
- Manual refresh always available.

## Workflow Performance

The dedicated panel workflow should:
- Trigger only for new/changed `panel_commands/*.json` files.
- Use a separate concurrency group such as `browser-panel-command-${{ github.ref }}` and never the main `telegram-news-agent` group.
- Avoid running the full project test suite for every user click.
- Install only runtime dependencies needed for command execution.
- Process the target command and persist queue/history/state/result in one short execution.
- Use fetch/rebase/merge-safe persistence to avoid overwriting state changes made by the monitor.

Target behavior is “a few seconds plus GitHub Actions startup latency,” not minutes.

## Error Handling

User-facing errors are inline and actionable.

Examples:
- GitHub 401/403 → connection badge turns red and asks to reconnect/check Contents permission.
- Command creation conflict → retry with a new command ID/path once automatically.
- Publish validation error → keep card in place and highlight the invalid field.
- Telegram failure → restore the card and retain draft.
- Workflow/result timeout → keep item in `در حال انجام` with a retry/status action rather than claiming success.
- Queue/history fetch failure → keep last rendered data visible with a stale-data warning.

No destructive action is hidden behind an unhandled exception.

## Safety Against Duplicate Publishing

Duplicate prevention is mandatory at multiple layers:
- UI disables duplicate submission for the same item while a command is active.
- Command processor is idempotent by command ID.
- Editorial state is checked before Telegram send.
- Existing channel publication/source-link guard is checked before Telegram send.
- Processed command files do not remain live indefinitely.
- A failed persistence step after Telegram success must reconcile on retry without sending Telegram again.

## Accessibility and Typography

- Persian RTL is the default direction.
- Minimum comfortable body text size is 15–16 px on desktop and mobile.
- Headline editing area is visually larger than metadata.
- Buttons have large click/tap targets.
- Status is not conveyed by color alone; text/icon labels accompany color.
- Focus states are visible for keyboard use.
- Contrast should remain readable in dark mode.

Font strategy:
- Prefer locally available Persian-friendly system fonts to avoid a blocking external font dependency.
- Use a stack that prioritizes `Vazirmatn` when installed, then `Tahoma`, `Segoe UI`, and system sans-serif fallbacks.
- If a webfont is later introduced, it must not block first render and must be legally distributable; no font binary is committed unless explicitly licensed for redistribution.

## Mobile Behavior

On narrow screens:
- One-column cards.
- Sticky bottom action bar inside the active card for Publish / Reject / Source.
- Search/filter toolbar collapses into a compact controls row.
- Textareas remain comfortably editable.
- No horizontal scrolling for normal content.

## Data Compatibility

The redesign must continue to read existing:
- `data/editorial_queue.json`
- `data/editorial_history.json`
- `state.json`

Existing statuses remain supported:
- `pending`
- `published_manual`
- `published_auto`
- `rejected_manual`
- `superseded`

New command-result status data is additive and must not require rewriting historical editorial data.

## Files Expected to Change

Likely files/components:
- `docs/panel.html` — replacement newsroom UI.
- Optional `docs/panel.css` and `docs/panel.js` if splitting improves maintainability and cache behavior.
- `.github/workflows/panel-file-command.yml` or replacement dedicated workflow.
- `src/panel_command_file.py` — idempotent command processing and result writing.
- `src/manual_publish.py` — only if a clearer idempotent publish interface is needed.
- `src/persist_merge.py` — only if command persistence needs explicit result-file merge support.
- Focused tests for command idempotency, no duplicate Telegram send, optimistic-panel contract, and workflow isolation.

The main monitor workflow should only be changed if necessary to remove shared concurrency with panel commands; unrelated news logic is out of scope.

## Testing Strategy

Server-side tests:
- Reject is idempotent.
- Publish sends Telegram at most once under command retry.
- Already-published/channel-present item reconciles without Telegram send.
- Telegram failure leaves item pending.
- Successful Telegram send followed by workflow retry does not resend.
- Command result file reaches the correct terminal status.

Frontend static/contract tests:
- No `alert(` or `confirm(` in panel source.
- Publish/reject actions are present and optimistic-state hooks exist.
- Search/source/sort controls exist.
- Draft persistence keys/functions exist.
- Command results are polled separately from full history refresh.
- Token is session-scoped, never embedded.
- Mobile viewport and RTL are preserved.

Workflow tests/inspection:
- Panel command workflow has a concurrency group separate from `telegram-news-agent`.
- Panel workflow does not run the full pytest suite on every command.
- Main production monitor remains unchanged in behavior.

Verification before completion:
- Run focused panel/backend tests.
- Run the full existing suite.
- Inspect the actual panel workflow run through completion.
- Execute a safe reject test on a disposable/test record if available; do not alter a real editorial item solely for testing.
- Verify GitHub Pages serves the new panel assets.
- Do not claim Telegram publish latency or success without observing a real command result path.

## Non-Goals

- Replacing GitHub Pages with a VPS, Vercel, or new hosted backend.
- Embedding the Telegram bot token in the browser.
- Embedding a GitHub PAT in repository files.
- Rebuilding the news-monitor editorial algorithms.
- Changing the channel’s news formatting rules except where needed to safely complete manual publishing.

## Acceptance Criteria

The redesign is accepted when:
- The queue is readable and usable immediately on desktop and mobile.
- Reject removes the card immediately without a popup and either completes or restores on failure.
- Publish transitions immediately to `در حال انتشار`, then only shows success after server-side confirmation.
- A failed publish restores the item and its edited draft.
- A duplicated/retried publish command cannot send Telegram twice.
- Panel commands no longer wait behind the long monitor concurrency group.
- Search, source filtering, sorting, history views, health/status, and draft autosave work.
- Authentication UX is compact after connection.
- Focused tests and the full test suite pass before the implementation is called complete.
