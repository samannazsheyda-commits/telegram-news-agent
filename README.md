# Telegram News Agent

A zero-monthly-cost GitHub Actions bot for the Telegram channel `@bikhabaar`.

## What it publishes

Only Iran-related items are allowed through the news filter.

- Donald Trump Truth Social posts, only when the post text is directly about Iran / Hormuz / Tehran / IRGC / related Iran terms
- Iran-related reporting found through Google News RSS for:
  - Axios
  - Al Jazeera
  - Israel Channel 14 / now14.co.il
  - Marco Rubio
  - Mohammad Bagher Ghalibaf
  - Scott Bessent
  - J.D. Vance
  - Donald Trump
  - Strait of Hormuz tankers / shipping
- Iran free-market USD price every ~2 hours
- Iran 18k gold price every ~2 hours

All English news is translated to Persian on a best-effort, no-key translation endpoint. If translation is temporarily unavailable, the original text is still sent so a story is not lost.

## Schedule

The GitHub Actions workflow runs every 5 minutes. News sources are checked each run. Market prices are posted only after at least two hours have passed since the last successful market post.

GitHub scheduled workflows can sometimes be delayed, so this is near-real-time rather than guaranteed instant delivery.

## Required GitHub Actions secrets

Create these under **Settings → Secrets and variables → Actions**:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` = `@bikhabaar`

Never commit the bot token into the repository.

## State / duplicate prevention

`state.json` stores:

- newest Truth Social post ID already examined
- recent news item keys already seen
- last successful market-send time

On first run, old news is only recorded as the starting point and is not flooded into the channel. The market snapshot is sent immediately. After that, only new items are published.

## Run tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
