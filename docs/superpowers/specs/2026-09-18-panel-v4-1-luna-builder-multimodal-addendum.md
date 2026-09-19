# Panel V4.1 — Luna Builder + Multimodal Addendum

This addendum extends the approved `2026-09-18-panel-v4-1-luna-operator-design.md` design. It is part of the same V4.1 acceptance scope.

## Product intent

Luna must feel like a real assistant inside the Bikhabar panel, not a command form. The user should be able to speak or type naturally in Persian, attach an image, continue a conversation with context, and ask Luna either to operate the newsroom or to propose/build controlled panel changes.

Examples that must be understood naturally:

- «این گزارش انگلیسیه، فارسیش کن.»
- «این خبر رو رد کن و دیگه منتشرش نکن.»
- «این منبع رو اضافه کن.»
- «این منبع رو خاموش کن.»
- «یه ماژول برای فلان چیز اضافه کن.»
- «یه پنل جدید برای این گزارش بساز.»
- «این بخش داشبورد رو حذف کن.»
- «این اسکرین‌شات رو بررسی کن و بگو مشکل چیه.»

## Two Luna modes

### 1. Operator mode

Operator mode performs bounded newsroom actions using explicit tools. It may:

- search/get stories,
- translate stories,
- move stories to review,
- reject and durably block stories,
- inspect recent publications and newsroom health,
- list/add/enable/disable/delete approved source types,
- inspect current panel configuration and module state.

Actions that mutate sources or permanently block a story require a short confirmation card before execution.

### 2. Builder mode

Builder mode is used when the user asks for a panel/module/UI/code change. It is not an unrestricted shell.

Builder mode must:

1. classify the request as a code/configuration change,
2. produce a short implementation summary,
3. create or reuse a dedicated GitHub change branch,
4. write tests first,
5. make the smallest code change needed,
6. run repository CI,
7. show the user a structured result containing files changed, tests, and preview/deploy status,
8. require explicit confirmation before merge/deploy,
9. retain a rollback reference to the pre-change production commit.

Builder mode must never edit the production checkout directly, run arbitrary shell supplied by the model, expose server secrets, or merge/deploy while CI is red.

Builder requests are allowed to create or modify panel pages, modules, navigation items, dashboard cards, settings controls, styles, and newsroom tools. Changes outside the Bikhabar repository or destructive server operations are out of scope unless a separate explicit tool is later added.

### Builder credentials

Builder mode requires a server-side GitHub credential with the minimum repository permissions required to create branches/commits/PRs and read checks. Store it only in `/etc/bikhabar/agent.env`, e.g. `LUNA_GITHUB_TOKEN`. Never expose it in HTML, JavaScript, logs, tool results, prompts, or telemetry.

If the credential is missing, Luna must explain that Builder mode is disconnected while Operator mode continues to work.

## Natural-language intent resolution

Luna must resolve colloquial Persian and contextual references such as «این خبر»، «همین منبع»، «اون کارت»، and «همین صفحه» from the bounded conversation context and explicit UI context sent by the browser.

If more than one story/source/module is a plausible target, Luna asks one focused clarification rather than guessing.

## Image input

The Luna composer supports image attachments in JPG, PNG, and WebP.

- Images are passed to an OpenAI vision-capable Responses API model as part of the current turn.
- The user can ask Luna to inspect screenshots, charts, article images, UI bugs, or text visible in an image.
- Uploaded images are temporary and are deleted after processing unless a future explicit archive feature is enabled.
- Maximum size and dimensions are server-validated before upload to the provider.
- No image is interpreted as authorization for a destructive action; destructive actions still require confirmation.

## Voice input

The Luna composer includes a microphone button.

Flow:

1. Browser records a short voice message.
2. Audio is POSTed to an authenticated panel endpoint.
3. Server sends the temporary audio to OpenAI speech-to-text.
4. The transcription is returned into the composer and may be edited before sending.
5. Temporary audio is deleted immediately after transcription.

Voice recordings are not stored as newsroom data.

## Streaming chat UX

The assistant UI must support streamed/near-streamed responses so it does not feel frozen.

Required states:

- user message appears immediately,
- Luna typing/working indicator,
- incremental assistant text where supported,
- explicit tool activity cards such as «در حال پیدا کردن خبر…» / «منبع پیدا شد» / «نیاز به تأیید»،
- recoverable retry state on provider/network error,
- composer remains usable after an error.

The chat is mobile-first, full-width, and keeps the composer pinned to the bottom safe area.

## Durable operator block

V3 currently preserves only selected terminal rejection reasons. Add `operator_block:` as a terminal rejection reason (or an equivalent durable block mechanism) so a user-blocked story cannot become `ready` again on a later ingest cycle.

Blocking must be test-covered against rediscovery/reingestion.

## Translation from chat

When the user asks Luna in chat to translate a report/story, Luna must use the same guarded OpenAI translation pipeline as the story-card `ترجمه با Luna` action. It must not fall back to Google/MyMemory as publishable copy.

## Air Traffic

Air Traffic remains excluded from the V4.1 panel UI, navigation, system-health cards, dashboard modules, Luna UI suggestions, and service-worker shell. Its independent backend service is not deleted by this change.

## Additional acceptance criteria

V4.1 is not accepted until all of the following are true:

1. Voice input transcribes Persian into the Luna composer.
2. Image attachments can be analyzed in the same chat turn.
3. Luna understands contextual Persian references and asks clarification when ambiguous.
4. Source add/disable/delete and permanent story block can be requested conversationally and executed only after confirmation.
5. A Builder request such as «یه پنل جدید برای X بساز» produces a controlled branch/PR workflow instead of pretending the change happened.
6. Builder mode cannot merge/deploy with failing CI and cannot access unrestricted shell.
7. Operator-blocked stories remain blocked on later ingest cycles.
8. Chat responses and tool states feel responsive on mobile and desktop.
