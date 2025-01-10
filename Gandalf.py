import asyncio

import discord
from discord import app_commands
from discord.ext import tasks
import matplotlib.pyplot as plt  # Ensure you're using pyplot for plotting
import matplotlib.dates as mdates
from io import BytesIO
import datetime
import json
import os
from typing import Literal
from pytz import timezone


CONFIG_FILE = "config.json"
BACKUP_FILE = "backup_data.json"
COMMANDER_ROLE = "BotCommander"  # Name of the role that has elevated privileges
PROJECTS_BACKUP_FILE = "projects_backup.json"
loans = {}
projects = {}
LOANS_BACKUP_FILE = "loans_backup.json"
DURATION_CHOICES = [
    app_commands.Choice(name="1 Week", value="1 Week"),
    app_commands.Choice(name="2 Weeks", value="2 Weeks"),
    app_commands.Choice(name="3 Weeks", value="3 Weeks"),
    app_commands.Choice(name="1 Month", value="1 Month"),
    app_commands.Choice(name="2 Months", value="2 Months"),
    app_commands.Choice(name="3 Months", value="3 Months"),
    app_commands.Choice(name="4 Months", value="4 Months"),
]


# Load bot configuration
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found!")

TOKEN = config.get("TOKEN")  # Discord bot token
GUILD_ID = config.get("GUILD_ID")
if not GUILD_ID or not isinstance(GUILD_ID, int):
    raise ValueError("GUILD_ID must be a valid integer in the config.json file.")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Store user data and interest rates
user_data = {
    # Example format
    "user_id": {
        "balance": 0.0,
        "initial_deposit": 0.0,
        "start_date": "YYYY-MM-DD",  # New field
        "history": []
    }
}

current_interest_rate = 0.0  # Default rate, set bi-weekly
fund_history = []  # Track total fund balance over time for reporting
@tasks.loop(hours=6)
async def backup_data_task():
    global projects  # Add this line to access the global projects variable
    # Backup user data and fund history
    if not os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "w") as f:
            json.dump({"user_data": {}, "fund_history": []}, f, indent=4)
    with open(BACKUP_FILE, "w") as f:
        json.dump({"user_data": user_data, "fund_history": fund_history}, f, indent=4)
    print("User data and fund history backup completed.")

    # Backup projects data
    if not os.path.exists(PROJECTS_BACKUP_FILE):
        with open(PROJECTS_BACKUP_FILE, "w") as f:
            json.dump({}, f, indent=4)
    with open(PROJECTS_BACKUP_FILE, "w") as f:
        json.dump(projects, f, indent=4)
    print("Projects data backup completed.")

    # Backup loans data
    if not os.path.exists(LOANS_BACKUP_FILE):
        with open(LOANS_BACKUP_FILE, "w") as f:
            json.dump({}, f, indent=4)
    with open(LOANS_BACKUP_FILE, "w") as f:
        json.dump(loans, f, indent=4)
    print("Loans data backup completed.")


def validate_backup(filepath, default_data):
    try:
        with open(filepath, "r") as f:
            json.load(f)  # Check if the file has valid JSON
    except (FileNotFoundError, json.JSONDecodeError):
        # Create a default backup file if invalid
        with open(filepath, "w") as f:
            json.dump(default_data, f, indent=4)


@client.event
async def on_ready():
    print(f"{client.user} is now running!")

    # Load backups for user data, projects, and loans
    try:
        load_backup()
        load_projects_backup()
        load_loans_backup()
        print("All backup data loaded successfully.")
    except Exception as e:
        print(f"Error while loading backups: {e}")

    try:
        # Attempt global sync instead of guild-specific sync
        await tree.sync()
        print("Commands synced globally.")
    except Exception as e:
        print(f"Failed to sync commands globally: {e}")

    # Start tasks after syncing
    if not backup_data_task.is_running():
        backup_data_task.start()
    print("Bi-weekly interest task and backup tasks initialized.")


def has_commander_role(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator or COMMANDER_ROLE in [role.name for role in interaction.user.roles]


# Helper function to load data from backup file
def load_backup():
    global user_data, fund_history
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            backup_content = json.load(f)
            user_data = backup_content.get("user_data", {})
            fund_history = backup_content.get("fund_history", [])
            print("User data and fund history loaded successfully.")
    else:
        print("User backup file not found. Creating a new one.")
        user_data = {}  # Initialize as an empty dictionary
        fund_history = []  # Initialize as an empty list
        with open(BACKUP_FILE, "w") as f:
            json.dump({"user_data": user_data, "fund_history": fund_history}, f, indent=4)


def load_loans_backup():
    global loans
    if os.path.exists(LOANS_BACKUP_FILE):
        with open(LOANS_BACKUP_FILE, "r") as f:
            loans = json.load(f)
            print("Loans data loaded successfully.")
    else:
        print("Loans backup file not found. Creating a new one.")
        loans = {}
        with open(LOANS_BACKUP_FILE, "w") as f:
            json.dump(loans, f, indent=4)

def load_projects_backup():
    global projects
    if os.path.exists(PROJECTS_BACKUP_FILE):
        with open(PROJECTS_BACKUP_FILE, "r") as f:
            projects = json.load(f)
            print("Projects data loaded successfully.")
    else:
        print("Projects backup file not found. Creating a new one.")
        projects = {}
        with open(PROJECTS_BACKUP_FILE, "w") as f:
            json.dump(projects, f, indent=4)


@tree.command(name="load_backups", description="Manually load backups for user accounts, projects, and loans (Admin only).")
async def load_backups(interaction: discord.Interaction):
    """Manually load all backup data."""
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    try:
        # Load all backups
        load_backup()
        load_projects_backup()
        load_loans_backup()
        await interaction.response.send_message("All backups have been successfully loaded.", ephemeral=True)
        print("Backups successfully reloaded.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to load backups: {e}", ephemeral=True)
        print(f"Error loading backups: {e}")


# Helper to plot graph
import matplotlib.ticker as mticker

def plot_graph(dates, values, title, xlabel, ylabel):
    # Remove leading zero values
    valid_indices = [i for i, value in enumerate(values) if value > 0]
    if not valid_indices:  # If all values are zero, return an empty graph
        return None

    # Filter dates and values to remove leading zeros
    dates = [dates[i] for i in valid_indices]
    values = [values[i] for i in valid_indices]

    plt.figure()  # Create a new figure
    plt.plot(dates, values, marker="o")  # Plot the data points
    plt.title(title)  # Set the title
    plt.xlabel(xlabel)  # Set the x-axis label
    plt.ylabel(ylabel)  # Set the y-axis label
    plt.xticks(rotation=45)  # Rotate the x-axis labels for better readability

    # Format x-axis with readable dates
    ax = plt.gca()  # Get current axis
    locator = mdates.AutoDateLocator(interval_multiples=True)  # Add interval multiples
    ax.xaxis.set_major_locator(locator)  # Set the interval-based locator
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))  # Format date labels

    # Format y-axis numbers with commas
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))  # Format numbers

    # Save the plot to a BytesIO buffer for sending as a file
    buf = BytesIO()
    plt.savefig(buf, format="png")  # Save the figure to the buffer in PNG format
    buf.seek(0)  # Move the pointer to the start of the buffer
    plt.close()  # Close the figure to free up memory
    return buf


# Helper function: Apply hourly interest
def apply_hourly_interest():
    total_fund = 0
    hourly_interest_rate = current_interest_rate / (14 * 24)  # Divide bi-weekly rate over 14 days and 24 hours

    for user_id, data in user_data.items():
        hourly_interest = data["balance"] * hourly_interest_rate
        data["balance"] += hourly_interest
        data["history"].append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), data["balance"]))
        total_fund += data["balance"]

    fund_history.append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), total_fund))
    print("Hourly interest applied.")


# Command: Set Interest Rate
@tree.command(name="set_interest_rate", description="Set the bi-weekly interest rate (Admin only).")
async def set_interest_rate(interaction: discord.Interaction, rate: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    global current_interest_rate
    current_interest_rate = rate
    await interaction.response.send_message(f"Bi-weekly interest rate set to {rate:.2%}")


@tree.command(name="set_account_start", description="Set the account start date for a user (Admin only).")
async def set_account_start(interaction: discord.Interaction, user: discord.User, start_date: str):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    try:
        datetime.datetime.strptime(start_date, "%Y-%m-%d")  # Validate date format
    except ValueError:
        await interaction.response.send_message("Invalid date format. Use 'YYYY-MM-DD'.", ephemeral=True)
        return

    user_id = str(user.id)
    if user_id not in user_data:
        await interaction.response.send_message(
            f"{user.display_name} does not have an account. Set an initial deposit first.", ephemeral=True
        )
        return

    user_data[user_id]["start_date"] = start_date

    await interaction.response.send_message(
        f"Account start date for {user.display_name} has been manually set to {start_date}.",
        ephemeral=True
    )

@tree.command(name="set_initial_deposit", description="Set an initial deposit for a user (Admin only).")
async def set_initial_deposit(interaction: discord.Interaction, user: discord.User, amount: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    now = datetime.datetime.now().strftime("%Y-%m-%d")  # Current date in YYYY-MM-DD format

    # Ensure user data exists
    if user_id not in user_data:
        user_data[user_id] = {
            "initial_deposit": amount,
            "balance": amount,
            "history": [(now, amount)],
            "start_date": now  # Automatically set start date
        }
    else:
        # Update deposit and reset start date
        user_data[user_id]["initial_deposit"] = amount
        user_data[user_id]["balance"] = amount
        user_data[user_id]["start_date"] = now  # Reset start date
        user_data[user_id]["history"].append((now, amount))

    update_fund_balance()  # Update total fund balance for the graph

    await interaction.response.send_message(
        f"Set new initial deposit of {amount:.2f} for {user.display_name}. Balance has been updated to {amount:.2f}, and the account start date has been reset to {now}.",
        ephemeral=True
    )


# Command: View Initial Deposit
@tree.command(name="initial_deposit", description="View your own or another user's initial deposit.")
async def initial_deposit(interaction: discord.Interaction, user: discord.User = None):
    if user:
        if not has_commander_role(interaction):
            await interaction.response.send_message("You do not have permission to view another user's initial deposit.", ephemeral=True)
            return
        user_id = str(user.id)
        if user_id in user_data:
            initial_amount = user_data[user_id]["initial_deposit"]
            await interaction.response.send_message(f"{user.display_name}'s initial deposit: {initial_amount:.2f}")
        else:
            await interaction.response.send_message("User not found.")
    else:
        user_id = str(interaction.user.id)  # Use the command sender's own ID
        if user_id in user_data:
            initial_amount = user_data[user_id]["initial_deposit"]
            await interaction.response.send_message(f"Your initial deposit: {initial_amount:.2f}")
        else:
            await interaction.response.send_message("No account found for you. Please ask an admin to set your initial deposit.")


# Command: View Balance
@tree.command(name="balance", description="View your own or another user's balance.")
async def balance(interaction: discord.Interaction, user: discord.User = None):
    if user:
        if not has_commander_role(interaction):
            await interaction.response.send_message("You do not have permission to view another user's balance.", ephemeral=True)
            return
        user_id = str(user.id)
        if user_id in user_data:
            await interaction.response.send_message(f"{user.display_name}'s current balance: {user_data[user_id]['balance']:.2f}")
        else:
            await interaction.response.send_message("User not found.")
    else:
        user_id = str(interaction.user.id)  # Use the command sender's own ID
        if user_id in user_data:
            await interaction.response.send_message(f"Your current balance: {user_data[user_id]['balance']:.2f}")
        else:
            await interaction.response.send_message("No account found for you.")


@tree.command(name="apply_interest_now", description="Manually apply bi-weekly interest to all accounts (Admin only).")
async def apply_interest_now(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Apply interest to all accounts
    global_interest_rate = current_interest_rate
    for user_id, data in user_data.items():
        initial_deposit = data.get("initial_deposit", 0.0)
        interest = initial_deposit * global_interest_rate
        data["balance"] += interest
        data.setdefault("history", []).append(
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), data["balance"])
        )

    # Notify in the finance-updates channel
    guild = interaction.guild
    finance_updates_channel = discord.utils.get(guild.text_channels, name="📣│finance-updates")

    if finance_updates_channel:
        finance_updates_role = discord.utils.get(guild.roles, name="Finance Updates")
        finance_updates_mention = finance_updates_role.mention if finance_updates_role else "`Finance Updates` role"
        await finance_updates_channel.send(
            f"{finance_updates_mention}, the interest has been manually applied!\n\n"
            f"**Global Interest Rate**: {current_interest_rate:.2f}%\n"
            "All accounts (bank and project investments) have been updated accordingly."
        )

    await interaction.response.send_message("Bi-weekly interest manually applied to all accounts.", ephemeral=True)


@tree.command(name="time_until_interest", description="Check the time remaining until the next interest calculation.")
async def time_until_interest(interaction: discord.Interaction):
    """Calculate and display the time until the next bi-weekly Monday 8 PM CET."""
    cet = timezone("Europe/Berlin")
    now = datetime.datetime.now(cet)

    # Calculate the next Monday at 8 PM CET
    days_until_monday = (7 - now.weekday()) % 7
    next_monday = now + datetime.timedelta(days=days_until_monday)
    next_monday = next_monday.replace(hour=20, minute=0, second=0, microsecond=0)

    # Bi-weekly adjustment: Skip to the following Monday if it's an odd-numbered week
    week_number = next_monday.isocalendar()[1]
    if week_number % 2 == 1:  # Odd-numbered week; skip one week
        next_monday += datetime.timedelta(days=7)

    # Calculate time difference
    time_difference = next_monday - now
    days, seconds = divmod(time_difference.total_seconds(), 86400)  # Days and remaining seconds
    hours, seconds = divmod(seconds, 3600)  # Hours and remaining seconds
    minutes = seconds // 60  # Remaining minutes

    # Respond with the time remaining
    await interaction.response.send_message(
        f"**Time until the next interest calculation:**\n"
        f"🔹 {int(days)} days, {int(hours)} hours, {int(minutes)} minutes."
    )

def interpolate_graph_points(start_balance, end_balance, num_points=6):
    """Generate smooth points between start_balance and end_balance for visualization."""
    step_size = (end_balance - start_balance) / num_points
    return [start_balance + step_size * i for i in range(1, num_points + 1)]


def update_fund_balance():
    """Update the total fund balance for tracking and graphs."""
    total_fund_before = sum(
        user_data[user_id].get("balance", 0) - (current_interest_rate * user_data[user_id].get("initial_deposit", 0))
        for user_id in user_data
    )
    total_fund_after = sum(user_data[user_id].get("balance", 0) for user_id in user_data)

    # Interpolate smooth graph points
    interpolated_points = interpolate_graph_points(total_fund_before, total_fund_after, num_points=6)
    timestamps = [datetime.datetime.now() - datetime.timedelta(hours=i * 4) for i in range(6)][::-1]

    # Simulate incremental points in the history
    for timestamp, point in zip(timestamps, interpolated_points):
        fund_history.append((timestamp.strftime("%Y-%m-%d %H:%M"), point))


@tree.command(name="add_funds", description="Add funds to a user's account (Admin only).")
async def add_funds(interaction: discord.Interaction, user: discord.User, amount: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    if user_id not in user_data:
        user_data[user_id] = {"balance": 0.0, "history": []}

    user_data[user_id]["balance"] += amount
    user_data[user_id]["history"].append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[user_id]["balance"]))

    # Update the total fund balance
    update_fund_balance()

    await interaction.response.send_message(f"Added {amount:.2f} to {user.display_name}'s account. New balance: {user_data[user_id]['balance']:.2f}")


@tree.command(name="withdraw_funds", description="Withdraw funds from a user's account (Admin only).")
async def withdraw_funds(interaction: discord.Interaction, user: discord.User, amount: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    # Ensure the user has a default structure
    if user_id not in user_data:
        await interaction.response.send_message("User not found or insufficient balance.", ephemeral=True)
        return

    if user_data[user_id].get("balance", 0) < amount:
        await interaction.response.send_message("Insufficient balance to withdraw.", ephemeral=True)
        return

    start_date_str = user_data[user_id].get("start_date")
    if not start_date_str:
        await interaction.response.send_message(
            "Account start date not set. Please set the account start date first.", ephemeral=True
        )
        return

    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    today = datetime.datetime.now()
    account_duration_weeks = (today - start_date).days // 7

    # Calculate withdrawal fee
    fee_percentage = max(8 - account_duration_weeks, 0)  # Fee decreases 1% per week
    fee = (amount * fee_percentage) / 100
    final_withdrawal = amount - fee

    # Deduct from balance and record transaction
    user_data[user_id]["balance"] -= amount
    user_data[user_id].setdefault("history", []).append(
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[user_id]["balance"])
    )

    # Send fee to receiver account (ID: 262945457045635075)
    receiver_id = "262945457045635075"
    if receiver_id not in user_data:
        user_data[receiver_id] = {"balance": 0.0, "history": []}

    user_data[receiver_id]["balance"] += fee
    user_data[receiver_id]["history"].append(
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[receiver_id]["balance"])
    )
    print(f"Transferred {fee:.2f} withdrawal fees to user with ID {receiver_id}. New balance: {user_data[receiver_id]['balance']}")

    update_fund_balance()

    await interaction.response.send_message(
        f"Withdrawn {amount:.2f} coins from {user.display_name}'s account.\n"
        f"**Fee**: {fee:.2f} coins ({fee_percentage}% based on account age).\n"
        f"**Final Amount**: {final_withdrawal:.2f} coins.\n"
        f"**New Balance**: {user_data[user_id]['balance']:.2f}.",
        ephemeral=True
    )


@tree.command(name="withdrawal_fee", description="View withdrawal fees based on account age.")
async def withdrawal_fee(interaction: discord.Interaction):
    withdrawal_fees = []
    for week in range(9):  # 0 to 8 weeks
        fee_rate = max(0, 8 - week)  # 8% down to 0%
        withdrawal_fees.append(f"Age: {week} week(s) - Fee: {fee_rate}%")

    fee_message = "\n".join(withdrawal_fees)
    await interaction.response.send_message(
        f"**Withdrawal Fee Rates Based on Account Age:**\n{fee_message}"
    )

# Command: Generate Balance History Graph
@tree.command(name="generate_graph", description="Generate a balance history graph for a user.")
async def generate_graph(interaction: discord.Interaction, user: discord.User = None):
    user_id = str(user.id) if user else str(interaction.user.id)

    if user_id not in user_data:
        await interaction.response.send_message("No data found for this user.", ephemeral=True)
        return

    # Extract data for graphing
    history = user_data[user_id].get("history", [])
    if not history:
        await interaction.response.send_message("No history data available for this user.", ephemeral=True)
        return

    dates, balances = zip(*history)
    buf = plot_graph(dates, balances, f"Balance History for {user.display_name if user else interaction.user.display_name}", "Date/Time", "Balance")
    await interaction.response.defer()
    await interaction.followup.send(file=discord.File(buf, filename="balance_graph.png"))


# Command: Generate Total Fund Report
@tree.command(name="generate_fund_report", description="Generate a total fund balance history graph (Admin only).")
async def generate_fund_report(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if not fund_history:
        await interaction.response.send_message("No fund history data available.", ephemeral=True)
        return

    # Extract data for graphing
    dates, total_balances = zip(*fund_history)

    # Use the same plotting logic as generate_graph
    buf = plot_graph(
        dates,
        total_balances,  # No need to divide by a million unless explicitly required
        "Total Fund Balance Over Time",
        "Date/Time",
        "Total Balance (coins)"
    )

    await interaction.response.defer()
    await interaction.followup.send(file=discord.File(buf, filename="fund_report.png"))


# Command: Transfer Account Ownership
@tree.command(name="transfer_account", description="Transfer account ownership from one user to another (Admin only).")
async def transfer_account(interaction: discord.Interaction, current_owner: discord.User, new_owner: discord.User):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    current_owner_id = str(current_owner.id)
    new_owner_id = str(new_owner.id)
    if current_owner_id in user_data:
        user_data[new_owner_id] = user_data.pop(current_owner_id)
        await interaction.response.send_message(f"Account ownership transferred from {current_owner.display_name} to {new_owner.display_name}")
    else:
        await interaction.response.send_message("Current owner not found.")



async def project_name_autocomplete(interaction: discord.Interaction, current: str):
    # Ensure we correctly filter and return active projects
    return [
        app_commands.Choice(name=name, value=name)
        for name, details in projects.items()
        if details["status"] == "active" and current.lower() in name.lower()
    ]

async def autocomplete_projects(interaction: discord.Interaction, current: str):
    # Force include specific projects
    hardcoded_projects = ["War Plan RED", "Greyhames DILF XP"]

    # Combine hardcoded projects with other active projects dynamically
    all_projects = hardcoded_projects + [
        name for name, details in projects.items()
        if details["status"] == "active" and name not in hardcoded_projects
    ]

    # Filter projects based on the current input
    return [
        app_commands.Choice(name=project_name, value=project_name)
        for project_name in all_projects
        if current.lower() in project_name.lower()
    ]

@tree.command(name="create_project", description="Create a new investment project (Admin only).")
async def create_project(
    interaction: discord.Interaction,
    name: str,
    description: str,
    expected_yield: float,
    profit_share: float,
    duration: Literal[
        "1 Week", "2 Weeks", "3 Weeks", "1 Month", "2 Months", "3 Months", "4 Months"
    ],  # Restrict duration to predefined options
):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to create projects.", ephemeral=True)
        return

    if name in projects:
        await interaction.response.send_message(f"A project with the name '{name}' already exists.", ephemeral=True)
        return

    # Create the project
    projects[name] = {
        "description": description,
        "expected_yield": expected_yield,
        "expected_duration": duration,  # Save the selected duration
        "profit_share": profit_share,
        "total_invested": 0.0,
        "investors": {},
        "status": "active",
        "total_earnings": 0.0,
    }

    guild = interaction.guild
    investment_channel = discord.utils.get(guild.text_channels, name="investment-projects")
    if not investment_channel:
        await interaction.response.send_message("The investment-projects channel was not found. Please create one.", ephemeral=True)
        return

    investor_role = discord.utils.get(interaction.guild.roles, name="Investor")
    investor_mention = investor_role.mention if investor_role else "`Investor` role"
    await investment_channel.send(
        f"{investor_mention}, a new investment project has been created!\n\n"
        f"**Project Name**: {name}\n"
        f"**Description**: {description}\n"
        f"**Expected Yield**: {expected_yield:,.2f} coins\n"
        f"**Expected Duration**: {duration}\n"
        f"**Profit Share**: {profit_share:.2f}%\n\n"
        "Get started by investing in this project!"
    )

    await interaction.response.send_message("Project created and posted in the investment-projects channel.", ephemeral=True)

@tree.command(name="list_projects", description="List all projects and their statuses.")
async def list_projects(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if not projects:
        await interaction.response.send_message("No projects are available.", ephemeral=True)
        return

    message = "**All Projects:**\n"
    for name, details in projects.items():
        message += (
            f"🔹 **Name**: {name}\n"
            f"   **Status**: {details['status']}\n"
            f"   **Total Invested**: {details['total_invested']:,.2f} coins\n\n"
        )

    await interaction.response.send_message(message, ephemeral=True)

# Command: Add Project Earnings
@tree.command(name="add_project_earnings", description="Add earnings to a project (Admin only).")
@app_commands.autocomplete(project_name=project_name_autocomplete)
async def add_project_earnings(interaction: discord.Interaction, project_name: str, amount: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to add earnings to projects.", ephemeral=True)
        return

    if project_name not in projects:
        await interaction.response.send_message(f"Project '{project_name}' does not exist.", ephemeral=True)
        return

    if projects[project_name]["status"] != "active":
        await interaction.response.send_message(f"Project '{project_name}' is not active.", ephemeral=True)
        return

    projects[project_name]["total_earnings"] += amount

    await interaction.response.send_message(
        f"Successfully added {amount:,.2f} coins to project '{project_name}'."
    )

@tree.command(name="finish_project", description="Finish a project and distribute earnings (Admin only).")
@app_commands.autocomplete(project_name=project_name_autocomplete)
async def finish_project(interaction: discord.Interaction, project_name: str):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to finish projects.", ephemeral=True)
        return

    if project_name not in projects:
        await interaction.response.send_message(f"Project '{project_name}' does not exist.", ephemeral=True)
        return

    if projects[project_name]["status"] != "active":
        await interaction.response.send_message(f"Project '{project_name}' is not active.", ephemeral=True)
        return

    project = projects[project_name]

    total_invested = project["total_invested"]
    if total_invested > 0:
        for user_id, invested_amount in project["investors"].items():
            profit_share = (invested_amount / total_invested) * project["total_earnings"] * (project["profit_share"] / 100)
            user_data[user_id]["balance"] += invested_amount + profit_share

            # Notify the user about their repayment and earnings
            user = await client.fetch_user(int(user_id))
            try:
                await user.send(
                    f"The project '{project_name}' has been completed, and your investment has been repaid!\n"
                    f"**Initial Investment**: {invested_amount:,.2f} coins\n"
                    f"**Total Earnings**: {profit_share:,.2f} coins\n"
                    f"**Total Repaid (with Earnings)**: {(invested_amount + profit_share):,.2f} coins"
                )
            except discord.Forbidden:
                print(f"Could not send DM to user {user_id}. They may have DMs disabled.")

    project["status"] = "finished"

    await interaction.response.send_message(
        f"Project '{project_name}' has been finished. Investments and profits have been distributed.",
        ephemeral=True,
    )



@tree.command(name="opt_into_project", description="Invest in a project.")
@app_commands.autocomplete(project_name=autocomplete_projects)
async def opt_into_project(interaction: discord.Interaction, project_name: str, amount: float):
    # Logic for investing in a project
    user_id = str(interaction.user.id)

    # Check if the user has the required role
    investor_role = discord.utils.get(interaction.guild.roles, name="Investor")
    if not investor_role or investor_role not in interaction.user.roles:
        await interaction.response.send_message("You must have the 'Investor' role to use this command.", ephemeral=True)
        return

    # Validate the project name
    if project_name not in projects:
        await interaction.response.send_message(f"Project '{project_name}' does not exist.", ephemeral=True)
        return

    if projects[project_name]["status"] != "active":
        await interaction.response.send_message(f"Project '{project_name}' is not active.", ephemeral=True)
        return

    # Check if the user has enough balance
    if user_id not in user_data or user_data[user_id]["balance"] < amount:
        await interaction.response.send_message("Insufficient balance to invest in this project.", ephemeral=True)
        return

    # Deduct the amount from the user's balance
    user_data[user_id]["balance"] -= amount

    # Add the investment to the project
    if user_id not in projects[project_name]["investors"]:
        projects[project_name]["investors"][user_id] = 0.0
    projects[project_name]["investors"][user_id] += amount
    projects[project_name]["total_invested"] += amount

    # Send a confirmation message
    await interaction.response.send_message(
        f"Successfully invested {amount:,.2f} coins into project '{project_name}'.", ephemeral=True
    )




    # Define the unified autocomplete function
@tree.command(name="edit_project", description="Edit a project's details (Admin only).")
@app_commands.autocomplete(project_name=project_name_autocomplete)
async def edit_project(
    interaction: discord.Interaction,
    project_name: str,
    new_name: str = None,
    description: str = None,
    expected_yield: float = None,
    profit_share: float = None,
    duration: Literal[
        "1 Week", "2 Weeks", "3 Weeks", "1 Month", "2 Months", "3 Months", "4 Months"
    ] = None,
):
    """Edit an investment project's details."""
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to edit projects.", ephemeral=True)
        return

    if project_name not in projects:
        await interaction.response.send_message(f"Project '{project_name}' does not exist.", ephemeral=True)
        return

    project = projects[project_name]

    # Update project details as provided
    if new_name:
        if new_name in projects:
            await interaction.response.send_message(f"A project with the name '{new_name}' already exists.", ephemeral=True)
            return
        projects[new_name] = projects.pop(project_name)  # Rename the project
        project_name = new_name

    if description:
        project["description"] = description

    if expected_yield is not None:
        project["expected_yield"] = expected_yield

    if profit_share is not None:
        project["profit_share"] = profit_share

    if duration:
        project["expected_duration"] = duration

    # Confirm the changes to the user
    await interaction.response.send_message(
        f"Project '{project_name}' has been updated successfully:\n"
        f"🔹 **Description**: {project['description']}\n"
        f"🔹 **Expected Yield**: {project['expected_yield']:.2f}%\n"
        f"🔹 **Profit Share**: {project['profit_share']:.2f}%\n"
        f"🔹 **Expected Duration**: {project['expected_duration']}\n",
        ephemeral=True
    )


async def loan_id_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete function to display loan titles."""
    print(f"Autocomplete invoked for command: {interaction.command.name} with input: {current}")
    print(f"Current loans dictionary: {loans}")

    if interaction.command.name == "approve_loan":
        # Filter loans pending approval and display their titles with IDs
        choices = [
            app_commands.Choice(name=f"{details['title']} (ID: {loan_id})", value=loan_id)
            for loan_id, details in loans.items()
            if details.get("status") == "pending_approval" and current.lower() in details['title'].lower()
        ]
    elif interaction.command.name == "opt_into_loan":
        # Filter approved loans and display their titles with IDs
        choices = [
            app_commands.Choice(name=f"{details['title']} (ID: {loan_id})", value=loan_id)
            for loan_id, details in loans.items()
            if details.get("status") == "approved" and current.lower() in details['title'].lower()
        ]
    elif interaction.command.name == "finish_loan":
        # Filter running loans and display their titles with IDs
        choices = [
            app_commands.Choice(name=f"{details['title']} (ID: {loan_id})", value=loan_id)
            for loan_id, details in loans.items()
            if details.get("status") == "running" and current.lower() in details['title'].lower()
        ]
        print(f"Filtered running loans: {choices}")
    elif interaction.command.name == "edit_loan":
        # Include both pending and approved loans for editing
        choices = [
            app_commands.Choice(name=f"{details['title']} (ID: {loan_id})", value=loan_id)
            for loan_id, details in loans.items()
            if details.get("status") in ["pending_approval", "approved"] and current.lower() in details['title'].lower()
        ]
    else:
        # Default to no choices if the command is unrecognized
        choices = []

    print(f"Generated Choices: {choices}")
    return choices



@tree.command(name="request_loan", description="Request a new loan.")
async def request_loan(
    interaction: discord.Interaction,
    title: str,
    amount: float,
    backing_value: float,
    description: str,
    duration: Literal[
        "1 Week", "2 Weeks", "3 Weeks", "1 Month", "2 Months", "3 Months", "4 Months"
    ],
):
    if backing_value < 0.1 * amount:  # Check if backing value meets the minimum requirement
        await interaction.response.send_message("The backing value must be at least 10% of the loan amount.", ephemeral=True)
        return

    # Generate a unique loan ID
    loan_id = f"loan_{len(loans) + 1}"

    # Save loan details
    loans[loan_id] = {
        "title": title,
        "amount": amount,
        "backing_value": backing_value,
        "description": description,
        "duration": duration,
        "status": "pending_approval",
        "interest_rate": None,
        "investors": {},
    }

    guild = interaction.guild
    loan_tickets_category = discord.utils.get(guild.categories, name="Loan Tickets")

    if not loan_tickets_category:
        await interaction.response.send_message(
            "Loan Tickets category not found. Please create a category named 'Loan Tickets'.", ephemeral=True
        )
        return

    # Get the BotCommander role
    bot_commander_role = discord.utils.get(guild.roles, name="BotCommander")

    # Create a new channel in the Loan Tickets category
    channel_name = f"{interaction.user.name}-loan"
    loan_channel = await guild.create_text_channel(
        name=channel_name,
        category=loan_tickets_category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Default role can't view
            interaction.user: discord.PermissionOverwrite(view_channel=True),  # User who made the request
            bot_commander_role: discord.PermissionOverwrite(view_channel=True),  # BotCommander role can view
        },
    )

    bot_commander_mention = bot_commander_role.mention if bot_commander_role else "`BotCommander` role"
    await loan_channel.send(
        f"{bot_commander_mention}, a new loan request has been created and is awaiting approval!\n\n"
        f"**Title**: {title}\n"
        f"**Amount Requested**: {amount:,.2f} coins\n"
        f"**Backing Value**: {backing_value:,.2f} coins\n"
        f"**Description**: {description}\n"
        f"**Duration**: {duration}\n\n"
        f"Use `/approve_loan` to approve this loan request."
    )

    # Send only a single response to the interaction
    await interaction.response.send_message(
        f"Your loan request has been submitted. Check {loan_channel.mention} for updates.", ephemeral=True
    )



@tree.command(name="edit_loan", description="Edit a loan's title or backing value (Admin only).")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def edit_loan(interaction: discord.Interaction, loan_id: str, title: str = None, backing_value: float = None):
    """Edit a loan's title or backing value."""
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to edit loans.", ephemeral=True)
        return

    if loan_id not in loans:
        await interaction.response.send_message("Invalid loan ID. No such loan exists.", ephemeral=True)
        return

    loan = loans[loan_id]

    # Update the title if provided
    if title:
        loan["title"] = title

    # Update the backing value if provided
    if backing_value is not None:
        if backing_value < 0.1 * loan["amount"]:
            await interaction.response.send_message(
                "The backing value must be at least 10% of the loan amount.", ephemeral=True
            )
            return
        loan["backing_value"] = backing_value

    # Save changes back to the loans dictionary
    loans[loan_id] = loan

    # Confirm the changes
    await interaction.response.send_message(
        f"Loan '{loan_id}' has been updated:\n"
        f"🔹 **Title**: {loan['title']}\n"
        f"🔹 **Backing Value**: {loan['backing_value']:.2f} coins",
        ephemeral=True,
    )

# Command: Approve Loan
@tree.command(name="approve_loan", description="Approve a loan request and set an interest rate (Admin only).")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def approve_loan(interaction: discord.Interaction, loan_id: str, interest_rate: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to approve loans.", ephemeral=True)
        return

    if loan_id not in loans or loans[loan_id].get("status") != "pending_approval":
        await interaction.response.send_message("Invalid loan ID or the loan is not pending approval.", ephemeral=True)
        return

    loans[loan_id]["interest_rate"] = interest_rate
    loans[loan_id]["status"] = "approved"  # Mark the loan as approved

    # Notify about the loan approval
    investment_channel = discord.utils.get(interaction.guild.text_channels, name="loan-board")
    if not investment_channel:
        await interaction.response.send_message("Loan board channel not found.", ephemeral=True)
        return

    investor_role = discord.utils.get(interaction.guild.roles, name="Investor")
    investor_mention = investor_role.mention if investor_role else "`Investor` role"
    await investment_channel.send(
        f"{investor_mention}, a new loan request has been approved and is now available for investment!\n\n"
        f"**Title**: {loans[loan_id]['title']}\n"
        f"**Amount Requested**: {loans[loan_id]['amount']:,.2f} coins\n"
        f"**Backing Value**: {loans[loan_id]['backing_value']:,.2f} coins\n"
        f"**Description**: {loans[loan_id]['description']}\n"
        f"**Duration**: {loans[loan_id]['duration']}\n"
        f"**Interest Rate**: {interest_rate:.2f}%\n\n"
        "Get started by opting into this loan!"
    )

    await interaction.response.send_message(f"Loan '{loan_id}' has been approved and posted to the loan board.", ephemeral=True)

@tree.command(name="opt_into_loan", description="Invest in a loan.")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def opt_into_loan(interaction: discord.Interaction, loan_id: str, amount: float):
    user_id = str(interaction.user.id)

    # Check if the user has the 'Investor' role
    investor_role = discord.utils.get(interaction.guild.roles, name="Investor")
    if not investor_role or investor_role not in interaction.user.roles:
        await interaction.response.send_message("You must have the 'Investor' role to use this command.", ephemeral=True)
        return

    if loan_id not in loans or loans[loan_id].get("status") != "approved":
        await interaction.response.send_message("Invalid loan ID or the loan is not available for investment.", ephemeral=True)
        return

    if user_id not in user_data or user_data[user_id]["balance"] < amount:
        await interaction.response.send_message("Insufficient balance to invest in this loan.", ephemeral=True)
        return

    loan = loans[loan_id]
    remaining_amount = loan["amount"] - loan.get("total_invested", 0)

    # Check if the user is attempting to invest more than the remaining amount
    if amount > remaining_amount:
        await interaction.response.send_message(
            f"Cannot invest {amount:,.2f} coins. Only {remaining_amount:,.2f} coins are needed to fully fund this loan.",
            ephemeral=True
        )
        return

    # Deduct the amount and update loan details
    user_data[user_id]["balance"] -= amount
    loan["investors"] = loan.get("investors", {})
    loan["investors"][user_id] = loan["investors"].get(user_id, 0) + amount
    loan["total_invested"] = loan.get("total_invested", 0) + amount

    # Check if the loan is fully funded
    if loan["total_invested"] >= loan["amount"]:
        loan["status"] = "running"

        # Notify investors and admins
        investor_mention = investor_role.mention if investor_role else "`Investor` role"
        await interaction.channel.send(
            f"{investor_mention}, the loan '{loan_id}' has been fully funded and is now running! Please transfer the money in-game."
        )

    await interaction.response.send_message(f"Successfully invested {amount:,.2f} coins into loan '{loan_id}'.", ephemeral=True)


@tree.command(name="finish_loan", description="Finish a running loan and distribute funds to investors.")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def finish_loan(interaction: discord.Interaction, loan_id: str, shares: float):
    print(f"finish_loan invoked with loan_id: {loan_id} and shares: {shares}")

    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to finish loans.", ephemeral=True)
        print("Permission denied for finish_loan.")
        return

    if loan_id not in loans:
        await interaction.response.send_message("Invalid loan ID. No such loan exists.", ephemeral=True)
        print(f"Loan ID {loan_id} not found in loans.")
        return

    loan = loans.get(loan_id)
    if loan.get("status") != "running":
        await interaction.response.send_message("The loan is not currently running.", ephemeral=True)
        print(f"Loan {loan_id} is not in 'running' status. Current status: {loan.get('status')}")
        return

    # Calculate total repayment and shares
    total_interest = loan["amount"] * (loan["interest_rate"] / 100)
    total_repayment = loan["amount"] + total_interest
    bot_share = (shares / 100) * total_repayment
    investor_repayment_pool = total_repayment - bot_share

    # Add bot's share to specific user account (ID: 262945457045635075)
    receiver_id = "262945457045635075"  # Replace with the intended user's ID
    if receiver_id not in user_data:
        user_data[receiver_id] = {"balance": 0.0, "history": []}

    user_data[receiver_id]["balance"] += bot_share
    user_data[receiver_id]["history"].append(
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[receiver_id]["balance"])
    )
    print(f"Transferred {bot_share} to user with ID {receiver_id}. New balance: {user_data[receiver_id]['balance']}")

    # Distribute remaining funds to investors
    for user_id, invested_amount in loan["investors"].items():
        repayment = invested_amount + (invested_amount / loan["amount"]) * investor_repayment_pool
        user_data[user_id]["balance"] += repayment

        # Notify the user
        try:
            user = await client.fetch_user(int(user_id))
            await user.send(
                f"Your investment in loan '{loan_id}' has been repaid!\n"
                f"**Initial Investment**: {invested_amount:,.2f} coins\n"
                f"**Total Repaid (with Interest)**: {repayment:,.2f} coins\n"
                f"**Interest Earned**: {(repayment - invested_amount):,.2f} coins\n"
            )
        except discord.Forbidden:
            print(f"Could not send DM to user {user_id}. They may have DMs disabled.")

    # Mark loan as finished
    loan["status"] = "finished"
    print(f"Loan {loan_id} marked as finished.")

    await interaction.response.send_message(
        f"The loan '{loan_id}' has been successfully finished.\n"
        f"**Shares to User (ID: {receiver_id})**: {bot_share:,.2f} coins.\n"
        f"Investors have been notified.",
        ephemeral=True
    )


@tree.command(name="info", description="View detailed information about a user's account.")
async def info(interaction: discord.Interaction, user: discord.User = None):
    """
    View account details for a specific user.
    Admins or BotCommanders can view others' data; others can only view their own.
    """
    user_id = str(user.id if user else interaction.user.id)  # Target user or self

    # Check if the command is restricted to the user or if the invoker is an admin/BotCommander
    if user and not has_commander_role(interaction):
        await interaction.response.send_message(
            "You do not have permission to view another user's account details.", ephemeral=True
        )
        return

    # Ensure the target user exists in the database
    if user_id not in user_data:
        await interaction.response.send_message(
            f"No account found for {user.display_name if user else 'you'}. Please ask an admin to set the initial deposit.",
            ephemeral=True,
        )
        return

    # Retrieve account information
    user_info = user_data[user_id]
    balance = user_info.get("balance", 0.0)
    initial_deposit = user_info.get("initial_deposit", 0.0)
    start_date_str = user_info.get("start_date", "Unknown")
    today = datetime.datetime.now()

    # Calculate account age
    if start_date_str != "Unknown":
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        account_age_days = (today - start_date).days
        account_age_weeks = account_age_days // 7
    else:
        account_age_weeks = "Unknown"

    # Calculate current withdrawal fee
    withdrawal_fee_percentage = max(8 - account_age_weeks, 0) if account_age_weeks != "Unknown" else "Unknown"

    # Calculate money in projects
    money_in_projects = sum(
        project["investors"].get(user_id, 0) for project in projects.values() if project["status"] == "active"
    )

    # Calculate money in loans
    money_in_loans = sum(
        loan["investors"].get(user_id, 0) for loan in loans.values() if loan["status"] == "approved"
    )

    # Construct the info message
    info_message = (
        f"**Account Information for {user.display_name if user else interaction.user.display_name}**\n"
        f"🔹 **Account Age**: {account_age_weeks} week(s)\n"
        f"🔹 **Current Withdrawal Fee**: {withdrawal_fee_percentage}%\n"
        f"🔹 **Balance**: {balance:.2f} coins\n"
        f"🔹 **Initial Deposit**: {initial_deposit:.2f} coins\n"
        f"🔹 **Money in Projects**: {money_in_projects:.2f} coins\n"
        f"🔹 **Money in Loans**: {money_in_loans:.2f} coins\n"
    )

    # Respond to the command
    await interaction.response.send_message(info_message, ephemeral=(user is None))

@tree.command(name="project_info", description="View detailed information about a project (Admin only).")
async def project_info(interaction: discord.Interaction, project_name: str):
    """
    View detailed information about a specific project.
    """
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if project_name not in projects:
        await interaction.response.send_message(f"Project '{project_name}' does not exist.", ephemeral=True)
        return

    project = projects[project_name]

    if project["status"] not in ["active", "finished"]:
        await interaction.response.send_message(f"Project '{project_name}' is not in a valid state to view.", ephemeral=True)
        return

    # Generate the message content
    investors = project["investors"]
    if not investors:
        investor_info = "No users have opted into this project."
    else:
        investor_info = "\n".join(
            [f"<@{user_id}>: {amount:,.2f} coins" for user_id, amount in investors.items()]
        )

    message = (
        f"**Project Information: {project_name}**\n"
        f"**Status**: {project['status']}\n"
        f"**Description**: {project['description']}\n"
        f"**Total Invested**: {project['total_invested']:,.2f} coins\n"
        f"**Expected Yield**: {project['expected_yield']:.2f}%\n"
        f"**Profit Share**: {project['profit_share']:.2f}%\n"
        f"**Investors**:\n{investor_info}"
    )

    await interaction.response.send_message(message, ephemeral=True)

@tree.command(name="loan_info", description="View detailed information about a loan (Admin only).")
async def loan_info(interaction: discord.Interaction, loan_id: str):
    """
    View detailed information about a specific loan.
    """
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if loan_id not in loans:
        await interaction.response.send_message(f"Loan '{loan_id}' does not exist.", ephemeral=True)
        return

    loan = loans[loan_id]

    if loan["status"] not in ["approved", "running", "finished"]:
        await interaction.response.send_message(f"Loan '{loan_id}' is not in a valid state to view.", ephemeral=True)
        return

    # Generate the message content
    investors = loan.get("investors", {})
    if not investors:
        investor_info = "No users have opted into this loan."
    else:
        investor_info = "\n".join(
            [f"<@{user_id}>: {amount:,.2f} coins" for user_id, amount in investors.items()]
        )

    message = (
        f"**Loan Information: {loan['title']}**\n"
        f"**Status**: {loan['status']}\n"
        f"**Amount Requested**: {loan['amount']:,.2f} coins\n"
        f"**Backing Value**: {loan['backing_value']:,.2f} coins\n"
        f"**Interest Rate**: {loan.get('interest_rate', 0):.2f}%\n"
        f"**Duration**: {loan['duration']}\n"
        f"**Investors**:\n{investor_info}"
    )

    await interaction.response.send_message(message, ephemeral=True)


@tree.command(name="view_fund_summary", description="View a summary of the total fund, loans, and projects.")
async def view_fund_summary(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Calculate total fund balance
    total_fund_balance = sum(data.get("balance", 0) for data in user_data.values())

    # Count active loans
    active_loans = [loan for loan in loans.values() if loan.get("status") in ["approved", "running"]]
    total_loan_amount = sum(loan["amount"] for loan in active_loans)

    # Count active projects
    active_projects = [project for project in projects.values() if project.get("status") == "active"]
    total_project_invested = sum(project["total_invested"] for project in active_projects)

    # Construct the summary message
    summary = (
        f"**Fund Summary**\n"
        f"🔹 **Total Fund Balance**: {total_fund_balance:,.2f} coins\n"
        f"🔹 **Active Loans**: {len(active_loans)} (Total Value: {total_loan_amount:,.2f} coins)\n"
        f"🔹 **Active Projects**: {len(active_projects)} (Total Invested: {total_project_invested:,.2f} coins)"
    )

    await interaction.response.send_message(summary, ephemeral=True)

@tree.command(name="view_my_projects", description="View all projects you have invested in.")
async def view_my_projects(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Find projects the user has invested in
    user_projects = [
        (name, details["investors"][user_id])
        for name, details in projects.items()
        if user_id in details.get("investors", {}) and details["status"] == "active"
    ]

    if not user_projects:
        await interaction.response.send_message("You have not invested in any active projects.", ephemeral=True)
        return

    # Construct the message
    message = "**Your Active Project Investments**\n"
    for project_name, invested_amount in user_projects:
        message += (
            f"🔹 **Project Name**: {project_name}\n"
            f"   **Invested Amount**: {invested_amount:,.2f} coins\n"
        )

    await interaction.response.send_message(message, ephemeral=True)

@tree.command(name="view_my_loans", description="View all loans you have invested in.")
async def view_my_loans(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Find loans the user has invested in
    user_loans = [
        (loan_id, details["investors"][user_id], details)
        for loan_id, details in loans.items()
        if user_id in details.get("investors", {}) and details["status"] in ["approved", "running"]
    ]

    if not user_loans:
        await interaction.response.send_message("You have not invested in any active loans.", ephemeral=True)
        return

    # Construct the message
    message = "**Your Active Loan Investments**\n"
    for loan_id, invested_amount, loan_details in user_loans:
        message += (
            f"🔹 **Loan ID**: {loan_id}\n"
            f"   **Title**: {loan_details['title']}\n"
            f"   **Invested Amount**: {invested_amount:,.2f} coins\n"
            f"   **Status**: {loan_details['status']}\n"
        )

    await interaction.response.send_message(message, ephemeral=True)

@tree.command(name="calculate_total_interest", description="Calculate total interest payout for all accounts.")
async def calculate_total_interest(interaction: discord.Interaction):
    total_interest_payout = 0.0

    # Iterate through all user accounts
    for user_id, data in user_data.items():
        # Calculate interest based on the global interest rate
        initial_deposit = data.get("initial_deposit", 0)
        interest = initial_deposit * current_interest_rate

    # Respond with the total payout
    await interaction.response.send_message(
        f"**Total Interest Payout**: {total_interest_payout:,.2f} coins",
        ephemeral=True
    )

    @tree.command(name="restore_data", description="Restore projects and user data from backup files (Admin only).")
    async def restore_data(interaction: discord.Interaction):
        if not has_commander_role(interaction):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        try:
            global projects, user_data

            # Reload projects from backup
            with open(PROJECTS_BACKUP_FILE, "r") as f:
                projects = json.load(f)

            # Reload user data from backup
            with open(BACKUP_FILE, "r") as f:
                backup_content = json.load(f)
                user_data = backup_content.get("user_data", {})

            await interaction.response.send_message("Data has been successfully restored from backup.", ephemeral=True)
            print("Data restoration completed successfully.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to restore data: {e}", ephemeral=True)
            print(f"Error during data restoration: {e}")

@tree.command(name="backup_all_data", description="Backup all data (Admin only).")
async def backup_all_data(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    try:
        # Backup user data
        with open(BACKUP_FILE, "w") as f:
            json.dump({"user_data": user_data, "fund_history": fund_history}, f, indent=4)

        # Backup projects
        with open(PROJECTS_BACKUP_FILE, "w") as f:
            json.dump(projects, f, indent=4)

        # Backup loans
        with open(LOANS_BACKUP_FILE, "w") as f:
            json.dump(loans, f, indent=4)

        await interaction.response.send_message("Backup completed successfully.", ephemeral=True)
        print("Backup completed successfully.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to backup data: {e}", ephemeral=True)
        print(f"Backup failed: {e}")



load_backup()
client.run(TOKEN)
