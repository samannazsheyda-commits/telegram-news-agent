# TDD red phase

The new regression tests intentionally reference behavior that does not exist on the base branch yet:

- `src.newsroom_v3.final_gate.FinalGateDecision`
- `run_once(..., final_gate=..., daily_limit=...)`
- daily V3 publish counting/recent published context
- canonical `Clash Report`
- air-traffic midnight-only timer
- air-traffic snapshot digest helpers
- `Report:` hard editorial rejection

The feature implementation should make these tests green without weakening existing safety tests.