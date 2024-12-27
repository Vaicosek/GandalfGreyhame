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


CONFIG_FILE = "config.json"
BACKUP_FILE = "backup_data.json"
COMMANDER_ROLE = "BotCommander"  # Name of the role that has elevated privileges
PROJECTS_BACKUP_FILE = "projects_backup.json"
loans = {}
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
GUILD_ID = config.get("GUILD_ID")  # Discord server ID

if not GUILD_ID:
    raise ValueError("GUILD_ID is not defined in the config.json file.")


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


@tasks.loop(hours=1)
async def calculate_hourly_interest():
    apply_hourly_interest()

@tasks.loop(hours=168)
async def apply_biweekly_interest():
    global_interest_rate = current_interest_rate   # Convert percentage to decimal

    # Apply interest to user accounts
    for user_id, data in user_data.items():
        initial_deposit = data.get("initial_deposit", 0.0)
        interest = initial_deposit * global_interest_rate
        data["balance"] += interest
        data.setdefault("history", []).append(
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), data["balance"])
        )

    # Apply interest to active projects
    for project_name, project in projects.items():
        if project["status"] == "active":  # Only active projects
            for user_id, invested_amount in project["investors"].items():
                interest = invested_amount * global_interest_rate
                project["investors"][user_id] += interest
                project["total_invested"] += interest

    # Notify in the finance-updates channel
    guild = client.get_guild(GUILD_ID)
    finance_updates_channel = discord.utils.get(guild.text_channels, name="📣│finance-updates")  # Exact channel name

    if not finance_updates_channel:
        print("The 📣│finance-updates channel does not exist. Please create it.")
        return

    tester_role = discord.utils.get(guild.roles, name="Tester")  # Replace with Finance Updates role name if applicable
    tester_mention = tester_role.mention if tester_role else "`Tester` role"

    try:
        await finance_updates_channel.send(
            f"{tester_mention}, the bi-weekly interest has been applied!\n\n"
            f"**Global Interest Rate**: {current_interest_rate:.2f}%\n"
            "All accounts (bank and project investments) have been updated accordingly."
        )
    except discord.Forbidden:
        print("The bot lacks permissions to send messages to the 📣│finance-updates channel.")
    except Exception as e:
        print(f"An error occurred while sending a message: {e}")

    print("Bi-weekly interest applied.")


@tasks.loop(hours=6)
async def backup_data_task():
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

@client.event
async def on_ready():
    print(f"{client.user} is now running!")

    try:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        print("Commands synced successfully.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    # Start periodic tasks
    if not backup_data_task.is_running():
        backup_data_task.start()
    if not apply_biweekly_interest.is_running():
        apply_biweekly_interest.start()  # Start the bi-weekly interest task
    print("All tasks started.")

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
        projects = {}  # Initialize as an empty dictionary
        with open(PROJECTS_BACKUP_FILE, "w") as f:
            json.dump(projects, f, indent=4)


# Helper to plot graph
import matplotlib.ticker as mticker

def plot_graph(dates, values, title, xlabel, ylabel):
    plt.figure()  # Create a new figure
    plt.plot(dates, values, marker="o")  # Plot the data points
    plt.title(title)  # Set the title
    plt.xlabel(xlabel)  # Set the x-axis label
    plt.ylabel(ylabel)  # Set the y-axis label
    plt.xticks(rotation=45)  # Rotate the x-axis labels for better readability

    # Format x-axis with readable dates
    ax = plt.gca()  # Get current axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))  # Format date labels
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))  # Limit the number of x-axis labels

    # Format y-axis numbers with commas
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))  # Format numbers

    # Save the plot to a BytesIO buffer for sending as a file
    buf = BytesIO()
    plt.savefig(buf, format="png")  # Save the figure to the buffer in PNG format
    buf.seek(0)  # Move the pointer to the start of the buffer
    plt.close()  # Close the figure to free up memory
    return buf


user_data = {}
projects = {}
fund_history = []  # Historical records for fund balance
current_interest_rate = 0.0  # Default interest rate

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

@tree.command(name="set_account_start", description="Set the account start date for a user (Admin only).")
async def set_account_start(interaction: discord.Interaction, user: discord.User, start_date: str):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    try:
        # Validate the date format
        datetime.datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message("Invalid date format. Use 'YYYY-MM-DD'.", ephemeral=True)
        return

    user_id = str(user.id)

    # Ensure the user's data structure exists
    if user_id not in user_data:
        user_data[user_id] = {
            "balance": 0.0,
            "initial_deposit": 0.0,
            "history": [],
            "start_date": None  # Default value if no start date was set
        }

    # Set the account start date
    user_data[user_id]["start_date"] = start_date

    await interaction.response.send_message(
        f"Account start date for {user.display_name} has been set to {start_date}.", ephemeral=True
    )



# Command: Set Interest Rate
@tree.command(name="set_interest_rate", description="Set the bi-weekly interest rate (Admin only).")
async def set_interest_rate(interaction: discord.Interaction, rate: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    global current_interest_rate
    current_interest_rate = rate
    await interaction.response.send_message(f"Bi-weekly interest rate set to {rate:.2%}")


@tree.command(name="set_initial_deposit", description="Set an initial deposit for a user (Admin only).")
async def set_initial_deposit(interaction: discord.Interaction, user: discord.User, amount: float):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    if user_id not in user_data:
        user_data[user_id] = {
            "initial_deposit": amount,
            "balance": amount,
            "history": [(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), amount)]
        }
    else:
        user_data[user_id]["initial_deposit"] = amount
        user_data[user_id]["balance"] = amount
        user_data[user_id]["history"].append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), amount))

    # Update the total fund balance
    update_fund_balance()

    await interaction.response.send_message(f"Set new initial deposit of {amount:.2f} for {user.display_name}, balance has been updated to {amount:.2f}.")


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


# Command: Apply Bi-Weekly Interest Now
@tree.command(name="apply_interest_now", description="Apply bi-weekly interest to all accounts immediately (Admin only).")
async def apply_interest_now(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    for user_id, data in user_data.items():
        # Apply full bi-weekly interest
        biweekly_interest = data["initial_deposit"] * current_interest_rate
        data["balance"] += biweekly_interest
        data["history"].append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), data["balance"]))

    # Update the total fund balance for the graph
    update_fund_balance()
    await interaction.response.send_message("Bi-weekly interest applied to all accounts.")


# Command: Apply Bi-Weekly Interest to a Specific User
@tree.command(name="apply_interest_to_user", description="Apply bi-weekly interest to a specific user's account (Admin only).")
async def apply_interest_to_user(interaction: discord.Interaction, user: discord.User):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(user.id)
    if user_id in user_data:
        # Apply full bi-weekly interest
        biweekly_interest = user_data[user_id]["initial_deposit"] * current_interest_rate
        user_data[user_id]["balance"] += biweekly_interest
        user_data[user_id]["history"].append(
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[user_id]["balance"])
        )

        await interaction.response.send_message(
            f"Bi-weekly interest of {biweekly_interest:.2f} applied to {user.display_name}'s account. "
            f"New balance: {user_data[user_id]['balance']:.2f}"
        )
    else:
        await interaction.response.send_message("User not found. Please set the initial deposit first.")


def interpolate_graph_points(start_balance, end_balance, num_points=6):
    """Generate smooth points between start_balance and end_balance for visualization."""
    step_size = (end_balance - start_balance) / num_points
    return [start_balance + step_size * i for i in range(1, num_points + 1)]


def update_fund_balance():
    """Update the total fund balance for tracking and graphs."""
    total_fund_before = sum(
        user_data[user_id]["balance"] - (current_interest_rate * user_data[user_id]["initial_deposit"])
        for user_id in user_data
    )
    total_fund_after = sum(user_data[user_id]["balance"] for user_id in user_data)

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
    if user_id not in user_data or user_data[user_id]["balance"] < amount:
        await interaction.response.send_message("User not found or insufficient balance.", ephemeral=True)
        return

    start_date_str = user_data[user_id].get("start_date")
    if not start_date_str:
        await interaction.response.send_message(
            "Account start date not set. Please set the account start date first.", ephemeral=True
        )
        return

    # Calculate account duration in weeks
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    today = datetime.datetime.now()
    account_duration_weeks = (today - start_date).days // 7

    # Calculate withdrawal fee
    fee_percentage = max(8 - account_duration_weeks, 0)  # Fee decreases 1% per week
    fee = (amount * fee_percentage) / 100
    final_withdrawal = amount - fee

    # Deduct from balance and record transaction
    user_data[user_id]["balance"] -= amount
    user_data[user_id]["history"].append(
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user_data[user_id]["balance"])
    )

    update_fund_balance()

    await interaction.response.send_message(
        f"Withdrawn {amount:.2f} coins from {user.display_name}'s account.\n"
        f"**Fee**: {fee:.2f} coins ({fee_percentage}% based on account age).\n"
        f"**Final Amount**: {final_withdrawal:.2f} coins.\n"
        f"**New Balance**: {user_data[user_id]['balance']:.2f}.",
        ephemeral=True
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
    return [
        app_commands.Choice(name=name, value=name)
        for name, details in projects.items()
        if details["status"] == "active" and current.lower() in name.lower()
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

    tester_role = discord.utils.get(interaction.guild.roles, name="Tester")
    tester_mention = tester_role.mention if tester_role else "`Tester` role"

    await investment_channel.send(
        f"{tester_mention}, a new investment project has been created!\n\n"
        f"**Project Name**: {name}\n"
        f"**Description**: {description}\n"
        f"**Expected Yield**: {expected_yield:,.2f} coins\n"
        f"**Expected Duration**: {duration}\n"
        f"**Profit Share**: {profit_share:.2f}%\n\n"
        "Get started by investing in this project!"
    )

    await interaction.response.send_message("Project created and posted in the investment-projects channel.", ephemeral=True)


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
@app_commands.autocomplete(project_name=project_name_autocomplete)
async def opt_into_project(interaction: discord.Interaction, project_name: str, amount: float):
    user_id = str(interaction.user.id)

    if project_name not in projects:
        active_projects = [name for name, details in projects.items() if details["status"] == "active"]
        suggestions = "\n".join(active_projects) if active_projects else "No active projects available."
        await interaction.response.send_message(
            f"Project '{project_name}' does not exist. Here are the available active projects:\n\n{suggestions}",
            ephemeral=True
        )
        return

    if projects[project_name]["status"] != "active":
        await interaction.response.send_message(f"Project '{project_name}' is not active.", ephemeral=True)
        return

    if user_id not in user_data or user_data[user_id]["balance"] < amount:
        await interaction.response.send_message("Insufficient balance to invest in this project.", ephemeral=True)
        return

    user_data[user_id]["balance"] -= amount

    if user_id not in projects[project_name]["investors"]:
        projects[project_name]["investors"][user_id] = 0.0
    projects[project_name]["investors"][user_id] += amount
    projects[project_name]["total_invested"] += amount

    # Remove the first notification
    await interaction.response.send_message(
        f"Successfully invested {amount:,.2f} coins into project '{project_name}'.", ephemeral=True
    )

# Restore Data Command
@tree.command(name="restore_data", description="Restore data from the backup file (Admin only).")
async def restore_data(interaction: discord.Interaction):
    if not has_commander_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    load_backup()
    await interaction.response.send_message("Data restoration complete.")

    # Define the unified autocomplete function

async def loan_id_autocomplete(interaction: discord.Interaction, current: str):
        if interaction.command.name == "approve_loan":
            # Autocomplete for loans pending approval
            return [
                app_commands.Choice(name=loan_id, value=loan_id)
                for loan_id, details in loans.items()
                if details.get("status") == "pending_approval" and current.lower() in loan_id.lower()
            ]
        elif interaction.command.name == "opt_into_loan":
            # Autocomplete for loans approved for investment
            return [
                app_commands.Choice(name=loan_id, value=loan_id)
                for loan_id, details in loans.items()
                if details.get("status") == "approved" and current.lower() in loan_id.lower()
            ]
        elif interaction.command.name == "finish_loan":
            # Autocomplete for loans that are running
            return [
                app_commands.Choice(name=loan_id, value=loan_id)
                for loan_id, details in loans.items()
                if details.get("status") == "running" and current.lower() in loan_id.lower()
            ]
        else:
            return []


@tree.command(name="request_loan", description="Request a new loan.")
async def request_loan(
    interaction: discord.Interaction,
    title: str,
    amount: float,
    backing_value: float,
    description: str,
    duration: Literal[
        "1 Week", "2 Weeks", "3 Weeks", "1 Month", "2 Months", "3 Months", "4 Months"
    ],  # Restrict to these choices
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
        "duration": duration,  # Save the selected duration
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

    # Get BotCommander role
    bot_commander_role = discord.utils.get(guild.roles, name="BotCommander")
    bot_commander_permissions = discord.PermissionOverwrite(view_channel=True)

    # Create a new channel in the Loan Tickets category
    channel_name = f"{interaction.user.name}-loan"
    loan_channel = await guild.create_text_channel(
        name=channel_name,
        category=loan_tickets_category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),  # User who made the request
            bot_commander_role: bot_commander_permissions,  # BotCommander permissions
        },
    )

    tester_role = discord.utils.get(guild.roles, name="Tester")
    tester_mention = tester_role.mention if tester_role else "`Tester` role"

    await loan_channel.send(
        f"{tester_mention}, a new loan request has been created and is awaiting approval!\n\n"
        f"**Title**: {title}\n"
        f"**Amount Requested**: {amount:,.2f} coins\n"
        f"**Backing Value**: {backing_value:,.2f} coins\n"
        f"**Description**: {description}\n"
        f"**Duration**: {duration}\n\n"
        f"Use `/approve_loan` to approve this loan request."
    )

    await interaction.response.send_message(f"Your loan request has been submitted. Check {loan_channel.mention} for updates.", ephemeral=True)

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

    tester_role = discord.utils.get(interaction.guild.roles, name="Tester")
    tester_mention = tester_role.mention if tester_role else "`Tester` role"

    await investment_channel.send(
        f"{tester_mention}, a new loan request has been approved and is now available for investment!\n\n"
        f"**Title**: {loans[loan_id]['title']}\n"
        f"**Amount Requested**: {loans[loan_id]['amount']:,.2f} coins\n"
        f"**Backing Value**: {loans[loan_id]['backing_value']:,.2f} coins\n"
        f"**Description**: {loans[loan_id]['description']}\n"
        f"**Duration**: {loans[loan_id]['duration']}\n"
        f"**Interest Rate**: {interest_rate:.2f}%\n\n"
        "Get started by opting into this loan!"
    )

    await interaction.response.send_message(f"Loan '{loan_id}' has been approved and posted to the loan board.", ephemeral=True)

# Command: Opt Into Loan
@tree.command(name="opt_into_loan", description="Invest in a loan.")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def opt_into_loan(interaction: discord.Interaction, loan_id: str, amount: float):
    user_id = str(interaction.user.id)

    if loan_id not in loans or loans[loan_id].get("status") != "approved":
        await interaction.response.send_message("Invalid loan ID or the loan is not available for investment.", ephemeral=True)
        return

    if user_id not in user_data or user_data[user_id]["balance"] < amount:
        await interaction.response.send_message("Insufficient balance to invest in this loan.", ephemeral=True)
        return

    user_data[user_id]["balance"] -= amount
    loans[loan_id]["investors"] = loans[loan_id].get("investors", {})
    loans[loan_id]["investors"][user_id] = loans[loan_id]["investors"].get(user_id, 0) + amount
    loans[loan_id]["total_invested"] = loans[loan_id].get("total_invested", 0) + amount

    # Check if the loan is fully funded
    if loans[loan_id]["total_invested"] >= loans[loan_id]["amount"]:
        loans[loan_id]["status"] = "running"

        # Notify testers to transfer the money
        tester_role = discord.utils.get(interaction.guild.roles, name="Tester")
        tester_mention = tester_role.mention if tester_role else "`Tester` role"

        await interaction.channel.send(
            f"{tester_mention}, the loan '{loan_id}' has been fully funded and is now running! Please transfer the money in-game."
        )

    await interaction.response.send_message(f"Successfully invested {amount:,.2f} coins into loan '{loan_id}'.", ephemeral=True)

@tree.command(name="finish_loan", description="Finish a running loan and distribute funds to investors.")
@app_commands.autocomplete(loan_id=loan_id_autocomplete)
async def finish_loan(interaction: discord.Interaction, loan_id: str):
    if loan_id not in loans or loans[loan_id].get("status") != "running":
        await interaction.response.send_message("Invalid loan ID or the loan is not currently running.", ephemeral=True)
        return

    loan = loans[loan_id]
    total_invested = loan.get("total_invested", 0)

    if total_invested <= 0:
        await interaction.response.send_message("The loan has no funds invested and cannot be finished.", ephemeral=True)
        return

    # Calculate and distribute interest among investors
    total_interest = loan["amount"] * (loan["interest_rate"] / 100)
    total_repayment = loan["amount"] + total_interest

    for user_id, invested_amount in loan["investors"].items():
        # Calculate repayment proportional to investment
        repayment = invested_amount + (invested_amount / loan["amount"]) * total_interest
        user_data[user_id]["balance"] += repayment

        # Notify the user
        user = await client.fetch_user(int(user_id))  # Fetch the user object
        try:
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

    await interaction.response.send_message(f"The loan '{loan_id}' has been successfully finished, and investors have been notified.", ephemeral=True)

load_backup()
client.run(TOKEN)
