# Panel V4.1 Luna Operator — Implementation Plan

**Goal:** Deliver a polished V4.1 panel where Luna is a real Persian conversational operator with guarded OpenAI translation, image/voice input, durable story blocking, source management, and a controlled Builder mode for panel/module changes.

**Architecture:** Keep the existing Flask panel and Newsroom V3 publish path. Add a server-side OpenAI Responses client and explicit Luna tool registry. Separate everyday Operator tools from code-changing Builder tools. No unrestricted shell is exposed. Builder changes use GitHub branches/commits/PRs and cannot merge/deploy unless checks are green and the user confirms.

**Technology:** Python/Flask, requests, Jinja, vanilla JS/CSS, SSE/chunked responses where practical, SQLite/JSON existing state, GitHub REST, OpenAI Responses API + speech transcription.

---

## Task 1 — Contract tests for V4.1 behavior (RED)

**Create:**
- `tests/test_panel_luna_operator_v41.py`
- `tests/test_panel_luna_multimodal_v41.py`
- `tests/test_panel_luna_builder_v41.py`
- `tests/test_newsroom_v3_operator_block.py`
- `tests/test_panel_v41_ui_contract.py`

**Tests first:**
- Operator tool resolution handles Persian story/source requests without keyword-only canned routing.
- Ambiguous target returns clarification and does not mutate state.
- Source add/enable/disable/delete require confirmation.
- Story reject/block requires confirmation and produces a durable `operator_block:` decision.
- Reingesting the same V3 story keeps it rejected.
- Translation failure cannot promote machine fallback to final Persian copy.
- Voice endpoint rejects unsupported/oversized files and returns provider transcription when valid.
- Image attachment metadata is validated and accepted only for allowed formats.
- Builder request is classified separately from Operator request.
- Builder cannot directly deploy or run arbitrary shell.
- V4.1 templates/service worker have no Air Traffic UI references and load only current assets.
- Luna page contains image + mic controls and no canned demo command section.

**Verification:** open/update draft PR after the tests-only commit and confirm CI fails for missing V4.1 implementation, not syntax/fixture mistakes.

## Task 2 — Durable operator block

**Modify:**
- `src/newsroom_v3/shadow.py`
- `panel/newsroom_api.py`
- optionally `panel/luna_tools.py`

**Behavior:**
- Treat `operator_block:` as a terminal V3 rejection.
- When blocking a V3 story, set decision state `rejected` with `operator_block:<reason>`.
- For panel-live/V2 projection, continue marking seen/removing from queue while also persisting a bounded block fingerprint/URL registry if needed for parity.
- Block tool returns exact story title/id and audit record.

**Tests:** run `pytest -q tests/test_newsroom_v3_operator_block.py`.

## Task 3 — OpenAI provider layer and usage telemetry

**Create:**
- `panel/openai_luna.py`
- `panel/luna_usage.py`

**Modify:**
- `panel/wsgi.py`

**Provider responsibilities:**
- Read only server env: `OPENAI_API_KEY`, `LUNA_MODEL_FAST`, `LUNA_MODEL_COMPLEX`, `LUNA_TRANSCRIBE_MODEL`.
- Responses API requests for text + image + function calling.
- Speech-to-text request for voice notes.
- Structured provider errors: missing key, timeout, rate limit, invalid response.
- Usage extraction and daily/monthly aggregates in `data/luna_usage.json` without prompts or secrets.

**No new SDK dependency required:** use existing `requests` so VPS dependency footprint stays small.

## Task 4 — Guarded Luna translation pipeline

**Create:**
- `panel/luna_translation.py`

**Modify:**
- `panel/v4.py`
- `panel/templates/dashboard.html`
- `panel/static/newsroom-v4-dashboard.js`

**Flow:**
1. Send original title/body to OpenAI with strict Persian newsroom schema.
2. Validate Persian output, numbers, URLs/handles, attribution, length, and hallucination indicators.
3. On failure, run one repair pass with explicit failure reasons.
4. If still failing, return `needs_review` and do not persist as final copy.
5. On pass, persist `final_persian_title/body` and translation quality metadata.
6. Existing `machine_translation` is diagnostic/cache only and never silently publishable.

**Story UI:** replace old Luna judgment/importance controls with `ترجمه با Luna`, edit/review, publish, block, source.

## Task 5 — Real Luna Operator tool registry

**Create:**
- `panel/luna_tools.py`
- `panel/luna_conversation.py`

**Rewrite:**
- `panel/luna_assistant.py`

**Initial tools:**
- `search_stories`
- `get_story`
- `translate_story`
- `reject_and_block_story`
- `move_story_to_review`
- `list_recent_published`
- `diagnose_newsroom`
- `list_sources`
- `add_source`
- `enable_source`
- `disable_source`
- `delete_source`
- `inspect_panel_state`

**Rules:**
- Model chooses tools from natural Persian.
- Tool arguments are server validated.
- Context window is bounded and server-side.
- Ambiguous story/source -> ask clarification.
- Mutating/destructive tools -> single-use confirmation object.
- No arbitrary Python/shell/HTTP tool.

## Task 6 — Voice and image input

**Modify:**
- `panel/luna_assistant.py`
- `panel/templates/luna.html`
- `panel/static/luna-assistant.js`

**Add endpoints:**
- `POST /api/panel/luna/transcribe`
- `POST /api/panel/luna/chat` or streaming equivalent with optional image attachment token

**Voice:**
- record via `MediaRecorder`,
- upload temporary blob,
- transcribe server-side,
- return text into composer,
- delete temp audio immediately.

**Image:**
- JPG/PNG/WebP only,
- server size/type/dimension validation,
- temporary in-memory/tempfile handling,
- send current-turn image to OpenAI vision input,
- delete after provider request.

## Task 7 — Dynamic chat UI

**Rewrite:**
- `panel/templates/luna.html`
- `panel/static/luna-assistant.js`

**Create/extend:**
- `panel/static/newsroom-v4-luna.css`

**UX:**
- full-width chat,
- pinned composer,
- mic/image/send controls,
- immediate user bubble,
- Luna working indicator,
- streamed/near-streamed assistant text,
- tool cards,
- confirmation cards,
- clickable story/source references,
- retry state,
- mobile safe-area support,
- no canned sample-command panel.

## Task 8 — Builder mode for module/panel changes

**Create:**
- `panel/luna_builder.py`
- `panel/github_builder.py`

**Environment:**
- `LUNA_GITHUB_TOKEN`
- optional `LUNA_GITHUB_REPOSITORY` defaulting to this repository
- `LUNA_BUILDER_BASE_BRANCH=production`

**Builder workflow:**
1. Detect code-change intent (`ماژول اضافه کن`, `پنل بساز`, `این بخش UI رو حذف کن`, etc.).
2. Summarize requested change and request confirmation to start a code change.
3. Create dedicated branch `luna/change-<timestamp>-<slug>`.
4. Inspect only repository files needed for the request.
5. Generate tests before implementation edits.
6. Commit test change, then implementation change(s).
7. Open a draft PR and poll/read CI checks.
8. Report changed files + checks + preview state in Luna chat.
9. Require explicit confirmation before ready/merge/deploy.
10. Never deploy when checks are red or unknown.
11. Store the production SHA as rollback reference.

**Security:** no direct production checkout edits; no shell tool; token never enters model context.

## Task 9 — Visual redesign and typography

**Modify:**
- `panel/templates/base.html`
- `panel/templates/dashboard.html`
- `panel/templates/intake.html`
- `panel/templates/review_queue.html`
- `panel/templates/history.html`
- `panel/templates/source_manager.html`
- `panel/templates/settings_v4.html`
- `panel/templates/system_health.html`
- `panel/static/newsroom-v4.css`

**Typography:** use a reliably loaded Persian webfont where licensing/distribution permits; otherwise use a high-quality system-safe Persian stack and do not declare an unavailable font. Font assets must never be exposed outside normal app serving/distribution rules.

**Layout:** reduce decorative KPIs, denser story cards, better line-height/contrast, fewer buttons, one primary action per card, responsive desktop/mobile hierarchy.

## Task 10 — Air Traffic UI/cache removal

**Modify:**
- `panel/static/sw.js`
- any current V4 templates/static assets that still contain Air Traffic strings/links
- `panel/newsroom_api.py` only where panel snapshot exposes the module

**Do not delete:** independent backend Air Traffic service/runtime unless separately requested.

**Service worker:** increment cache version and cache only V4.1 assets. Navigation requests stay network-first/no-store.

## Task 11 — Settings/health usage display

**Modify:**
- `panel/templates/settings_v4.html`
- `panel/templates/system_health.html`
- `panel/v4.py`

Show:
- Luna connected/disconnected,
- today/month requests,
- input/output/cached tokens,
- estimated cost,
- fast/complex/transcription model names (no key),
- Builder connected/disconnected.

## Task 12 — Verification and rollout

**Focused tests:** run all new V4.1 tests.

**Full test suite:** `pytest -q`.

**Static checks:** existing workflow JS/Python syntax checks plus new V4.1 assets.

**PR:** keep draft until focused + full CI green.

**Deploy:** merge to target only after explicit user confirmation. Update VPS production checkout, install only changed dependencies if any, restart `bikhabar-panel.service`; restart agent only if durable block runtime code changed and requires reload.

**Post-deploy smoke:** login, dashboard, Luna text chat, translation, source confirmation, block confirmation, image analysis, voice transcription, Builder connectivity, no Air Traffic UI, service worker cache version, panel/agent health.
