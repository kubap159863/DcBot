# Deploying to Railway

1. Create a new project on Railway and connect your GitHub repo (or deploy from a repository ZIP).
2. In Railway project settings -> Variables, add DISCORD_TOKEN with your bot token.
3. Railway will detect `requirements.txt` and install dependencies.
4. The included `Procfile` runs `python main.py`.
5. Enable Auto Deploy if you want automatic redeploys on push.
