import discord
from discord.ext import commands
from discord import app_commands
import os

# Récupère le token depuis les variables d'environnement
TOKEN = os.environ.get("TOKEN")

# Initialise le bot avec tous les intents
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Événement de démarrage
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur de synchronisation : {e}")

# Exemple de commande slash basique
@bot.tree.command(name="ping", description="Vérifie si le bot est en ligne")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong !", ephemeral=True)

# Exemple de commande slash avec paramètre
@bot.tree.command(name="salut", description="Dis bonjour à un membre")
@app_commands.describe(membre="Le membre à saluer")
async def salut(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.send_message(f"👋 Salut {membre.mention} !")

# Exemple de commande réservée aux administrateurs
@bot.tree.command(name="admin", description="Commande réservée aux admins")
@app_commands.checks.has_permissions(administrator=True)
async def admin(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Tu es admin !", ephemeral=True)

# Gestion des erreurs de permissions
@admin.error
async def admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)

# Lancement du bot
bot.run(TOKEN)
