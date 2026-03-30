import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, asyncio
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

TICKETS_FILE = "tickets.json"
GIVEAWAYS_FILE = "giveaways.json"
CONFIG_FILE = "config.json"
LOTO_FILE = "loto.json"

def load_tickets():
    if not os.path.exists(TICKETS_FILE):
        return {"tickets": {}}
    with open(TICKETS_FILE) as f:
        return json.load(f)

def save_tickets(data):
    with open(TICKETS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_giveaways():
    if not os.path.exists(GIVEAWAYS_FILE):
        return {"giveaways": {}, "snapshots": {}}
    with open(GIVEAWAYS_FILE) as f:
        return json.load(f)

def save_giveaways(data):
    with open(GIVEAWAYS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_loto():
    if not os.path.exists(LOTO_FILE):
        return {"joueurs": {}, "loterie_quotidienne": {}, "loterie_hebdo": {}}
    with open(LOTO_FILE) as f:
        return json.load(f)

def save_loto(data):
    with open(LOTO_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_joueur_data(data, gid, uid):
    if gid not in data["joueurs"]:
        data["joueurs"][gid] = {}
    if uid not in data["joueurs"][gid]:
        data["joueurs"][gid][uid] = {"jetons": 0, "tours_gratuits": 0, "dernier_claim": None}
    if "tours_gratuits" not in data["joueurs"][gid][uid]:
        data["joueurs"][gid][uid]["tours_gratuits"] = 0
    if "dernier_claim" not in data["joueurs"][gid][uid]:
        data["joueurs"][gid][uid]["dernier_claim"] = None
    return data["joueurs"][gid][uid]

# ══════════════════════════════════════════════
#  DÉMARRAGE
# ══════════════════════════════════════════════
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        await bot.tree.sync()
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"✅ Sync {guild.name}")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    bot.add_view(PanelView())
    bot.add_view(TicketView())
    bot.add_view(GiveawayView(0))
    check_giveaways.start()

@bot.event
async def on_guild_join(guild):
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"✅ Sync {guild.name}")
    except Exception as e:
        print(f"❌ Erreur sync {guild.name} : {e}")

# ══════════════════════════════════════════════
#  SYSTÈME WELCOME
# ══════════════════════════════════════════════
invite_cache = {}

@bot.event
async def on_invite_create(invite):
    invite_cache[invite.code] = invite.uses

@bot.event
async def on_member_join(member):
    guild = member.guild
    config = load_config()
    guild_config = config.get(str(guild.id), {})
    welcome_channel_id = guild_config.get("welcome_channel")
    role_id = guild_config.get("welcome_role")
    if role_id:
        role = guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    inviter = None
    try:
        current_invites = await guild.invites()
        for invite in current_invites:
            old_uses = invite_cache.get(invite.code, 0)
            if invite.uses > old_uses:
                inviter = invite.inviter
                invite_cache[invite.code] = invite.uses
                break
    except:
        pass
    account_age = datetime.now(timezone.utc) - member.created_at
    is_fake = account_age.total_seconds() < 300
    if welcome_channel_id:
        channel = guild.get_channel(int(welcome_channel_id))
        if channel:
            embed = discord.Embed(
                title=f"👋 Bienvenue {member.display_name} !",
                description=f"On est ravis de t'accueillir sur **{guild.name}** ! 🎉\nN'hésite pas à te présenter et à explorer le serveur.",
                color=0x2ecc71
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            if inviter:
                embed.add_field(name="📨 Invité par", value=inviter.mention, inline=True)
            embed.add_field(name="📅 Compte créé le", value=f"<t:{int(member.created_at.timestamp())}:D>", inline=True)
            embed.add_field(name="👥 Membre n°", value=str(guild.member_count), inline=True)
            if is_fake:
                embed.add_field(name="⚠️ Compte suspect", value="Compte créé **il y a moins de 5 minutes** !", inline=False)
                embed.color = 0xe74c3c
            embed.set_footer(text=f"ID : {member.id}")
            await channel.send(embed=embed)

@bot.tree.command(name="setup-welcome", description="⚙️ Configurer le salon et rôle de bienvenue")
@app_commands.describe(salon="Salon de bienvenue", role="Rôle auto pour les nouveaux")
@app_commands.checks.has_permissions(administrator=True)
async def setup_welcome(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role):
    config = load_config()
    config[str(interaction.guild.id)] = {"welcome_channel": str(salon.id), "welcome_role": str(role.id)}
    save_config(config)
    embed = discord.Embed(title="✅ Bienvenue configuré", description=f"**Salon :** {salon.mention}\n**Rôle :** {role.mention}", color=0x2ecc71)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════
#  TICKETS
# ══════════════════════════════════════════════
@bot.tree.command(name="panel", description="📩 Poster le panel de création de ticket")
@app_commands.describe(message="Le message à afficher sur le panel")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction, message: str):
    embed = discord.Embed(title="🎫 Support", description=message, color=0x5865f2)
    embed.set_footer(text="Clique sur le bouton pour ouvrir un ticket")
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("✅ Panel posté !", ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

class TicketModal(discord.ui.Modal, title="📩 Ouvrir un ticket"):
    sujet = discord.ui.TextInput(label="Sujet", placeholder="Ex: Problème de paiement...", max_length=100)
    description = discord.ui.TextInput(label="Explique ton problème", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        data = load_tickets()
        for ch_id, info in data["tickets"].items():
            if info["user_id"] == str(user.id) and info["ouvert"]:
                await interaction.response.send_message(f"❌ T'as déjà un ticket ouvert : <#{ch_id}>", ephemeral=True)
                return
        category = discord.utils.get(guild.categories, name="🎫 Tickets")
        if not category:
            category = await guild.create_category("🎫 Tickets")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await guild.create_text_channel(f"ticket-{user.name}", category=category, overwrites=overwrites)
        data["tickets"][str(channel.id)] = {"user_id": str(user.id), "ouvert": True, "sujet": str(self.sujet)}
        save_tickets(data)
        embed = discord.Embed(title=f"🎫 Ticket de {user.display_name}", color=0x5865f2)
        embed.add_field(name="📌 Sujet", value=str(self.sujet), inline=False)
        embed.add_field(name="📝 Description", value=str(self.description), inline=False)
        embed.set_footer(text="Un admin va te répondre bientôt. Clique sur 🔒 pour fermer.")
        await channel.send(content=f"{user.mention} | <@&{guild.owner_id}>", embed=embed, view=TicketView())
        await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = load_tickets()
        if str(channel.id) in data["tickets"]:
            data["tickets"][str(channel.id)]["ouvert"] = False
            save_tickets(data)
        await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
        await asyncio.sleep(5)
        await channel.delete()

@bot.tree.command(name="fermer", description="🔒 Fermer le ticket actuel")
@app_commands.checks.has_permissions(administrator=True)
async def fermer(interaction: discord.Interaction):
    channel = interaction.channel
    data = load_tickets()
    if str(channel.id) not in data["tickets"]:
        await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        return
    data["tickets"][str(channel.id)]["ouvert"] = False
    save_tickets(data)
    await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
    await asyncio.sleep(5)
    await channel.delete()

# ══════════════════════════════════════════════
#  GIVEAWAY
# ══════════════════════════════════════════════
async def snapshot_invites(guild):
    data = load_giveaways()
    invites = await guild.invites()
    data["snapshots"][str(guild.id)] = {
        inv.code: {"uses": inv.uses, "inviter": str(inv.inviter.id) if inv.inviter else None}
        for inv in invites
    }
    save_giveaways(data)

async def count_new_invites(guild, user_id):
    data = load_giveaways()
    snapshot = data["snapshots"].get(str(guild.id), {})
    current_invites = await guild.invites()
    count = 0
    for inv in current_invites:
        if inv.inviter and str(inv.inviter.id) == str(user_id):
            old_uses = snapshot.get(inv.code, {}).get("uses", 0)
            count += inv.uses - old_uses
    return count

async def terminer_giveaway(gw):
    data = load_giveaways()
    gw["termine"] = True
    save_giveaways(data)
    guild = bot.get_guild(int(gw["guild_id"]))
    if not guild:
        return
    channel = guild.get_channel(int(gw["channel_id"]))
    if not channel:
        return
    participants = gw["participants"]
    if not participants:
        await channel.send(embed=discord.Embed(title="🎉 Giveaway terminé", description="Personne n'a participé... 😢", color=0xe74c3c))
        return
    gagnant_id = random.choice(participants)
    embed = discord.Embed(
        title="🎉 Giveaway terminé !",
        description=f"🏆 **Félicitations à <@{gagnant_id}> !**\n\nTu remportes **{gw['prix']}** !\n*(Tiré parmi {len(participants)} participant(s))*",
        color=0xf5a623
    )
    await channel.send(embed=embed)

@bot.tree.command(name="giveaway", description="🎉 Lancer un giveaway")
@app_commands.describe(prix="Récompense", duree_minutes="Durée en minutes", invitations_requises="Invitations minimum", salon="Salon (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, prix: str, duree_minutes: int, invitations_requises: int, salon: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    target = salon or interaction.channel
    await snapshot_invites(guild)
    end_timestamp = int((datetime.now(timezone.utc) + timedelta(minutes=duree_minutes)).timestamp())
    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        description=f"**Prix :** {prix}\n\n**Condition :** Inviter **{invitations_requises}** personne(s) depuis maintenant\n**Comment :** Invite des gens puis clique ✅\n\n**Fin :** <t:{end_timestamp}:R>\n\n*Le bot vérifie tes invitations automatiquement.*",
        color=0xf5a623
    )
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    view = GiveawayView(invitations_requises)
    msg = await target.send(embed=embed, view=view)
    data = load_giveaways()
    data["giveaways"][str(msg.id)] = {
        "guild_id": str(guild.id), "channel_id": str(target.id), "message_id": str(msg.id),
        "prix": prix, "invitations_requises": invitations_requises, "end_timestamp": end_timestamp,
        "participants": [], "invite_credits": {}, "termine": False, "annule": False
    }
    save_giveaways(data)
    await interaction.followup.send(f"✅ Giveaway lancé dans {target.mention} !", ephemeral=True)

class GiveawayView(discord.ui.View):
    def __init__(self, invitations_requises):
        super().__init__(timeout=None)
        self.invitations_requises = invitations_requises

    @discord.ui.button(label="✅ Rejoindre", style=discord.ButtonStyle.success, custom_id="join_giveaway")
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = load_giveaways()
        gw = data["giveaways"].get(str(interaction.message.id))
        if not gw or gw["termine"]:
            await interaction.followup.send("❌ Ce giveaway est terminé.", ephemeral=True)
            return
        user_id = str(interaction.user.id)
        if user_id in gw["participants"]:
            await interaction.followup.send("✅ Tu es déjà inscrit !", ephemeral=True)
            return
        nb = await count_new_invites(interaction.guild, user_id)
        if nb >= gw["invitations_requises"]:
            gw["participants"].append(user_id)
            gw["invite_credits"][user_id] = nb
            save_giveaways(data)
            await interaction.followup.send(f"🎉 **Inscrit !** Tu as invité **{nb}** personne(s). Bonne chance !", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Tu as invité **{nb}** personne(s). Il t'en faut encore **{gw['invitations_requises'] - nb}**.\n💡 Invite des amis puis reviens !", ephemeral=True)

@bot.tree.command(name="cancel", description="❌ Annuler le giveaway en cours")
@app_commands.checks.has_permissions(administrator=True)
async def cancel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = load_giveaways()
    found = False
    for gw_id, gw in data["giveaways"].items():
        if gw["guild_id"] == str(interaction.guild.id) and not gw["termine"]:
            gw["termine"] = True
            gw["annule"] = True
            found = True
            channel = interaction.guild.get_channel(int(gw["channel_id"]))
            if channel:
                await channel.send(embed=discord.Embed(title="❌ Giveaway annulé", description=f"Giveaway **{gw['prix']}** annulé.\nInvitations des **{len(gw['participants'])}** participants sauvegardées.", color=0xe74c3c))
            break
    save_giveaways(data)
    await interaction.followup.send("✅ Annulé." if found else "❌ Aucun giveaway en cours.", ephemeral=True)

@bot.tree.command(name="avancer", description="⏩ Terminer immédiatement le giveaway")
@app_commands.checks.has_permissions(administrator=True)
async def avancer(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = load_giveaways()
    found = False
    for gw_id, gw in data["giveaways"].items():
        if gw["guild_id"] == str(interaction.guild.id) and not gw["termine"]:
            found = True
            await terminer_giveaway(gw)
            break
    await interaction.followup.send("✅ Terminé !" if found else "❌ Aucun giveaway en cours.", ephemeral=True)

@bot.tree.command(name="invites-sauvegardees", description="📋 Invitations sauvegardées du dernier giveaway")
@app_commands.checks.has_permissions(administrator=True)
async def invites_sauvegardees(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = load_giveaways()
    last_gw = None
    for gw_id, gw in data["giveaways"].items():
        if gw["guild_id"] == str(interaction.guild.id) and gw["termine"]:
            last_gw = gw
    if not last_gw or not last_gw["invite_credits"]:
        await interaction.followup.send("❌ Aucune invitation sauvegardée.", ephemeral=True)
        return
    lines = [f"<@{uid}> — **{count}** invitation(s)" for uid, count in last_gw["invite_credits"].items()]
    embed = discord.Embed(title="📋 Invitations sauvegardées", description="\n".join(lines), color=0x3498db)
    embed.set_footer(text=f"Prix : {last_gw['prix']}")
    await interaction.followup.send(embed=embed, ephemeral=True)

@tasks.loop(seconds=30)
async def check_giveaways():
    data = load_giveaways()
    now = int(datetime.now(timezone.utc).timestamp())
    for gw_id, gw in data["giveaways"].items():
        if not gw["termine"] and now >= gw["end_timestamp"]:
            await terminer_giveaway(gw)
    save_giveaways(data)

@check_giveaways.before_loop
async def before_check():
    await bot.wait_until_ready()

# ══════════════════════════════════════════════
#  SYSTÈME LOTO / JETONS
# ══════════════════════════════════════════════

@bot.tree.command(name="ajouter-jetons", description="🎟️ Ajouter des jetons à un joueur")
@app_commands.describe(membre="Le joueur", quantite="Nombre de jetons à ajouter")
@app_commands.checks.has_permissions(administrator=True)
async def ajouter_jetons(interaction: discord.Interaction, membre: discord.Member, quantite: int):
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(membre.id)
    joueur = get_joueur_data(data, gid, uid)
    joueur["jetons"] += quantite
    save_loto(data)
    embed = discord.Embed(title="🎟️ Jetons ajoutés", description=f"{membre.mention} a reçu **{quantite} jeton(s)** !\nSolde total : **{joueur['jetons']} jeton(s)**", color=0xf5a623)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="retirer-jetons", description="❌ Retirer des jetons à un joueur")
@app_commands.describe(membre="Le joueur", quantite="Nombre de jetons à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def retirer_jetons(interaction: discord.Interaction, membre: discord.Member, quantite: int):
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(membre.id)
    joueur = get_joueur_data(data, gid, uid)
    joueur["jetons"] = max(0, joueur["jetons"] - quantite)
    save_loto(data)
    await interaction.response.send_message(embed=discord.Embed(title="❌ Jetons retirés", description=f"{membre.mention} a perdu **{quantite} jeton(s)**.\nSolde : **{joueur['jetons']} jeton(s)**", color=0xe74c3c))

@bot.tree.command(name="jetons", description="🎟️ Voir ton solde de jetons et tours gratuits")
@app_commands.describe(membre="Voir les jetons d'un autre membre (optionnel)")
async def jetons(interaction: discord.Interaction, membre: discord.Member = None):
    cible = membre or interaction.user
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(cible.id)
    joueur = get_joueur_data(data, gid, uid)
    save_loto(data)
    embed = discord.Embed(
        title=f"🎟️ Compte de {cible.display_name}",
        description=f"💰 Jetons : **{joueur['jetons']}**\n🎰 Tours gratuits : **{joueur['tours_gratuits']}**",
        color=0xf5a623
    )
    embed.set_footer(text="Utilise /daily pour récupérer 5 tours gratuits chaque jour !")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="classement-jetons", description="🏆 Classement des jetons")
async def classement_jetons(interaction: discord.Interaction):
    data = load_loto()
    gid = str(interaction.guild.id)
    joueurs = data.get("joueurs", {}).get(gid, {})
    if not joueurs:
        await interaction.response.send_message("❌ Personne n'a de jetons pour l'instant.", ephemeral=True)
        return
    sorted_joueurs = sorted(joueurs.items(), key=lambda x: x[1].get("jetons", 0), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, info) in enumerate(sorted_joueurs):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"<@{uid}>"
        lines.append(f"{medals[i]} **{name}** — {info.get('jetons', 0)} jeton(s)")
    embed = discord.Embed(title="🏆 Classement des jetons", description="\n".join(lines), color=0xf5a623)
    await interaction.response.send_message(embed=embed)

# ══════════════════════════════════════════════
#  /daily — Récupérer 5 tours gratuits
# ══════════════════════════════════════════════
@bot.tree.command(name="daily", description="🎁 Récupérer tes 5 tours de slot gratuits quotidiens")
async def daily(interaction: discord.Interaction):
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)

    now = datetime.now(timezone.utc)
    dernier = joueur.get("dernier_claim")

    if dernier:
        dernier_dt = datetime.fromisoformat(dernier)
        diff = now - dernier_dt
        if diff.total_seconds() < 86400:
            restant = 86400 - diff.total_seconds()
            heures = int(restant // 3600)
            minutes = int((restant % 3600) // 60)
            await interaction.response.send_message(
                f"❌ Tu as déjà réclamé tes tours aujourd'hui !\nReviens dans **{heures}h {minutes}min**.",
                ephemeral=True
            )
            return

    joueur["tours_gratuits"] += 5
    joueur["dernier_claim"] = now.isoformat()
    save_loto(data)

    embed = discord.Embed(
        title="🎁 Tours quotidiens réclamés !",
        description=f"Tu as reçu **5 tours de slot gratuits** ! 🎰\nTours gratuits disponibles : **{joueur['tours_gratuits']}**\n\nUtilise `/slot` ou `/multi-slot` pour jouer !",
        color=0x2ecc71
    )
    embed.set_footer(text="Reviens demain pour en récupérer d'autres !")
    await interaction.response.send_message(embed=embed)

# ══════════════════════════════════════════════
#  MACHINE À SOUS
# ══════════════════════════════════════════════
# 🍒x3, 🍋x2, 🍊x2 → ~1 chance sur 5 de gagner quelque chose
SLOTS_SYMBOLS = ["🍒", "🍒", "🍒", "🍋", "🍋", "🍊", "🍊", "⭐", "💎", "7️⃣"]
SLOTS_WINS = {
    ("💎", "💎", "💎"): 50,
    ("7️⃣", "7️⃣", "7️⃣"): 30,
    ("⭐", "⭐", "⭐"): 20,
    ("🍊", "🍊", "🍊"): 10,
    ("🍋", "🍋", "🍋"): 8,
    ("🍒", "🍒", "🍒"): 5,
}

def jouer_un_slot():
    result = [random.choice(SLOTS_SYMBOLS) for _ in range(3)]
    gain = SLOTS_WINS.get(tuple(result), 0)
    return result, gain

# ─── /slot — 1 tour ───────────────────────────
@bot.tree.command(name="slot", description="🎰 Jouer à la machine à sous (1 jeton ou 1 tour gratuit)")
async def slot(interaction: discord.Interaction):
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)

    # Priorité : tours gratuits d'abord
    if joueur["tours_gratuits"] > 0:
        joueur["tours_gratuits"] -= 1
        gratuit = True
    elif joueur["jetons"] >= 1:
        joueur["jetons"] -= 1
        gratuit = False
    else:
        await interaction.response.send_message(
            "❌ Tu n'as pas de jetons ni de tours gratuits !\nUtilise `/daily` pour récupérer 5 tours gratuits.",
            ephemeral=True
        )
        return

    result, gain = jouer_un_slot()
    if gain > 0:
        joueur["jetons"] += gain
        titre = "🎰 JACKPOT !" if gain >= 20 else "🎰 Gagné !"
        desc = f"{'  '.join(result)}\n\n🏆 Tu gagnes **{gain} jeton(s)** !\n💰 Solde : **{joueur['jetons']} jeton(s)** | 🎰 Tours gratuits : **{joueur['tours_gratuits']}**"
        couleur = 0x2ecc71
    else:
        titre = "🎰 Perdu !"
        desc = f"{'  '.join(result)}\n\nDommage... Réessaie !\n💰 Solde : **{joueur['jetons']} jeton(s)** | 🎰 Tours gratuits : **{joueur['tours_gratuits']}**"
        couleur = 0xe74c3c

    save_loto(data)
    embed = discord.Embed(title=titre, description=desc, color=couleur)
    embed.set_footer(text=f"{'Tour gratuit utilisé 🎁' if gratuit else 'Jeton utilisé 🎟️'} | 💎x3=50j | 7️⃣x3=30j | ⭐x3=20j | 🍊x3=10j | 🍋x3=8j | 🍒x3=5j")
    await interaction.response.send_message(embed=embed)

# ─── /multi-slot — Plusieurs tours à la fois ──
@bot.tree.command(name="multi-slot", description="🎰 Lancer plusieurs slots en même temps (1 jeton = 1 tour)")
@app_commands.describe(nombre="Nombre de tours à lancer (max 20)")
async def multi_slot(interaction: discord.Interaction, nombre: int):
    if nombre < 2:
        await interaction.response.send_message("❌ Mets au moins 2 tours.", ephemeral=True)
        return
    if nombre > 20:
        await interaction.response.send_message("❌ Maximum 20 tours à la fois.", ephemeral=True)
        return

    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)

    # Calculer combien on peut payer avec tours gratuits + jetons
    tours_gratuits_dispo = joueur["tours_gratuits"]
    jetons_dispo = joueur["jetons"]
    total_dispo = tours_gratuits_dispo + jetons_dispo

    if total_dispo < nombre:
        await interaction.response.send_message(
            f"❌ Tu n'as pas assez !\n🎰 Tours gratuits : **{tours_gratuits_dispo}** | 💰 Jetons : **{jetons_dispo}**\nTotal disponible : **{total_dispo}** / {nombre} nécessaires.",
            ephemeral=True
        )
        return

    # Déduire : tours gratuits en premier, puis jetons
    tours_gratuits_utilisés = min(tours_gratuits_dispo, nombre)
    jetons_utilisés = nombre - tours_gratuits_utilisés
    joueur["tours_gratuits"] -= tours_gratuits_utilisés
    joueur["jetons"] -= jetons_utilisés

    # Lancer tous les slots
    resultats = []
    total_gain = 0
    wins = 0
    for _ in range(nombre):
        result, gain = jouer_un_slot()
        total_gain += gain
        if gain > 0:
            wins += 1
            resultats.append(f"{'  '.join(result)} → **+{gain}j** 🏆")
        else:
            resultats.append(f"{'  '.join(result)} → Perdu")

    joueur["jetons"] += total_gain
    save_loto(data)

    # Affichage
    lines = "\n".join(resultats)
    if len(lines) > 1800:
        lines = lines[:1800] + "\n..."

    couleur = 0x2ecc71 if total_gain > 0 else 0xe74c3c
    embed = discord.Embed(
        title=f"🎰 Multi-Slot — {nombre} tours !",
        description=lines,
        color=couleur
    )
    embed.add_field(
        name="📊 Résumé",
        value=(
            f"🏆 Victoires : **{wins}/{nombre}**\n"
            f"💰 Gain total : **+{total_gain} jeton(s)**\n"
            f"📉 Coût : **{jetons_utilisés} jeton(s)** + **{tours_gratuits_utilisés} tour(s) gratuit(s)**\n"
            f"✅ Profit net : **{total_gain - jetons_utilisés:+} jeton(s)**\n\n"
            f"💰 Solde : **{joueur['jetons']} jeton(s)** | 🎰 Tours gratuits : **{joueur['tours_gratuits']}**"
        ),
        inline=False
    )
    embed.set_footer(text="💎x3=50j | 7️⃣x3=30j | ⭐x3=20j | 🍊x3=10j | 🍋x3=8j | 🍒x3=5j")
    await interaction.response.send_message(embed=embed)

# ─── Loterie quotidienne ──────────────────────
@bot.tree.command(name="loto-quotidien", description="🎟️ Participer à la loterie quotidienne (1 jeton = 1 ticket)")
@app_commands.describe(tickets="Nombre de tickets à acheter")
async def loto_quotidien(interaction: discord.Interaction, tickets: int):
    if tickets < 1:
        await interaction.response.send_message("❌ Tu dois acheter au moins 1 ticket.", ephemeral=True)
        return
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)
    if joueur["jetons"] < tickets:
        await interaction.response.send_message(f"❌ Tu n'as que **{joueur['jetons']} jeton(s)**, il t'en faut **{tickets}**.", ephemeral=True)
        return
    joueur["jetons"] -= tickets
    if gid not in data["loterie_quotidienne"]:
        data["loterie_quotidienne"][gid] = {"participants": {}, "recompense": "À définir"}
    data["loterie_quotidienne"][gid]["participants"][uid] = data["loterie_quotidienne"][gid]["participants"].get(uid, 0) + tickets
    save_loto(data)
    total = data["loterie_quotidienne"][gid]["participants"][uid]
    embed = discord.Embed(title="🎟️ Loterie Quotidienne", description=f"Tu as acheté **{tickets} ticket(s)** !\nTu as maintenant **{total} ticket(s)** dans cette loterie.\n\n*Plus t'as de tickets, plus t'as de chances !*", color=0x3498db)
    await interaction.response.send_message(embed=embed)

# ─── Loterie hebdo ────────────────────────────
@bot.tree.command(name="loto-hebdo", description="🎟️ Participer à la loterie hebdomadaire (1 jeton = 1 ticket)")
@app_commands.describe(tickets="Nombre de tickets à acheter")
async def loto_hebdo(interaction: discord.Interaction, tickets: int):
    if tickets < 1:
        await interaction.response.send_message("❌ Tu dois acheter au moins 1 ticket.", ephemeral=True)
        return
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)
    if joueur["jetons"] < tickets:
        await interaction.response.send_message(f"❌ Tu n'as que **{joueur['jetons']} jeton(s)**, il t'en faut **{tickets}**.", ephemeral=True)
        return
    joueur["jetons"] -= tickets
    if gid not in data["loterie_hebdo"]:
        data["loterie_hebdo"][gid] = {"participants": {}, "recompense": "À définir"}
    data["loterie_hebdo"][gid]["participants"][uid] = data["loterie_hebdo"][gid]["participants"].get(uid, 0) + tickets
    save_loto(data)
    total = data["loterie_hebdo"][gid]["participants"][uid]
    embed = discord.Embed(title="🎟️ Loterie Hebdomadaire", description=f"Tu as acheté **{tickets} ticket(s)** !\nTu as maintenant **{total} ticket(s)** dans cette loterie.\n\n*Plus t'as de tickets, plus t'as de chances !*", color=0x9b59b6)
    await interaction.response.send_message(embed=embed)

# ─── Setup loto ───────────────────────────────
@bot.tree.command(name="setup-loto", description="⚙️ Définir la récompense d'une loterie")
@app_commands.describe(type_loto="quotidienne ou hebdo", recompense="La récompense")
@app_commands.checks.has_permissions(administrator=True)
async def setup_loto(interaction: discord.Interaction, type_loto: str, recompense: str):
    data = load_loto()
    gid = str(interaction.guild.id)
    if type_loto.lower() == "quotidienne":
        if gid not in data["loterie_quotidienne"]:
            data["loterie_quotidienne"][gid] = {"participants": {}, "recompense": recompense}
        else:
            data["loterie_quotidienne"][gid]["recompense"] = recompense
        save_loto(data)
        await interaction.response.send_message(f"✅ Récompense quotidienne : **{recompense}**", ephemeral=True)
    elif type_loto.lower() == "hebdo":
        if gid not in data["loterie_hebdo"]:
            data["loterie_hebdo"][gid] = {"participants": {}, "recompense": recompense}
        else:
            data["loterie_hebdo"][gid]["recompense"] = recompense
        save_loto(data)
        await interaction.response.send_message(f"✅ Récompense hebdo : **{recompense}**", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Tape `quotidienne` ou `hebdo`.", ephemeral=True)

# ─── Tirage loto ──────────────────────────────
@bot.tree.command(name="tirer-loto", description="🎰 Lancer le tirage d'une loterie")
@app_commands.describe(type_loto="quotidienne ou hebdo")
@app_commands.checks.has_permissions(administrator=True)
async def tirer_loto(interaction: discord.Interaction, type_loto: str):
    await interaction.response.defer()
    data = load_loto()
    gid = str(interaction.guild.id)
    if type_loto.lower() == "quotidienne":
        loterie = data["loterie_quotidienne"].get(gid)
        titre = "🎟️ Loterie Quotidienne"
        couleur = 0x3498db
    elif type_loto.lower() == "hebdo":
        loterie = data["loterie_hebdo"].get(gid)
        titre = "🎟️ Loterie Hebdomadaire"
        couleur = 0x9b59b6
    else:
        await interaction.followup.send("❌ Tape `quotidienne` ou `hebdo`.", ephemeral=True)
        return
    if not loterie or not loterie.get("participants"):
        await interaction.followup.send("❌ Aucun participant dans cette loterie.")
        return
    pool = []
    for uid, nb_tickets in loterie["participants"].items():
        pool.extend([uid] * nb_tickets)
    gagnant_id = random.choice(pool)
    recompense = loterie.get("recompense", "Surprise !")
    if type_loto.lower() == "quotidienne":
        data["loterie_quotidienne"][gid] = {"participants": {}, "recompense": recompense}
    else:
        data["loterie_hebdo"][gid] = {"participants": {}, "recompense": recompense}
    save_loto(data)
    embed = discord.Embed(
        title=f"🎉 {titre} — Résultat !",
        description=f"🏆 **Félicitations à <@{gagnant_id}> !**\n\nTu remportes **{recompense}** !\n*(Tiré au sort parmi {len(pool)} ticket(s))*",
        color=couleur
    )
    await interaction.followup.send(embed=embed)

# ─── Voir loto ────────────────────────────────
@bot.tree.command(name="voir-loto", description="👀 Voir les participants d'une loterie")
@app_commands.describe(type_loto="quotidienne ou hebdo")
async def voir_loto(interaction: discord.Interaction, type_loto: str):
    data = load_loto()
    gid = str(interaction.guild.id)
    if type_loto.lower() == "quotidienne":
        loterie = data["loterie_quotidienne"].get(gid)
        titre = "🎟️ Loterie Quotidienne"
        couleur = 0x3498db
    elif type_loto.lower() == "hebdo":
        loterie = data["loterie_hebdo"].get(gid)
        titre = "🎟️ Loterie Hebdomadaire"
        couleur = 0x9b59b6
    else:
        await interaction.response.send_message("❌ Tape `quotidienne` ou `hebdo`.", ephemeral=True)
        return
    if not loterie or not loterie.get("participants"):
        await interaction.response.send_message("❌ Aucun participant pour l'instant.", ephemeral=True)
        return
    total = sum(loterie["participants"].values())
    lines = []
    for uid, nb in sorted(loterie["participants"].items(), key=lambda x: x[1], reverse=True):
        pct = round((nb / total) * 100, 1)
        lines.append(f"<@{uid}> — **{nb} ticket(s)** ({pct}% de chances)")
    embed = discord.Embed(title=titre, description="\n".join(lines), color=couleur)
    embed.add_field(name="🎁 Récompense", value=loterie.get("recompense", "Non définie"), inline=False)
    embed.set_footer(text=f"Total : {total} ticket(s)")
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
