# Discord Event Bot

## Overview
This is a Discord bot for creating and managing game events. It was imported from GitHub and configured to run in the Replit environment.

**Bot Name:** Bocik#5227  
**Language:** Python 3.11  
**Database:** SQLite (local file-based storage)  
**Status:** Running and operational

## Features
- Create events with `/event` command
- Join/leave events via interactive buttons
- Admin panel for event creators (close registrations, delete events)
- Participant limits
- Persistent storage with SQLite
- Event reminders (if time provided in ISO format: YYYY-MM-DDTHH:MM)

## Project Structure
- `main.py` - Main bot logic, slash commands, and event handlers
- `database.py` - Database initialization and schema
- `event_system.py` - Event management functions (CRUD operations)
- `events.db` - SQLite database (auto-created on first run)
- `requirements.txt` - Python dependencies

## Recent Changes (December 1, 2025)
1. Installed Python 3.11 and dependencies (discord.py, python-dotenv)
2. Fixed privileged intents issue by removing unnecessary `message_content` and `members` intents
3. Fixed SQL syntax error by renaming `limit` column to `participant_limit` (limit is a reserved keyword in SQLite)
4. Configured workflow to run the bot with console output
5. Added .gitignore for Python project

## Configuration
- **DISCORD_TOKEN**: Secret stored in Replit Secrets (required for bot authentication)
- **Workflow**: "Discord Bot" running `python main.py` with console output

## Discord Slash Commands
- `/event` - Create a new event
  - Parameters: name, time (optional), category (optional), limit (optional)
- `/uczestnicy` - Show participants for a specific event (by message ID)

## Database Schema
**events table:**
- id (PRIMARY KEY)
- message_id (UNIQUE) - Discord message ID
- name - Event name
- time - Event time (ISO format string)
- category - Event category
- participant_limit - Maximum number of participants
- author_id - Discord user ID of event creator
- closed - Boolean flag (0 = open, 1 = closed)

**participants table:**
- event_id - Foreign key to events.id
- user_id - Discord user ID

## Notes
- The bot uses default Discord intents (no privileged intents required)
- SQLite database file is excluded from git via .gitignore
- Voice support is not available (PyNaCl not installed)
- Event reminders are scheduled if time is provided in ISO format
