import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, random, asyncio
from datetime import datetime, timedelta

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

TICKETS_FILE = "tickets.json"
GIVEAWAYS_FILE = "giveaways.json"

# ══════════════════════════════════════════════
#  DATA HELPERS
# ══════════════════════════════════════════════
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

# ══════════════════════════════════════════════
#  DÉMARRAGE
# ══════════════════════════════════════════════
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash prêtes")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    check_giveaways.start()

# ══════════════════════════════════════════════
#  TICKETS
# ══════════════════════════════════════════════
@bot.tree.command(name="panel", description="📩 Poster le panel de création de ticket")
@app_commands.describe(message="Le message à afficher sur le panel")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction, message: str):
    embed = discord.Embed(
        title="🎫 Support",
        description=message,
        color=0x5865f2
    )
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
    sujet = discord.ui.TextInput(
        label="Sujet",
        placeholder="Ex: Problème de paiement, question...",
        max_length=100
    )
    description = discord.ui.TextInput(
        label="Explique ton problème",
        placeholder="Décris en détail ce dont tu as besoin...",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        data = load_tickets()
        for ch_id, info in data["tickets"].items():
            if info["user_id"] == str(user.id) and info["ouvert"]:
                await interaction.response.send_message(
                    f"❌ T'as déjà un ticket ouvert : <#{ch_id}>",
                    ephemeral=True
                )
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

        channel = await guild.create_text_channel(
            f"ticket-{user.name}",
            category=category,
            overwrites=overwrites
        )

        data["tickets"][str(channel.id)] = {
            "user_id": str(user.id),
            "ouvert": True,
            "sujet": str(self.sujet)
        }
        save_tickets(data)

        embed = discord.Embed(
            title=f"🎫 Ticket de {user.display_name}",
            color=0x5865f2
        )
        embed.add_field(name="📌 Sujet", value=str(self.sujet), inline=False)
        embed.add_field(name="📝 Description", value=str(self.description), inline=False)
        embed.set_footer(text="Un admin va te répondre bientôt. Clique sur 🔒 pour fermer le ticket.")

        await channel.send(
            content=f"{user.mention} | <@&{guild.owner_id}>",
            embed=embed,
            view=TicketView()
        )

        await interaction.response.send_message(
            f"✅ Ton ticket a été créé : {channel.mention}",
            ephemeral=True
        )


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
        await interaction.response.send_message("🔒 Ticket fermé. Le salon sera supprimé dans 5 secondes...")
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
    await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
    await asyncio.sleep(5)
    await channel.delete()


# ══════════════════════════════════════════════
#  GIVEAWAY — HELPERS
# ══════════════════════════════════════════════
async def snapshot_invites(guild):
    data = load_giveaways()
    invites = await guild.invites()
    data["snapshots"][str(guild.id)] = {
        inv.code: {
            "uses": inv.uses,
            "inviter": str(inv.inviter.id) if inv.inviter else None
        }
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
        embed = discord.Embed(
            title="🎉 Giveaway terminé",
            description="Personne n'a participé... 😢",
            color=0xe74c3c
        )
        await channel.send(embed=embed)
        return

    gagnant_id = random.choice(participants)
    embed = discord.Embed(
        title="🎉 Giveaway terminé !",
        description=(
            f"🏆 **Félicitations à <@{gagnant_id}> !**\n\n"
            f"Tu remportes **{gw['prix']}** !\n\n"
            f"*(Tiré au sort parmi {len(participants)} participant(s))*"
        ),
        color=0xf5a623
    )
    await channel.send(embed=embed)


# ══════════════════════════════════════════════
#  /giveaway
# ══════════════════════════════════════════════
@bot.tree.command(name="giveaway", description="🎉 Lancer un giveaway")
@app_commands.describe(
    prix="Ce que le gagnant remporte",
    duree_minutes="Durée en minutes",
    invitations_requises="Nombre d'invitations minimum pour participer",
    salon="Salon où poster le giveaway (optionnel)"
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

    end_time = datetime.utcnow() + timedelta(minutes=duree_minutes)
    end_timestamp = int(end_time.timestamp())

    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        description=(
            f"**Prix :** {prix}\n\n"
            f"**Condition :** Inviter **{invitations_requises}** personne(s) depuis maintenant\n"
            f"**Comment :** Invite des gens puis clique sur ✅\n\n"
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
        "annule": False
    }
    save_giveaways(data)

    await interaction.followup.send(f"✅ Giveaway lancé dans {target.mention} !", ephemeral=True)


# ─── Bouton rejoindre ─────────────────────────
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

        guild = interaction.guild
        nb = await count_new_invites(guild, user_id)

        if nb >= gw["invitations_requises"]:
            gw["participants"].append(user_id)
            gw["invite_credits"][user_id] = nb
            save_giveaways(data)
            await interaction.followup.send(
                f"🎉 **Inscrit !** Tu as invité **{nb}** personne(s). Bonne chance !",
                ephemeral=True
            )
        else:
            manquants = gw["invitations_requises"] - nb
            await interaction.followup.send(
                f"❌ Tu as invité **{nb}** personne(s).\n"
                f"Il t'en faut encore **{manquants}** pour participer.\n\n"
                f"💡 Invite des amis puis reviens cliquer !",
                ephemeral=True
            )


# ══════════════════════════════════════════════
#  /cancel
# ══════════════════════════════════════════════
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
                embed = discord.Embed(
                    title="❌ Giveaway annulé",
                    description=(
                        f"Le giveaway pour **{gw['prix']}** a été annulé.\n"
                        f"Les invitations des **{len(gw['participants'])}** participant(s) ont été sauvegardées."
                    ),
                    color=0xe74c3c
                )
                await channel.send(embed=embed)
            break
    save_giveaways(data)
    if found:
        await interaction.followup.send("✅ Giveaway annulé. Les invitations sont sauvegardées.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Aucun giveaway en cours.", ephemeral=True)


# ══════════════════════════════════════════════
#  /avancer
# ══════════════════════════════════════════════
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
    if found:
        await interaction.followup.send("✅ Giveaway terminé et gagnant tiré au sort !", ephemeral=True)
    else:
        await interaction.followup.send("❌ Aucun giveaway en cours.", ephemeral=True)


# ══════════════════════════════════════════════
#  /invites-sauvegardees
# ══════════════════════════════════════════════
@bot.tree.command(name="invites-sauvegardees", description="📋 Voir les invitations sauvegardées du dernier giveaway")
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

    lines = []
    for uid, count in last_gw["invite_credits"].items():
        lines.append(f"<@{uid}> — **{count}** invitation(s)")

    embed = discord.Embed(
        title="📋 Invitations sauvegardées",
        description="\n".join(lines),
        color=0x3498db
    )
    embed.set_footer(text=f"Prix : {last_gw['prix']}")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════
#  Check automatique giveaways
# ══════════════════════════════════════════════
@tasks.loop(seconds=30)
async def check_giveaways():
    data = load_giveaways()
    now = int(datetime.utcnow().timestamp())
    for gw_id, gw in data["giveaways"].items():
        if gw["termine"]:
            continue
        if now >= gw["end_timestamp"]:
            await terminer_giveaway(gw)
    save_giveaways(data)

@check_giveaways.before_loop
async def before_check():
    await bot.wait_until_ready()


bot.run(TOKEN)
