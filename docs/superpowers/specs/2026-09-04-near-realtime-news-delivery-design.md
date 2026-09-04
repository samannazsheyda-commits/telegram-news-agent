# Near-Realtime News Delivery Design

## Goal

Change the Telegram news agent so newly discoverable important Iran-related news is delivered close to when the source becomes visible to the bot, instead of arriving in large batches followed by long quiet gaps.

At the same time, normal news posts should stay concise but become more complete: a clear headline plus one short, useful explanatory sentence when the source provides enough information.

## Current behavior

The repository currently uses GitHub Actions with a scheduled workflow. Each workflow run starts the Python agent, fetches many feeds, posts up to a batch of selected stories, persists state, and exits. This naturally causes bursty delivery: multiple stories can arrive together, then nothing is sent until the next workflow run.

The current agent also caps normal news at `MAX_NEWS_PER_RUN = 8`, which is useful for batch execution but is not the right delivery model for near-realtime monitoring.

## Desired behavior

1. The agent continuously polls sources with a target cadence of about one minute while the runtime is alive.
2. A story that becomes newly visible and passes the existing freshness, Iran relevance, importance, translation, and duplicate checks is sent on that polling cycle rather than waiting for a later batch window.
3. Several stories discovered in the same poll may still be posted close together, because they genuinely became visible together; the system must not intentionally hold a breaking story merely to make the channel look evenly spaced.
4. Military/security events such as missile launches, drone attacks, strikes, explosions, air-defense activity, airspace closures, Hormuz incidents, and similar high-priority events remain highest priority.
5. Truth Social monitoring remains Iran-related only. Direct Truth Social fetch is attempted first; the existing independent archive RSS fallback remains available when the direct endpoint is inaccessible.
6. X-based monitors remain best-effort through public indexing because the project does not have a stable zero-cost direct X API.
7. No claim of zero-second latency is made. The delivery target is approximately one minute after a source becomes visible to the bot; upstream feeds/search indexes may themselves be delayed.

## Post completeness

Normal news output should be:

- one complete, understandable Persian headline;
- at most one short explanatory sentence with the most useful non-redundant fact available from the source summary;
- timestamp;
- source link;
- the existing `بی‌خبر` footer.

The explanatory sentence must not merely repeat the headline. If no useful non-redundant detail is available, the headline may stand alone rather than inventing context.

## Scheduling architecture

The existing one-shot `run()` logic should be separated from the process lifecycle:

- one polling iteration performs the existing fetch/filter/send/state work;
- a long-running loop invokes that iteration approximately every 60 seconds;
- market delivery keeps its existing two-hour interval and Tehran quiet-hours rules even though the news polling loop runs more frequently;
- state is saved after successful sends exactly as needed to prevent duplicates across iterations and restarts.

The GitHub Actions workflow must be adjusted to support the long-running polling model within GitHub Actions runtime limits. Because GitHub-hosted jobs are not permanent daemons, the workflow should run the loop for a bounded session and restart automatically on a schedule before the prior session can age out. Manual dispatch must remain available.

The implementation must avoid overlapping active sessions where possible. If overlap occurs because of scheduler delay, persisted duplicate state must prevent duplicate Telegram posts.

## Filtering and prioritization

Existing rules remain unless explicitly changed by a later approved task:

- same Tehran calendar-day freshness rule;
- important-news-only policy;
- approved-source restrictions;
- semantic duplicate suppression;
- speaker/interview deduplication;
- source names displayed in Persian;
- natural Persian translation only when translation succeeds;
- no routine tanker traffic;
- no market messages between 00:00 and 07:59 Tehran;
- military/security news has priority over ordinary political statements.

`MAX_NEWS_PER_RUN` must not cause a newly discovered high-priority breaking event to wait for a later multi-minute batch. The near-realtime flow should process newly eligible stories from each poll while retaining duplicate and quality controls.

## Failure behavior

A failed source fetch must not crash the whole monitoring session if other sources can still be processed. Existing source-level or section-level exception handling should be preserved or tightened so one transient network failure does not stop near-realtime monitoring.

If Telegram sending fails, state must not mark that item as successfully delivered until the send succeeds.

## Verification

Tests must cover at least:

- one polling iteration sends newly eligible news immediately;
- a second polling iteration does not resend the same story;
- a newly appearing missile/attack story on the next iteration is not blocked by an old per-run batch cap;
- market posts still respect the two-hour interval and Tehran quiet hours while polling every minute;
- richer formatting includes one useful non-redundant detail sentence and never more than one;
- a redundant summary is omitted;
- Truth Social Iran filtering remains intact;
- workflow configuration launches the bounded long-running monitor and keeps manual dispatch.

A fresh CI run must pass before the feature is described as complete.
