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
INVITES_FILE = "invites.json"

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

def load_invites():
    if not os.path.exists(INVITES_FILE):
        return {}
    with open(INVITES_FILE) as f:
        return json.load(f)

def save_invites(data):
    with open(INVITES_FILE, "w") as f:
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

def get_invite_count(guild_id: str, user_id: str) -> int:
    """Retourne le total d'invitations d'un joueur (permanent, hors reset)."""
    data = load_invites()
    return data.get(str(guild_id), {}).get(str(user_id), 0)

def add_invite(guild_id: str, user_id: str, amount: int = 1):
    """Ajoute des invitations au compteur total d'un joueur."""
    data = load_invites()
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in data:
        data[gid] = {}
    data[gid][uid] = data[gid].get(uid, 0) + amount
    save_invites(data)

# ══════════════════════════════════════════════════════
#  DÉMARRAGE
# ══════════════════════════════════════════════════════
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
    bot.add_view(TicketTypeView())
    bot.add_view(GiveawayVIPView())
    check_giveaways.start()

@bot.event
async def on_guild_join(guild):
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"✅ Sync {guild.name}")
    except Exception as e:
        print(f"❌ Erreur sync {guild.name} : {e}")

# ══════════════════════════════════════════════════════
#  SYSTÈME WELCOME + COMPTAGE INVITATIONS TOTAL
# ══════════════════════════════════════════════════════
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
                # ✅ Compteur permanent d'invitations (toutes invits confondues)
                if inviter:
                    add_invite(str(guild.id), str(inviter.id), 1)
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
                total_inv = get_invite_count(str(guild.id), str(inviter.id))
                embed.add_field(
                    name="📨 Invité par",
                    value=f"{inviter.mention} (**{total_inv}** invit(s) au total)",
                    inline=True
                )
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
    gid = str(interaction.guild.id)
    if gid not in config:
        config[gid] = {}
    config[gid]["welcome_channel"] = str(salon.id)
    config[gid]["welcome_role"] = str(role.id)
    save_config(config)
    embed = discord.Embed(
        title="✅ Bienvenue configuré",
        description=f"**Salon :** {salon.mention}\n**Rôle :** {role.mention}",
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════════════
#  COMMANDES INVITATIONS
# ══════════════════════════════════════════════════════

@bot.tree.command(name="mes-invitations", description="📊 Voir ton nombre total d'invitations")
@app_commands.describe(membre="Voir les invitations d'un autre membre (optionnel)")
async def mes_invitations(interaction: discord.Interaction, membre: discord.Member = None):
    cible = membre or interaction.user
    total = get_invite_count(str(interaction.guild.id), str(cible.id))
    montant = total * 50000

    embed = discord.Embed(title="📨 Invitations", color=0x5865f2)
    embed.set_author(name=cible.display_name, icon_url=cible.display_avatar.url)
    embed.add_field(name="🔗 Total d'invitations", value=f"**{total}** invitation(s)", inline=True)
    embed.add_field(
        name="💰 Valeur estimée",
        value=f"**{montant:,} $**".replace(",", " "),
        inline=True
    )

    if total >= 3:
        embed.add_field(
            name="✅ Éligible aux récompenses",
            value="Tu peux ouvrir un ticket et sélectionner **💰 Invit Récomp** pour récupérer ta récompense !",
            inline=False
        )
        embed.color = 0x2ecc71
    else:
        manquantes = 3 - total
        embed.add_field(
            name="❌ Non éligible",
            value=f"Il te manque **{manquantes}** invitation(s) pour atteindre le minimum de **3 invitations** requis.",
            inline=False
        )
        embed.color = 0xe74c3c

    embed.set_footer(text="50 000 $ par invitation • Minimum 3 invitations pour récupérer")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="reset-invitations", description="🔄 Remettre à zéro les invitations (d'un membre ou de tout le serveur)")
@app_commands.describe(membre="Membre à reset (laisser vide pour reset tout le serveur)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_invitations(interaction: discord.Interaction, membre: discord.Member = None):
    data = load_invites()
    gid = str(interaction.guild.id)

    if membre:
        uid = str(membre.id)
        if gid in data and uid in data[gid]:
            data[gid][uid] = 0
        save_invites(data)
        embed = discord.Embed(
            title="🔄 Reset effectué",
            description=f"Les invitations de {membre.mention} ont été remises à **0**.",
            color=0xe67e22
        )
    else:
        data[gid] = {}
        save_invites(data)
        embed = discord.Embed(
            title="🔄 Reset total effectué",
            description="Toutes les invitations du serveur ont été remises à **0**.",
            color=0xe74c3c
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="classement-invitations", description="🏆 Classement des meilleurs inviteurs du serveur")
async def classement_invitations(interaction: discord.Interaction):
    data = load_invites()
    gid = str(interaction.guild.id)
    guild_data = data.get(gid, {})

    if not guild_data:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📨 Classement invitations",
                description="Aucune invitation enregistrée pour l'instant.",
                color=0x95a5a6
            ),
            ephemeral=True
        )
        return

    sorted_inv = sorted(guild_data.items(), key=lambda x: x[1], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, count) in enumerate(sorted_inv):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"<@{uid}>"
        montant = count * 50000
        lines.append(f"{medals[i]} **{name}** — {count} invit(s) • `{montant:,} $`".replace(",", " "))

    embed = discord.Embed(
        title="🏆 Classement des Inviteurs",
        description="\n".join(lines),
        color=0xf5a623
    )
    embed.set_footer(text="50 000 $ par invitation")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajouter-invitations", description="➕ Ajouter manuellement des invitations à un membre")
@app_commands.describe(membre="Le membre", nombre="Nombre d'invitations à ajouter")
@app_commands.checks.has_permissions(administrator=True)
async def ajouter_invitations(interaction: discord.Interaction, membre: discord.Member, nombre: int):
    add_invite(str(interaction.guild.id), str(membre.id), nombre)
    total = get_invite_count(str(interaction.guild.id), str(membre.id))
    embed = discord.Embed(
        title="✅ Invitations ajoutées",
        description=f"{membre.mention} a reçu **+{nombre}** invitation(s) !\n💎 Total : **{total}** invitation(s)",
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════
#  TICKETS
# ══════════════════════════════════════════════════════

TICKET_TYPES = [
    ("💰 Invit Récomp", "invit_recomp", "Récupérer ta récompense d'invitations (min. 3)"),
    ("🛒 Achat / Commande", "achat", "Passer une commande ou effectuer un achat"),
    ("⚠️ Signalement", "signalement", "Signaler un joueur ou un problème"),
    ("🎁 Réclamation Giveaway", "giveaway", "Réclamer un gain de giveaway"),
    ("❓ Question / Support", "support", "Question générale ou demande d'aide"),
    ("✏️ Autre (personnalisé)", "autre", "Écrire ton propre justificatif"),
]

@bot.tree.command(name="panel", description="📩 Poster le panel de création de ticket")
@app_commands.describe(message="Le message à afficher sur le panel")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction, message: str):
    embed = discord.Embed(
        title="🎫 Support & Assistance",
        description=message,
        color=0x5865f2
    )
    embed.set_footer(text="Clique sur le bouton ci-dessous pour ouvrir un ticket")
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("✅ Panel posté !", ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifier si l'user a déjà un ticket ouvert
        data = load_tickets()
        for ch_id, info in data["tickets"].items():
            if info["user_id"] == str(interaction.user.id) and info["ouvert"]:
                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : <#{ch_id}>",
                    ephemeral=True
                )
                return
        embed = discord.Embed(
            title="🎫 Nouveau Ticket",
            description=(
                "Sélectionne la **raison de ta demande** dans le menu ci-dessous.\n"
                "Tu pourras ensuite ajouter tes informations."
            ),
            color=0x5865f2
        )
        await interaction.response.send_message(embed=embed, view=TicketTypeView(), ephemeral=True)


class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        custom_id="ticket_type_select",
        placeholder="📋 Choisis le type de ta demande...",
        options=[
            discord.SelectOption(label=label, value=value, description=desc)
            for label, value, desc in TICKET_TYPES
        ]
    )
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        ticket_type = select.values[0]
        if ticket_type == "invit_recomp":
            await interaction.response.send_modal(TicketInvitRecompModal())
        elif ticket_type == "autre":
            await interaction.response.send_modal(TicketCustomModal())
        else:
            label_map = {v: l for l, v, d in TICKET_TYPES}
            await interaction.response.send_modal(
                TicketStandardModal(ticket_type, label_map.get(ticket_type, ticket_type))
            )


class TicketStandardModal(discord.ui.Modal):
    def __init__(self, ticket_type: str, ticket_label: str):
        super().__init__(title=f"🎫 {ticket_label[:40]}")
        self.ticket_type = ticket_type
        self.ticket_label = ticket_label
        self.description = discord.ui.TextInput(
            label="Décris ta demande en détail",
            style=discord.TextStyle.paragraph,
            placeholder="Explique clairement ta demande...",
            max_length=1000
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        await creer_ticket(interaction, self.ticket_type, self.ticket_label, str(self.description), None)


class TicketCustomModal(discord.ui.Modal, title="✏️ Ticket personnalisé"):
    sujet = discord.ui.TextInput(
        label="Sujet",
        placeholder="Résume ta demande en quelques mots...",
        max_length=100
    )
    description = discord.ui.TextInput(
        label="Justificatif / Description",
        style=discord.TextStyle.paragraph,
        placeholder="Explique ta demande en détail...",
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await creer_ticket(
            interaction, "autre",
            f"✏️ {str(self.sujet)}",
            str(self.description),
            None
        )


class TicketInvitRecompModal(discord.ui.Modal, title="💰 Invit Récomp"):
    pseudo_jeu = discord.ui.TextInput(
        label="Ton pseudo en jeu",
        placeholder="Ex: MonPseudo123",
        max_length=50
    )
    infos_supp = discord.ui.TextInput(
        label="Informations supplémentaires (optionnel)",
        style=discord.TextStyle.paragraph,
        placeholder="Toute info utile pour le traitement...",
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        gid = str(guild.id)
        uid = str(user.id)

        total_invites = get_invite_count(gid, uid)
        montant = total_invites * 50000

        config = load_config()
        guild_config = config.get(gid, {})
        admin_role_id = guild_config.get("admin_role")

        if total_invites < 3:
            # ❌ Pas assez d'invitations — message automatique de refus
            embed = discord.Embed(
                title="❌ Invitations insuffisantes",
                description=(
                    f"Désolé {user.mention}, tu n'as **pas encore atteint le minimum requis** "
                    f"pour récupérer ta récompense d'invitations.\n\n"
                    f"```\n"
                    f"📨 Tes invitations totales : {total_invites}\n"
                    f"🎯 Minimum requis         : 3 invitations\n"
                    f"⛔ Il te manque           : {3 - total_invites} invitation(s)\n"
                    f"```\n"
                    f"💡 **Continue d'inviter des amis** sur le serveur pour débloquer ta récompense !\n\n"
                    f"*Rappel : 50 000 $ par invitation confirmée — les invitations de giveaway ne sont pas comptabilisées.*"
                ),
                color=0xe74c3c
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="Minimum 3 invitations requises • Les invits giveaway ne comptent pas")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ✅ Assez d'invitations — créer le ticket
        await creer_ticket(
            interaction,
            "invit_recomp",
            "💰 Invit Récomp",
            f"**Pseudo en jeu :** {str(self.pseudo_jeu)}\n**Infos :** {str(self.infos_supp) if self.infos_supp.value else 'Aucune'}",
            {"total_invites": total_invites, "montant": montant, "admin_role_id": admin_role_id}
        )


async def creer_ticket(
    interaction: discord.Interaction,
    ticket_type: str,
    ticket_label: str,
    description: str,
    extra_data: dict
):
    guild = interaction.guild
    user = interaction.user
    data = load_tickets()

    # Double check ticket déjà ouvert
    for ch_id, info in data["tickets"].items():
        if info["user_id"] == str(user.id) and info["ouvert"]:
            try:
                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : <#{ch_id}>", ephemeral=True
                )
            except discord.errors.InteractionResponded:
                pass
            return

    # Catégorie tickets
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
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    safe_name = user.name[:15].replace(" ", "-")
    channel = await guild.create_text_channel(
        f"ticket-{safe_name}", category=category, overwrites=overwrites
    )

    data["tickets"][str(channel.id)] = {
        "user_id": str(user.id),
        "ouvert": True,
        "type": ticket_type,
        "sujet": ticket_label
    }
    save_tickets(data)

    # Couleur selon le type
    color_map = {
        "invit_recomp": 0xf5a623,
        "achat": 0x2ecc71,
        "signalement": 0xe74c3c,
        "giveaway": 0x9b59b6,
        "support": 0x3498db,
        "autre": 0x95a5a6,
    }

    embed = discord.Embed(
        title=f"🎫 Ticket — {ticket_label}",
        color=color_map.get(ticket_type, 0x5865f2)
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="📋 Type", value=ticket_label, inline=True)
    embed.add_field(name="👤 Demandeur", value=user.mention, inline=True)
    embed.add_field(
        name="📅 Ouvert le",
        value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
        inline=True
    )
    embed.add_field(name="📝 Description", value=description or "Aucune description fournie.", inline=False)
    embed.set_footer(text="Un admin va te répondre bientôt • Clique sur 🔒 pour fermer")

    # ── Ticket Invit Récomp : message spécial avec mention admin ──
    if ticket_type == "invit_recomp" and extra_data:
        total_invites = extra_data["total_invites"]
        montant = extra_data["montant"]
        admin_role_id = extra_data.get("admin_role_id")

        embed.add_field(
            name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            value=(
                f"💎 **Récapitulatif Invit Récomp**\n\n"
                f"📨 **Invitations totales :** `{total_invites}`\n"
                f"💰 **Montant dû :** `{montant:,} $`\n".replace(",", " ") +
                f"📌 *50 000 $ × {total_invites} invitation(s)*"
            ),
            inline=False
        )

        admin_mention = f"<@&{admin_role_id}>" if admin_role_id else f"<@{guild.owner_id}>"

        auto_msg = discord.Embed(
            title="🔔 Nouvelle demande de récompense d'invitations !",
            description=(
                f"Hey {admin_mention} ! 👋\n\n"
                f"**{user.mention}** vient de soumettre une demande de récompense pour ses invitations.\n\n"
                f"```\n"
                f"👤 Joueur              : {user.display_name}\n"
                f"📨 Invitations totales : {total_invites}\n"
                f"💰 Montant à verser   : {montant:,} $\n".replace(",", " ") +
                f"```\n"
                f"⚡ **Un admin arrive pour traiter la demande !**"
            ),
            color=0xf5a623
        )
        auto_msg.set_thumbnail(url=user.display_avatar.url)
        auto_msg.set_footer(
            text=f"Ticket créé automatiquement • {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC"
        )

        await channel.send(embed=embed, view=TicketView())
        await channel.send(content=admin_mention, embed=auto_msg)

    else:
        # Ticket standard — ping admin/owner
        config = load_config()
        guild_config = config.get(str(guild.id), {})
        admin_role_id = guild_config.get("admin_role")
        ping = f"<@&{admin_role_id}>" if admin_role_id else f"<@{guild.owner_id}>"
        await channel.send(content=f"{user.mention} | {ping}", embed=embed, view=TicketView())

    # Confirmation éphémère à l'utilisateur
    confirm_embed = discord.Embed(
        title="✅ Ticket créé !",
        description=(
            f"Ton ticket a bien été ouvert : {channel.mention}\n"
            f"Un membre de l'équipe va te répondre très bientôt ! 🙌"
        ),
        color=0x2ecc71
    )
    try:
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)
    except discord.errors.InteractionResponded:
        pass


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
        embed = discord.Embed(
            title="🔒 Ticket fermé",
            description=f"Ce ticket a été fermé par {interaction.user.mention}.\nSuppression dans **5 secondes**...",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed)
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
    embed = discord.Embed(
        title="🔒 Fermeture en cours...",
        description="Ce ticket sera supprimé dans **5 secondes**.",
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(5)
    await channel.delete()


@bot.tree.command(name="setup-admin-role", description="⚙️ Définir le rôle admin/staff à mentionner dans les tickets")
@app_commands.describe(role="Le rôle admin à mentionner")
@app_commands.checks.has_permissions(administrator=True)
async def setup_admin_role(interaction: discord.Interaction, role: discord.Role):
    config = load_config()
    gid = str(interaction.guild.id)
    if gid not in config:
        config[gid] = {}
    config[gid]["admin_role"] = str(role.id)
    save_config(config)
    embed = discord.Embed(
        title="✅ Rôle admin configuré",
        description=(
            f"Le rôle {role.mention} sera mentionné dans les tickets "
            f"et les demandes d'invitations récompenses."
        ),
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════
#  GIVEAWAY
# ══════════════════════════════════════════════════════
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
        await channel.send(embed=discord.Embed(
            title="🎉 Giveaway terminé",
            description="Personne n'a participé... 😢",
            color=0xe74c3c
        ))
        return
    gagnant_id = random.choice(participants)
    embed = discord.Embed(
        title="🎉 Giveaway terminé !",
        description=(
            f"🏆 **Félicitations à <@{gagnant_id}> !**\n\n"
            f"Tu remportes **{gw['prix']}** !\n"
            f"*(Tiré parmi {len(participants)} participant(s))*"
        ),
        color=0xf5a623
    )
    await channel.send(embed=embed)

@bot.tree.command(name="giveaway", description="🎉 Lancer un giveaway")
@app_commands.describe(
    prix="Récompense",
    duree_minutes="Durée en minutes",
    invitations_requises="Invitations minimum",
    salon="Salon (optionnel)"
)
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(
    interaction: discord.Interaction,
    prix: str,
    duree_minutes: int,
    invitations_requises: int,
    salon: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    target = salon or interaction.channel
    await snapshot_invites(guild)
    end_timestamp = int((datetime.now(timezone.utc) + timedelta(minutes=duree_minutes)).timestamp())
    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        description=(
            f"**Prix :** {prix}\n\n"
            f"**Condition :** Inviter **{invitations_requises}** personne(s) depuis maintenant\n"
            f"**Comment :** Invite des gens puis clique ✅\n\n"
            f"**Fin :** <t:{end_timestamp}:R>\n\n"
            f"*Le bot vérifie tes invitations automatiquement.*"
        ),
        color=0xf5a623
    )
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    view = GiveawayView(invitations_requises)
    msg = await target.send(embed=embed, view=view)
    data = load_giveaways()
    data["giveaways"][str(msg.id)] = {
        "guild_id": str(guild.id),
        "channel_id": str(target.id),
        "message_id": str(msg.id),
        "prix": prix,
        "invitations_requises": invitations_requises,
        "end_timestamp": end_timestamp,
        "participants": [],
        "invite_credits": {},
        "termine": False,
        "annule": False,
        "vip_only": False
    }
    save_giveaways(data)
    await interaction.followup.send(f"✅ Giveaway lancé dans {target.mention} !", ephemeral=True)

class GiveawayView(discord.ui.View):
    def __init__(self, invitations_requises=0):
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
            await interaction.followup.send(
                f"🎉 **Inscrit !** Tu as invité **{nb}** personne(s). Bonne chance !",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Tu as invité **{nb}** personne(s). Il t'en faut encore **{gw['invitations_requises'] - nb}**.\n"
                f"💡 Invite des amis puis reviens !",
                ephemeral=True
            )

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
                await channel.send(embed=discord.Embed(
                    title="❌ Giveaway annulé",
                    description=f"Giveaway **{gw['prix']}** annulé.\nInvitations des **{len(gw['participants'])}** participants sauvegardées.",
                    color=0xe74c3c
                ))
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

# ══════════════════════════════════════════════════════
#  SYSTÈME VIP
# ══════════════════════════════════════════════════════

@bot.tree.command(name="setup-vip", description="👑 Créer la catégorie VIP avec ses salons dédiés")
@app_commands.describe(role_vip="Le rôle VIP à utiliser")
@app_commands.checks.has_permissions(administrator=True)
async def setup_vip(interaction: discord.Interaction, role_vip: discord.Role):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    config = load_config()
    gid = str(guild.id)
    if gid not in config:
        config[gid] = {}
    config[gid]["vip_role"] = str(role_vip.id)
    save_config(config)

    existing_cat = discord.utils.get(guild.categories, name="👑 VIP")
    if existing_cat:
        await interaction.followup.send(
            embed=discord.Embed(
                title="ℹ️ Catégorie VIP déjà existante",
                description=f"La catégorie **👑 VIP** existe déjà.\nRôle VIP enregistré : {role_vip.mention}",
                color=0xe67e22
            ),
            ephemeral=True
        )
        return

    # Permissions catégorie VIP
    overwrites_base = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role_vip: discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            read_message_history=True, add_reactions=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            manage_channels=True, manage_messages=True
        )
    }
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites_base[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )

    overwrites_readonly = {
        **overwrites_base,
        role_vip: discord.PermissionOverwrite(
            view_channel=True, send_messages=False,
            read_message_history=True, add_reactions=True
        )
    }

    category = await guild.create_category("👑 VIP", overwrites=overwrites_base)
    lounge       = await guild.create_text_channel("💎┃vip-lounge",     category=category, overwrites=overwrites_base)
    annonces     = await guild.create_text_channel("📢┃vip-annonces",   category=category, overwrites=overwrites_readonly)
    giveaways_ch = await guild.create_text_channel("🎁┃vip-giveaways",  category=category, overwrites=overwrites_readonly)
    avantages    = await guild.create_text_channel("⭐┃vip-avantages",  category=category, overwrites=overwrites_readonly)

    config[gid].update({
        "vip_category":  str(category.id),
        "vip_lounge":    str(lounge.id),
        "vip_annonces":  str(annonces.id),
        "vip_giveaways": str(giveaways_ch.id),
        "vip_avantages": str(avantages.id),
    })
    save_config(config)

    # Message de bienvenue dans le lounge
    await lounge.send(embed=discord.Embed(
        title="💎 Bienvenue dans le salon VIP !",
        description=(
            f"Félicitations pour ton accès **VIP** ! 🎉\n\n"
            f"En tant que membre VIP, tu as accès à :\n"
            f"• {lounge.mention} — Salon de discussion privé\n"
            f"• {annonces.mention} — Annonces exclusives VIP\n"
            f"• {giveaways_ch.mention} — Giveaways réservés aux VIP\n"
            f"• {avantages.mention} — Tes avantages & perks VIP\n\n"
            f"*Profite bien de tes privilèges !* 👑"
        ),
        color=0xf5a623
    ))

    # Message avantages
    await avantages.send(embed=discord.Embed(
        title="⭐ Avantages VIP",
        description=(
            f"En tant que membre {role_vip.mention}, tu bénéficies de :\n\n"
            f"🎁 **Giveaways exclusifs** — Participe à des giveaways réservés aux VIP\n"
            f"📢 **Annonces en avant-première** — Sois le premier informé\n"
            f"💬 **Salon privé** — Discute avec les autres membres VIP\n"
            f"👑 **Statut privilégié** — Reconnaissance sur le serveur\n"
        ),
        color=0xf5a623
    ))

    await interaction.followup.send(embed=discord.Embed(
        title="✅ Catégorie VIP créée !",
        description=(
            f"La zone **👑 VIP** a été configurée pour {role_vip.mention} !\n\n"
            f"**Salons créés :**\n"
            f"• {lounge.mention} — Lounge VIP\n"
            f"• {annonces.mention} — Annonces VIP\n"
            f"• {giveaways_ch.mention} — Giveaways VIP\n"
            f"• {avantages.mention} — Avantages VIP"
        ),
        color=0x2ecc71
    ), ephemeral=True)


@bot.tree.command(name="giveaway-vip", description="👑 Lancer un giveaway exclusif pour les membres VIP")
@app_commands.describe(
    prix="La récompense du giveaway",
    duree_minutes="Durée en minutes",
    salon="Salon cible (laisser vide pour utiliser le salon VIP configuré)"
)
@app_commands.checks.has_permissions(administrator=True)
async def giveaway_vip(
    interaction: discord.Interaction,
    prix: str,
    duree_minutes: int,
    salon: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)

    config = load_config()
    gid = str(interaction.guild.id)
    guild_config = config.get(gid, {})

    vip_role_id    = guild_config.get("vip_role")
    vip_giveaways_id = guild_config.get("vip_giveaways")

    if not vip_role_id:
        await interaction.followup.send(
            "❌ Aucun rôle VIP configuré. Utilise `/setup-vip` d'abord.", ephemeral=True
        )
        return

    vip_role = interaction.guild.get_role(int(vip_role_id))

    if salon:
        target = salon
    elif vip_giveaways_id:
        target = interaction.guild.get_channel(int(vip_giveaways_id))
    else:
        target = interaction.channel

    if not target:
        await interaction.followup.send("❌ Salon introuvable.", ephemeral=True)
        return

    end_timestamp = int((datetime.now(timezone.utc) + timedelta(minutes=duree_minutes)).timestamp())

    embed = discord.Embed(
        title="👑 GIVEAWAY VIP EXCLUSIF",
        description=(
            f"🎁 **Prix :** {prix}\n\n"
            f"👑 **Réservé aux :** {vip_role.mention if vip_role else 'VIP'}\n"
            f"⏰ **Fin :** <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Clique sur **✅ Participer** pour tenter ta chance !\n"
            f"*Ce giveaway est exclusivement réservé aux membres VIP.*"
        ),
        color=0xf5a623
    )
    embed.set_footer(text=f"Giveaway VIP • Lancé par {interaction.user.display_name}")

    view = GiveawayVIPView(vip_role_id)
    msg = await target.send(embed=embed, view=view)

    data = load_giveaways()
    data["giveaways"][str(msg.id)] = {
        "guild_id":            str(interaction.guild.id),
        "channel_id":          str(target.id),
        "message_id":          str(msg.id),
        "prix":                prix,
        "invitations_requises": 0,
        "end_timestamp":       end_timestamp,
        "participants":        [],
        "invite_credits":      {},
        "termine":             False,
        "annule":              False,
        "vip_only":            True,
        "vip_role_id":         vip_role_id
    }
    save_giveaways(data)

    await interaction.followup.send(embed=discord.Embed(
        title="✅ Giveaway VIP lancé !",
        description=f"Le giveaway **{prix}** a été posté dans {target.mention} !",
        color=0x2ecc71
    ), ephemeral=True)


class GiveawayVIPView(discord.ui.View):
    def __init__(self, vip_role_id: str = None):
        super().__init__(timeout=None)
        self.vip_role_id = vip_role_id

    @discord.ui.button(label="✅ Participer", style=discord.ButtonStyle.success, custom_id="join_giveaway_vip")
    async def participer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        data = load_giveaways()
        gw = data["giveaways"].get(str(interaction.message.id))

        if not gw or gw["termine"]:
            await interaction.followup.send("❌ Ce giveaway est terminé.", ephemeral=True)
            return

        vip_role_id = gw.get("vip_role_id") or self.vip_role_id
        if vip_role_id:
            vip_role = interaction.guild.get_role(int(vip_role_id))
            if vip_role and vip_role not in interaction.user.roles:
                await interaction.followup.send(embed=discord.Embed(
                    title="👑 Accès refusé",
                    description=(
                        f"Désolé {interaction.user.mention}, ce giveaway est "
                        f"**exclusivement réservé aux membres VIP** ! 👑\n\n"
                        f"Tu dois avoir le rôle {vip_role.mention} pour participer."
                    ),
                    color=0xe74c3c
                ), ephemeral=True)
                return

        user_id = str(interaction.user.id)
        if user_id in gw["participants"]:
            await interaction.followup.send("✅ Tu es déjà inscrit au giveaway !", ephemeral=True)
            return

        gw["participants"].append(user_id)
        save_giveaways(data)

        await interaction.followup.send(embed=discord.Embed(
            title="🎉 Inscription confirmée !",
            description=(
                f"Tu es bien inscrit au giveaway **VIP** ! 👑\n\n"
                f"🎁 **Prix :** {gw['prix']}\n"
                f"👥 **Participants :** {len(gw['participants'])}\n\n"
                f"*Bonne chance ! Les résultats seront annoncés bientôt.*"
            ),
            color=0x2ecc71
        ), ephemeral=True)


@bot.tree.command(name="annoncer-vip", description="📢 Envoyer une annonce dans le salon VIP")
@app_commands.describe(titre="Titre de l'annonce", message="Contenu de l'annonce")
@app_commands.checks.has_permissions(administrator=True)
async def annoncer_vip(interaction: discord.Interaction, titre: str, message: str):
    config = load_config()
    gid = str(interaction.guild.id)
    guild_config = config.get(gid, {})

    vip_annonces_id = guild_config.get("vip_annonces")
    vip_role_id     = guild_config.get("vip_role")

    if not vip_annonces_id:
        await interaction.response.send_message(
            "❌ La catégorie VIP n'est pas configurée. Utilise `/setup-vip` d'abord.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(vip_annonces_id))
    if not channel:
        await interaction.response.send_message("❌ Salon VIP introuvable.", ephemeral=True)
        return

    vip_role = interaction.guild.get_role(int(vip_role_id)) if vip_role_id else None

    embed = discord.Embed(title=f"📢 {titre}", description=message, color=0xf5a623)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.set_footer(text=f"Annonce VIP • {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC")

    ping = vip_role.mention if vip_role else ""
    await channel.send(content=ping, embed=embed)

    await interaction.response.send_message(embed=discord.Embed(
        title="✅ Annonce envoyée !",
        description=f"L'annonce a été publiée dans {channel.mention}",
        color=0x2ecc71
    ), ephemeral=True)


@bot.tree.command(name="ajouter-vip", description="👑 Donner le rôle VIP à un membre")
@app_commands.describe(membre="Le membre à promouvoir VIP")
@app_commands.checks.has_permissions(administrator=True)
async def ajouter_vip(interaction: discord.Interaction, membre: discord.Member):
    config = load_config()
    gid = str(interaction.guild.id)
    vip_role_id = config.get(gid, {}).get("vip_role")

    if not vip_role_id:
        await interaction.response.send_message(
            "❌ Rôle VIP non configuré. Utilise `/setup-vip` d'abord.", ephemeral=True
        )
        return

    vip_role = interaction.guild.get_role(int(vip_role_id))
    if not vip_role:
        await interaction.response.send_message("❌ Rôle VIP introuvable.", ephemeral=True)
        return

    if vip_role in membre.roles:
        await interaction.response.send_message(f"ℹ️ {membre.mention} est déjà VIP.", ephemeral=True)
        return

    await membre.add_roles(vip_role)

    # Bienvenue dans le lounge VIP
    lounge_id = config.get(gid, {}).get("vip_lounge")
    if lounge_id:
        lounge = interaction.guild.get_channel(int(lounge_id))
        if lounge:
            await lounge.send(embed=discord.Embed(
                title="👑 Nouveau membre VIP !",
                description=(
                    f"Bienvenue {membre.mention} dans le **club VIP** ! 🎉\n\n"
                    f"Tu as maintenant accès à tous les avantages exclusifs VIP.\n"
                    f"Profite bien de tes privilèges ! 💎"
                ),
                color=0xf5a623
            ))

    await interaction.response.send_message(embed=discord.Embed(
        title="✅ Rôle VIP attribué",
        description=f"{membre.mention} est maintenant **VIP** ! 👑",
        color=0x2ecc71
    ), ephemeral=True)


@bot.tree.command(name="retirer-vip", description="👑 Retirer le rôle VIP à un membre")
@app_commands.describe(membre="Le membre à qui retirer le VIP")
@app_commands.checks.has_permissions(administrator=True)
async def retirer_vip(interaction: discord.Interaction, membre: discord.Member):
    config = load_config()
    gid = str(interaction.guild.id)
    vip_role_id = config.get(gid, {}).get("vip_role")

    if not vip_role_id:
        await interaction.response.send_message("❌ Rôle VIP non configuré.", ephemeral=True)
        return

    vip_role = interaction.guild.get_role(int(vip_role_id))
    if not vip_role or vip_role not in membre.roles:
        await interaction.response.send_message(f"ℹ️ {membre.mention} n'est pas VIP.", ephemeral=True)
        return

    await membre.remove_roles(vip_role)
    await interaction.response.send_message(embed=discord.Embed(
        title="🚫 Rôle VIP retiré",
        description=f"Le rôle VIP a été retiré à {membre.mention}.",
        color=0xe74c3c
    ), ephemeral=True)


@bot.tree.command(name="info-vip", description="👑 Voir la configuration de la zone VIP")
@app_commands.checks.has_permissions(administrator=True)
async def info_vip(interaction: discord.Interaction):
    config = load_config()
    gid = str(interaction.guild.id)
    gc = config.get(gid, {})

    vip_role_id = gc.get("vip_role")
    if not vip_role_id:
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ VIP non configuré",
            description="Utilise `/setup-vip` pour configurer la zone VIP.",
            color=0xe74c3c
        ), ephemeral=True)
        return

    vip_role = interaction.guild.get_role(int(vip_role_id))
    vip_members = len([m for m in interaction.guild.members if vip_role in m.roles]) if vip_role else 0

    def ch(key):
        cid = gc.get(key)
        return f"<#{cid}>" if cid else "Non configuré"

    embed = discord.Embed(title="👑 Configuration VIP", color=0xf5a623)
    embed.add_field(name="🎭 Rôle VIP",   value=vip_role.mention if vip_role else "Introuvable", inline=True)
    embed.add_field(name="👥 Membres VIP", value=f"**{vip_members}** membre(s)",                  inline=True)
    embed.add_field(name="📁 Catégorie",  value=ch("vip_category"),                               inline=True)
    embed.add_field(name="💬 Lounge",     value=ch("vip_lounge"),                                 inline=True)
    embed.add_field(name="📢 Annonces",   value=ch("vip_annonces"),                               inline=True)
    embed.add_field(name="🎁 Giveaways",  value=ch("vip_giveaways"),                              inline=True)
    embed.add_field(name="⭐ Avantages",  value=ch("vip_avantages"),                              inline=True)
    embed.set_footer(text="Utilise /setup-vip pour reconfigurer")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════
#  SYSTÈME LOTO / JETONS
# ══════════════════════════════════════════════════════

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
    embed = discord.Embed(
        title="🎟️ Jetons ajoutés",
        description=f"{membre.mention} a reçu **{quantite} jeton(s)** !\nSolde total : **{joueur['jetons']} jeton(s)**",
        color=0xf5a623
    )
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
    await interaction.response.send_message(embed=discord.Embed(
        title="❌ Jetons retirés",
        description=f"{membre.mention} a perdu **{quantite} jeton(s)**.\nSolde : **{joueur['jetons']} jeton(s)**",
        color=0xe74c3c
    ))

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

# ══════════════════════════════════════════════════════
#  /daily — Récupérer 5 tours gratuits
# ══════════════════════════════════════════════════════
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
        description=(
            f"Tu as reçu **5 tours de slot gratuits** ! 🎰\n"
            f"Tours gratuits disponibles : **{joueur['tours_gratuits']}**\n\n"
            f"Utilise `/slot` ou `/multi-slot` pour jouer !"
        ),
        color=0x2ecc71
    )
    embed.set_footer(text="Reviens demain pour en récupérer d'autres !")
    await interaction.response.send_message(embed=embed)

# ══════════════════════════════════════════════════════
#  MACHINE À SOUS
# ══════════════════════════════════════════════════════
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

@bot.tree.command(name="slot", description="🎰 Jouer à la machine à sous (1 jeton ou 1 tour gratuit)")
async def slot(interaction: discord.Interaction):
    data = load_loto()
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    joueur = get_joueur_data(data, gid, uid)

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
        desc = (
            f"{'  '.join(result)}\n\n"
            f"🏆 Tu gagnes **{gain} jeton(s)** !\n"
            f"💰 Solde : **{joueur['jetons']} jeton(s)** | 🎰 Tours gratuits : **{joueur['tours_gratuits']}**"
        )
        couleur = 0x2ecc71
    else:
        titre = "🎰 Perdu !"
        desc = (
            f"{'  '.join(result)}\n\n"
            f"Dommage... Réessaie !\n"
            f"💰 Solde : **{joueur['jetons']} jeton(s)** | 🎰 Tours gratuits : **{joueur['tours_gratuits']}**"
        )
        couleur = 0xe74c3c

    save_loto(data)
    embed = discord.Embed(title=titre, description=desc, color=couleur)
    embed.set_footer(text=f"{'Tour gratuit utilisé 🎁' if gratuit else 'Jeton utilisé 🎟️'} | 💎x3=50j | 7️⃣x3=30j | ⭐x3=20j | 🍊x3=10j | 🍋x3=8j | 🍒x3=5j")
    await interaction.response.send_message(embed=embed)

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

    tours_gratuits_dispo = joueur["tours_gratuits"]
    jetons_dispo = joueur["jetons"]
    total_dispo = tours_gratuits_dispo + jetons_dispo

    if total_dispo < nombre:
        await interaction.response.send_message(
            f"❌ Tu n'as pas assez !\n🎰 Tours gratuits : **{tours_gratuits_dispo}** | 💰 Jetons : **{jetons_dispo}**\n"
            f"Total disponible : **{total_dispo}** / {nombre} nécessaires.",
            ephemeral=True
        )
        return

    tours_gratuits_utilisés = min(tours_gratuits_dispo, nombre)
    jetons_utilisés = nombre - tours_gratuits_utilisés
    joueur["tours_gratuits"] -= tours_gratuits_utilisés
    joueur["jetons"] -= jetons_utilisés

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

# ══════════════════════════════════════════════════════
#  LOTERIE QUOTIDIENNE
# ══════════════════════════════════════════════════════
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
        await interaction.response.send_message(
            f"❌ Tu n'as que **{joueur['jetons']} jeton(s)**, il t'en faut **{tickets}**.", ephemeral=True
        )
        return
    joueur["jetons"] -= tickets
    if gid not in data["loterie_quotidienne"]:
        data["loterie_quotidienne"][gid] = {"participants": {}, "recompense": "À définir"}
    data["loterie_quotidienne"][gid]["participants"][uid] = \
        data["loterie_quotidienne"][gid]["participants"].get(uid, 0) + tickets
    save_loto(data)
    total = data["loterie_quotidienne"][gid]["participants"][uid]
    embed = discord.Embed(
        title="🎟️ Loterie Quotidienne",
        description=(
            f"Tu as acheté **{tickets} ticket(s)** !\n"
            f"Tu as maintenant **{total} ticket(s)** dans cette loterie.\n\n"
            f"*Plus t'as de tickets, plus t'as de chances !*"
        ),
        color=0x3498db
    )
    await interaction.response.send_message(embed=embed)

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
        await interaction.response.send_message(
            f"❌ Tu n'as que **{joueur['jetons']} jeton(s)**, il t'en faut **{tickets}**.", ephemeral=True
        )
        return
    joueur["jetons"] -= tickets
    if gid not in data["loterie_hebdo"]:
        data["loterie_hebdo"][gid] = {"participants": {}, "recompense": "À définir"}
    data["loterie_hebdo"][gid]["participants"][uid] = \
        data["loterie_hebdo"][gid]["participants"].get(uid, 0) + tickets
    save_loto(data)
    total = data["loterie_hebdo"][gid]["participants"][uid]
    embed = discord.Embed(
        title="🎟️ Loterie Hebdomadaire",
        description=(
            f"Tu as acheté **{tickets} ticket(s)** !\n"
            f"Tu as maintenant **{total} ticket(s)** dans cette loterie.\n\n"
            f"*Plus t'as de tickets, plus t'as de chances !*"
        ),
        color=0x9b59b6
    )
    await interaction.response.send_message(embed=embed)

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

@bot.tree.command(name="tirer-loto", description="🎰 Lancer le tirage d'une loterie")
@app_commands.describe(type_loto="quotidienne ou hebdo")
@app_commands.checks.has_permissions(administrator=True)
async def tirer_loto(interaction: discord.Interaction, type_loto: str):
    await interaction.response.defer()
    data = load_loto()
    gid = str(interaction.guild.id)
    if type_loto.lower() == "quotidienne":
        loterie = data["loterie_quotidienne"].get(gid)
        titre   = "🎟️ Loterie Quotidienne"
        couleur = 0x3498db
    elif type_loto.lower() == "hebdo":
        loterie = data["loterie_hebdo"].get(gid)
        titre   = "🎟️ Loterie Hebdomadaire"
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
        description=(
            f"🏆 **Félicitations à <@{gagnant_id}> !**\n\n"
            f"Tu remportes **{recompense}** !\n"
            f"*(Tiré au sort parmi {len(pool)} ticket(s))*"
        ),
        color=couleur
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="voir-loto", description="👀 Voir les participants d'une loterie")
@app_commands.describe(type_loto="quotidienne ou hebdo")
async def voir_loto(interaction: discord.Interaction, type_loto: str):
    data = load_loto()
    gid = str(interaction.guild.id)
    if type_loto.lower() == "quotidienne":
        loterie = data["loterie_quotidienne"].get(gid)
        titre   = "🎟️ Loterie Quotidienne"
        couleur = 0x3498db
    elif type_loto.lower() == "hebdo":
        loterie = data["loterie_hebdo"].get(gid)
        titre   = "🎟️ Loterie Hebdomadaire"
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