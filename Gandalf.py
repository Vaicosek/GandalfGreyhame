import discord
from discord.ext import commands, tasks
import matplotlib.pyplot as plt
from io import BytesIO
import datetime
import json
import os

TOKEN = "MTMwMzM4OTQ0OTYxODcxODc1MA.GwvaVM.XJrvGneTm02F1tpHQEwErLvbadcIcvYX06FJlc"  # Replace with your bot's token
BACKUP_FILE = "backup_data.json"
COMMANDER_ROLE = "BotCommander"  # Name of the role that has elevated privileges

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

# Store interest rate and balances as a dictionary for tracking
user_data = {}
current_interest_rate = 0.0  # Default rate, set weekly
fund_history = []  # Track total fund balance over time for reporting


@bot.event
async def on_ready():
    print(f"{bot.user} is now running!")
    # Start the weekly interest calculation task
    if not calculate_weekly_interest.is_running():
        calculate_weekly_interest.start()


# Helper function to check if a user has the BotCommander role or is an admin
def has_commander_role(ctx):
    return ctx.author.guild_permissions.administrator or COMMANDER_ROLE in [role.name for role in ctx.author.roles]


# Set interest rate command
@bot.command(name="set_interest_rate")
async def set_interest_rate(ctx, rate: float):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    global current_interest_rate
    current_interest_rate = rate
    await ctx.send(f"Weekly interest rate set to {rate:.2%}")


# Command to set initial deposit for a user
@bot.command(name="set_initial_deposit")
async def set_initial_deposit(ctx, user: discord.User, amount: float):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id not in user_data:
        # If the user doesn't already have an account, create one
        user_data[user_id] = {
            "initial_deposit": amount,
            "balance": amount,  # Set the initial deposit as the current balance
            "history": [(datetime.datetime.now().strftime("%Y-%m-%d"), amount)]
        }
        await ctx.send(f"Set initial deposit of {amount:.2f} for {user.display_name}. The balance is now {amount:.2f}.")
    else:
        # If the user already has an account, don't override balance but just set the initial deposit
        user_data[user_id]["initial_deposit"] = amount
        await ctx.send(f"Set new initial deposit of {amount:.2f} for {user.display_name}, current balance is {user_data[user_id]['balance']:.2f}.")

# Command for users to view their own initial deposit
@bot.command(name="initial_deposit")
async def initial_deposit(ctx):
    user_id = str(ctx.author.id)  # Use the command sender's own ID
    if user_id in user_data:
        initial_amount = user_data[user_id]["initial_deposit"]
        await ctx.send(f"Your initial deposit: {initial_amount:.2f}")
    else:
        await ctx.send("No account found for you. Please ask an admin to set your initial deposit.")


# Command to view another user's initial deposit
@bot.command(name="view_initial_deposit")
async def view_initial_deposit(ctx, user: discord.User):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id in user_data:
        initial_amount = user_data[user_id]["initial_deposit"]
        await ctx.send(f"{user.display_name}'s initial deposit: {initial_amount:.2f}")
    else:
        await ctx.send("User not found or no initial deposit set.")


# Calculate interest and apply to all users
@tasks.loop(time=datetime.time(0, 0, 0))  # Set to run every Monday at midnight
async def calculate_weekly_interest():
    apply_interest()
    print("Weekly interest calculation complete.")


# Immediate interest application for testing
@bot.command(name="apply_interest_now")
async def apply_interest_now(ctx):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    apply_interest()
    await ctx.send("Interest applied to all accounts immediately.")


# Helper function to apply flat interest to all accounts based on initial deposit only
def apply_interest():
    total_fund = 0
    for user_id, data in user_data.items():
        # Calculate interest only on the initial deposit
        interest = data["initial_deposit"] * current_interest_rate
        data["balance"] += interest  # Add flat interest to current balance
        data["history"].append((datetime.datetime.now().strftime("%Y-%m-%d"), data["balance"]))
        total_fund += data["balance"]
    fund_history.append((datetime.datetime.now().strftime("%Y-%m-%d"), total_fund))


# Command to apply interest to a specific user's account
@bot.command(name="apply_interest_to_user")
async def apply_interest_to_user(ctx, user: discord.User):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id in user_data:
        # Calculate interest only on the initial deposit
        interest = user_data[user_id]["initial_deposit"] * current_interest_rate
        user_data[user_id]["balance"] += interest  # Add flat interest to current balance
        user_data[user_id]["history"].append(
            (datetime.datetime.now().strftime("%Y-%m-%d"), user_data[user_id]["balance"]))

        await ctx.send(
            f"Interest of {interest:.2f} applied to {user.display_name}'s account. New balance: {user_data[user_id]['balance']:.2f}")
    else:
        await ctx.send("User not found. Please set the initial deposit first.")


# Command to add funds to a user's account
@bot.command(name="add_funds")
async def add_funds(ctx, user: discord.User, amount: float):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id not in user_data:
        await ctx.send("User not found. Please set the initial deposit first.")
        return

    # Only update the balance, keep the initial deposit unchanged
    user_data[user_id]["balance"] += amount
    await ctx.send(
        f"Added {amount:.2f} to {user.display_name}'s account. New balance: {user_data[user_id]['balance']:.2f}")


# Command to withdraw funds from an account
@bot.command(name="withdraw_funds")
async def withdraw_funds(ctx, user: discord.User, amount: float):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id in user_data and user_data[user_id]["balance"] >= amount:
        user_data[user_id]["balance"] -= amount
        await ctx.send(
            f"Withdrew {amount:.2f} from {user.display_name}'s account. New balance: {user_data[user_id]['balance']:.2f}")
    else:
        await ctx.send("User not found or insufficient balance.")


# Command to view the user's own balance
@bot.command(name="balance")
async def balance(ctx):
    user_id = str(ctx.author.id)  # Use the command sender's own ID
    if user_id in user_data:
        await ctx.send(f"Your current balance: {user_data[user_id]['balance']:.2f}")
    else:
        await ctx.send("No account found for you.")


# Command for admins or BotCommander to view another user's balance
@bot.command(name="view_balance")
async def view_balance(ctx, user: discord.User):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    user_id = str(user.id)
    if user_id in user_data:
        await ctx.send(f"{user.display_name}'s current balance: {user_data[user_id]['balance']:.2f}")
    else:
        await ctx.send("User not found.")


# Generate a balance history graph for the user
@bot.command(name="generate_graph")
async def generate_graph(ctx, user: discord.User = None):
    is_admin = has_commander_role(ctx)

    if not is_admin and user:
        await ctx.send("You do not have permission to view other users' graphs.")
        return

    user_id = str(user.id) if user else str(ctx.author.id)
    if user_id in user_data:
        history = user_data[user_id]["history"]
        dates, balances = zip(*history)

        plt.figure()
        plt.plot(dates, balances, marker="o")
        plt.title(f"Balance History for {ctx.author.display_name}")
        plt.xlabel("Date")
        plt.ylabel("Balance")
        plt.xticks(rotation=45)

        buf = BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await ctx.send(file=discord.File(buf, filename="balance_graph.png"))
        plt.close()
    else:
        await ctx.send("User not found or you do not have permission to view this account.")


# Generate a total fund balance history graph
@bot.command(name="generate_fund_report")
async def generate_fund_report(ctx):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    if fund_history:
        dates, total_balances = zip(*fund_history)
        plt.figure()
        plt.plot(dates, total_balances, marker="o", color="green")
        plt.title("Total Fund Balance Over Time")
        plt.xlabel("Date")
        plt.ylabel("Total Balance in Fund")
        plt.xticks(rotation=45)

        buf = BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await ctx.send(file=discord.File(buf, filename="fund_report.png"))
        plt.close()
    else:
        await ctx.send("No fund history data available.")


# Transfer account ownership
@bot.command(name="transfer_account")
async def transfer_account(ctx, current_owner: discord.User, new_owner: discord.User):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    current_owner_id = str(current_owner.id)
    new_owner_id = str(new_owner.id)
    if current_owner_id in user_data:
        user_data[new_owner_id] = user_data.pop(current_owner_id)
        await ctx.send(f"Account ownership transferred from {current_owner.display_name} to {new_owner.display_name}")
    else:
        await ctx.send("Current owner not found.")


# Backup data to a JSON file
@bot.command(name="backup_data")
async def backup_data(ctx):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    backup_content = {
        "user_data": user_data,
        "fund_history": fund_history
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup_content, f, indent=4)
    await ctx.send("Data backup complete.")


# Restore data from a JSON file
@bot.command(name="restore_data")
async def restore_data(ctx):
    if not has_commander_role(ctx):
        await ctx.send("You do not have permission to use this command.")
        return

    global user_data, fund_history
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            backup_content = json.load(f)
            user_data = backup_content.get("user_data", {})
            fund_history = backup_content.get("fund_history", [])
        await ctx.send("Data restoration complete.")
    else:
        await ctx.send("No backup file found to restore data.")


# Start the bot
bot.run(TOKEN)
