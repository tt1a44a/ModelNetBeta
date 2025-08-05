import discord
from discord.ext import commands
from discord import ui

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

class RoomRequestView(ui.View):
    @ui.button(label="Request a Room", style=discord.ButtonStyle.green)
    async def request_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Create a voice channel named after the user
        channel = await guild.create_voice_channel(name=f"{user.name}'s Room")

        # Reply privately to the button click
        await interaction.response.send_message(f"Room created: {channel.mention}", ephemeral=True)

        # Try sending the user a DM
        try:
            await user.send(f"Hello {user.name}! Your room **{channel.name}** has been created in **{guild.name}**.")
        except discord.Forbidden:
            print(f"Couldn't DM {user.name}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
async def setup(ctx):
    """Command to send the Request Room button."""
    await ctx.send("Click the button below to request a room!", view=RoomRequestView())

bot.run("YOUR_BOT_TOKEN")