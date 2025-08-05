import discord
from discord.ext import commands
from discord import ui
import random
import string

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.dm_messages = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMOTE_SERVER_ID = 123456789012345678  # Your remote server ID
REMOTE_CHANNEL_ID = 987654321098765432  # Your remote channel ID

# Dictionary to store users who already clicked a button
clicked_buttons = {}

def generate_reference_code(length=8):
    """Generate a short alphanumeric code, good for Bitcoin references."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

class ProfileRequestView(ui.View):
    @ui.button(label="Request Type A", style=discord.ButtonStyle.primary)
    async def type_a_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_profile_request(interaction, "Type A")

    @ui.button(label="Request Type B", style=discord.ButtonStyle.success)
    async def type_b_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_profile_request(interaction, "Type B")

    @ui.button(label="Request Type C", style=discord.ButtonStyle.danger)
    async def type_c_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_profile_request(interaction, "Type C")

async def handle_profile_request(interaction: discord.Interaction, profile_type: str):
    user = interaction.user
    user_id = user.id

    # Initialize if user not in dict
    if user_id not in clicked_buttons:
        clicked_buttons[user_id] = []

    # Check if already clicked this profile type
    if profile_type in clicked_buttons[user_id]:
        await interaction.response.send_message(f"You have already created a **{profile_type}** profile.", ephemeral=True)
        return

    # Mark button as clicked
    clicked_buttons[user_id].append(profile_type)

    # Generate short reference code
    reference_code = generate_reference_code()

    # Message to send
    message = (
        f"New Bitcoin Reference Created:\n"
        f"**Username:** {user.name}#{user.discriminator}\n"
        f"**Profile Type:** {profile_type}\n"
        f"**Reference Code:** `{reference_code}`\n"
        f"**Origin Server:** {interaction.guild.name}"
    )

    # Respond to the button click
    await interaction.response.send_message(f"Your {profile_type} reference code has been generated! Check your DMs.", ephemeral=True)

    # DM the user
    try:
        await user.send(f"Here’s your **{profile_type}** Bitcoin reference code: `{reference_code}`")
    except discord.Forbidden:
        print(f"Couldn't DM {user.name}")

    # Send info to remote server
    remote_guild = bot.get_guild(REMOTE_SERVER_ID)
    if remote_guild:
        remote_channel = remote_guild.get_channel(REMOTE_CHANNEL_ID)
        if remote_channel:
            await remote_channel.send(message)
        else:
            print("Remote channel not found!")
    else:
        print("Remote guild not found!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
async def setup(ctx):
    """Command to send the Bitcoin Reference Request buttons."""
    await ctx.send("Request your Bitcoin reference code:", view=ProfileRequestView())

bot.run("YOUR_BOT_TOKEN")