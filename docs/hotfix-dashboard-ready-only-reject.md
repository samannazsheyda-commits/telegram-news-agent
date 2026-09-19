# Dashboard ready-only / reject-only hotfix

This hotfix locks two operator-facing contracts:

- An active Dashboard card is rendered only after a Persian machine/source copy is ready. Pending localization remains internal and never appears as a placeholder card.
- Rejecting a story uses the existing newsroom reject endpoint and records a normal rejected decision. The Dashboard does not expose the permanent block action.

Luna remains optional. Its publish button stays disabled until a Luna final copy is ready.
