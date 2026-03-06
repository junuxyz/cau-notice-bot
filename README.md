# CAU Notice Bot v0.2.0

<p align="center">
  <img src="cau_notice_bot_logo_v.0.2.0.png" width="280">
</p>

Chung-Ang University notice alert Discord bot

---

## What it does

Sends new notices from the past 24 hours to one or more Discord channels every day at 8 AM KST

**Sources**
- 📢 **CAU Official Notices**
- 📚 **Library Notices**
- 🌈 **Rainbow System Links**

## How it works

```
GitHub Actions (Daily 08:00 KST)
    ↓
Fetch CAU API → Check new notices
    ↓
Send alerts via Discord Webhook
```

## Environment

```env
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432
```

- `DISCORD_CHANNEL_IDS` is the preferred format (comma-separated).
- `DISCORD_CHANNEL_ID` is still supported as a legacy fallback.

## Development

```bash
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint check
uv run ruff check .

# Auto-fix lint issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Run bot
uv run python -m src.main
```

