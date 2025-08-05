import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.dm_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMOTE_SERVER_ID = 111111111111111111  # Replace with your remote server ID
REMOTE_PAYMENT_CHANNEL_ID = 333333333333333333  # Replace with your remote payment confirmation channel ID

USER_DATA_FILE = "user_data.json"

# Load user data (first purchase date, payment due date, payment confirmation)
def load_user_data():
    if not os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(USER_DATA_FILE, "r") as f:
        return json.load(f)

# Save user data
def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Function to calculate the payment due date (30 days after the first purchase)
def calculate_due_date(first_purchase_date):
    return first_purchase_date + timedelta(days=30)

# Function to check if a user needs a reminder (5 days before due date)
def needs_payment_reminder(user):
    if user['payment_confirmed']:
        return False  # No need for a reminder if payment is confirmed
    due_date = datetime.fromisoformat(user['payment_due_date'])
    reminder_date = due_date - timedelta(days=5)
    return reminder_date <= datetime.utcnow() <= due_date

# Function to send a payment reminder DM
async def send_payment_reminder(user_id):
    user = bot.get_user(user_id)
    if user:
        await user.send("**Reminder**: Your payment is due in 5 days. Please make sure to complete the payment before the due date.")
        print(f"Payment reminder sent to {user.name}#{user.discriminator}.")

# Function to send payment confirmation message
async def send_payment_confirmation(user_id):
    user = bot.get_user(user_id)
    if user:
        await user.send("**Payment Confirmed**: Your payment has been confirmed. Thank you!")
        print(f"Payment confirmed message sent to {user.name}#{user.discriminator}.")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    # If payment is confirmed by team in the remote management channel
    if message.channel.id == REMOTE_PAYMENT_CHANNEL_ID and message.content.startswith("Payment Confirmed"):
        try:
            # Extract user ID from message
            user_id = int(message.content.split("User: ")[1].strip())
        except (IndexError, ValueError):
            pass  # If the message format is invalid

        if user_id:
            # Get the user data from file
            user_data = load_user_data()

            if str(user_id) in user_data:
                user_data[str(user_id)]['payment_confirmed'] = True
                save_user_data(user_data)
                await send_payment_confirmation(user_id)
            else:
                print(f"User with ID {user_id} not found in database.")

# Task to check for payment reminders every day
@tasks.loop(hours=24)
async def check_payment_reminders():
    user_data = load_user_data()
    for user_id, user in user_data.items():
        if needs_payment_reminder(user):
            await send_payment_reminder(int(user_id))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Start the payment reminder check task
    check_payment_reminders.start()

@bot.command()
async def firstpurchase(ctx):
    """Command to log the first purchase date and calculate the payment due date."""
    user_id = ctx.author.id
    user_data = load_user_data()

    if str(user_id) not in user_data:
        # Log the first purchase date and payment due date (30 days from now)
        first_purchase_date = datetime.utcnow()
        payment_due_date = calculate_due_date(first_purchase_date)
        user_data[str(user_id)] = {
            "first_purchase_date": first_purchase_date.isoformat(),
            "payment_due_date": payment_due_date.isoformat(),
            "payment_confirmed": False
        }
        save_user_data(user_data)
        await ctx.send(f"Your first purchase has been logged. Your payment due date is {payment_due_date.date()}.")
    else:
        await ctx.send("Your purchase date is already logged.")

bot.run("YOUR_BOT_TOKEN")