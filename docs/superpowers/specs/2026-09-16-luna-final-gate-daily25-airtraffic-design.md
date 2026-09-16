# Bikhabar — Luna final gate, daily 25, and fresh air-traffic design

Date: 2026-09-16

## Goal

Make Newsroom V3 publish a maximum/target of 25 genuinely distinct breaking-news events per Tehran day, with Luna as the final editorial judge. Articles, analysis, long-form reports, question/teaser items, and repeated coverage of the same event must not publish. Air-traffic reporting must use a fresh nightly capture and must never repost the same image as a new update.

## Editorial pipeline

1. Raw intake remains unchanged and continues using the existing configured sources/topics.
2. Cheap deterministic hard filters run first. They reject article/commentary/opinion/explainer/reportage/liveblog/teaser/question-style items and clearly off-topic candidates.
3. Existing deterministic dedup runs before AI and removes exact/near-exact repeats.
4. Only surviving candidates are sent to Luna for a final structured judgement.
5. Luna returns a strict JSON decision: `PUBLISH` or `REJECT`, plus one reason code. Supported rejection reasons include `ARTICLE`, `REPORTAGE`, `QUESTION_OR_TEASER`, `NOT_BREAKING`, `OFF_TOPIC`, `DUPLICATE`, `LOW_SIGNAL`, and `INVALID`.
6. For semantic duplicate judgement, Luna receives only a compact set of the nearest recent published/accepted events, not the entire archive.
7. Luna is authoritative at this final gate. If Luna is unavailable or returns invalid output, the candidate is deferred/rejected for that cycle; the system does not silently bypass the final AI gate and publish anyway.
8. Only a candidate approved by every prior gate and by Luna can reach the Telegram publisher.

## Daily publication rule

- Tehran timezone is authoritative for daily counting.
- Hard cap: 25 news posts per Tehran calendar day. A 26th news post is never allowed.
- Target: 25 valid news posts when enough qualifying unique breaking events exist.
- Quality beats quota: the system must not publish an article, duplicate, weak/non-breaking item, or off-topic item merely to fill the daily target.
- Count only confirmed successful news publications, not failed attempts or rejected candidates.
- Non-news scheduled utilities such as the air-traffic card are tracked separately and do not consume one of the 25 news slots.

## Uniqueness

A different source, wording, or headline does not make an event new. Multiple reports about the same underlying event count as one event. A materially new development may publish as a separate event only when the factual event state has changed, not merely because another outlet repeated it.

## Source identity

The publisher must preserve the normalized source identity. In particular, content originating from Clash Report must display the source as `Clash Report`, not a generic/derived label.

## Hard content exclusions

At minimum, reject before publication:

- articles, columns, opinion and commentary;
- analysis and explainers;
- long-form reportage/feature reports without a new breaking event;
- question headlines;
- teaser/promotional phrasing such as “stay with us”, “live updates to follow”, or “X reports” when it does not itself state a new event;
- duplicate/repackaged coverage of a previously published event;
- candidates outside the configured Bikhabar topics/priority terms.

The existing configured priority terms/settings remain the source of truth rather than introducing a second conflicting keyword list.

## Luna request shape

Luna receives a compact payload containing the candidate headline/summary/source/time, current configured topic terms, and a small nearest-neighbour list of recent events when available. The prompt explicitly asks for factual event classification only and forbids rewriting the article. The response is machine-validated JSON with decision/reason/confidence/event fingerprint summary. No free-form response may authorize publication.

## Air traffic at 00:00 Tehran

- Run the air-traffic publication job once nightly at 00:00 Asia/Tehran.
- Fetch/capture a fresh image from the real live source used by the project; do not generate a fictional traffic image.
- Compute and persist a content hash for the image. If it matches the last successfully published air-traffic image, do not repost it as a fresh update.
- Build the caption from fresh traffic data/image metadata using the previously established Bikhabar format. Luna may word/summarize the caption from fresh factual inputs, but must not invent aircraft counts, routes, closures, or incidents.
- If a fresh capture cannot be obtained, fail safely and publish nothing rather than recycling the previous image.

## Observability

Persist/log the final gate decision and reason without storing secrets. Production status should expose useful counters/reasons such as daily published count, remaining daily slots, Luna rejections, hard-filter rejections, dedup rejections, and daily-limit stop.

## Performance and cost

Luna is intentionally placed after hard filtering and deterministic dedup so only plausible final candidates incur an AI request. Repeated candidates should reuse local dedup/cache state and must not be re-judged unnecessarily within the same event lifecycle.

## Testing / acceptance

Automated tests must prove:

1. a 26th successful news publication is blocked in Tehran time;
2. the daily count resets at Tehran midnight;
3. failed publish attempts do not consume a daily slot;
4. article/analysis/question/teaser fixtures are rejected before publisher invocation;
5. duplicate events from different sources do not both publish;
6. Luna `REJECT` prevents publication and the reason is recorded;
7. Luna failure/invalid JSON fails closed;
8. Luna `PUBLISH` can proceed only when all other gates pass;
9. `Clash Report` source identity is preserved;
10. identical air-traffic image bytes are not reposted;
11. a fresh air-traffic image can publish and its hash is persisted only after success;
12. nightly scheduling is expressed in Tehran local time.

## Out of scope for this change

The web-panel visual redesign and bottom-tab performance work are a separate change/PR so editorial safety and production publication policy can be tested and rolled out independently.