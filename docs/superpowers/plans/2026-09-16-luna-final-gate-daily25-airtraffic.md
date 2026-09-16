# Luna Final Gate, Daily-25 and Air-Traffic Implementation Plan

> Approved 2026-09-16. Execute with TDD and verify through GitHub Actions before merge.

## Goal

Newsroom V3 must publish only concise, factual, non-duplicate event updates; cap public news at 25 items per Tehran day; use 1xAI GPT-5.6 Luna as the final fail-closed pre-publish judge; preserve exact source identity (including `Clash Report`); and publish a fresh air-traffic snapshot once daily at 00:00 Tehran without reusing the prior image.

## Task 1 — Regression tests first

Create `tests/test_newsroom_v3_final_gate.py` covering:
- Luna approval allows one Telegram write.
- Luna rejection prevents Telegram write and marks the story rejected so it cannot block later cycles.
- Luna/API error fails closed and prevents Telegram write.
- a candidate judged duplicate of recent published context is rejected.
- after 25 successful V3 publications in the current Tehran day, the next cycle returns `daily_limit` and does not call Luna or Telegram.
- a new Tehran day resets the count.

Create `tests/test_newsroom_source_identity.py` covering exact canonical preservation of `Clash Report`.

Extend `tests/test_air_traffic.py` covering:
- timer has exactly one schedule: 00:00 Tehran / 20:30 UTC.
- identical rendered image digest to the last published snapshot is refused before Telegram send.
- a fresh digest publishes and persists the new digest.

Run the PR checks at this point and confirm the new tests fail for the expected missing behavior before implementation.

## Task 2 — Final Luna pre-publish gate

Create `src/newsroom_v3/final_gate.py`:
- `FinalGateDecision(approved, reason)` dataclass.
- `LunaFinalPublishGate` backed directly by `OneXAINewsAI` / `OneXAIConfig`.
- Send candidate title, summary, exact source, URL and recent-published context.
- Require JSON with `approve` boolean and a short `reason`.
- System rules explicitly reject article/analysis/report/opinion, question/teaser/incomplete items, and materially duplicate updates.
- Any missing key, invalid response, unavailable Luna, timeout, or provider error returns a rejection (`fail closed`).
- Never log or expose the API key.

Modify `src/newsroom_v3/production.py`:
- accept an injectable final-gate callable for tests.
- immediately before creating a publish attempt, run the final gate.
- on rejection, set the story decision to `rejected` with `final_gate:<reason>` and return without Telegram write.
- pass recent published stories to the gate so Luna can detect semantically repeated events.

## Task 3 — Tehran daily hard cap of 25

Modify `src/newsroom_v3/store.py`:
- add a query for successful V3 publications in a UTC interval.
- add a query for recent successfully published stories.

Modify `src/newsroom_v3/production.py`:
- default `NEWSROOM_V3_DAILY_LIMIT=25`.
- compute Tehran local midnight boundaries with `ZoneInfo("Asia/Tehran")` and convert to UTC.
- before selecting/calling Luna, stop with `reason="daily_limit"` when successful publications for that Tehran day are already at the limit.
- include `daily_published` and `daily_limit` in production status for panel/ops visibility.

Update `deploy/agent.env.example` with `NEWSROOM_V3_DAILY_LIMIT=25`.

## Task 4 — Deterministic editorial hard filters and source identity

Keep existing deterministic V3 intake filtering before AI and strengthen only where needed in `src/newsroom_eligibility.py` so obvious long-form/report/opinion/question/teaser formats never spend a Luna call.

Modify `src/sources.py` to include canonical `Clash Report` and its known literal aliases while preserving the canonical spelling exactly.

Run editorial/source tests plus all V3 tests.

## Task 5 — Air traffic at midnight only, fresh image only

Modify `deploy/bikhabar-air-traffic.timer`:
- keep a single daily `OnCalendar=*-*-* 20:30:00 UTC` entry (00:00 Tehran).
- update unit description accordingly.

Modify `src/air_traffic.py`:
- hash the completed output bytes with SHA-256 before send.
- persist the last successfully published image digest in the runtime/state directory (configurable for tests).
- if the new digest equals the last successful digest, raise/skip before Telegram send.
- only persist a digest after Telegram reports success, so a failed send does not suppress a later retry.

Update `tests/test_air_traffic.py` accordingly.

## Task 6 — Verification and delivery

Run/verify:
- focused final-gate/daily-limit/source/air-traffic tests.
- full project PR checks.
- inspect the PR diff for secret leakage and unintended legacy behavior.
- merge only after all required checks are green.
- verify `production` is promoted to the merge SHA.

Only after all of the above is complete report to the user that the repository/production work is finished. VPS live deployment must be reported separately unless server deployment is independently verified.