# Discord Event Bot (Advanced)

Ready-to-deploy Discord bot for creating and managing game events.

Features:
- Create events with `/event name time category limit`
- Join/leave via buttons
- Admin panel (close/delete)
- Participant limits
- Persistent storage with SQLite
- Reminders scheduled if event time is provided in ISO format (YYYY-MM-DDTHH:MM)

⚠️ IMPORTANT: Do **not** put your Discord token in code. Use environment variables (`DISCORD_TOKEN`).

## Quickstart (local)
1. Create a virtualenv and activate it:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux / macOS
   .\.venv\Scripts\activate  # Windows (PowerShell)
   ```
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` -> `.env` and fill `DISCORD_TOKEN`.
4. Initialize DB (first run will auto-init). Then run:
   ```bash
   python main.py
   ```

## Deploy to Railway
1. Create new project on https://railway.app and link a GitHub repo or upload this project.
2. Add environment variable `DISCORD_TOKEN` in Railway project settings.
3. Use `Procfile` and `requirements.txt` included.

## Create GitHub repo and push
```bash
git init
git add .
git commit -m "Initial commit - Discord Event Bot"
# create a repo on GitHub via website, then:
git remote add origin https://github.com/<you>/<repo>.git
git branch -M main
git push -u origin main
```
