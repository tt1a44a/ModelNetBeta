import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# IDs
SOURCE_CHANNEL_ID = 111111111111111111  # Channel to listen to
TARGET_CHANNEL_ID = 222222222222222222  # Channel to echo into

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == SOURCE_CHANNEL_ID:
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not target_channel:
            print("Target channel not found!")
            return

        # Forward the text if there is any
        if message.content:
            await target_channel.send(message.content)

        # Forward each attachment individually
        for attachment in message.attachments:
            await target_channel.send(attachment.url)

    await bot.process_commands(message)

bot.run("YOUR_BOT_TOKEN")