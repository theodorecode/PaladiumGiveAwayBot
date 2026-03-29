import discord
from discord.ext import commands
from discord import app_commands
import os
import json

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "tickets.json"

def load():
    if not os.path.exists(DATA_FILE):
        return {"tickets": {}}
    with open(DATA_FILE) as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── Démarrage ────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash prêtes")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")

# ══════════════════════════════════════════════
#  /panel — Poster le message avec bouton
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


# ─── Bouton ouvrir ticket ─────────────────────
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())


# ─── Modal : description du problème ─────────
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

        # Vérifier si le user a déjà un ticket ouvert
        data = load()
        for ch_id, info in data["tickets"].items():
            if info["user_id"] == str(user.id) and info["ouvert"]:
                await interaction.response.send_message(
                    f"❌ T'as déjà un ticket ouvert : <#{ch_id}>",
                    ephemeral=True
                )
                return

        # Créer catégorie Tickets si elle existe pas
        category = discord.utils.get(guild.categories, name="🎫 Tickets")
        if not category:
            category = await guild.create_category("🎫 Tickets")

        # Permissions : seulement le user + admins
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # Créer le salon
        channel = await guild.create_text_channel(
            f"ticket-{user.name}",
            category=category,
            overwrites=overwrites
        )

        # Sauvegarder
        data["tickets"][str(channel.id)] = {
            "user_id": str(user.id),
            "ouvert": True,
            "sujet": str(self.sujet)
        }
        save(data)

        # Message dans le ticket
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


# ─── Boutons dans le ticket ───────────────────
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = load()

        if str(channel.id) in data["tickets"]:
            data["tickets"][str(channel.id)]["ouvert"] = False
            save(data)

        await interaction.response.send_message("🔒 Ticket fermé. Le salon sera supprimé dans 5 secondes...")
        import asyncio
        await asyncio.sleep(5)
        await channel.delete()


# ══════════════════════════════════════════════
#  /fermer — Fermer un ticket manuellement
# ══════════════════════════════════════════════
@bot.tree.command(name="fermer", description="🔒 Fermer le ticket actuel")
@app_commands.checks.has_permissions(administrator=True)
async def fermer(interaction: discord.Interaction):
    channel = interaction.channel
    data = load()

    if str(channel.id) not in data["tickets"]:
        await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        return

    data["tickets"][str(channel.id)]["ouvert"] = False
    save(data)

    await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
    import asyncio
    await asyncio.sleep(5)
    await channel.delete()

bot.run(TOKEN)
