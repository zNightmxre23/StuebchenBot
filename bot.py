import os
import sys
import math
import sqlite3
import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ==============================================================================
# CONFIGURATION & LOGGING SETUP
# ==============================================================================

# WICHTIGER HINWEIS: Generiere diesen Token im Discord Developer Portal neu!
TOKEN = "MTUzMzg2OTEyNzU0MDgwNTgzNA.GhCeXb.QnKgGpSwpVlhqMn6m2zMrZar8XAFzMwntrtMQg"
CREATE_CHANNEL_ID = 1532736890829275176

# Level-Rollen Belohnungen festlegen (Level: "Rollenname auf Discord")
LEVEL_ROLES = {
    5: "🌿 Stübchen Neuling",
    10: "🍃 Chill Master",
    20: "💨 Smoke Legend",
    50: "👑 Stübchen Boss"
}

# Logging in den Dokumente-Ordner des Systems
documents_dir = os.path.expanduser("~/Documents")
log_dir = os.path.join(documents_dir, "StuebchenBot_Logs")
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "stuebchen_activity.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

# ==============================================================================
# DATABASE SETUP (SQLite für Voice-Zeit & XP)
# ==============================================================================

db_conn = sqlite3.connect("voice_levels.db")
db_cursor = db_conn.cursor()

# 1. Tabelle für User-XP, Level und Voice-Zeit anlegen
db_cursor.execute("""
CREATE TABLE IF NOT EXISTS user_levels (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    voice_time INTEGER DEFAULT 0
)
""")
db_conn.commit()

# 2. Automatische Migration für bestehende Datenbanken
db_cursor.execute("PRAGMA table_info(user_levels)")
columns = [column[1] for column in db_cursor.fetchall()]
if "voice_time" not in columns:
    logging.info("🪴 [STÜBCHEN-DB] Ergänze fehlende Spalte 'voice_time' in der Datenbank...")
    db_cursor.execute("ALTER TABLE user_levels ADD COLUMN voice_time INTEGER DEFAULT 0")
    db_conn.commit()


async def add_voice_time(guild: discord.Guild, user_id: int, seconds: int = 15):
    """Fügt verbrachte Sekunden und XP in die DB ein und vergibt Level-Rollen."""
    if seconds <= 0:
        return

    # Formel: 5 XP pro 15 Sekunden
    earned_xp = int((seconds / 15) * 5)

    db_cursor.execute("SELECT xp, level, voice_time FROM user_levels WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()

    if row is None:
        xp = earned_xp
        level = 1
        total_time = seconds
        db_cursor.execute(
            "INSERT INTO user_levels (user_id, xp, level, voice_time) VALUES (?, ?, ?, ?)",
            (user_id, xp, level, total_time)
        )
    else:
        xp = row[0] + earned_xp
        level = row[1]
        total_time = row[2] + seconds

        # Level-Up Berechnung: 100 * (Level ^ 1.5)
        needed_xp = int(100 * math.pow(level, 1.5))
        if xp >= needed_xp:
            level += 1
            logging.info(f"💨 [LEVEL UP] User {user_id} wurde im Stübchen auf Level {level} befördert!")

            # Rollen-Vergabe & PN-Benachrichtigung
            member = guild.get_member(user_id)
            if member:
                # 1. Prüfen, ob für das NEUE Level eine Rolle existiert
                if level in LEVEL_ROLES:
                    role_name = LEVEL_ROLES[level]
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role)
                            logging.info(f"🌿 [REWARD] Rolle '{role_name}' an {member.display_name} vergeben!")
                        except discord.Forbidden:
                            logging.error(f"⚠️ [FEHLER] StübchenBot fehlen Rechte für die Rolle '{role_name}'!")

                # 2. Level-Up Benachrichtigung per Direktnachricht senden
                try:
                    embed = discord.Embed(
                        title="🎉 Stübchen Level Up!",
                        description=f"Glückwunsch **{member.display_name}**! Du bist im Stübchen-Voice auf **Level {level}** aufgestiegen! 💨",
                        color=discord.Color.dark_green()
                    )
                    if level in LEVEL_ROLES:
                        embed.add_field(name="🎁 Neue Stübchen-Rolle", value=f"Du hast die Rolle **{LEVEL_ROLES[level]}** freigeschaltet! 🌿")
                    
                    await member.send(embed=embed)
                except discord.Forbidden:
                    pass  # Falls der User PNs blockiert hat

        db_cursor.execute(
            "UPDATE user_levels SET xp = ?, level = ?, voice_time = ? WHERE user_id = ?",
            (xp, level, total_time, user_id)
        )

    db_conn.commit()


def format_time(seconds: int) -> str:
    """Konvertiert Sekunden in ein lesbares 'Xh Ym Zs' Format."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {minutes}m {secs}s"

# ==============================================================================
# BOT INITIALIZATION
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

temp_channels = set()
user_temp_channels = {}  # {user_id: channel_id}


# ==============================================================================
# DISCORD UI (BUTTON CONTROL PANEL)
# ==============================================================================

class LimitSelect(discord.ui.Select):
    """Dropdown-Menü zum Einstellen des User-Limits."""
    def __init__(self):
        options = [
            discord.SelectOption(label="Unbegrenzt", value="0", emoji="♾️"),
            discord.SelectOption(label="2 Chiller (Duo)", value="2", emoji="🌿"),
            discord.SelectOption(label="3 Chiller (Trio)", value="3", emoji="🍃"),
            discord.SelectOption(label="5 Chiller (Session)", value="5", emoji="💨"),
            discord.SelectOption(label="10 Chiller (Ganzes Stübchen)", value="10", emoji="🪴"),
        ]
        super().__init__(placeholder="Wähle ein User-Limit für die Session...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        limit = int(self.values[0])
        await channel.edit(user_limit=limit)
        await interaction.response.send_message(f"🍃 Stübchen-Limit auf **{limit if limit > 0 else 'Unbegrenzt'}** gesetzt.", ephemeral=True)


class OwnerSelect(discord.ui.UserSelect):
    """User-Select zum Übertragen von Channel-Rechten."""
    def __init__(self):
        super().__init__(placeholder="Wähle den neuen Stübchen-Chef...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        new_owner = self.values[0]
        channel = interaction.channel

        old_owner_id = None
        for uid, cid in user_temp_channels.items():
            if cid == channel.id:
                old_owner_id = uid
                break

        if old_owner_id:
            del user_temp_channels[old_owner_id]

        user_temp_channels[new_owner.id] = channel.id

        await channel.set_permissions(new_owner, manage_channels=True, move_members=True, manage_permissions=True)
        await interaction.response.send_message(f"👑 **{new_owner.display_name}** leitet ab sofort die Session!", ephemeral=False)


class VoiceControlView(discord.ui.View):
    """Das interaktive Button-Panel im Voice-Textkanal."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(LimitSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        channel_id = interaction.channel_id
        owner_id = None
        for uid, cid in user_temp_channels.items():
            if cid == channel_id:
                owner_id = uid
                break

        if interaction.user.id != owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Nur der Besitzer dieser Stübchen-Session kann das Panel bedienen!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Sperren / Freigeben", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild
        current_overwrite = channel.overwrites_for(guild.default_role)

        is_locked = current_overwrite.connect is False
        await channel.set_permissions(guild.default_role, connect=is_locked)

        status = "freigegeben 🔓" if is_locked else "gesperrt 🔒"
        await interaction.response.send_message(f"Das Stübchen wurde **{status}**.", ephemeral=True)

    @discord.ui.button(label="Verstecken / Zeigen", style=discord.ButtonStyle.primary, emoji="👁️")
    async def toggle_hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild
        current_overwrite = channel.overwrites_for(guild.default_role)

        is_hidden = current_overwrite.view_channel is False
        await channel.set_permissions(guild.default_role, view_channel=is_hidden)

        status = "sichtbar 👁️" if is_hidden else "im Nebel versteckt 😶‍🌫️"
        await interaction.response.send_message(f"Das Stübchen ist jetzt **{status}**.", ephemeral=True)

    @discord.ui.button(label="Chef wechseln", style=discord.ButtonStyle.danger, emoji="👑")
    async def transfer_owner(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(OwnerSelect())
        await interaction.response.send_message("Wähle das Mitglied aus, das die Führung übernimmt:", view=view, ephemeral=True)


# ==============================================================================
# BACKGROUND TASKS (15-SEKUNDEN LIVE UPDATER)
# ==============================================================================

@tasks.loop(seconds=15)
async def voice_xp_loop():
    """Gibt ALLEN Usern in Voice-Channels alle 15 Sekunden live Zeit & XP."""
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            if len(channel.members) > 0:
                for member in channel.members:
                    # AFK-Channel ignorieren (falls vorhanden)
                    if guild.afk_channel and channel.id == guild.afk_channel.id:
                        continue
                    
                    if not member.bot:
                        await add_voice_time(guild, member.id, seconds=15)


# ==============================================================================
# BOT EVENTS
# ==============================================================================

@bot.event
async def on_ready():
    logging.info(f"🌿 StübchenBot ist am Start und eingeloggt als {bot.user}!")

    # Synchronisiert die Slash Commands mit Discord
    try:
        synced = await bot.tree.sync()
        logging.info(f"💨 Erfolgreich {len(synced)} Stübchen Slash Commands synchronisiert!")
    except Exception as e:
        logging.error(f"⚠️ Fehler beim Synchronisieren der Slash Commands: {e}")

    # Startet den 15-Sekunden Loop für Live-Gutschriften
    if not voice_xp_loop.is_running():
        voice_xp_loop.start()

    # Aufräumen alter Leichen & Re-Initialisierung bei Neustart
    create_channel = bot.get_channel(CREATE_CHANNEL_ID)
    if create_channel and create_channel.category:
        for channel in create_channel.category.voice_channels:
            if channel.id == CREATE_CHANNEL_ID:
                continue
            if len(channel.members) == 0:
                try:
                    await channel.delete()
                except discord.HTTPException:
                    pass
            else:
                temp_channels.add(channel.id)
                owner = channel.members[0]
                user_temp_channels[owner.id] = channel.id

    logging.info("🍃 TempVoice-System & Stübchen-XP gestartet.")


@bot.event
async def on_voice_state_update(member, before, after):

    # --------------------------------------------------------------------------
    # USER-REGISTRIERUNG BEIM BEITRITT
    # --------------------------------------------------------------------------
    if not member.bot and before.channel is None and after.channel is not None:
        # Sofort mit 0 Werten anlegen, falls der User neu ist
        db_cursor.execute(
            "INSERT OR IGNORE INTO user_levels (user_id, xp, level, voice_time) VALUES (?, 0, 1, 0)",
            (member.id,)
        )
        db_conn.commit()

    # --------------------------------------------------------------------------
    # CREATE TEMP CHANNEL
    # --------------------------------------------------------------------------
    if after.channel and after.channel.id == CREATE_CHANNEL_ID:
        guild = member.guild
        category = after.channel.category

        # Spam-Schutz Check
        if member.id in user_temp_channels:
            existing_channel = guild.get_channel(user_temp_channels[member.id])
            if existing_channel:
                try:
                    await member.move_to(existing_channel)
                except discord.HTTPException:
                    pass
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            member: discord.PermissionOverwrite(manage_channels=True, move_members=True, manage_permissions=True)
        }

        channel_name = f"🌿 Stübchen | {member.display_name}"
        
        try:
            temp_channel = await guild.create_voice_channel(name=channel_name, category=category, overwrites=overwrites)
            temp_channels.add(temp_channel.id)
            user_temp_channels[member.id] = temp_channel.id

            await member.move_to(temp_channel)
            logging.info(f"🍃 [ERSTELLT] Neues Stübchen für {member.display_name}")

            embed = discord.Embed(
                title="🪴 Stübchen Control Panel",
                description=f"Willkommen in deiner Stübchen-Session, {member.mention}! 💨\nNutze die Buttons unten, um deine Lounge anzupassen.",
                color=discord.Color.dark_green()
            )
            embed.add_field(name="Session-Rechte", value="Du hast die volle Kontrolle über dieses Stübchen.", inline=False)
            
            await temp_channel.send(embed=embed, view=VoiceControlView())

        except discord.HTTPException as e:
            logging.error(f"⚠️ [FEHLER] Stübchen-Erstellung fehlgeschlagen: {e}")

    # --------------------------------------------------------------------------
    # DELETE EMPTY TEMP CHANNEL
    # --------------------------------------------------------------------------
    if before.channel and before.channel.id in temp_channels:
        if len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                logging.info(f"💨 [GELÖSCHT] Leeres Stübchen {before.channel.id} gelöscht.")
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                logging.error(f"⚠️ [FEHLER] Löschen fehlgeschlagen: {e}")
            finally:
                temp_channels.discard(before.channel.id)
                owner_id_to_remove = [uid for uid, cid in user_temp_channels.items() if cid == before.channel.id]
                for uid in owner_id_to_remove:
                    del user_temp_channels[uid]


# ==============================================================================
# SLASH COMMANDS (Werden bei "/" auf Discord vorgeschlagen)
# ==============================================================================

@bot.tree.command(name="rank", description="Zeigt dein Stübchen-Level, XP und deine gesammelte Chill-Zeit an.")
@app_commands.describe(user="Der User, dessen Stübchen-Rang du sehen möchtest (optional)")
async def rank_cmd(interaction: discord.Interaction, user: discord.Member = None):
    """Slash Command für /rank"""
    target_user = user or interaction.user
    
    db_cursor.execute("SELECT xp, level, voice_time FROM user_levels WHERE user_id = ?", (target_user.id,))
    row = db_cursor.fetchone()

    if not row:
        await interaction.response.send_message(f"🍃 **{target_user.display_name}** hat noch keine Zeit im Stübchen verbracht.")
        return

    xp, level, total_seconds = row
    needed_xp = int(100 * math.pow(level, 1.5))

    embed = discord.Embed(title=f"🪴 Stübchen-Stats für {target_user.display_name}", color=discord.Color.dark_green())
    embed.add_field(name="Stübchen Level", value=f"**{level}** 🌿", inline=True)
    embed.add_field(name="XP gesamt", value=f"**{xp}** / {needed_xp} XP 💨", inline=True)
    embed.add_field(name="Gesamte Chill-Zeit", value=f"⏱️ **{format_time(total_seconds)}**", inline=False)
    embed.set_thumbnail(url=target_user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="top", description="Zeigt die Top 5 aktivsten Chiller im Stübchen an.")
async def leaderboard_cmd(interaction: discord.Interaction):
    """Slash Command für /top"""
    db_cursor.execute("SELECT user_id, level, xp, voice_time FROM user_levels ORDER BY level DESC, xp DESC LIMIT 5")
    rows = db_cursor.fetchall()

    if not rows:
        await interaction.response.send_message("Noch keine Stübchen-Daten in der Rangliste vorhanden.")
        return

    embed = discord.Embed(title="🏆 Top 5 Stübchen Chiller Leaderboard 🌿", color=discord.Color.dark_green())
    
    for idx, (uid, level, xp, total_seconds) in enumerate(rows, 1):
        member = interaction.guild.get_member(uid)
        name = member.display_name if member else f"User ID {uid}"
        embed.add_field(
            name=f"#{idx} {name}",
            value=f"Level **{level}** 🌿 ({xp} XP) | ⏱️ {format_time(total_seconds)}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    bot.run(TOKEN)