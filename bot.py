import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, random, os
from datetime import datetime, timedelta

# ══════════════════════════════════════════════
#  METS TON TOKEN ICI
# ══════════════════════════════════════════════
TOKEN = "METS_TON_TOKEN_ICI"

DATA_FILE = "data.json"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def load():
    if not os.path.exists(DATA_FILE):
        return {"giveaways": {}, "snapshots": {}}
    with open(DATA_FILE) as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash prêtes")
    except Exception as e:
        print(f"❌ Erreur : {e}")
    check_giveaways.start()

async def snapshot_invites(guild):
    data = load()
    invites = await guild.invites()
    data["snapshots"][str(guild.id)] = {
        inv.code: {
            "uses": inv.uses,
            "inviter": str(inv.inviter.id) if inv.inviter else None
        }
        for inv in invites
    }
    save(data)

async def count_new_invites(guild, user_id):
    data = load()
    snapshot = data["snapshots"].get(str(guild.id), {})
    current_invites = await guild.invites()
    count = 0
    for inv in current_invites:
        if inv.inviter and str(inv.inviter.id) == str(user_id):
            old_uses = snapshot.get(inv.code, {}).get("uses", 0)
            count += inv.uses - old_uses
    return count

@bot.tree.command(name="giveaway", description="🎉 Lancer un giveaway avec condition d'invitations")
@app_commands.describe(
    prix="Ce que le gagnant remporte",
    duree_minutes="Durée du giveaway en minutes",
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
            f"**Condition :** Inviter **{invitations_requises}** personne(s) sur le serveur\n"
            f"**Comment participer :** Invite des gens puis clique sur ✅\n\n"
            f"**Fin :** <t:{end_timestamp}:R>\n\n"
            f"*Le bot vérifie tes invitations automatiquement.*"
        ),
        color=0xf5a623
    )
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")

    view = GiveawayView(invitations_requises)
    msg = await target.send(embed=embed, view=view)

    data = load()
    data["giveaways"][str(msg.id)] = {
        "guild_id": str(guild.id),
        "channel_id": str(target.id),
        "message_id": str(msg.id),
        "prix": prix,
        "invitations_requises": invitations_requises,
        "end_timestamp": end_timestamp,
        "participants": [],
        "termine": False
    }
    save(data)

    await interaction.followup.send(f"✅ Giveaway lancé dans {target.mention} !", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, invitations_requises):
        super().__init__(timeout=None)
        self.invitations_requises = invitations_requises

    @discord.ui.button(label="✅ Je participe", style=discord.ButtonStyle.success)
    async def participer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = load()
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
            save(data)
            await interaction.followup.send(
                f"🎉 **Inscrit !** Tu as invité **{nb}** personne(s). Bonne chance !",
                ephemeral=True
            )
        else:
            manquants = gw["invitations_requises"] - nb
            await interaction.followup.send(
                f"❌ T'as invité **{nb}** personne(s).\n"
                f"Il t'en faut encore **{manquants}** pour participer.\n\n"
                f"💡 Invite des amis puis reviens cliquer !",
                ephemeral=True
            )


@bot.tree.command(name="leaderboard", description="🏆 Classement des invitations")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    invites = await guild.invites()
    data = load()
    snapshot = data["snapshots"].get(str(guild.id), {})

    scores = {}
    for inv in invites:
        if not inv.inviter:
            continue
        old = snapshot.get(inv.code, {}).get("uses", 0)
        new = inv.uses - old
        if new > 0:
            uid = str(inv.inviter.id)
            scores[uid] = scores.get(uid, 0) + new

    if not scores:
        await interaction.followup.send("Personne n'a encore invité depuis le dernier giveaway.")
        return

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, count) in enumerate(sorted_scores):
        member = guild.get_member(int(uid))
        name = member.display_name if member else f"<@{uid}>"
        lines.append(f"{medals[i]} **{name}** — {count} invitation(s)")

    embed = discord.Embed(
        title="🏆 Classement des invitations",
        description="\n".join(lines),
        color=0x2ecc71
    )
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="annuler", description="❌ Annuler le giveaway en cours")
@app_commands.checks.has_permissions(administrator=True)
async def annuler(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = load()
    found = False
    for gw_id, gw in data["giveaways"].items():
        if gw["guild_id"] == str(interaction.guild.id) and not gw["termine"]:
            gw["termine"] = True
            found = True
    save(data)
    if found:
        await interaction.followup.send("✅ Giveaway annulé.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Aucun giveaway en cours.", ephemeral=True)


@tasks.loop(seconds=30)
async def check_giveaways():
    data = load()
    now = int(datetime.utcnow().timestamp())
    for gw_id, gw in data["giveaways"].items():
        if gw["termine"]:
            continue
        if now >= gw["end_timestamp"]:
            gw["termine"] = True
            guild = bot.get_guild(int(gw["guild_id"]))
            if not guild:
                continue
            channel = guild.get_channel(int(gw["channel_id"]))
            if not channel:
                continue

            participants = gw["participants"]
            if not participants:
                await channel.send("🎉 Le giveaway est terminé mais **personne n'a participé** ! 😢")
            else:
                gagnant_id = random.choice(participants)
                await channel.send(
                    f"🎉 **Le giveaway est terminé !**\n\n"
                    f"🏆 Félicitations à <@{gagnant_id}> qui remporte **{gw['prix']}** !\n"
                    f"*(Tiré au sort parmi {len(participants)} participant(s))*"
                )
    save(data)

bot.run(TOKEN)
