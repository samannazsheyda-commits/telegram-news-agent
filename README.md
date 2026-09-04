# Telegram News Agent

A zero-monthly-cost GitHub Actions bot that publishes:

- New Donald Trump Truth Social posts (Persian translation, best effort)
- Axios stories specifically related to Iran war/conflict
- Iran free-market USD and 18k gold prices about every two hours

## How it works

The workflow runs every 5 minutes. Truth Social and Axios are checked every run. TGJU is checked only when two hours have passed since the last successful market post. `state.json` stores the last Truth ID, Axios links already seen, and the last market-send time so posts are not duplicated.

On its first successful run, the bot **does not flood old Truth/Axios news**. It marks the currently visible news as the starting point and sends only the current market snapshot. After that, only new news is posted.

## Required GitHub secrets

The repository needs exactly two Actions secrets:

- `TELEGRAM_BOT_TOKEN` — token from Telegram @BotFather
- `TELEGRAM_CHAT_ID` — destination channel ID (for a public channel, `@channelusername` also works if the bot is an admin)

Do not commit the bot token to the repository.

## Telegram setup

Create a bot with @BotFather, add it as an administrator to the target channel, and grant permission to post messages. Then add the two values above as GitHub Actions secrets.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python -m src.main
```

## Reliability notes

- GitHub scheduled workflows are nominally every 5 minutes, but GitHub can delay scheduled jobs. It is not a guaranteed real-time service.
- Truth Social's Mastodon-compatible endpoint and Google's no-key translation endpoint are unofficial/best-effort and can change. A translation failure falls back to the original text rather than dropping the news.
- Price values are read from TGJU in rial and displayed in toman by dividing by 10.
