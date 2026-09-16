# TDD red: tolerate Luna JSON wrapped in short prose

Production evidence from the VPS on 2026-09-16 shows 1xAI Luna reached the air-traffic reporter but the shared strict decoder raised `AIServiceError: invalid_ai_json`. The final newsroom gate also recorded `luna_error` in the same period.

Expected fix scope:
- Keep the strict dict contract.
- Keep normal JSON and code-fenced JSON behavior unchanged.
- For 1xAI/Luna only, tolerate a short natural-language prefix/suffix around one valid JSON object.
- Reject responses with no JSON object, a non-object JSON value, or multiple top-level JSON objects.
- Do not change the OpenRouter decoder contract globally.
