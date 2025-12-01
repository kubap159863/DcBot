import os
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord import app_commands
from database import init_db
from event_system import EventDB
from keep_alive import keep_alive
import requests
import threading
import time

keep_alive()

# Twój URL publiczny Replit
URL = "https://31e7fb2e-3e30-491f-9f7c-d592f10e4555-00-2dcwfi9zggevo.kirk.replit.dev"


# Funkcja pingująca Twój własny URL co 5 minut
def self_ping():
    while True:
        try:
            requests.get(URL)
            print("✅ Pinged self successfully")
        except Exception as e:
            print("❌ Ping failed:", e)
        time.sleep(2 * 60)  # co 5 minut


# Uruchamiamy ping w osobnym wątku, żeby nie blokował bota
threading.Thread(target=self_ping).start()

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError('DISCORD_TOKEN not set in environment')

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()

bot = commands.Bot(command_prefix='!', intents=intents)

REMINDER_MINUTES_BEFORE = 15  # default reminder before event if time provided


@bot.event
async def on_ready():
    init_db()
    logging.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await bot.tree.sync()
    logging.info('Slash commands synced.')
    schedule_existing_events.start()


# ---------- UI ----------
class EventView(discord.ui.View):

    def __init__(self, message_id, author_id):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.author_id = author_id

    @discord.ui.button(label='Wezmę udział', style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        success, reason = EventDB.add_participant(self.message_id,
                                                  interaction.user.id)
        if success:
            await interaction.response.send_message('✔️ Zapisano!',
                                                    ephemeral=True)
            await refresh_message(interaction.channel, self.message_id)
        else:
            if reason == 'already':
                await interaction.response.send_message(
                    '❗ Już jesteś zapisany.', ephemeral=True)
            elif reason == 'full':
                await interaction.response.send_message(
                    '❌ Brak wolnych miejsc.', ephemeral=True)
            elif reason == 'closed':
                await interaction.response.send_message(
                    '🔒 Zapisy są zamknięte.', ephemeral=True)
            else:
                await interaction.response.send_message('⚠️ Błąd zapisu.',
                                                        ephemeral=True)

    @discord.ui.button(label='Jednak nie', style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        ok = EventDB.remove_participant(self.message_id, interaction.user.id)
        if ok:
            await interaction.response.send_message('❌ Usunięto z listy.',
                                                    ephemeral=True)
            await refresh_message(interaction.channel, self.message_id)
        else:
            await interaction.response.send_message('⚠️ Błąd.', ephemeral=True)


class AdminView(discord.ui.View):

    def __init__(self, message_id, author_id):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.author_id = author_id

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                '⛔ Tylko twórca wydarzenia może użyć.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Zamknij zapisy',
                       style=discord.ButtonStyle.primary)
    async def close(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        EventDB.close_event(self.message_id)
        await interaction.response.send_message('🔒 Zapisy zamknięte.',
                                                ephemeral=True)
        await refresh_message(interaction.channel, self.message_id)

    @discord.ui.button(label='Usuń wydarzenie',
                       style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        EventDB.delete_event_by_message(self.message_id)
        # delete both messages if possible
        try:
            msg = await interaction.channel.fetch_message(self.message_id)
            await msg.delete()
        except Exception:
            pass
        await interaction.response.send_message('🗑️ Wydarzenie usunięte.',
                                                ephemeral=True)


# ---------- Helpers ----------
async def refresh_message(channel, message_id):
    row = EventDB.get_event_by_message(message_id)
    if not row:
        return
    _, msg_id, name, time, category, limit, author_id, closed = row
    participants = EventDB.get_participants(message_id)
    if participants:
        part_lines = '\n'.join(f'• <@{u}>' for u in participants)
    else:
        part_lines = 'Brak zapisanych.'
    title = f'🎮 {name}'
    desc = f'📅 **{time or "—"}**\n📂 **{category or "—"}**\n\n👥 **Uczestnicy ({len(participants)}/{limit or "∞"}):**\n' + part_lines
    embed = discord.Embed(title=title,
                          description=desc,
                          color=discord.Color.blue())
    view = EventView(message_id, author_id)
    admin_view = AdminView(message_id, author_id)
    try:
        msg = await channel.fetch_message(message_id)
        await msg.edit(embed=embed, view=view)
        # send or edit admin panel below message (create a companion message id scheme)
        # for simplicity, try to edit a message just after (not guaranteed). We'll skip editing admin companion to keep logic simple.
    except Exception as e:
        logging.warning('Could not refresh message: %s', e)


# ---------- Scheduling ----------
scheduled_tasks = {}


def parse_iso(dt_str):
    try:
        # Accept 'YYYY-MM-DDTHH:MM' or 'YYYY-MM-DD HH:MM'
        dt_str = dt_str.replace(' ', 'T')
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


async def schedule_reminder(channel, message_id, when_dt):
    now = datetime.utcnow()
    # assume provided datetime is in local server time — convert if needed
    delay = (when_dt - now).total_seconds()
    if delay <= 0:
        return
    # if reminder > 3600*24*30, skip scheduling now
    await asyncio.sleep(delay - REMINDER_MINUTES_BEFORE *
                        60 if delay > REMINDER_MINUTES_BEFORE * 60 else delay)
    # send reminder
    try:
        msg = await channel.fetch_message(message_id)
        row = EventDB.get_event_by_message(message_id)
        if not row:
            return
        _, _, name, time, category, limit, author_id, closed = row
        participants = EventDB.get_participants(message_id)
        pmentions = ', '.join(f'<@{u}>'
                              for u in participants) or 'Brak zapisanych'
        await channel.send(
            f'⏰ Przypomnienie: Wydarzenie **{name}** zaczyna się za {REMINDER_MINUTES_BEFORE} minut. Uczestnicy: {pmentions}'
        )
    except Exception as e:
        logging.warning('Failed reminder: %s', e)


@tasks.loop(minutes=10)
async def schedule_existing_events():
    # scan DB for events with future times and schedule reminders if not scheduled
    conn_sched = None
    try:
        import sqlite3
        from pathlib import Path
        DB_PATH = Path(__file__).parent / 'events.db'
        conn_sched = sqlite3.connect(DB_PATH)
        c = conn_sched.cursor()
        c.execute(
            "SELECT message_id, time FROM events WHERE closed = 0 AND time IS NOT NULL AND time != ''"
        )
        rows = c.fetchall()
        for message_id, time_str in rows:
            if message_id in scheduled_tasks:
                continue
            dt = None
            try:
                dt = parse_iso(time_str)
            except Exception:
                dt = None
            if dt:
                # find the channel where message exists by searching across guilds (costly but acceptable)
                for guild in bot.guilds:
                    for channel in guild.text_channels:
                        try:
                            msg = await channel.fetch_message(message_id)
                            # schedule task
                            task = asyncio.create_task(
                                schedule_reminder(channel, message_id, dt))
                            scheduled_tasks[message_id] = task
                            raise StopIteration
                        except discord.NotFound:
                            continue
                        except Exception:
                            continue
    except StopIteration:
        pass
    except Exception as e:
        logging.warning('schedule_existing_events failed: %s', e)
    finally:
        if conn_sched:
            conn_sched.close()


# ---------- Slash commands ----------
@bot.tree.command(name='event', description='Utwórz wydarzenie')
@app_commands.describe(name='Nazwa wydarzenia',
                       time='Czas (ISO: YYYY-MM-DDTHH:MM lub pusty)',
                       category='Kategoria',
                       limit='Limit miejsc (0 = brak limitu)')
async def cmd_event(interaction: discord.Interaction,
                    name: str,
                    time: str = None,
                    category: str = None,
                    limit: int = 0):
    # create embed and send message
    limit_val = limit if limit > 0 else None
    embed = discord.Embed(
        title=f'🎮 {name}',
        description=
        f'📅 **{time or "—"}**\n📂 **{category or "—"}**\n\nKliknij przycisk, aby zapisać się.',
        color=discord.Color.blue())
    sent = await interaction.channel.send(embed=embed)
    # store in DB
    EventDB.create_event(sent.id, name, time or '', category or '', limit_val,
                         interaction.user.id)
    # create companion admin message
    admin_msg = await interaction.channel.send(
        f'🔧 Panel administracyjny dla wydarzenia `{sent.id}`. (Twórca: <@{interaction.user.id}>)',
        view=AdminView(sent.id, interaction.user.id))
    # attach view to the event message
    await sent.edit(view=EventView(sent.id, interaction.user.id))
    # schedule reminder if time parseable
    if time:
        dt = parse_iso(time)
        if dt:
            # schedule a reminder task
            task = asyncio.create_task(
                schedule_reminder(interaction.channel, sent.id, dt))
            scheduled_tasks[sent.id] = task
    await interaction.response.send_message(
        f'✔️ Wydarzenie utworzone (ID: {sent.id})', ephemeral=True)


@bot.tree.command(
    name='uczestnicy',
    description='Pokaż uczestników (po ID wiadomości z wydarzeniem)')
@app_commands.describe(message_id='ID wiadomości z wydarzeniem')
async def cmd_participants(interaction: discord.Interaction, message_id: str):
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message('Nieprawidłowe ID.',
                                                ephemeral=True)
        return
    users = EventDB.get_participants(mid)
    if not users:
        await interaction.response.send_message('Brak zapisanych uczestników.')
        return
    mention_list = '\n'.join(f'<@{u}>' for u in users)
    await interaction.response.send_message(f'Uczestnicy:\n{mention_list}')


if __name__ == '__main__':
    bot.run(TOKEN)
