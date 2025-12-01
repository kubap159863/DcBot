import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from database import init_db
from event_system import EventDB
from keep_alive import keep_alive

keep_alive()
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError('DISCORD_TOKEN not set in environment')

TICKETS_CATEGORY_NAME = os.getenv('TICKETS_CATEGORY_NAME', 'TICKETY')
TICKETS_ADMIN_ROLE = os.getenv('TICKETS_ADMIN_ROLE', 'Moderator')  # rola admina

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
REMINDER_MINUTES_BEFORE = 15  # przypomnienia przed wydarzeniem w minutach

# ---------- Ticket UI ----------

class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Otwórz ticket',
                       style=discord.ButtonStyle.primary,
                       emoji='📩',
                       custom_id='open_ticket_button')
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        author = interaction.user
        category = discord.utils.get(guild.categories, name=TICKETS_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKETS_CATEGORY_NAME)

        name = f"ticket-{author.name.lower()}-{author.discriminator}"
        existing = discord.utils.get(category.text_channels, name=name)
        if existing:
            await interaction.response.send_message(f'Masz już otwarty ticket: {existing.mention}', ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            author: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        admin_role = discord.utils.get(guild.roles, name=TICKETS_ADMIN_ROLE)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        panel = TicketPanel(author.id)
        await channel.send(f'Witaj {author.mention}! Napisz tutaj swój problem — moderatorzy wkrótce się pojawią.', view=panel)
        await interaction.response.send_message(f'Ticket utworzony: {channel.mention}', ephemeral=True)

class TicketPanel(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.claimed_by = None

    async def check_admin(self, interaction):
        if interaction.user.id == self.owner_id:
            return True
        admin_role = discord.utils.get(interaction.guild.roles, name=TICKETS_ADMIN_ROLE)
        if admin_role and admin_role in interaction.user.roles:
            return True
        await interaction.response.send_message('Brak uprawnień.', ephemeral=True)
        return False

    @discord.ui.button(label='Zamknij ticket', style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        await interaction.response.send_message('Zamykanie ticketu za 5s...')
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label='Claim', style=discord.ButtonStyle.secondary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        self.claimed_by = interaction.user.id
        await interaction.response.send_message(f'Ticket przejęty przez {interaction.user.mention}', ephemeral=False)

# ---------- Event system ----------

class EventView(discord.ui.View):
    def __init__(self, message_id, author_id):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.author_id = author_id

    @discord.ui.button(label='Wezmę udział', style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, reason = EventDB.add_participant(self.message_id, interaction.user.id)
        if success:
            await interaction.response.send_message('✔️ Zapisano!', ephemeral=True)
            await refresh_message(interaction.channel, self.message_id)
        else:
            if reason == 'already':
                await interaction.response.send_message('❗ Już jesteś zapisany.', ephemeral=True)
            elif reason == 'full':
                await interaction.response.send_message('❌ Brak wolnych miejsc.', ephemeral=True)
            elif reason == 'closed':
                await interaction.response.send_message('🔒 Zapisy są zamknięte.', ephemeral=True)
            else:
                await interaction.response.send_message('⚠️ Błąd zapisu.', ephemeral=True)

    @discord.ui.button(label='Jednak nie', style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok = EventDB.remove_participant(self.message_id, interaction.user.id)
        if ok:
            await interaction.response.send_message('❌ Usunięto z listy.', ephemeral=True)
            await refresh_message(interaction.channel, self.message_id)
        else:
            await interaction.response.send_message('⚠️ Błąd.', ephemeral=True)

class AdminView(discord.ui.View):
    def __init__(self, message_id, author_id):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message('⛔ Tylko twórca wydarzenia może użyć.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Zamknij zapisy', style=discord.ButtonStyle.primary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        EventDB.close_event(self.message_id)
        await interaction.response.send_message('🔒 Zapisy zamknięte.', ephemeral=True)
        await refresh_message(interaction.channel, self.message_id)

    @discord.ui.button(label='Usuń wydarzenie', style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        EventDB.delete_event_by_message(self.message_id)
        try:
            msg = await interaction.channel.fetch_message(self.message_id)
            await msg.delete()
        except Exception:
            pass
        await interaction.response.send_message('🗑️ Wydarzenie usunięte.', ephemeral=True)

# ---------- Helpers ----------

async def refresh_message(channel, message_id):
    row = EventDB.get_event_by_message(message_id)
    if not row:
        return
    _, msg_id, name, time, category, limit, author_id, closed = row
    participants = EventDB.get_participants(message_id)
    part_lines = '\n'.join(f'• <@{u}>' for u in participants) if participants else 'Brak zapisanych.'
    desc = f'📅 **{time or "—"}**\n📂 **{category or "—"}**\n\n👥 **Uczestnicy ({len(participants)}/{limit or "∞"}):**\n' + part_lines
    embed = discord.Embed(title=f'🎮 {name}', description=desc, color=discord.Color.blue())
    view = EventView(message_id, author_id)
    try:
        msg = await channel.fetch_message(message_id)
        await msg.edit(embed=embed, view=view)
    except Exception as e:
        logging.warning('Could not refresh message: %s', e)

# ---------- Scheduling ----------

scheduled_tasks = {}

def parse_iso(dt_str):
    try:
        dt_str = dt_str.replace(' ', 'T')
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

async def schedule_reminder(channel, message_id, when_dt):
    now = datetime.utcnow()
    delay = (when_dt - now).total_seconds()
    if delay <= 0:
        return
    await asyncio.sleep(delay - REMINDER_MINUTES_BEFORE*60 if delay > REMINDER_MINUTES_BEFORE*60 else delay)
    try:
        row = EventDB.get_event_by_message(message_id)
        if not row:
            return
        _, _, name, time, category, limit, author_id, closed = row
        participants = EventDB.get_participants(message_id)
        pmentions = ', '.join(f'<@{u}>' for u in participants) or 'Brak zapisanych'
        await channel.send(f'⏰ Przypomnienie: Wydarzenie **{name}** zaczyna się za {REMINDER_MINUTES_BEFORE} minut. Uczestnicy: {pmentions}')
    except Exception as e:
        logging.warning('Failed reminder: %s', e)

@tasks.loop(minutes=10)
async def schedule_existing_events():
    try:
        import sqlite3
        from pathlib import Path
        DB_PATH = Path(__file__).parent / 'events.db'
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT message_id, time FROM events WHERE closed = 0 AND time IS NOT NULL AND time != ''")
        rows = c.fetchall()
        for message_id, time_str in rows:
            if message_id in scheduled_tasks:
                continue
            dt = parse_iso(time_str)
            if dt:
                for guild in bot.guilds:
                    for channel in guild.text_channels:
                        try:
                            await channel.fetch_message(message_id)
                            task = asyncio.create_task(schedule_reminder(channel, message_id, dt))
                            scheduled_tasks[message_id] = task
                            raise StopIteration
                        except discord.NotFound:
                            continue
    except StopIteration:
        pass
    except Exception as e:
        logging.warning('schedule_existing_events failed: %s', e)

# ---------- Slash commands – wydarzenia ----------

@bot.tree.command(name='event', description='Utwórz wydarzenie')
@app_commands.describe(name='Nazwa wydarzenia', time='Czas (ISO: YYYY-MM-DDTHH:MM lub pusty)', category='Kategoria', limit='Limit miejsc (0 = brak limitu)')
async def cmd_event(interaction: discord.Interaction, name: str, time: str = None, category: str = None, limit: int = 0):
    limit_val = limit if limit > 0 else None
    embed = discord.Embed(title=f'🎮 {name}', description=f'📅 **{time or "—"}**\n📂 **{category or "—"}**\n\nKliknij przycisk, aby zapisać się.', color=discord.Color.blue())
    sent = await interaction.channel.send(embed=embed)
    EventDB.create_event(sent.id, name, time or '', category or '', limit_val, interaction.user.id)
    admin_msg = await interaction.channel.send(f'🔧 Panel administracyjny dla wydarzenia `{sent.id}`. (Twórca: <@{interaction.user.id}>)', view=AdminView(sent.id, interaction.user.id))
    await sent.edit(view=EventView(sent.id, interaction.user.id))
    if time:
        dt = parse_iso(time)
        if dt:
            task = asyncio.create_task(schedule_reminder(interaction.channel, sent.id, dt))
            scheduled_tasks[sent.id] = task
    await interaction.response.send_message(f'✔️ Wydarzenie utworzone (ID: {sent.id})', ephemeral=True)

@bot.tree.command(name='uczestnicy', description='Pokaż uczestników')
@app_commands.describe(message_id='ID wiadomości wydarzenia')
async def cmd_participants(interaction: discord.Interaction, message_id: str):
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message('Nieprawidłowe ID.', ephemeral=True)
        return
    users = EventDB.get_participants(mid)
    if not users:
        await interaction.response.send_message('Brak zapisanych uczestników.')
        return
    mention_list = '\n'.join(f'<@{u}>' for u in users)
    await interaction.response.send_message(f'Uczestnicy:\n{mention_list}')

# ---------- Deploy ticket panel command ----------

@bot.command()
@commands.has_permissions(manage_guild=True)
async def deploy_ticket_panel(ctx, channel: discord.TextChannel = None):
    """Umieszcza w wybranym kanale przycisk 'Otwórz ticket'."""
    channel = channel or ctx.channel
    view = OpenTicketView()
    await channel.send('Kliknij, aby otworzyć ticket:', view=view)
    await ctx.send('Panel ticketów wdrożony.')

# ---------- Bot events ----------

@bot.event
async def on_ready():
    init_db()
    logging.info(f'Logged in as {bot.user} (ID: {bot.user.id})')

    # Load cogs
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                bot.load_extension(f'cogs.{filename[:-3]}')
                logging.info(f'Loaded cog: {filename}')
            except Exception as e:
                logging.exception(f'Failed to load cog {filename}: {e}')

    await bot.tree.sync()
    logging.info('Slash commands synced.')
    schedule_existing_events.start()

    # Persistent ticket view
    bot.add_view(OpenTicketView())

# ---------- Run bot ----------

if __name__ == '__main__':
    bot.run(TOKEN)
