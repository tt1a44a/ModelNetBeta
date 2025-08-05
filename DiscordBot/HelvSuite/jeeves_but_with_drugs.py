import discord
from discord.ext import commands
from discord import ui
import os
import json
from datetime import datetime

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.dm_messages = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMOTE_SERVER_ID = 111111111111111111  # Replace with your remote server ID
REMOTE_CHANNEL_ID = 222222222222222222  # Replace with your remote channel ID

TICKET_COUNTER_FILE = "ticket_counter.txt"
TICKETS_DATABASE_FILE = "tickets.json"

user_ticket_context = {}

# Load ticket counter
def load_ticket_counter():
    if not os.path.exists(TICKET_COUNTER_FILE):
        with open(TICKET_COUNTER_FILE, "w") as f:
            f.write("0")
        return 0
    with open(TICKET_COUNTER_FILE, "r") as f:
        return int(f.read().strip())

# Save ticket counter
def save_ticket_counter(counter):
    with open(TICKET_COUNTER_FILE, "w") as f:
        f.write(str(counter))

# Load ticket database
def load_ticket_database():
    if not os.path.exists(TICKETS_DATABASE_FILE):
        with open(TICKETS_DATABASE_FILE, "w") as f:
            json.dump([], f)
        return []
    with open(TICKETS_DATABASE_FILE, "r") as f:
        return json.load(f)

# Save ticket database
def save_ticket_database(data):
    with open(TICKETS_DATABASE_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Start with loaded values
ticket_counter = load_ticket_counter()
ticket_database = load_ticket_database()

class TicketButtonView(ui.View):
    @ui.button(label="Support", style=discord.ButtonStyle.primary)
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_ticket(interaction, "Support")

    @ui.button(label="Sales", style=discord.ButtonStyle.success)
    async def sales(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_ticket(interaction, "Sales")

    @ui.button(label="Partnerships", style=discord.ButtonStyle.secondary)
    async def partnerships(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_ticket(interaction, "Partnerships")

    @ui.button(label="Other", style=discord.ButtonStyle.danger)
    async def other(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_ticket(interaction, "Other")

async def start_ticket(interaction: discord.Interaction, ticket_type: str):
    user = interaction.user

    await interaction.response.send_message("Please check your DMs to continue your ticket!", ephemeral=True)

    try:
        await user.send(f"You selected **{ticket_type}**.\nPlease describe your issue. Reply to this message.")

        user_ticket_context[user.id] = {
            "ticket_type": ticket_type,
            "waiting_for_reply": True
        }
    except discord.Forbidden:
        await interaction.followup.send("I couldn't DM you. Please enable DMs from server members.", ephemeral=True)

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if not isinstance(message.channel, discord.DMChannel):
        return

    user_id = message.author.id

    if user_id in user_ticket_context and user_ticket_context[user_id]["waiting_for_reply"]:
        global ticket_counter
        global ticket_database

        ticket_counter += 1
        save_ticket_counter(ticket_counter)

        ticket_type = user_ticket_context[user_id]["ticket_type"]
        user = message.author
        description = message.content

        # Build ticket report
        ticket_message = (
            f"**New Ticket #{ticket_counter:03}**\n"
            f"**User:** {user.name}#{user.discriminator} (ID: {user.id})\n"
            f"**Ticket Type:** {ticket_type}\n"
            f"**Message:**\n{description}"
        )

        # Save ticket to database
        ticket_entry = {
            "ticket_number": ticket_counter,
            "user_id": user.id,
            "username": f"{user.name}#{user.discriminator}",
            "ticket_type": ticket_type,
            "message": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        ticket_database.append(ticket_entry)
        save_ticket_database(ticket_database)

        # Send to remote server
        remote_guild = bot.get_guild(REMOTE_SERVER_ID)
        if remote_guild:
            remote_channel = remote_guild.get_channel(REMOTE_CHANNEL_ID)
            if remote_channel:
                await remote_channel.send(ticket_message)
            else:
                print("Remote channel not found!")
        else:
            print("Remote guild not found!")

        await user.send(f"Thank you! Your ticket has been submitted. (Ticket #{ticket_counter:03})")

        user_ticket_context.pop(user_id, None)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
async def ticket(ctx):
    """Command to display ticket buttons."""
    await ctx.send("Please select the type of ticket you'd like to create:", view=TicketButtonView())

@bot.command()
async def findticket(ctx, *, search_term: str):
    """Command to search tickets by number or username."""
    search_term = search_term.strip()

    # Search by ticket number (ensure it's an integer)
    if search_term.isdigit():
        ticket_number = int(search_term)
        ticket = next((t for t in ticket_database if t["ticket_number"] == ticket_number), None)
        if ticket:
            await ctx.send(f"**Ticket #{ticket_number}** found:\n"
                           f"User: {ticket['username']}\n"
                           f"Type: {ticket['ticket_type']}\n"
                           f"Message: {ticket['message']}\n"
                           f"Timestamp: {ticket['timestamp']}")
        else:
            await ctx.send(f"Ticket #{ticket_number} not found.")
    else:
        # Search by username
        matching_tickets = [t for t in ticket_database if search_term.lower() in t["username"].lower()]
        if matching_tickets:
            response = f"Found {len(matching_tickets)} tickets for '{search_term}':\n"
            for ticket in matching_tickets:
                response += (f"\n**Ticket #{ticket['ticket_number']}** - {ticket['ticket_type']}: "
                             f"{ticket['message']} (Timestamp: {ticket['timestamp']})")
            await ctx.send(response)
        else:
            await ctx.send(f"No tickets found for username '{search_term}'.")

bot.run("YOUR_BOT_TOKEN")