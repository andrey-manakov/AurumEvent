# Tomorrow Planner Telegram Bot

A minimal Telegram bot built with Python and `pyTelegramBotAPI` for planning events with friends for tomorrow.

## Features

- Create tomorrow's events privately with `/new`.
- Invite friends using shareable deep links.
- Track RSVPs (`Yes`, `No`, `Maybe`) directly inside Telegram.
- List and manage your events via `/my`.
- Lightweight SQLite storage with automatic schema creation.

## Requirements

- Python 3.10+
- Telegram bot token from [@BotFather](https://t.me/BotFather)

## Installation

1. Clone the repository and enter the project directory:

   ```bash
   git clone <your-repo-url>
   cd AurumEvent
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment template and fill in your bot token:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `BOT_TOKEN` to the token you obtained from BotFather. Optionally adjust `DATABASE_PATH`.

## Database Schema

The SQLite database is created automatically on first launch with the following tables:

```sql
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    time TEXT NOT NULL,
    location TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rsvp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(event_id, user_id)
);
```

## Running the Bot Locally

```bash
python bot.py
```

The bot starts polling Telegram updates immediately. Make sure your `.env` file is configured before running.

## Deployment on RuVDS Ubuntu Server

1. SSH into your RuVDS instance.
2. Install system dependencies (Python 3.10+ and git).
3. Clone the repository:

   ```bash
   git clone <your-repo-url>
   cd AurumEvent
   ```

4. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

5. Configure environment variables:

   ```bash
   cp .env.example .env
   nano .env  # paste your BOT_TOKEN
   ```

6. Start the bot using `nohup` so it keeps running after you disconnect:

   ```bash
   nohup python bot.py > bot.log 2>&1 &
   ```

7. (Optional) Monitor the logs:

   ```bash
   tail -f bot.log
   ```

## Environment Variables

- `BOT_TOKEN` (required): Telegram bot token.
- `DATABASE_PATH` (optional): Path to the SQLite database file. Defaults to `events.db` in the project root.

## License

This project is provided as-is without warranty.
