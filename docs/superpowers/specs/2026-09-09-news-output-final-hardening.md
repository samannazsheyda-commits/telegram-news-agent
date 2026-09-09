# بی‌خبر — final newsroom hardening

Goal: make production publication strict, Persian-only, relevant-only, deduplicated, and complete the operational newsroom panel without requiring further approvals.

## Publication contract
- Publish only: war/direct military action, missiles from Iran to outside, missiles toward Iran, Strait of Hormuz, sanctions, ships/tankers/warships, explosions, FX/currency, gold.
- Reject questions, explainers, analysis, opinion, articles, teasers, and unrelated politics/company/lifestyle content.
- Final Telegram output must be Persian. English source text may remain only in editor/panel detail views.
- One event should produce one post unless there is a material factual update.
- Emergency/manual broadcast paths must not race the VPS runtime.

## Reliability
- Runtime is the sole automatic news publisher.
- Dedup works both by exact source identity and event-level normalized claim similarity.
- Translation must fail closed: no publish if Persian quality gate fails.
- Panel shows real command results, real health, collapsible module previews, final Telegram preview, edit/delete/review actions, and fast new-item ding.
- Telegram editor bot consumes the same queue/result contract as the panel and never bypasses validation/dedup.

## Verification
- Regression tests for whitelist relevance, question/article rejection, Persian-only publish, flag/boilerplate-insensitive dedup, no duplicate automatic publisher, panel command/result flow, and editor bot actions.
- Full pytest and CI must pass before production promotion.
