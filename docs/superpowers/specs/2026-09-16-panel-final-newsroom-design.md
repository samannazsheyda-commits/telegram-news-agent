# Bikhabar Final Newsroom Panel Design

## Goal

Turn the existing Bikhabar V3 admin panel into a fast, professional, mobile-first newsroom where the operator can understand each incoming story with an offline literal Persian translation, reject it immediately, or publish it with Luna producing the final polished Persian Telegram copy.

## Product Rules

1. Incoming source text remains the source of truth and is never overwritten by panel translation.
2. Every live story shown to the operator should receive a cached **offline Argos** Persian preview. This preview is explicitly labeled `ترجمه آفلاین · تحت‌اللفظی` and is for comprehension only.
3. The offline preview must never be used as final Telegram copy.
4. One-tap **رد** rejects the story immediately. No confirmation dialog.
5. One-tap **انتشار** immediately starts finalization/publishing. No confirmation dialog.
6. Manual publish must use **Luna/1xAI** to translate/edit the original source into final natural Persian. If Luna cannot produce a faithful/natural result, publishing fails closed and nothing is sent to Telegram.
7. Visible news copy must not leak English source labels such as `Clash Report`; canonical source labels must be localized for display.
8. Global destructive controls such as “stop all publishing” may keep confirmation because they affect the whole system.
9. The UI must be usable on mobile first, with a reliable fixed bottom navigation and proper safe-area spacing.
10. The panel should feel like a modern newsroom/SaaS product: light slate background, light cards, charcoal/navy navigation, red only for urgent/danger actions, minimal animation and minimal expensive blur.

## Architecture

### Live feed localization

`panel/live_api.py` owns the panel-only localization endpoint. It must call `src.offline_translation.translate_to_fa_offline` directly, not Google, Google Mobile, MyMemory, Lingva, OpenRouter, or Luna. Results are cached by a stable hash of the source title/body so repeated polling does not rerun Argos.

The API returns localized fields plus a machine-readable mode such as `translation_mode: "offline_literal"`. The browser shows the result as a rough literal preview and keeps the original source text available in a collapsed block.

### Manual publish

The panel publish action must never forward the rough offline preview as publishable copy. It submits the story identity to the backend. The backend reloads the original story, asks Luna/1xAI for a faithful Persian translation plus natural Persian edit, validates the result using the existing strict editorial/translation guards, formats the Telegram message, and sends it. Luna failure or invalid output causes a visible panel error and zero Telegram writes.

The existing V3 automatic publisher and daily cap remain unchanged unless required to reuse the same strict finalization code.

### Reject

Reject changes story state immediately and removes the card from the active feed after the server confirms success. No client-side confirmation sheet is used for a per-story rejection.

### UI and performance

The current dark shell is replaced with a light/slate design token set. `backdrop-filter` and heavy continuous animations are removed from the primary shell. Cards use simple borders/shadows. Bottom nav remains fixed and receives explicit safe-area padding and z-index isolation.

Polling becomes less aggressive: approximately 5 seconds while visible and 30 seconds while hidden. The existing fingerprint short-circuit remains. Localization is limited and cached, and the browser should avoid rerendering when the fingerprint has not changed.

## Main Files

- `panel/live_api.py`: offline Argos localization endpoint and cache.
- `panel/newsroom_api.py` / panel action backend: one-tap reject and manual Luna publish orchestration.
- `panel/static/newsroom-live.js`: literal-preview labeling, polling cadence, cached localization rendering.
- `panel/static/newsroom-actions.js`: no confirmation for story publish/reject; busy/result states.
- `panel/static/newsroom-shell.css`: final light/slate responsive shell.
- `panel/templates/base.html`: light color-scheme/theme metadata and stable navigation shell.
- `panel/templates/dashboard.html`: concise newsroom hierarchy and preview labels.
- `src/formatters.py`: canonical source-label localization for `Clash Report` and similar visible labels when needed.
- tests under `tests/`: API behavior, no-confirm UI contract, light-theme contract, source-label regression.

## Error Handling

- Offline translation error: original source remains visible, card shows a retry state, publish is still permitted because final publish does not rely on the offline preview.
- Luna unavailable/invalid: publish fails closed; card remains; UI shows a concise error; no Telegram request is made.
- Telegram failure: existing ambiguous-write protections remain in force.
- Reject failure: card remains and button returns to enabled state with an error toast.

## Acceptance Criteria

- A new English story appears with an offline literal Persian preview without any network translator call.
- The preview is labeled as offline/literal and cannot be mistaken for final Telegram copy.
- Tapping Reject once rejects it with no confirmation.
- Tapping Publish once invokes Luna finalization and publishes only the validated polished Persian output.
- If Luna errors, no Telegram write occurs.
- `Clash Report` is displayed in Persian in final visible news output.
- Mobile bottom navigation remains clickable and unobscured.
- The primary panel is light/slate, not near-black, and does not use backdrop blur for the main top bar/cards.
- Live polling is reduced from 3s/15s to 5s/30s or slower while preserving timely updates.
- Existing newsroom backend tests continue to pass.
