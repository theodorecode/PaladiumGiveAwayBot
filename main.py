import discord
from discord.ext import commands
from discord import app_commands
import os
import json
from datetime import datetime
 
# ─── Config ───────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("TOKEN")
 
DATA_FILE = "data.json"
 
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)
 
def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
 
# ─── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
 
# Cache des invitations : {guild_id: {code: uses}}
invite_cache = {}
 
# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_guild_data(data, guild_id):
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {
            "welcome_channel": None,
            "invites": {},      # {inviter_id: {"real": int, "rejoin": int}}
            "members": {}       # {member_id: {"inviter": str, "rejoined": bool}}
        }
    return data[gid]
 
async def fetch_invite_cache(guild):
    try:
        invites = await guild.fetch_invites()
        return {inv.code: inv.uses for inv in invites}
    except Exception:
        return {}
 
# ─── Events ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    # Populate invite cache for all guilds
    for guild in bot.guilds:
        invite_cache[guild.id] = await fetch_invite_cache(guild)
        print(f"   📋 Cache invitations chargé pour : {guild.name}")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur de synchronisation : {e}")
 
@bot.event
async def on_guild_join(guild):
    invite_cache[guild.id] = await fetch_invite_cache(guild)
 
@bot.event
async def on_invite_create(invite):
    if invite.guild:
        if invite.guild.id not in invite_cache:
            invite_cache[invite.guild.id] = {}
        invite_cache[invite.guild.id][invite.code] = invite.uses
 
@bot.event
async def on_invite_delete(invite):
    if invite.guild and invite.guild.id in invite_cache:
        invite_cache[invite.guild.id].pop(invite.code, None)
 
@bot.event
async def on_member_join(member):
    guild = member.guild
    data = load_data()
    guild_data = get_guild_data(data, guild.id)
 
    # Détecter quelle invitation a été utilisée
    new_cache = await fetch_invite_cache(guild)
    old_cache = invite_cache.get(guild.id, {})
    used_invite = None
    inviter = None
 
    for code, uses in new_cache.items():
        old_uses = old_cache.get(code, 0)
        if uses > old_uses:
            used_invite = code
            try:
                inv = await guild.fetch_invite(code)
                inviter = inv.inviter
            except Exception:
                pass
            break
 
    invite_cache[guild.id] = new_cache
 
    member_id = str(member.id)
    already_joined_before = member_id in guild_data["members"]
    is_rejoin = already_joined_before
 
    # Mettre à jour les stats de l'inviteur
    if inviter:
        inviter_id = str(inviter.id)
        if inviter_id not in guild_data["invites"]:
            guild_data["invites"][inviter_id] = {"real": 0, "rejoin": 0}
 
        if is_rejoin:
            guild_data["invites"][inviter_id]["rejoin"] += 1
        else:
            guild_data["invites"][inviter_id]["real"] += 1
 
        guild_data["members"][member_id] = {
            "inviter": inviter_id,
            "rejoined": is_rejoin
        }
    else:
        guild_data["members"][member_id] = {
            "inviter": None,
            "rejoined": is_rejoin
        }
 
    save_data(data)
 
    # Message de bienvenue
    welcome_channel_id = guild_data.get("welcome_channel")
    if not welcome_channel_id:
        return
 
    channel = guild.get_channel(int(welcome_channel_id))
    if not channel:
        return
 
    embed = discord.Embed(color=0x2ecc71 if not is_rejoin else 0xe67e22)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = datetime.utcnow()
 
    if is_rejoin:
        embed.title = f"👋 Content de te revoir, {member.name} !"
        embed.description = (
            f"Bienvenue de retour {member.mention} sur **{guild.name}** !\n"
            f"*(Cette rejointe ne compte pas comme une vraie invitation)*"
        )
        if inviter:
            inviter_stats = guild_data["invites"].get(str(inviter.id), {"real": 0, "rejoin": 0})
            embed.add_field(
                name="📨 Invité par",
                value=f"{inviter.mention} — **{inviter_stats['real']}** invitations réelles",
                inline=False
            )
        embed.set_footer(text="Rejointe")
    else:
        embed.title = f"🎉 Bienvenue, {member.name} !"
        embed.description = f"{member.mention} vient de rejoindre **{guild.name}** !"
        if inviter:
            inviter_stats = guild_data["invites"].get(str(inviter.id), {"real": 0, "rejoin": 0})
            total_real = inviter_stats["real"]
            embed.add_field(
                name="📨 Invité par",
                value=(
                    f"{inviter.mention}\n"
                    f"Il/elle a maintenant **{total_real}** invitation{'s' if total_real > 1 else ''} réelle{'s' if total_real > 1 else ''} !"
                ),
                inline=False
            )
        else:
            embed.add_field(name="📨 Source", value="Invitation inconnue (lien direct ?)", inline=False)
 
        embed.add_field(
            name="👥 Membres",
            value=f"Tu es le **{guild.member_count}ème** membre !",
            inline=True
        )
        embed.set_footer(text=f"ID : {member.id}")
 
    await channel.send(embed=embed)
 
# ─── Commandes slash ──────────────────────────────────────────────────────────
 
@bot.tree.command(name="ping", description="Vérifie si le bot est en ligne")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong !", ephemeral=True)
 
@bot.tree.command(name="salut", description="Dis bonjour à un membre")
@app_commands.describe(membre="Le membre à saluer")
async def salut(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.send_message(f"👋 Salut {membre.mention} !")
 
@bot.tree.command(name="setup-welcome", description="Configure le salon de bienvenue")
@app_commands.describe(salon="Le salon où afficher les messages de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def setup_welcome(interaction: discord.Interaction, salon: discord.TextChannel):
    data = load_data()
    guild_data = get_guild_data(data, interaction.guild.id)
    guild_data["welcome_channel"] = str(salon.id)
    save_data(data)
    await interaction.response.send_message(
        f"✅ Salon de bienvenue configuré sur {salon.mention} !",
        ephemeral=True
    )
 
@setup_welcome.error
async def setup_welcome_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
 
@bot.tree.command(name="invitations", description="Voir les invitations d'un membre")
@app_commands.describe(membre="Le membre à inspecter (toi par défaut)")
async def invitations(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    data = load_data()
    guild_data = get_guild_data(data, interaction.guild.id)
 
    stats = guild_data["invites"].get(str(target.id), {"real": 0, "rejoin": 0})
    real = stats["real"]
    rejoin = stats["rejoin"]
 
    embed = discord.Embed(
        title=f"📊 Invitations de {target.display_name}",
        color=0x3498db
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="✅ Vraies invitations", value=str(real), inline=True)
    embed.add_field(name="🔄 Rejointes", value=str(rejoin), inline=True)
    embed.add_field(name="📈 Total comptabilisé", value=str(real), inline=True)
    embed.set_footer(text=f"Les rejointes ne comptent pas dans le total.")
 
    await interaction.response.send_message(embed=embed)
 
@bot.tree.command(name="leaderboard-invitations", description="Top 10 des inviteurs du serveur")
async def leaderboard(interaction: discord.Interaction):
    data = load_data()
    guild_data = get_guild_data(data, interaction.guild.id)
    invites = guild_data["invites"]
 
    if not invites:
        await interaction.response.send_message("❌ Aucune invitation enregistrée pour l'instant.", ephemeral=True)
        return
 
    sorted_inv = sorted(invites.items(), key=lambda x: x[1]["real"], reverse=True)[:10]
 
    embed = discord.Embed(
        title="🏆 Top Inviteurs",
        color=0xf1c40f
    )
 
    description = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, stats) in enumerate(sorted_inv):
        medal = medals[i] if i < 3 else f"**#{i+1}**"
        member = interaction.guild.get_member(int(uid))
        name = member.mention if member else f"<@{uid}>"
        description += f"{medal} {name} — **{stats['real']}** invitations\n"
 
    embed.description = description or "Aucune donnée."
    await interaction.response.send_message(embed=embed)
 
@bot.tree.command(name="admin", description="Commande réservée aux admins")
@app_commands.checks.has_permissions(administrator=True)
async def admin(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Tu es admin !", ephemeral=True)
 
@admin.error
async def admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
 
# ─── Lancement ────────────────────────────────────────────────────────────────
bot.run(TOKEN)
 
